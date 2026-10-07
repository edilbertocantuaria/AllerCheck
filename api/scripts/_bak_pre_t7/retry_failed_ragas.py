#!/usr/bin/env python3
"""
Refaz só os itens que falharam na avaliação RAGAS, reaproveitando respostas e contextos já gravados
(sem recoletar, então as respostas COM/SEM continuam as mesmas).

Uso, dentro do container:
    python scripts/retry_failed_ragas.py tools/data/processed/evaluation/unified/evaluation_<ts>.json [gpt,gemini,claude]

Gera um novo evaluation_<ts>.json; o original não é alterado.
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import click

import evaluate_with_ontology_robust as base
from cost_guard import ABORT
from tools.evaluation.ragas.evaluator import RagasEvaluator
from tools.evaluation.ragas.helpers import get_iso_timestamp

CONDITION_LABELS = {"com_ontologia": "COM", "sem_ontologia": "SEM"}
RETRY_CONCURRENCY = 3


def _evaluation_failures(data: dict) -> list:
    failures = []
    for cond in data["conditions"]:
        for item in cond["items"]:
            if item.get("errors"):
                failures.append({
                    "question_id": item.get("question_id"),
                    "condition": CONDITION_LABELS[cond["name"]],
                    "stage": "evaluation",
                    "error": "; ".join(item["errors"]),
                })
    return failures


async def main(source_file: str, evaluators: list = None):
    source = Path(source_file)
    data = json.loads(source.read_text(encoding="utf-8"))

    evaluators = evaluators or data["evaluators"]
    invalid = [e for e in evaluators if e not in base.RAGAS_MODELS]
    if invalid:
        click.echo(f"❌ Avaliadores inválidos: {', '.join(invalid)} (válidos: {', '.join(base.RAGAS_MODELS)})", err=True)
        sys.exit(1)

    evaluator = RagasEvaluator(
        openai_llm_model=base.RAGAS_MODELS["gpt"],
        gemini_model=base.RAGAS_MODELS["gemini"],
        claude_model=base.RAGAS_MODELS["claude"],
        evaluators=evaluators,
    )
    semaphore = asyncio.Semaphore(RETRY_CONCURRENCY)
    retried = []

    for cond in data["conditions"]:
        label = CONDITION_LABELS[cond["name"]]
        failed_positions = [i for i, item in enumerate(cond["items"]) if item.get("errors")]
        click.echo(f"\n{label}: refazendo {len(failed_positions)} itens com erro")
        if not failed_positions:
            continue

        new_items = await asyncio.gather(*[
            base._evaluate_item(n + 1, len(failed_positions), cond["items"][i], evaluator, semaphore, set())
            for n, i in enumerate(failed_positions)
        ])

        for i, new_item in zip(failed_positions, new_items):
            succeeded = not new_item["errors"]
            new_item["retry"] = {"previous_errors": cond["items"][i]["errors"], "succeeded": succeeded}
            cond["items"][i] = new_item
            retried.append({"question_id": new_item["question_id"], "condition": label, "succeeded": succeeded})

        cond["evaluated_count"] = len([e for e in cond["items"] if not e.get("errors")])

    items_by_name = {c["name"]: c["items"] for c in data["conditions"]}
    actual_evaluators = sorted({
        ev for items in items_by_name.values() for it in items for ev in (it.get("results") or {})
    })

    data["evaluators"] = actual_evaluators
    data["failed_questions"] = [
        f for f in data.get("failed_questions", []) if f["stage"] != "evaluation"
    ] + _evaluation_failures(data)
    data["divergences"] = base._calculate_divergences(items_by_name["com_ontologia"], items_by_name["sem_ontologia"])
    data.setdefault("run_config", {})["retry"] = {
        "source_file": source.name,
        "timestamp": get_iso_timestamp(),
        "retried": retried,
    }

    output_dir = Path("tools/data/processed/evaluation/unified")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"evaluation_{datetime.now(base._BRT).strftime('%Y%m%d_%H%M%S')}.json"
    output_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    recovered = sum(1 for r in retried if r["succeeded"])
    click.echo(f"\n✅ {recovered}/{len(retried)} itens recuperados")
    for r in retried:
        if not r["succeeded"]:
            click.echo(f"   ainda falhando: Q{r['question_id']} ({r['condition']})")
    click.echo(f"   Arquivo: {output_file.name}")
    click.echo(f"   Caminho completo: {output_file.resolve()}")

    if ABORT.tripped:
        click.echo(f"❌ ABORTADO: {ABORT.reason}. Resultado parcial salvo; corrija chave/crédito e rode o retry de novo sobre o arquivo novo.", err=True)
        sys.exit(2)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/retry_failed_ragas.py <evaluation_*.json> [gpt,gemini,claude]")
        sys.exit(1)
    names = [e.strip() for e in sys.argv[2].split(",")] if len(sys.argv) > 2 else None
    asyncio.run(main(sys.argv[1], names))

"""Refaz UM avaliador RAGAS sobre todos os itens de um evaluation_*.json, reaproveitando resposta, contextos e ground truth.

Uso (container ou host, a partir de api/):
  python scripts/reevaluate_evaluator.py <evaluation_*.json> <gpt|gemini|claude> [--only-retried] [retomar_checkpoint.json]

--only-retried refaz só os itens que passaram pelo retry_failed_ragas.py (campo `retry`), mantendo os demais valores originais.

Serve para padronizar o modelo de um avaliador no arquivo (ex.: depois de trocar GEMINI_LLM_MODEL).
Só o avaliador pedido é chamado e pago; os valores dos outros ficam intactos. O arquivo original não é alterado.
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import click

import evaluate_with_ontology_robust as base
from checkpoint import Checkpoint, CheckpointMismatch
from cost_guard import ABORT, check_budget_or_exit, fatal_reason
from retry_failed_ragas import CONDITION_LABELS, _evaluation_failures
from tools.evaluation.ragas.evaluator import RagasEvaluator
from tools.evaluation.ragas.helpers import get_iso_timestamp

CONCURRENCY = 3


async def _redo_item(idx, total, item, evaluator, name, semaphore, checkpoint, cond):
    question_id = item.get("question_id")
    cached = checkpoint.get_evaluated(cond, question_id)
    if cached is not None:
        click.echo(f"      [{idx:>3}/{total}] Q{question_id} reaproveitada do checkpoint")
        return cached
    async with semaphore:
        if ABORT.tripped:
            return {"question_id": question_id, "skipped": f"abortado ({ABORT.reason})"}
        click.echo(f"      [{idx:>3}/{total}] Q{question_id}...")
        try:
            result = await evaluator.evaluate_all(
                question=item["question"], answer=item["answer"], contexts=item["contexts"],
                ground_truth=item["ground_truth"], log_prefix=f"      [{idx:>3}/{total}]",
                isolate_errors=True, fatal_check=fatal_reason,
            )
        except Exception as e:
            full = f"{type(e).__name__}: {e}"
            marker = fatal_reason(full)
            if marker:
                ABORT.trigger(marker)
            click.echo(f"      [{idx:>3}/{total}] [ERRO] Q{question_id}: {full[:300]}", err=True)
            return {"question_id": question_id, "errors": [full[:600]]}
    redo = {
        "question_id": question_id,
        "values": base._result_to_dict(result).get(name, {}),
        "errors": [],
        "evaluator_errors": result.errors,
    }
    checkpoint.record_evaluated(cond, redo)
    return redo


async def main(source_file, name, resume_file=None, only_retried=False):
    if name not in base.RAGAS_MODELS:
        click.echo(f"❌ Avaliador inválido: {name} (válidos: {', '.join(base.RAGAS_MODELS)})", err=True)
        sys.exit(1)
    source = Path(source_file)
    data = json.loads(source.read_text(encoding="utf-8"))
    if name not in data.get("evaluators", []):
        click.echo(f"❌ O arquivo não tem o avaliador {name} (tem: {', '.join(data.get('evaluators', []))}).", err=True)
        sys.exit(1)

    def _selected(it):
        return not it.get("errors") and (not only_retried or bool(it.get("retry")))

    targets = [(c["name"], i) for c in data["conditions"] for i, it in enumerate(c["items"]) if _selected(it)]
    if not targets:
        click.echo("❌ Nenhum item selecionado (com --only-retried é preciso haver itens com o campo `retry`).", err=True)
        sys.exit(1)
    params = {"source": source.name, "evaluator": name, "model": base.RAGAS_MODELS[name], "n": len(targets), "only_retried": only_retried}
    cp_dir = Path("tools/data/processed/evaluation/unified")
    try:
        checkpoint = (Checkpoint.resume(resume_file, params) if resume_file else
                      Checkpoint.create(cp_dir / f"checkpoint_reeval_{name}_{datetime.now(base._BRT).strftime('%Y%m%d_%H%M%S')}.json", params))
    except (CheckpointMismatch, OSError, ValueError) as e:
        click.echo(f"❌ Checkpoint inválido: {e}", err=True)
        sys.exit(1)
    click.echo(f"💾 Checkpoint: {checkpoint.path.name}")

    pending = sum(
        1 for c in data["conditions"] for it in c["items"]
        if _selected(it) and checkpoint.get_evaluated(c["name"], it["question_id"]) is None
    )
    check_budget_or_exit(pending, [name], label=f"REAVALIAÇÃO {name}")

    evaluator = RagasEvaluator(
        openai_llm_model=base.RAGAS_MODELS["gpt"], gemini_model=base.RAGAS_MODELS["gemini"],
        claude_model=base.RAGAS_MODELS["claude"], evaluators=[name],
    )
    semaphore = asyncio.Semaphore(CONCURRENCY)
    previous_model = data.get("run_config", {}).get("models", {}).get(name)
    redone = {}
    for cond in data["conditions"]:
        positions = [i for i, it in enumerate(cond["items"]) if _selected(it)]
        if not positions:
            continue
        click.echo(f"\n{CONDITION_LABELS[cond['name']]}: refazendo {name} em {len(positions)} itens")
        outs = await asyncio.gather(*[
            _redo_item(n + 1, len(positions), cond["items"][i], evaluator, name, semaphore, checkpoint, cond["name"])
            for n, i in enumerate(positions)
        ])
        for i, out in zip(positions, outs):
            item = cond["items"][i]
            if out.get("skipped") or out.get("errors"):
                redone[(cond["name"], item["question_id"])] = False
                continue
            item["results"][name] = out["values"]
            item["evaluator_errors"] = [e for e in item.get("evaluator_errors", []) if e["evaluator"] != name] + out["evaluator_errors"]
            item.setdefault("reevaluated", []).append({"evaluator": name, "model": base.RAGAS_MODELS[name], "previous_model": previous_model})
            redone[(cond["name"], item["question_id"])] = True

    ok = sum(redone.values())
    items_by_name = {c["name"]: c["items"] for c in data["conditions"]}
    data.setdefault("run_config", {}).setdefault("models", {})[name] = base.RAGAS_MODELS[name]
    data["run_config"].setdefault("reevaluations", []).append({
        "evaluator": name, "model": base.RAGAS_MODELS[name], "previous_model": previous_model,
        "timestamp": get_iso_timestamp(), "source_file": source.name, "items_redone": ok, "items_not_redone": len(redone) - ok,
    })
    data["failed_questions"] = [f for f in data.get("failed_questions", []) if f["stage"] not in ("evaluation", "evaluation_partial")] + _evaluation_failures(data)
    data["divergences"] = base._calculate_divergences(items_by_name["com_ontologia"], items_by_name["sem_ontologia"])

    output_dir = Path("tools/data/processed/evaluation/unified")
    output_file = output_dir / f"evaluation_{datetime.now(base._BRT).strftime('%Y%m%d_%H%M%S')}.json"
    output_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    click.echo(f"\n✅ {name} refeito em {ok}/{len(redone)} itens (modelo: {previous_model} → {base.RAGAS_MODELS[name]})")
    click.echo(f"   Arquivo: {output_file.name}")
    click.echo(f"   Caminho completo: {output_file.resolve()}")
    if ABORT.tripped:
        click.echo(f"❌ ABORTADO: {ABORT.reason}. Parcial salvo; retome com o checkpoint como 3º argumento: {checkpoint.path}", err=True)
        sys.exit(2)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python scripts/reevaluate_evaluator.py <evaluation_*.json> <gpt|gemini|claude> [checkpoint.json]")
        sys.exit(1)
    args = [a for a in sys.argv[3:] if a != "--only-retried"]
    asyncio.run(main(sys.argv[1], sys.argv[2], args[0] if args else None, only_retried="--only-retried" in sys.argv))

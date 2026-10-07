"""Linha de base de ruído (A'): segunda geração SEM ontologia das mesmas questões, avaliada com o RAGAS.

Uso (container, a partir de /app): 
  python scripts/run_baseline_sem.py <evaluation_ref.json> [seed] [gpt,gemini,claude] [checkpoint.json]

Reaproveita do arquivo de referência as questões completas nas duas condições e os itens SEM (geração 1, A) já avaliados;
só A' é coletada e paga. Gera um evaluation_*.json no mesmo formato, com os "slots" do juiz assim:
  com_ontologia := SEM geração 2 (A')      sem_ontologia := SEM geração 1 (A)
O campo `baseline` do JSON registra isso, para o juiz e os relatórios rotularem como comparação de ruído.
Quanto os juízes e o RAGAS "preferem" A' sobre A mede a variação que a regeneração sozinha produz.
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import click

import evaluate_with_ontology_robust as base
from checkpoint import Checkpoint, CheckpointMismatch
from cost_guard import ABORT, check_budget_or_exit
from retry_failed_ragas import _evaluation_failures
from tools.evaluation.ragas.helpers import get_iso_timestamp

SLOT_LABELS = {"com_ontologia": "SEM geração 2 (A')", "sem_ontologia": "SEM geração 1 (A)"}


async def main(ref_file, seed=42, evaluators=None, resume_file=None):
    ref_path = Path(ref_file)
    ref = json.loads(ref_path.read_text(encoding="utf-8"))
    evaluators = evaluators or ref["evaluators"]
    invalid = [e for e in evaluators if e not in base.RAGAS_MODELS]
    if invalid:
        click.echo(f"❌ Avaliadores inválidos: {', '.join(invalid)}", err=True)
        sys.exit(1)

    recorded = ref.get("run_config", {}).get("models", {})
    changed = {ev: (recorded[ev], base.RAGAS_MODELS[ev]) for ev in evaluators if recorded.get(ev) and recorded[ev] != base.RAGAS_MODELS[ev]}
    if changed:
        for ev, (old, new) in changed.items():
            click.echo(f"❌ Modelo do avaliador {ev} difere do arquivo de referência: arquivo={old} / .env atual={new}", err=True)
        click.echo("   A' precisa do mesmo modelo de A. Padronize com scripts/reevaluate_evaluator.py ou ajuste o .env. Nada foi gasto.", err=True)
        sys.exit(1)

    by_cond = {c["name"]: {it["question_id"]: it for it in c["items"] if not it.get("errors")} for c in ref["conditions"]}
    ids = sorted(set(by_cond["com_ontologia"]) & set(by_cond["sem_ontologia"]))
    if not ids:
        click.echo("❌ Nenhuma questão completa nas duas condições no arquivo de referência.", err=True)
        sys.exit(1)
    click.echo(f"Referência: {ref_path.name} | {len(ids)} questões completas nas duas condições")

    params = {"kind": "baseline_sem", "ref": ref_path.name, "seed": seed, "evaluators": sorted(evaluators),
              "question_ids": ids, "models": {ev: base.RAGAS_MODELS[ev] for ev in sorted(evaluators)}}
    cp_dir = Path("tools/data/processed/evaluation/unified")
    try:
        checkpoint = (Checkpoint.resume(resume_file, params) if resume_file else
                      Checkpoint.create(cp_dir / f"checkpoint_baseline_{datetime.now(base._BRT).strftime('%Y%m%d_%H%M%S')}.json", params))
    except (CheckpointMismatch, OSError, ValueError) as e:
        click.echo(f"❌ Checkpoint inválido: {e}", err=True)
        sys.exit(1)
    click.echo(f"💾 Checkpoint: {checkpoint.path.name}")

    pending = sum(1 for q in ids if checkpoint.get_evaluated("com_ontologia", q) is None)
    check_budget_or_exit(pending, evaluators, label="A'")

    # Coleta A' (SEM ontologia), uma questão por vez
    collected, failed = [], []
    for n, q_id in enumerate(ids, 1):
        ref_item = by_cond["sem_ontologia"][q_id]
        cached = checkpoint.get_collected(q_id)
        if cached:
            collected.append(cached[0])
            click.echo(f"      [{n}/{len(ids)}] Q{q_id}: reaproveitada do checkpoint")
            continue
        question = {"question_id": q_id, "question": ref_item["question"], "answer": ref_item["ground_truth"]}
        error = None
        try:
            got = await base.collect_api_responses(questions=[question], api_base_url="http://localhost:8000",
                                                    timeout=base.COLLECTION_TIMEOUT, use_hyde=False, use_ontology=False)
            item = got[0] if got else None
            if item is None:
                error = "coleta não retornou itens"
            elif not item.get("answer"):
                error, item = "resposta vazia", None
            elif not item.get("contexts"):
                error, item = "contextos vazios", None
        except Exception as e:
            item, error = None, f"{type(e).__name__}: {e}"
        if item:
            collected.append(item)
            checkpoint.record_collected(q_id, item, None)
            click.echo(f"      [{n}/{len(ids)}] Q{q_id}: [OK]")
        else:
            failed.append({"question_id": q_id, "condition": "A'", "stage": "collection", "error": error})
            click.echo(f"      [{n}/{len(ids)}] Q{q_id}: [SKIP] {error}")
    if not collected:
        click.echo("❌ Nenhuma resposta A' coletada.", err=True)
        sys.exit(1)

    evaluator = base.RagasEvaluator(
        openai_llm_model=base.RAGAS_MODELS["gpt"], gemini_model=base.RAGAS_MODELS["gemini"],
        claude_model=base.RAGAS_MODELS["claude"], evaluators=evaluators,
    )
    semaphore = asyncio.Semaphore(5)
    eval_a1 = await asyncio.gather(*[
        base._evaluate_item(i + 1, len(collected), item, evaluator, semaphore, set(), checkpoint, "com_ontologia")
        for i, item in enumerate(collected)
    ])

    a_items = [by_cond["sem_ontologia"][it["question_id"]] for it in eval_a1]
    actual_evaluators = sorted({ev for it in eval_a1 + a_items if it.get("results") for ev in it["results"]})
    failures = failed + [
        {"question_id": f["question_id"], "condition": "A'", "stage": f["stage"], "error": f["error"]}
        for f in _evaluation_failures({"conditions": [{"name": "com_ontologia", "items": eval_a1}]})
    ]
    # _evaluation_failures rotula pelo slot; troca o rótulo para A'
    result = {
        "evaluation_run": get_iso_timestamp(),
        "baseline": {
            "purpose": "linha de base de ruído: SEM geração 2 (A') contra SEM geração 1 (A)",
            "slots": SLOT_LABELS,
            "reference_file": ref_path.name,
        },
        "dataset": {"file": ref.get("dataset", {}).get("file"), "total_questions": len(ids), "target_samples": None, "seed": seed},
        "evaluators": actual_evaluators,
        "run_config": {
            "kind": "baseline_sem", "reference_file": ref_path.name, "seed": seed, "use_hyde": False,
            "requested_evaluators": evaluators,
            "models": {ev: base.RAGAS_MODELS[ev] for ev in actual_evaluators},
            "evaluator_temperature": base.os.environ.get("EVALUATOR_TEMPERATURE"),
        },
        "failed_questions": failures,
        "conditions": [
            {"name": "com_ontologia", "slot_label": SLOT_LABELS["com_ontologia"], "use_ontology": False,
             "collected_count": len(collected), "evaluated_count": len([e for e in eval_a1 if not e.get("errors")]), "items": eval_a1},
            {"name": "sem_ontologia", "slot_label": SLOT_LABELS["sem_ontologia"], "use_ontology": False,
             "collected_count": len(a_items), "evaluated_count": len(a_items), "items": a_items},
        ],
        "divergences": base._calculate_divergences(eval_a1, a_items),
    }
    cp_dir.mkdir(parents=True, exist_ok=True)
    out = cp_dir / f"evaluation_baseline_{datetime.now(base._BRT).strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = result["conditions"][0]["evaluated_count"]
    click.echo(f"\n✅ A' avaliada em {ok}/{len(ids)} questões")
    click.echo(f"   Arquivo: {out.name}")
    click.echo(f"   Caminho completo: {out.resolve()}")
    if ABORT.tripped:
        click.echo(f"❌ ABORTADO: {ABORT.reason}. Parcial salvo; retome com o checkpoint como 4º argumento: {checkpoint.path}", err=True)
        sys.exit(2)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/run_baseline_sem.py <evaluation_ref.json> [seed] [gpt,gemini,claude] [checkpoint.json]")
        sys.exit(1)
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 42
    evs = [e.strip() for e in sys.argv[3].split(",")] if len(sys.argv) > 3 else None
    asyncio.run(main(sys.argv[1], seed, evs, sys.argv[4] if len(sys.argv) > 4 else None))

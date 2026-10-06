#!/usr/bin/env python3
"""
Pipeline RAGAS com/sem ontologia com FALLBACK AUTOMÁTICO.
Se qualquer questão falhar (com ou sem ontologia), usa a próxima do dataset.
Garante que no final temos o MESMO número de questões avaliadas em ambas condições.
"""

import asyncio
import json
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

api_root = Path(__file__).resolve().parent
project_root = api_root.parent
load_dotenv(project_root / ".env")

os.chdir(str(api_root))

from tools.evaluation.ragas.evaluator import collect_api_responses, RagasEvaluator, _parse_answer
from tools.evaluation.ragas.helpers import (
    load_xlsx_dataset,
    get_iso_timestamp,
    ALL_METRICS,
    step as _step,
    banner as _banner,
    abort as _abort,
    check_gemini,
)

_BRT = timezone(timedelta(hours=-3))


def _result_to_dict(result):
    """Converte EvalResult para dict"""
    from tools.evaluation.ragas.evaluator import EvalResult
    by_metric = {
        "faithfulness":          result.faithfulness,
        "answer_relevancy":      result.answer_relevancy,
        "context_precision":     result.context_precision,
        "context_recall":        result.context_recall,
        "context_entity_recall": result.context_entity_recall,
    }
    evaluators = {ev for scores in by_metric.values() for ev in scores}
    return {
        ev: {metric: scores.get(ev) for metric, scores in by_metric.items()}
        for ev in sorted(evaluators)
    }


def _calculate_divergences(eval_com, eval_sem):
    """Calcula divergências de métricas entre COM vs SEM ontologia"""
    from collections import defaultdict

    metrics_by_eval = defaultdict(lambda: defaultdict(lambda: {'com_ontologia': [], 'sem_ontologia': []}))

    # Agregar métricas COM ontologia
    for item in eval_com:
        if item.get('errors'):
            continue
        for eval_name, metrics in item.get('results', {}).items():
            for metric_name, value in metrics.items():
                if value is not None:
                    metrics_by_eval[eval_name][metric_name]['com_ontologia'].append(value)

    # Agregar métricas SEM ontologia
    for item in eval_sem:
        if item.get('errors'):
            continue
        for eval_name, metrics in item.get('results', {}).items():
            for metric_name, value in metrics.items():
                if value is not None:
                    metrics_by_eval[eval_name][metric_name]['sem_ontologia'].append(value)

    # Calcular averages e deltas
    divergences = {
        "description": "Comparação das métricas entre condições (com vs sem ontologia). Delta positivo = sem ontologia melhor. Calculado apenas sobre questões avaliadas.",
        "by_evaluator": {}
    }

    for eval_name in sorted(metrics_by_eval.keys()):
        eval_metrics = {}
        for metric_name in sorted(metrics_by_eval[eval_name].keys()):
            com_values = metrics_by_eval[eval_name][metric_name]['com_ontologia']
            sem_values = metrics_by_eval[eval_name][metric_name]['sem_ontologia']

            com_avg = sum(com_values) / len(com_values) if com_values else 0
            sem_avg = sum(sem_values) / len(sem_values) if sem_values else 0
            delta = sem_avg - com_avg
            winner = "sem_ontologia" if delta > 0 else "com_ontologia" if delta < 0 else "empate"

            eval_metrics[metric_name] = {
                "com_ontologia": round(com_avg, 6),
                "sem_ontologia": round(sem_avg, 6),
                "delta": round(delta, 6),
                "winner": winner
            }

        divergences["by_evaluator"][eval_name] = eval_metrics

    return divergences


async def _evaluate_item(idx, total, item, evaluator, semaphore, active_evaluators):
    """Avalia um item com tratamento de erro"""
    import click

    question = item.get("question", "")
    answer_rag = item.get("answer", "")
    ground_truth = item.get("ground_truth", "")
    contexts = item.get("contexts", [])
    question_id = item.get("question_id")

    score_item = {
        "question_id": question_id,
        "question": question,
        "ground_truth": ground_truth,
        "answer": answer_rag,
        "contexts": contexts,
        "results": {},
        "errors": [],
    }

    _answer_sanitized = ''.join(
        c for c in answer_rag
        if ord(c) > 8 and ord(c) != 11
        and (ord(c) >= 32 or ord(c) == 9 or ord(c) == 10 or ord(c) == 13)
        and ord(c) != 127
    ).strip()

    if len(_answer_sanitized) < 50:
        msg = f"resposta corrompida/truncada ({len(_answer_sanitized)} chars)"
        score_item["errors"].append(msg)
        click.echo(f"      [{idx:>3}/{total}] [SKIP] Q{question_id}", err=True)
        return score_item

    async with semaphore:
        click.echo(f"      [{idx:>3}/{total}] Q{question_id}...")
        try:
            result = await evaluator.evaluate_all(
                question=question,
                answer=_answer_sanitized,
                contexts=contexts,
                ground_truth=ground_truth,
                log_prefix=f"      [{idx:>3}/{total}]",
            )
            score_item["results"] = _result_to_dict(result)
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            score_item["errors"].append(msg)
            click.echo(f"      [{idx:>3}/{total}] [ERRO] Q{question_id}: {msg}", err=True)

    return score_item


async def main(
    input_file: str = "tools/data/raw/evaluation/filtred_alergia_medicamentos.xlsx",
    target_samples: int = 30,
    seed: int = 42,
):
    """
    Avalia COM e SEM ontologia com fallback automático.
    Coleta questões até ter target_samples VÁLIDAS em ambas condições.
    """
    import click

    _banner("PIPELINE RAGAS: COM/SEM ONTOLOGIA (COM FALLBACK)")

    # 1. LOAD
    _step("1/6", "LOAD", "CARREGANDO DATASET")
    questions = load_xlsx_dataset(input_file, max_samples=None, seed=seed)
    total_available = len(questions)
    click.echo(f"      [OK] {total_available} questões disponíveis no dataset\n")

    # 2. VALIDATE
    _step("2/6", "VALIDATE", "VALIDANDO API")
    api_url = "http://localhost:8000"
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    gemini_model = "gemini-2.5-flash-lite"
    if gemini_api_key:
        try:
            await check_gemini(gemini_api_key, gemini_model)
            click.echo(f"      [OK] Gemini validado\n")
        except Exception as e:
            click.echo(f"      ⚠️  Aviso: Gemini validation falhou: {e}\n")
    else:
        click.echo(f"      ⚠️  Aviso: GEMINI_API_KEY não configurada\n")

    # 3. COLLECT COM ONTOLOGIA (com fallback)
    _step("3/6", "COLLECT", f"COLETANDO {target_samples} RESPOSTAS (COM ONTOLOGIA)")
    responses_com = []
    question_idx = 0
    while len(responses_com) < target_samples and question_idx < total_available:
        q = questions[question_idx]
        question_id = q.get("question_id", question_idx + 1)
        question_text = q.get("question", "")[:50]

        click.echo(f"      Coletando resposta {len(responses_com)+1}/{target_samples}: Q{question_id}")

        try:
            collected = await collect_api_responses(
                questions=[q],
                api_base_url=api_url,
                timeout=60,
                use_hyde=False,
                use_ontology=True,
            )
            if collected and len(collected) > 0:
                item = collected[0]
                if item.get("answer") and item.get("contexts"):
                    responses_com.append(item)
                    click.echo(f"      [OK] Resposta {len(responses_com)} coletada com sucesso\n")
                else:
                    click.echo(f"      [SKIP] Q{question_id}: resposta ou contextos vazios, tentando próxima\n")
                    question_idx += 1
                    continue
            else:
                click.echo(f"      [SKIP] Q{question_id}: coleta falhou, tentando próxima\n")
                question_idx += 1
                continue
        except Exception as e:
            click.echo(f"      [ERRO] Q{question_id}: {type(e).__name__}, tentando próxima\n")
            question_idx += 1
            continue

        question_idx += 1

    click.echo(f"      [OK] {len(responses_com)}/{target_samples} válidas\n")
    if len(responses_com) < target_samples:
        click.echo(f"      ⚠️  Aviso: Apenas {len(responses_com)}/{target_samples} questões coletadas COM ontologia\n")

    # 4. COLLECT SEM ONTOLOGIA (com fallback - pode usar questões diferentes)
    _step("4/6", "COLLECT", f"COLETANDO {len(responses_com)} RESPOSTAS (SEM ONTOLOGIA)")
    responses_sem = []
    question_idx = 0

    while len(responses_sem) < len(responses_com) and question_idx < total_available:
        q = questions[question_idx]
        q_id = q.get("question_id", question_idx + 1)
        question_text = q.get("question", "")[:50]

        click.echo(f"      Coletando resposta {len(responses_sem)+1}/{len(responses_com)}: Q{q_id}")

        try:
            collected = await collect_api_responses(
                questions=[q],
                api_base_url=api_url,
                timeout=60,
                use_hyde=False,
                use_ontology=False,
            )
            if collected and len(collected) > 0:
                item = collected[0]
                if item.get("answer") and item.get("contexts"):
                    responses_sem.append(item)
                    click.echo(f"      [OK] Resposta {len(responses_sem)} coletada com sucesso\n")
                else:
                    click.echo(f"      [SKIP] Q{q_id}: resposta ou contextos vazios, tentando próxima\n")
                    question_idx += 1
                    continue
            else:
                click.echo(f"      [SKIP] Q{q_id}: coleta falhou, tentando próxima\n")
                question_idx += 1
                continue
        except Exception as e:
            click.echo(f"      [ERRO] Q{q_id}: {type(e).__name__}, tentando próxima\n")
            question_idx += 1
            continue

        question_idx += 1

    click.echo(f"      [OK] {len(responses_sem)}/{len(responses_com)} válidas\n")

    # Garantir paridade
    min_count = min(len(responses_com), len(responses_sem))
    responses_com = responses_com[:min_count]
    responses_sem = responses_sem[:min_count]

    if min_count == 0:
        _abort("Nenhuma resposta válida coletada!")

    # 5. AVALIAR
    _step("5/6", "EVAL", f"AVALIANDO {min_count} questões (concorrência: 5)")

    evaluator = RagasEvaluator(
        openai_llm_model="gpt-4o-mini",
        gemini_model="gemini-2.5-flash-lite",
        claude_model="claude-haiku-4-5-20251001",
        evaluators=["gemini"],
    )

    # Avaliar COM ontologia
    click.echo("\nAvaliando COM ONTOLOGIA:\n")
    semaphore = asyncio.Semaphore(5)
    active_evaluators = set()

    eval_com = await asyncio.gather(*[
        _evaluate_item(i+1, min_count, item, evaluator, semaphore, active_evaluators)
        for i, item in enumerate(responses_com)
    ])

    # Avaliar SEM ontologia
    click.echo("\nAvaliando SEM ONTOLOGIA:\n")
    eval_sem = await asyncio.gather(*[
        _evaluate_item(i+1, min_count, item, evaluator, semaphore, active_evaluators)
        for i, item in enumerate(responses_sem)
    ])

    click.echo("      [OK] Avaliação concluída\n")

    # 6. SAVE
    _step("6/6", "SAVE", "CONSOLIDANDO RESULTADO")

    result = {
        "evaluation_run": get_iso_timestamp(),
        "dataset": {
            "file": Path(input_file).name,
            "total_questions": total_available,
            "target_samples": target_samples,
            "seed": seed,
        },
        "evaluators": ["gemini"],
        "conditions": [
            {
                "name": "com_ontologia",
                "use_ontology": True,
                "requested_count": target_samples,
                "collected_count": len(responses_com),
                "evaluated_count": len([e for e in eval_com if not e.get("errors")]),
                "items": eval_com,
            },
            {
                "name": "sem_ontologia",
                "use_ontology": False,
                "requested_count": target_samples,
                "collected_count": len(responses_sem),
                "evaluated_count": len([e for e in eval_sem if not e.get("errors")]),
                "items": eval_sem,
            },
        ],
        "divergences": _calculate_divergences(eval_com, eval_sem),
    }

    output_dir = Path("tools/data/processed/evaluation/unified")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(_BRT).strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"evaluation_{timestamp}.json"
    output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    latest_file = output_dir / "evaluation_latest.json"
    latest_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    click.echo(f"      [OK] {output_file.name}\n")

    _banner("CONCLUÍDO")
    click.echo(f"  Arquivo: {output_file.name}")
    click.echo(f"  Caminho completo: {output_file.resolve()}\n")
    eval_com_ok = len([e for e in eval_com if not e.get("errors")])
    eval_sem_ok = len([e for e in eval_sem if not e.get("errors")])
    click.echo(f"  COM ontologia: {len(responses_com)} coletadas → {eval_com_ok} avaliadas")
    click.echo(f"  SEM ontologia: {len(responses_sem)} coletadas → {eval_sem_ok} avaliadas\n")


if __name__ == "__main__":
    import sys

    input_file = sys.argv[1] if len(sys.argv) > 1 else "tools/data/raw/evaluation/filtred_alergia_medicamentos.xlsx"
    target_samples = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 42

    asyncio.run(main(input_file=input_file, target_samples=target_samples, seed=seed))

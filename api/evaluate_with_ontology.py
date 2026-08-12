#!/usr/bin/env python3
"""
Pipeline RAGAS com/sem ontologia: uma etapa simples adicionada ao fluxo existente.
Executa: dataset → API (com onto) → avaliação → API (sem onto) → avaliação → consolida
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

from tools.evaluation.ragas.evaluator import collect_api_responses, RagasEvaluator
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


async def _evaluate_item(idx, total, item, evaluator, semaphore, active_evaluators):
    """Avalia um item com tratamento de erro"""
    from tools.evaluation.ragas.evaluator import _parse_answer
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


async def evaluate_condition(responses, evaluator, active_evaluators, concurrency=5):
    """Avalia uma condição (com ou sem ontologia)"""
    import click

    semaphore = asyncio.Semaphore(concurrency)
    total = len(responses)

    tasks = [
        _evaluate_item(idx, total, item, evaluator, semaphore, active_evaluators)
        for idx, item in enumerate(responses, 1)
    ]

    scores_list = []
    for coro in asyncio.as_completed(tasks):
        score_item = await coro
        scores_list.append(score_item)

    scores_list.sort(key=lambda x: x.get("question_id") or 0)
    return scores_list


def compute_summary_metrics(scores_list, active_evaluators):
    """Computa médias das métricas"""
    sums = {ev: {m: 0.0 for m in ALL_METRICS} for ev in active_evaluators}
    counts = {ev: {m: 0 for m in ALL_METRICS} for ev in active_evaluators}

    for item in scores_list:
        if item.get("results"):
            for ev, metrics in item["results"].items():
                for metric, value in metrics.items():
                    if value is not None and ev in sums:
                        sums[ev][metric] += value
                        counts[ev][metric] += 1

    avgs = {}
    for ev in sums:
        avgs[ev] = {}
        for metric in ALL_METRICS:
            n = counts[ev][metric]
            avgs[ev][metric] = round(sums[ev][metric] / n, 6) if n > 0 else None

    return avgs


def compute_divergences(summary_com, summary_sem, active_evaluators):
    """Computa divergências entre condições (com vs sem ontologia)"""
    divergences = {}
    for ev in active_evaluators:
        divergences[ev] = {}
        for metric in ALL_METRICS:
            val_com = summary_com.get(ev, {}).get(metric)
            val_sem = summary_sem.get(ev, {}).get(metric)
            if val_com is not None and val_sem is not None:
                delta = val_sem - val_com
                winner = "sem_ontologia" if delta > 0 else "com_ontologia" if delta < 0 else "equivalente"
                divergences[ev][metric] = {
                    "com_ontologia": round(val_com, 6),
                    "sem_ontologia": round(val_sem, 6),
                    "delta": round(delta, 6),
                    "winner": winner,
                }
    return divergences


async def main(
    input_file: str,
    max_samples: int = 30,
    seed: int = None,
    api_url: str = "http://localhost:8000",
    api_timeout: int = 30,
    concurrency: int = 5,
    output_dir: str = None,
):
    """Pipeline unificado com/sem ontologia"""
    import click

    if output_dir is None:
        output_dir = str(Path(__file__).resolve().parent / "tools" / "data" / "processed" / "evaluation" / "unified")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    _banner("PIPELINE RAGAS: COM/SEM ONTOLOGIA")

    # 1. CARREGAR
    _step("1/6", "LOAD", "CARREGANDO DATASET")
    try:
        questions = load_xlsx_dataset(input_file, max_samples=max_samples)
        click.echo(f"      [OK] {len(questions)} questões carregadas\n")
    except Exception as e:
        _abort(f"Erro ao carregar: {e}")

    # 2. VALIDAR APIs
    _step("2/6", "VALIDATE", "VALIDANDO API")
    ok = await check_gemini(os.getenv("GEMINI_API_KEY"), "gemini-2.5-flash-lite")
    if not ok:
        _abort("Credencial de API inválida")
    click.echo(f"      [OK] Gemini validado\n")

    active_evaluators = ["gemini"]

    # 3. COLETAR COM ONTOLOGIA
    _step("3/6", "COLLECT", "COLETANDO RESPOSTAS (COM ONTOLOGIA)")
    try:
        responses_com = await collect_api_responses(
            questions=questions,
            api_base_url=api_url,
            timeout=api_timeout,
            use_hyde=False,
            use_ontology=True,
        )
        valid_com = [r for r in responses_com if r.get("answer") is not None]
        click.echo(f"      [OK] {len(valid_com)}/{len(responses_com)} válidas\n")
    except Exception as e:
        _abort(f"Erro ao coletar (com onto): {e}")

    # 4. COLETAR SEM ONTOLOGIA
    _step("4/6", "COLLECT", "COLETANDO RESPOSTAS (SEM ONTOLOGIA)")
    try:
        responses_sem = await collect_api_responses(
            questions=questions,
            api_base_url=api_url,
            timeout=api_timeout,
            use_hyde=False,
            use_ontology=False,
        )
        valid_sem = [r for r in responses_sem if r.get("answer") is not None]
        click.echo(f"      [OK] {len(valid_sem)}/{len(responses_sem)} válidas\n")
    except Exception as e:
        _abort(f"Erro ao coletar (sem onto): {e}")

    # 5. AVALIAR (apenas itens com contextos)
    _step("5/6", "EVAL", f"AVALIANDO (concorrência: {concurrency})")
    try:
        evaluator = RagasEvaluator(
            openai_llm_model="gpt-4o-mini",
            gemini_model="gemini-2.5-flash-lite",
            claude_model="claude-haiku-4-5-20251001",
            evaluators=active_evaluators,
        )

        no_context_com = [r.get("question_id") for r in valid_com if not r.get("contexts")]
        no_context_sem = [r.get("question_id") for r in valid_sem if not r.get("contexts")]

        evalable_com = [r for r in valid_com if r.get("contexts")]
        evalable_sem = [r for r in valid_sem if r.get("contexts")]

        if no_context_com:
            click.echo(f"      ⚠️  Q{no_context_com}: NÃO HÁ TRECHOS CORRESPONDENTES NO PINECONE/ONTOLOGIA")
        click.echo(f"      Com ontologia: {len(evalable_com)}/{len(valid_com)} itens (com contextos)")
        scores_com = await evaluate_condition(
            evalable_com, evaluator, active_evaluators, concurrency=concurrency
        ) if evalable_com else []

        if no_context_sem:
            click.echo(f"      ⚠️  Q{no_context_sem}: NÃO HÁ TRECHOS CORRESPONDENTES NO PINECONE/ONTOLOGIA")
        click.echo(f"      Sem ontologia: {len(evalable_sem)}/{len(valid_sem)} itens (com contextos)")
        scores_sem = await evaluate_condition(
            evalable_sem, evaluator, active_evaluators, concurrency=concurrency
        ) if evalable_sem else []

        click.echo(f"      [OK] Avaliação concluída\n")
    except Exception as e:
        _abort(f"Erro ao avaliar: {e}")

    # 6. CONSOLIDA JSON
    _step("6/6", "SAVE", "CONSOLIDANDO RESULTADO")

    summary_com = compute_summary_metrics(scores_com, active_evaluators)
    summary_sem = compute_summary_metrics(scores_sem, active_evaluators)
    divergences = compute_divergences(summary_com, summary_sem, active_evaluators)

    result = {
        "evaluation_run": get_iso_timestamp(),
        "dataset": {
            "file": Path(input_file).name,
            "total_questions": len(questions),
            "sampled_questions": max_samples,
            "seed": seed,
        },
        "evaluators": active_evaluators,
        "conditions": [
            {
                "name": "com_ontologia",
                "use_ontology": True,
                "sample_count": len(valid_com),
                "evaluated_count": len([s for s in scores_com if s.get("results")]),
                "no_context_questions": no_context_com,
                "items": scores_com,
                "summary_metrics": summary_com,
            },
            {
                "name": "sem_ontologia",
                "use_ontology": False,
                "sample_count": len(valid_sem),
                "evaluated_count": len([s for s in scores_sem if s.get("results")]),
                "no_context_questions": no_context_sem,
                "items": scores_sem,
                "summary_metrics": summary_sem,
            },
        ],
        "divergences": {
            "description": "Comparação das métricas entre condições (com vs sem ontologia). Delta positivo = sem ontologia melhor. Calculado apenas sobre questões avaliadas.",
            "by_evaluator": divergences,
        },
    }

    timestamp = datetime.now(_BRT).strftime("%Y%m%d_%H%M%S")
    output_file = output_path / f"evaluation_{timestamp}.json"
    output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    latest_file = output_path / "evaluation_latest.json"
    latest_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    click.echo(f"      [OK] {output_file.name}\n")

    _banner("CONCLUÍDO")
    click.echo(f"  Arquivo: {output_file.name}")
    click.echo(f"  Caminho completo: {output_file.resolve()}\n")
    click.echo(f"  Com ontologia: {len(valid_com)} coletadas → {len([s for s in scores_com if s.get('results')])} avaliadas")
    click.echo(f"  Sem ontologia: {len(valid_sem)} coletadas → {len([s for s in scores_sem if s.get('results')])} avaliadas")

    if no_context_com or no_context_sem:
        click.echo(f"\n  ⚠️  QUESTÕES SEM TRECHOS NO PINECONE/ONTOLOGIA:")
        if no_context_com:
            click.echo(f"      Com onto: Q{no_context_com}")
        if no_context_sem:
            click.echo(f"      Sem onto: Q{no_context_sem}")
    click.echo()


if __name__ == "__main__":
    import sys

    input_file = sys.argv[1] if len(sys.argv) > 1 else "tools/data/raw/evaluation/filtred_alergia_medicamentos.xlsx"
    max_samples = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    asyncio.run(main(
        input_file=input_file,
        max_samples=max_samples,
    ))

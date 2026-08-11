#!/usr/bin/env python3
"""
Pipeline RAGAS Unificado: executa ambas condições (com/sem ontologia)
e consolida tudo em um único JSON.
"""

import json
import asyncio
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Carregar .env
project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")

api_root = Path(__file__).parent
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
    check_openai,
)


_BRT = timezone(timedelta(hours=-3))


def _result_to_dict(result):
    """Converter EvalResult para dict"""
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


async def _evaluate_item_unified(idx, total, item, evaluator, semaphore, active_evaluators):
    """Avalia um item com tratamento de erro consolidado"""
    from tools.evaluation.ragas.evaluator import _parse_answer, _CONTROL_CHARS_RE
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

    # Sanitizar resposta
    _answer_sanitized = ''.join(
        c for c in answer_rag
        if ord(c) > 8 and ord(c) != 11
        and (ord(c) >= 32 or ord(c) == 9 or ord(c) == 10 or ord(c) == 13)
        and ord(c) != 127
    ).strip()

    if len(_answer_sanitized) < 50:
        msg = f"resposta corrompida/truncada ({len(_answer_sanitized)} chars após sanitização)"
        score_item["errors"].append(msg)
        click.echo(f"      [{idx:>3}/{total}] [SKIP] Q{question_id} | {msg}", err=True)
        return score_item

    async with semaphore:
        click.echo(f"      [{idx:>3}/{total}] Q{question_id} avaliando...")
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
            import traceback
            msg = f"{type(e).__name__}: {e}"
            score_item["errors"].append(msg)
            click.echo(f"      [{idx:>3}/{total}] [ERRO] Q{question_id}: {msg}", err=True)

    return score_item


async def evaluate_condition(
    responses,
    evaluator,
    active_evaluators,
    concurrency=5,
):
    """Avalia uma condição (com ou sem ontologia)"""
    import click

    semaphore = asyncio.Semaphore(concurrency)
    total = len(responses)

    tasks = [
        _evaluate_item_unified(idx, total, item, evaluator, semaphore, active_evaluators)
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


def build_comparison(conditions):
    """Constrói seção de comparação entre condições"""
    ids_with_ontology = set()
    ids_without_ontology = set()

    for condition in conditions:
        ids = set(item["question_id"] for item in condition["items"] if item.get("results"))
        if condition["use_ontology"]:
            ids_with_ontology = ids
        else:
            ids_without_ontology = ids

    comparison = {
        "total_questions_dataset": 30,
        "questions_in_both_conditions": sorted(ids_with_ontology & ids_without_ontology),
        "questions_only_with_ontology": sorted(ids_with_ontology - ids_without_ontology),
        "questions_only_without_ontology": sorted(ids_without_ontology - ids_with_ontology),
    }

    return comparison


async def run_unified_evaluation(
    input_file: str,
    max_samples: int = 30,
    seed: int = None,
    evaluators: str = "gemini",
    api_url: str = "http://localhost:8000",
    api_timeout: int = 30,
    concurrency: int = 5,
    output_dir: str = None,
):
    """Executa pipeline unificado com ambas as condições"""
    import click

    if output_dir is None:
        output_dir = str(Path(__file__).parent / "tools" / "data" / "processed" / "evaluation")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 1. CARREGAR DATASET
    _step("1/7", "LOAD", "CARREGANDO DATASET")
    try:
        questions = load_xlsx_dataset(input_file, max_samples=max_samples)
        click.echo(f"      [OK] {len(questions)} questões carregadas com seed={seed}\n")
    except Exception as e:
        _abort(f"Erro ao carregar dataset: {e}")

    # 2. VALIDAR APIs
    _step("2/7", "VALIDATE", "VALIDANDO CREDENCIAIS DE API")
    active_evaluators = [e.strip() for e in evaluators.split(",") if e.strip() in ("gpt", "gemini", "claude", "ollama")]

    checks = []
    if "gemini" in active_evaluators:
        click.echo(f"  Gemini... ", nl=False)
        ok = await check_gemini(os.getenv("GEMINI_API_KEY"), "gemini-2.5-flash-lite")
        click.echo("✅" if ok else "❌")
        checks.append(ok)

    if not all(checks):
        _abort("Credenciais de API inválidas")
    click.echo()

    # 3. COLETAR RESPOSTAS - COM ONTOLOGIA
    _step("3/7", "COLLECT", "COLETANDO RESPOSTAS (COM ONTOLOGIA)")
    try:
        responses_com = await collect_api_responses(
            questions=questions,
            api_base_url=api_url,
            timeout=api_timeout,
            use_hyde=False,
            use_ontology=True,
        )
        valid_responses_com = [r for r in responses_com if r.get("answer") is not None]
        click.echo(f"      [OK] {len(valid_responses_com)}/{len(responses_com)} respostas válidas\n")
    except Exception as e:
        _abort(f"Erro ao coletar respostas (com ontologia): {e}")

    # 4. COLETAR RESPOSTAS - SEM ONTOLOGIA
    _step("4/7", "COLLECT", "COLETANDO RESPOSTAS (SEM ONTOLOGIA)")
    try:
        responses_sem = await collect_api_responses(
            questions=questions,
            api_base_url=api_url,
            timeout=api_timeout,
            use_hyde=False,
            use_ontology=False,
        )
        valid_responses_sem = [r for r in responses_sem if r.get("answer") is not None]
        click.echo(f"      [OK] {len(valid_responses_sem)}/{len(responses_sem)} respostas válidas\n")
    except Exception as e:
        _abort(f"Erro ao coletar respostas (sem ontologia): {e}")

    # 5. AVALIAR - COM ONTOLOGIA
    _step("5/7", "EVAL", f"AVALIANDO COM ONTOLOGIA ({len(valid_responses_com)} itens)")
    try:
        evaluator = RagasEvaluator(
            openai_llm_model="gpt-4o-mini",
            gemini_model="gemini-2.5-flash-lite",
            claude_model="claude-haiku-4-5-20251001",
            evaluators=active_evaluators,
        )
        scores_com = await evaluate_condition(
            valid_responses_com,
            evaluator,
            active_evaluators,
            concurrency=concurrency,
        )
        click.echo(f"      [OK] Avaliação concluída\n")
    except Exception as e:
        _abort(f"Erro ao avaliar (com ontologia): {e}")

    # 6. AVALIAR - SEM ONTOLOGIA
    _step("6/7", "EVAL", f"AVALIANDO SEM ONTOLOGIA ({len(valid_responses_sem)} itens)")
    try:
        scores_sem = await evaluate_condition(
            valid_responses_sem,
            evaluator,
            active_evaluators,
            concurrency=concurrency,
        )
        click.echo(f"      [OK] Avaliação concluída\n")
    except Exception as e:
        _abort(f"Erro ao avaliar (sem ontologia): {e}")

    # 7. CONSOLIDAR RESULTADO
    _step("7/7", "SAVE", "CONSOLIDANDO RESULTADO EM JSON ÚNICO")

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
                "use_hyde": False,
                "sample_count": len(valid_responses_com),
                "items": scores_com,
                "summary_metrics": compute_summary_metrics(scores_com, active_evaluators),
            },
            {
                "name": "sem_ontologia",
                "use_ontology": False,
                "use_hyde": False,
                "sample_count": len(valid_responses_sem),
                "items": scores_sem,
                "summary_metrics": compute_summary_metrics(scores_sem, active_evaluators),
            },
        ],
        "comparison": build_comparison([
            {
                "use_ontology": True,
                "items": scores_com,
            },
            {
                "use_ontology": False,
                "items": scores_sem,
            },
        ]),
    }

    # Salvar JSON
    timestamp = datetime.now(_BRT).strftime("%Y%m%d_%H%M%S")
    output_file = output_path / f"unified_evaluation_{timestamp}.json"
    output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # Manter latest também
    latest_file = output_path / "unified_evaluation_latest.json"
    latest_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    click.echo(f"      [OK] {output_file.name}\n")

    # RESUMO
    _banner("AVALIAÇÃO UNIFICADA CONCLUÍDA")
    click.echo(f"  Arquivo: {output_file.name}")
    click.echo(f"  Tamanho: {output_file.stat().st_size / 1024:.1f} KB")
    click.echo(f"  Com ontologia: {len(valid_responses_com)} itens → {len([s for s in scores_com if s.get('results')])} avaliados")
    click.echo(f"  Sem ontologia: {len(valid_responses_sem)} itens → {len([s for s in scores_sem if s.get('results')])} avaliados")
    click.echo(f"  Diferença: {abs(len(valid_responses_com) - len(valid_responses_sem))} questões\n")

    return str(output_file)


if __name__ == "__main__":
    import sys

    # Argumentos
    input_file = sys.argv[1] if len(sys.argv) > 1 else "tools/data/raw/evaluation/filtred_alergia_medicamentos.xlsx"
    max_samples = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 42
    evaluators = sys.argv[4] if len(sys.argv) > 4 else "gemini"

    # Executar
    try:
        output = asyncio.run(run_unified_evaluation(
            input_file=input_file,
            max_samples=max_samples,
            seed=seed,
            evaluators=evaluators,
        ))
        print(f"\n✅ Resultado consolidado salvo em: {output}")
    except Exception as e:
        print(f"\n❌ Erro: {e}", file=sys.stderr)
        sys.exit(1)

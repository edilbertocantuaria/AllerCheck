#!/usr/bin/env python3
"""
Pipeline RAGAS com/sem ontologia com FALLBACK AUTOMÁTICO.
Se qualquer questão falhar (com ou sem ontologia), usa a próxima do dataset.
Garante que no final temos o MESMO número de questões avaliadas em ambas condições.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

api_root = Path(__file__).resolve().parent.parent
project_root = api_root.parent
load_dotenv(project_root / ".env")

os.chdir(str(api_root))
sys.path.insert(0, str(api_root))

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
        "ontology_expansion": item.get("ontology_expansion", []),
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
    selected_questions_file: str = None,
    evaluators: list = None,
):
    """
    Avalia COM e SEM ontologia com fallback automático.
    Se selected_questions_file for passado, usa aquele subset específico.
    Senão, carrega do Excel e seleciona target_samples.
    """
    import click

    _banner("PIPELINE RAGAS: COM/SEM ONTOLOGIA (COM FALLBACK)")

    # 1. LOAD
    _step("1/6", "LOAD", "CARREGANDO DATASET E QUESTÕES")

    if selected_questions_file:
        click.echo(f"      Lendo questões selecionadas: {selected_questions_file}\n")
        try:
            with open(selected_questions_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Suportar tanto formato antigo (lista) quanto novo (dict com metadata)
                if isinstance(data, dict) and "questions" in data:
                    questions = data["questions"]
                else:
                    questions = data
            click.echo(f"      [OK] {len(questions)} questões carregadas\n")
        except Exception as e:
            click.echo(f"      [ERRO] Falha ao ler {selected_questions_file}: {e}\n")
            click.echo(f"      Caindo para modo padrão (Excel + seed)\n")
            questions = load_xlsx_dataset(input_file, max_samples=target_samples, seed=seed)
    else:
        questions = load_xlsx_dataset(input_file, max_samples=target_samples, seed=seed)

    total_available = len(questions)
    click.echo(f"      [OK] {total_available} questões disponíveis\n")

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

    # 3. COLLECT COM/SEM SINCRONIZADO (mesmas questões em ambas condições)
    _step("3/6", "COLLECT", f"COLETANDO RESPOSTAS (COM + SEM ONTOLOGIA SINCRONIZADO)")

    responses_com = []
    responses_sem = []
    failed_questions = []

    for idx, q in enumerate(questions):
        question_id = q.get("question_id", idx + 1)
        question_text = q.get("question", "")[:50]

        # Tentar coletar COM ontologia
        click.echo(f"      [{idx+1}/{len(questions)}] Q{question_id}: Coletando COM ontologia...", nl=False)
        try:
            collected_com = await collect_api_responses(
                questions=[q],
                api_base_url=api_url,
                timeout=60,
                use_hyde=False,
                use_ontology=True,
            )
            item_com = None
            if collected_com and len(collected_com) > 0:
                item_com = collected_com[0]
                if not (item_com.get("answer") and item_com.get("contexts")):
                    item_com = None
        except Exception as e:
            click.echo(f" [ERRO: {type(e).__name__}]")
            item_com = None

        # Tentar coletar SEM ontologia
        click.echo(f" SEM ontologia...", nl=False)
        try:
            collected_sem = await collect_api_responses(
                questions=[q],
                api_base_url=api_url,
                timeout=60,
                use_hyde=False,
                use_ontology=False,
            )
            item_sem = None
            if collected_sem and len(collected_sem) > 0:
                item_sem = collected_sem[0]
                if not (item_sem.get("answer") and item_sem.get("contexts")):
                    item_sem = None
        except Exception as e:
            click.echo(f" [ERRO: {type(e).__name__}]")
            item_sem = None

        # Registrar resultado
        if item_com and item_sem:
            responses_com.append(item_com)
            responses_sem.append(item_sem)
            click.echo(f" [OK]\n")
        else:
            reason = []
            if not item_com:
                reason.append("COM")
            if not item_sem:
                reason.append("SEM")
            click.echo(f" [SKIP: {'/'.join(reason)} falhou]\n")
            failed_questions.append({"question_id": question_id, "reason": "/".join(reason)})

    click.echo(f"      [OK] {len(responses_com)} questões válidas em ambas condições\n")

    if failed_questions:
        click.echo(f"      ⚠️  {len(failed_questions)} questões falharam:\n")
        for fail in failed_questions[:5]:
            click.echo(f"         Q{fail['question_id']}: {fail['reason']}")
        if len(failed_questions) > 5:
            click.echo(f"         ... + {len(failed_questions) - 5} mais\n")

    if len(responses_com) == 0:
        _abort("Nenhuma resposta válida coletada em ambas condições!")

    min_count = len(responses_com)  # Ambas têm mesmo tamanho por construção

    _step("5/6", "EVAL", f"AVALIANDO {min_count} questões (concorrência: 5)")

    if evaluators is None:
        evaluators = ["gemini"]

    evaluator = RagasEvaluator(
        openai_llm_model="gpt-4o-mini",
        gemini_model="gemini-2.5-flash-lite",
        claude_model="claude-haiku-4-5-20251001",
        evaluators=evaluators,
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

    actual_evaluators = set()
    for item in eval_com + eval_sem:
        if item.get("results"):
            actual_evaluators.update(item["results"].keys())
    actual_evaluators = sorted(actual_evaluators)

    failed_questions_detail = [
        {
            "question_id": f["question_id"],
            "condition": f["reason"].split("/")[0] if "/" in f["reason"] else f["reason"],
            "stage": "collection",
            "error": f["reason"]
        }
        for f in failed_questions
    ]

    result = {
        "evaluation_run": get_iso_timestamp(),
        "dataset": {
            "file": Path(input_file).name,
            "total_questions": total_available,
            "target_samples": target_samples,
            "seed": seed,
        },
        "evaluators": actual_evaluators,
        "run_config": {
            "selected_questions": selected_questions_file or "from_excel",
            "seed": seed,
            "use_hyde": False,
            "gemini_model": "gemini-2.5-flash-lite",
            "openai_model": "gpt-4o-mini",
            "claude_model": "claude-haiku-4-5-20251001",
        },
        "failed_questions": failed_questions_detail,
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
    selected_questions_file = sys.argv[2] if len(sys.argv) > 2 else None
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 42
    evaluators_str = sys.argv[4] if len(sys.argv) > 4 else "gemini"
    evaluators_list = [e.strip() for e in evaluators_str.split(",")]

    valid_evaluators = {"gpt", "gemini", "claude"}
    invalid = [e for e in evaluators_list if e not in valid_evaluators]
    if invalid:
        click.echo(f"❌ Avaliadores inválidos: {', '.join(invalid)}", err=True)
        click.echo(f"   Válidos: {', '.join(sorted(valid_evaluators))}", err=True)
        sys.exit(1)

    if selected_questions_file:
        target_samples = None
    else:
        target_samples = 30

    asyncio.run(main(input_file=input_file, target_samples=target_samples, seed=seed, selected_questions_file=selected_questions_file, evaluators=evaluators_list))

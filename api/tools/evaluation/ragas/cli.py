from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import click

from .evaluator import collect_api_responses, EvalResult, RagasEvaluator
from .helpers import (
    get_iso_timestamp,
    load_xlsx_dataset,
    save_api_responses,
    save_evaluation_dataset,
    save_evaluation_results,
    ALL_METRICS,
    _GEMINI_BASE_URL,
    check_openai,
    check_gemini,
    check_anthropic,
    step as _step,
    abort as _abort,
    banner as _banner,
)


def _result_to_dict(result: EvalResult) -> dict:
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


def _build_empty_sums(active_evaluators: list[str]) -> dict:
    return {ev: {m: 0.0 for m in ALL_METRICS} for ev in active_evaluators}


def _accumulate(sums: dict, counts: dict, result: EvalResult) -> None:
    for evaluator, metrics in _result_to_dict(result).items():
        for metric, value in metrics.items():
            if value is not None and evaluator in sums:
                sums[evaluator][metric] += value
                counts[evaluator][metric] += 1


def _compute_averages(sums: dict, counts: dict) -> dict:
    avgs: dict = {}
    for ev in sums:
        avgs[ev] = {}
        for metric in ALL_METRICS:
            n = counts[ev][metric]
            avgs[ev][metric] = round(sums[ev][metric] / n, 6) if n > 0 else None
    return avgs


def _print_inline_scores(idx: int, total: int, result: EvalResult, active_evaluators: list[str]) -> None:
    parts = []
    for ev in active_evaluators:
        scores = {
            "F":  result.faithfulness.get(ev),
            "CP": result.context_precision.get(ev),
            "CR": result.context_recall.get(ev),
            "AR": result.answer_relevancy.get(ev),
        }
        vals = "  ".join(
            f"{k}={v:.2f}" if v is not None else f"{k}=n/a"
            for k, v in scores.items()
        )
        parts.append(f"{ev.upper()}[{vals}]")
    click.echo(f"      [{idx:>3}/{total}] {'  '.join(parts)}")


async def _evaluate_item(
    idx: int,
    total: int,
    item: dict,
    evaluator: RagasEvaluator,
    semaphore: asyncio.Semaphore,
    active_evaluators: list[str],
) -> dict:
    question     = item.get("question", "")
    answer_rag   = item.get("answer", "")
    ground_truth = item.get("ground_truth", "")
    contexts     = item.get("contexts", [])
    question_id = item.get("question_id")

    score_item: dict = {
        "question_id":  question_id,
        "question":     question,
        "ground_truth": ground_truth,
        "answer":       answer_rag,
        "contexts":     contexts,
        "results":      {},
        "errors":       [],
    }

    _answer_sanitized = ''.join(
        c for c in answer_rag
        if ord(c) > 8 and ord(c) != 11
        and (ord(c) >= 32 or ord(c) == 9 or ord(c) == 10 or ord(c) == 13)
        and ord(c) != 127
    ).strip()

    if len(_answer_sanitized) < 50:
        msg = f"resposta corrompida/truncada ({len(_answer_sanitized)} chars após sanitização)"
        score_item["errors"].append(msg)
        click.echo(f"      [{idx:>3}/{total}] [SKIP] question_id={question_id} | {msg}", err=True)
        click.echo(f"              PERGUNTA: {question}", err=True)
        click.echo(f"              RESPOSTA: {answer_rag[:100]}...", err=True)
        return score_item

    async with semaphore:
        click.echo(f"      [{idx:>3}/{total}] question_id={question_id} | iniciando... ({question[:60].strip()})")
        try:
            result: EvalResult = await evaluator.evaluate_all(
                question=question, answer=_answer_sanitized,
                contexts=contexts, ground_truth=ground_truth,
                log_prefix=f"      [{idx:>3}/{total}]",
            )
            score_item["results"] = _result_to_dict(result)
            _print_inline_scores(idx, total, result, active_evaluators)
        except Exception as e:
            import traceback
            msg = f"{type(e).__name__}: {e}"
            score_item["errors"].append(msg)
            click.echo(f"      [{idx:>3}/{total}] [ERRO] question_id={question_id}", err=True)
            click.echo(f"              PERGUNTA: {question}", err=True)
            click.echo(f"              ERRO: {msg}", err=True)
            click.echo(traceback.format_exc(), err=True)

    return score_item


async def _evaluate_all_concurrent(
    valid_responses: list[dict],
    evaluator: RagasEvaluator,
    concurrency: int,
    output_dir: str,
    evaluation_results: dict,
    openai_model: str,
    gemini_model: str,
    active_evaluators: list[str],
) -> tuple[list[dict], dict, dict]:
    semaphore = asyncio.Semaphore(concurrency)
    total = len(valid_responses)

    tasks = [
        _evaluate_item(idx, total, item, evaluator, semaphore, active_evaluators)
        for idx, item in enumerate(valid_responses, 1)
    ]

    sums   = _build_empty_sums(active_evaluators)
    counts = {ev: {m: 0 for m in ALL_METRICS} for ev in active_evaluators}
    scores_list: list[dict] = []

    completed = 0

    for coro in asyncio.as_completed(tasks):
        score_item = await coro
        scores_list.append(score_item)
        completed += 1

        if score_item["results"]:
            result_obj = EvalResult(
                faithfulness          = {ev: score_item["results"][ev]["faithfulness"]          for ev in score_item["results"]},
                answer_relevancy      = {ev: score_item["results"][ev]["answer_relevancy"]      for ev in score_item["results"]},
                context_precision     = {ev: score_item["results"][ev]["context_precision"]     for ev in score_item["results"]},
                context_recall        = {ev: score_item["results"][ev]["context_recall"]        for ev in score_item["results"]},
                context_entity_recall = {ev: score_item["results"][ev]["context_entity_recall"] for ev in score_item["results"]},
            )
            _accumulate(sums, counts, result_obj)
        elif score_item["errors"]:
            click.echo(f"      [{score_item['question_id']:>3}/{total}] [FALHOU] {score_item['errors'][0]}", err=True)

    scores_list.sort(key=lambda x: x.get("question_id") or 0)
    return scores_list, sums, counts


async def _validate_apis(
    openai_key: str,
    gemini_key: str,
    openai_model: str,
    gemini_model: str,
    claude_model: str,
    active_evaluators: list[str],
) -> bool:
    _step("0/6", "VALIDATE", "VALIDANDO CREDENCIAIS DE API")

    checks = []

    if "gpt" in active_evaluators:
        click.echo(f"  OpenAI ({openai_model})... ", nl=False)
        ok = await check_openai(openai_key, openai_model)
        click.echo("✅" if ok else "❌")
        checks.append(ok)

    if "gemini" in active_evaluators:
        click.echo(f"  Gemini ({gemini_model})... ", nl=False)
        ok = await check_gemini(gemini_key, gemini_model)
        click.echo("✅" if ok else "❌")
        checks.append(ok)

    if "claude" in active_evaluators:
        claude_key = os.getenv("ANTHROPIC_API_KEY")
        click.echo(f"  Claude ({claude_model})... ", nl=False)
        ok = await check_anthropic(claude_key, claude_model)
        click.echo("✅" if ok else "❌")
        checks.append(ok)

    click.echo()
    return all(checks)


@click.group()
def cli():
    pass


@cli.command()
@click.option("--input-file", type=click.Path(exists=True),
              default="api/tools/data/raw/evaluation/dataset.xlsx")
@click.option("--max-samples", type=int, default=None,
              help="Amostras aleatórias do dataset. None = todas.")
@click.option("--api-url", type=str, default="http://localhost:8000")
@click.option("--api-timeout", type=int, default=30)
@click.option("--jwt-token", type=str, default=None)
@click.option("--openai-model", type=str, default="gpt-4o-mini")
@click.option("--gemini-model", type=str, default="gemini-2.5-flash-lite")
@click.option("--claude-model", type=str, default="claude-haiku-4-5-20251001")
@click.option("--ollama-model", type=str, default=None,
              help=f"Modelo Ollama local para avaliação. (padrão: {os.getenv('SLM_MODEL', 'mistral')})")
@click.option("--ollama-base-url", type=str, default=None,
              help=f"Base URL do servidor Ollama. (padrão: {os.getenv('SLM_BASE_URL', 'http://localhost:11434')}/v1)")
@click.option("--evaluators", type=str, default="gpt,gemini,claude",
              help="Avaliadores separados por vírgula: gpt,gemini,claude,ollama")
@click.option("--seed", type=int, default=None, help="Semente para amostragem reprodutível")
@click.option("--output-dir", type=click.Path(), default="api/tools/data/processed/evaluation")
@click.option("--concurrency", type=int, default=5,
              help="Itens avaliados em paralelo. Aumentar acelera, mas pode atingir rate limits.")
@click.option("--skip-api-check", is_flag=True, default=False)
@click.option("--use-hyde", is_flag=True, default=False,
              help="Habilita HyDE ensemble no retrieval. Padrão: desabilitado.")
@click.option("--use-ontology", is_flag=True, default=False,
              help="Habilita expansão ontológica de queries. Padrão: desabilitado.")
def pipeline(
    input_file, max_samples, api_url, api_timeout,
    jwt_token, openai_model, gemini_model, claude_model,
    ollama_model, ollama_base_url,
    evaluators, seed, output_dir,
    concurrency, skip_api_check, use_hyde, use_ontology,
):
    evaluators_list = [e.strip() for e in evaluators.split(",")]
    SLM_MODEL = ollama_model or os.getenv("SLM_MODEL", "mistral")
    SLM_BASE_URL = ollama_base_url or os.getenv("SLM_BASE_URL", "http://localhost:11434")
    asyncio.run(_run_pipeline(
        input_file=input_file, max_samples=max_samples,
        api_url=api_url, api_timeout=api_timeout, jwt_token=jwt_token,
        openai_model=openai_model, gemini_model=gemini_model, claude_model=claude_model,
        SLM_MODEL=SLM_MODEL, SLM_BASE_URL=SLM_BASE_URL,
        evaluators=evaluators_list, seed=seed,
        output_dir=output_dir, concurrency=concurrency,
        skip_api_check=skip_api_check, use_hyde=use_hyde, use_ontology=use_ontology,
    ))


async def _run_pipeline(
    input_file, max_samples, api_url, api_timeout,
    jwt_token, openai_model, gemini_model, claude_model,
    SLM_MODEL, SLM_BASE_URL,
    evaluators, seed, output_dir,
    concurrency, skip_api_check, use_hyde: bool = False, use_ontology: bool = False,
) -> None:

    _banner("PIPELINE RAGAS: VALIDACAO > DATASET > API > AVALIACAO")

    if not skip_api_check:
        openai_key = os.getenv("OPENAI_API_KEY")
        gemini_key = os.getenv("GEMINI_API_KEY")
        ok = await _validate_apis(openai_key, gemini_key, openai_model, gemini_model, claude_model, active_evaluators=evaluators)
        if not ok:
            _abort("Corrija as chaves de API antes de continuar.")

    _step("1/6", "LOAD", "CARREGANDO DATASET")
    click.echo(f"      Arquivo: {input_file}")
    if seed is not None:
        import random as _random
        _random.seed(seed)
        click.echo(f"      Semente aleatória: {seed}")
    if max_samples:
        click.echo(f"      Amostras aleatórias: {max_samples}")
    try:
        questions = load_xlsx_dataset(input_file, max_samples=max_samples)
        click.echo(f"      [OK] {len(questions)} questões carregadas\n")
    except Exception as e:
        _abort(f"Erro ao carregar dataset: {e}")

    _step("2/6", "SAVE", "SALVANDO DATASET EM JSON")
    try:
        dataset_file = save_evaluation_dataset(questions, output_dir)
        click.echo(f"      [OK] {Path(dataset_file).name}\n")
    except Exception as e:
        click.echo(f"      [AVISO] {e}\n", err=True)

    _step("3/6", "COLLECT", f"COLETANDO RESPOSTAS DA API — {api_url} (use_hyde={use_hyde}, use_ontology={use_ontology})")
    try:
        collected = await collect_api_responses(
            questions=questions, api_base_url=api_url,
            jwt_token=jwt_token, timeout=api_timeout,
            use_hyde=use_hyde, use_ontology=use_ontology,
        )
        valid_responses = [r for r in collected if r.get("answer") is not None]
        click.echo(f"      [OK] {len(valid_responses)}/{len(collected)} respostas válidas\n")
    except Exception as e:
        _abort(f"Erro ao coletar respostas: {e}")

    if not valid_responses:
        _abort("Nenhuma resposta válida coletada.")

    _step("4/6", "SAVE", "SALVANDO RESPOSTAS DA API")
    try:
        api_file = save_api_responses(valid_responses, output_dir)
        click.echo(f"      [OK] {Path(api_file).name}\n")
    except Exception as e:
        click.echo(f"      [AVISO] {e}\n", err=True)

    active_evaluators = [e for e in evaluators if e in ("gpt", "gemini", "claude", "ollama")]

    _step("5/6", "EVAL",
          f"AVALIANDO {len(valid_responses)} ITENS "
          f"(avaliadores: {', '.join(active_evaluators)}, concorrência: {concurrency})")

    evaluator = RagasEvaluator(
        openai_llm_model=openai_model,
        gemini_model=gemini_model,
        claude_model=claude_model,
        SLM_MODEL=SLM_MODEL,
        SLM_BASE_URL=SLM_BASE_URL,
        evaluators=active_evaluators,
    )

    evaluation_results: dict = {
        "generated_at": get_iso_timestamp(),
        "sample_count": len(valid_responses),
        "models": {
            "gpt":    openai_model,
            "gemini": gemini_model,
            "claude": claude_model,
            "ollama": SLM_MODEL,
        },
        "evaluators": active_evaluators,
        "seed":       seed,
        "use_hyde":   use_hyde,
        "use_ontology": use_ontology,
        "metrics":    ALL_METRICS,
        "summary":    {},
        "scores":     [],
    }

    scores_list, sums, counts = await _evaluate_all_concurrent(
        valid_responses=valid_responses,
        evaluator=evaluator,
        concurrency=concurrency,
        output_dir=output_dir,
        evaluation_results=evaluation_results,
        openai_model=openai_model,
        gemini_model=gemini_model,
        active_evaluators=active_evaluators,
    )

    click.echo("\n")

    _step("6/6", "SAVE", "SALVANDO RESULTADOS")
    evaluation_results["scores"]  = scores_list
    evaluation_results["summary"] = _compute_averages(sums, counts)

    try:
        result_file = save_evaluation_results(evaluation_results, output_dir)
        click.echo(f"      [OK] {Path(result_file).name}\n")
    except Exception as e:
        _abort(f"Erro ao salvar resultados: {e}")

    _banner("RESUMO DO PIPELINE")
    click.echo(f"  Dataset:      {len(questions)} questões")
    click.echo(f"  Respostas:    {len(valid_responses)} válidas")
    click.echo(f"  HyDE:         {'habilitado' if use_hyde else 'desabilitado'}")
    click.echo(f"  Avaliadores:  {', '.join(active_evaluators)}")
    click.echo(f"  Concorrência: {concurrency} itens simultâneos\n")

    summary  = evaluation_results["summary"]
    col_w    = 26
    ev_cols  = "  ".join(f"{ev.upper():>10}" for ev in active_evaluators)
    click.echo(f"  {'Métrica':<{col_w}}  {ev_cols}")
    click.echo("  " + "-" * (col_w + 12 * len(active_evaluators)))

    for metric in ALL_METRICS:
        vals = []
        for ev in active_evaluators:
            v = summary.get(ev, {}).get(metric)
            vals.append(f"{v:.4f}" if v is not None else "  n/a  ")
        vals_str = "  ".join(f"{v:>10}" for v in vals)
        click.echo(f"  {metric:<{col_w}}  {vals_str}")

    click.echo()
    _banner("PIPELINE CONCLUÍDO COM SUCESSO")


@cli.command()
@click.option("--input-file", type=click.Path(exists=True), required=True)
@click.option("--max-samples", type=int, default=None)
@click.option("--output-dir", type=click.Path(), default="api/tools/data/processed/evaluation")
def prepare_dataset(input_file, max_samples, output_dir):
    click.echo(f"[LOAD] Carregando {input_file}...")
    questions = load_xlsx_dataset(input_file, max_samples=max_samples)
    click.echo(f"[OK]   {len(questions)} questões carregadas")
    dataset_file = save_evaluation_dataset(questions, output_dir)
    click.echo(f"[SAVE] {Path(dataset_file).name}")


if __name__ == "__main__":
    cli()

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path

import click
import httpx

try:
    from dotenv import load_dotenv
    _env = Path(__file__).parent.parent / ".env"
    if _env.exists():
        load_dotenv(_env)
except ImportError:
    pass

from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.embeddings.base import embedding_factory
from ragas.metrics.collections import (
    AnswerRelevancy,
    ContextEntityRecall,
    ContextPrecision,
    ContextRecall,
    Faithfulness,
)

from ragas_evaluation._cli_helpers import (
    ALL_METRICS,
    _GEMINI_BASE_URL,
    check_openai as _check_openai,
    check_gemini as _check_gemini,
    step as _step,
    abort as _abort,
    banner as _banner,
)

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
INPUT_FILE = Path(__file__).parent / "data" / "output" / "ragas_evaluation_30.json"
OUTPUT_DIR = Path(__file__).parent / "data" / "output" / "ablation"


def _sanitize(text: str) -> str:
    return _CONTROL_CHARS_RE.sub("", text).strip()


def _extract_value(result) -> float | None:
    if result is None:
        return None
    if hasattr(result, "value"):
        return result.value
    try:
        return float(result)
    except (TypeError, ValueError):
        return None


def _avg(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 4) if clean else None


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _build_evaluator(
    evaluator: str,
    openai_model: str,
    gemini_model: str,
) -> dict:
    _oai_key    = os.getenv("OPENAI_API_KEY")
    _oai_client = AsyncOpenAI(api_key=_oai_key)

    try:
        _emb = embedding_factory(
            "huggingface",
            model="neuralmind/bert-base-portuguese-cased",
        )
    except Exception:
        _emb = embedding_factory(
            "openai", model="text-embedding-3-small", client=_oai_client,
        )

    if evaluator == "gpt":
        _llm = llm_factory(openai_model, client=_oai_client, max_tokens=4096)
    elif evaluator == "gemini":
        _gem_key    = os.getenv("GEMINI_API_KEY")
        _gem_client = AsyncOpenAI(api_key=_gem_key, base_url=_GEMINI_BASE_URL)
        _llm        = llm_factory(gemini_model, client=_gem_client, max_tokens=4096)
    else:
        raise ValueError(f"Avaliador '{evaluator}' não suportado. Use: gpt, gemini")

    return {
        "faithfulness":          Faithfulness(llm=_llm),
        "answer_relevancy":      AnswerRelevancy(llm=_llm, embeddings=_emb),
        "context_precision":     ContextPrecision(llm=_llm),
        "context_recall":        ContextRecall(llm=_llm),
        "context_entity_recall": ContextEntityRecall(llm=_llm),
    }

async def _collect_answer(
    client: httpx.AsyncClient,
    api_url: str,
    question: str,
    jwt_token: str | None,
    use_hyde: bool,
    timeout: int,
) -> str:
    headers = {"Content-Type": "application/json"}
    if jwt_token:
        headers["Authorization"] = f"Bearer {jwt_token}"

    payload = {
        "conversation_id": "ablation-test",
        "question":        question,
        "history":         [],
        "use_hyde":        use_hyde,
    }

    try:
        async with client.stream(
            "POST", f"{api_url}/chat",
            json=payload, headers=headers, timeout=timeout,
        ) as response:
            response.raise_for_status()
            chunks = []
            async for chunk in response.aiter_text():
                chunks.append(chunk)
            return "".join(chunks).strip()
    except Exception as e:
        return f"[ERRO NA COLETA: {e}]"

async def _evaluate_item(
    metrics: dict,
    question: str,
    answer: str,
    contexts: list[str],
    ground_truth: str,
) -> dict[str, float | None]:
    results: dict[str, float | None] = {}

    async def _score(name: str, **kwargs) -> None:
        try:
            raw = await metrics[name].ascore(**kwargs)
            results[name] = _extract_value(raw)
        except Exception as e:
            click.echo(f"    [AVISO] {name}: {e}", err=True)
            results[name] = None

    await _score("faithfulness",
                 user_input=question, response=answer, retrieved_contexts=contexts)
    await _score("answer_relevancy",
                 user_input=question, response=answer)
    await _score("context_precision",
                 user_input=question, reference=ground_truth, retrieved_contexts=contexts)
    await _score("context_recall",
                 user_input=question, retrieved_contexts=contexts, reference=ground_truth)
    await _score("context_entity_recall",
                 reference=ground_truth, retrieved_contexts=contexts)

    return results

def _print_comparison(
    old_scores: list[dict],
    new_scores: list[dict],
    evaluator: str,
) -> None:
    _banner("ABLATION STUDY: PROMPT MONOLÍTICO vs. PROMPT MODULAR")
    click.echo(f"  Avaliador : {evaluator.upper()}")
    click.echo(f"  Amostras  : {len(old_scores)}\n")

    col = 26
    click.echo(f"  {'Métrica':<{col}}  {'Antigo':>10}  {'Novo':>10}  {'Delta':>10}")
    click.echo("  " + "-" * (col + 36))

    for metric in ALL_METRICS:
        old_avg = _avg([s.get(metric) for s in old_scores])
        new_avg = _avg([s.get(metric) for s in new_scores])

        if old_avg is not None and new_avg is not None:
            delta = new_avg - old_avg
            flag  = "↑" if delta > 0.01 else ("↓" if delta < -0.01 else "→")
            click.echo(
                f"  {metric:<{col}}  {old_avg:>10.4f}  {new_avg:>10.4f}  "
                f"{delta:>+10.4f} {flag}"
            )
        else:
            click.echo(f"  {metric:<{col}}  {'n/a':>10}  {'n/a':>10}  {'n/a':>10}")

    click.echo()

@click.group()
def cli():
    pass


@cli.command()
@click.option("--api-url",      default="http://localhost:8000", show_default=True)
@click.option("--jwt-token",    default=None,    help="Bearer token para autenticação")
@click.option("--use-hyde",     is_flag=True,    default=True,  show_default=True)
@click.option("--timeout",      default=60,      show_default=True)
@click.option("--evaluator",    default="gemini",
              type=click.Choice(["gpt", "gemini"]), show_default=True,
              help="Avaliador RAGAS a usar")
@click.option("--openai-model", default="gpt-4o-mini",         show_default=True)
@click.option("--gemini-model", default="gemini-2.5-flash-lite", show_default=True)
@click.option("--skip-api-check", is_flag=True, default=False)
def pipeline(
    api_url: str,
    jwt_token: str | None,
    use_hyde: bool,
    timeout: int,
    evaluator: str,
    openai_model: str,
    gemini_model: str,
    skip_api_check: bool,
) -> None:
    asyncio.run(_run_pipeline(
        api_url=api_url, jwt_token=jwt_token, use_hyde=use_hyde,
        timeout=timeout, evaluator=evaluator,
        openai_model=openai_model, gemini_model=gemini_model,
        skip_api_check=skip_api_check,
    ))


async def _run_pipeline(
    api_url: str,
    jwt_token: str | None,
    use_hyde: bool,
    timeout: int,
    evaluator: str,
    openai_model: str,
    gemini_model: str,
    skip_api_check: bool,
) -> None:
    _banner("ABLATION STUDY: COLETA + AVALIAÇÃO")

    if not skip_api_check:
        _step("1/4", "CHECK", f"Verificando avaliador: {evaluator.upper()}")
        if evaluator == "gpt":
            ok = await _check_openai(os.getenv("OPENAI_API_KEY"), openai_model)
        else:
            ok = await _check_gemini(os.getenv("GEMINI_API_KEY"), gemini_model)
        if not ok:
            _abort(f"Avaliador {evaluator.upper()} indisponível. Use --skip-api-check para ignorar.")
    else:
        _step("1/4", "CHECK", "Verificação de API ignorada (--skip-api-check)")

    _step("2/4", "LOAD", f"Carregando {INPUT_FILE.name}")
    with open(INPUT_FILE, encoding="utf-8") as f:
        data = json.load(f)
    dataset = data["scores"][:30]
    click.echo(f"      [OK] {len(dataset)} pares carregados\n")

    old_scores = [item.get("results", {}).get(evaluator, {}) for item in dataset]

    _step("3/4", "EVAL", f"Iniciando avaliador {evaluator.upper()} ({openai_model if evaluator == 'gpt' else gemini_model})")
    metrics    = _build_evaluator(evaluator, openai_model, gemini_model)
    new_scores = []
    results    = []

    async with httpx.AsyncClient() as http_client:
        for idx, item in enumerate(dataset, 1):
            question     = _sanitize(item["question"])
            ground_truth = _sanitize(item.get("ground_truth", ""))
            contexts     = [_sanitize(c) for c in item.get("contexts", [])]

            click.echo(f"      [{idx:>2}/30] Coletando: {question[:55]}...")
            new_answer = await _collect_answer(
                client=http_client, api_url=api_url,
                question=question, jwt_token=jwt_token,
                use_hyde=use_hyde, timeout=timeout,
            )

            click.echo(f"      [{idx:>2}/30] Avaliando com {evaluator.upper()}...")
            scores = await _evaluate_item(
                metrics=metrics,
                question=question, answer=new_answer,
                contexts=contexts, ground_truth=ground_truth,
            )

            for name, val in scores.items():
                v = f"{val:.4f}" if val is not None else "None"
                click.echo(f"               {name:<26}: {v}")

            new_scores.append(scores)
            results.append({
                "question_id":  item.get("question_id", idx),
                "question":     question,
                "old_answer":   item.get("answer", ""),
                "new_answer":   new_answer,
                "ground_truth": ground_truth,
                "old_scores":   old_scores[idx - 1],
                "new_scores":   scores,
            })

            if idx % 5 == 0:
                _save(
                    OUTPUT_DIR / "ablation_checkpoint.json",
                    {"results": results, "metrics": ALL_METRICS, "evaluator": evaluator},
                )
                click.echo(f"      → checkpoint salvo ({idx} itens)\n")

    _step("4/4", "SAVE", "Salvando resultados")
    ts          = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = OUTPUT_DIR / f"ablation_{evaluator}_{ts}.json"
    _save(output_file, {
        "generated_at": datetime.now().isoformat(),
        "evaluator":    evaluator,
        "model":        openai_model if evaluator == "gpt" else gemini_model,
        "prompt_old":   "question_init_monolitico",
        "prompt_new":   "question_init_modular",
        "sample_count": len(results),
        "metrics":      ALL_METRICS,
        "results":      results,
        "summary": {
            "old": {m: _avg([s.get(m) for s in old_scores]) for m in ALL_METRICS},
            "new": {m: _avg([s.get(m) for s in new_scores]) for m in ALL_METRICS},
        },
    })
    click.echo(f"      [OK] {output_file.name}\n")

    _print_comparison(old_scores, new_scores, evaluator)


if __name__ == "__main__":
    cli()
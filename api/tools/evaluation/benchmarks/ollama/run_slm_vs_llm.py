from __future__ import annotations

import json
from pathlib import Path

import click
import numpy as np
from scipy.stats import pearsonr

INPUT_30   = Path("ragas_evaluation/data/output/ragas_evaluation_30.json")
METRICS    = [
    "faithfulness", "answer_relevancy",
    "context_precision", "context_recall", "context_entity_recall",
]
API_EVALUATORS = ["gemini", "claude", "gpt"]


def _avg(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 4) if clean else None


def _pearson(a: list, b: list) -> tuple[float, float, int]:
    pairs = [
        (x, y) for x, y in zip(a, b)
        if x is not None and y is not None
        and not (isinstance(x, float) and np.isnan(x))
        and not (isinstance(y, float) and np.isnan(y))
    ]
    if len(pairs) < 5:
        return float("nan"), float("nan"), len(pairs)
    xs, ys = zip(*pairs)
    r, p = pearsonr(list(xs), list(ys))
    return float(r), float(p), len(pairs)


def _load_ollama(path: Path) -> dict[str, dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {
        str(s["question_id"]): s["ollama"]
        for s in data["scores"]
    }


def _load_api(path: Path) -> dict[str, dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {
        str(s["question_id"]): s.get("results", {})
        for s in data["scores"]
    }


def _print_summary_table(ollama: dict, api: dict) -> None:
    col = 26
    header = f"  {'Métrica':<{col}}"
    header += "  " + "  ".join(f"{'OLLAMA':>8}") 
    for ev in API_EVALUATORS:
        header += f"  {ev.upper():>8}"
    click.echo(header)
    click.echo("  " + "-" * (col + 10 * (1 + len(API_EVALUATORS))))

    for metric in METRICS:
        ollama_vals = [v.get(metric) for v in ollama.values()]
        ollama_avg  = _avg(ollama_vals)

        row = f"  {metric:<{col}}  {ollama_avg:>8.4f}" if ollama_avg is not None else f"  {metric:<{col}}  {'n/a':>8}"

        for ev in API_EVALUATORS:
            ev_vals = [
                r.get(ev, {}).get(metric)
                for r in api.values()
                if isinstance(r.get(ev), dict)
            ]
            ev_avg = _avg(ev_vals)
            row += f"  {ev_avg:>8.4f}" if ev_avg is not None else f"  {'n/a':>8}"

        click.echo(row)


def _print_correlation_table(ollama: dict, api: dict) -> None:
    col = 26
    click.echo(f"\n  {'Métrica':<{col}}", nl=False)
    for ev in API_EVALUATORS:
        click.echo(f"  {f'r vs {ev}':>14}", nl=False)
    click.echo()
    click.echo("  " + "-" * (col + 16 * len(API_EVALUATORS)))

    for metric in METRICS:
        ollama_vals = [ollama.get(qid, {}).get(metric) for qid in ollama]
        row = f"  {metric:<{col}}"

        for ev in API_EVALUATORS:
            ev_vals = [
                api.get(qid, {}).get(ev, {}).get(metric)
                if isinstance(api.get(qid, {}).get(ev), dict) else None
                for qid in ollama
            ]
            r, p, n = _pearson(ollama_vals, ev_vals)
            if np.isnan(r):
                row += f"  {'n/a (n<5)':>14}"
            else:
                flag = "✓FORTE" if r >= 0.7 else ("~MOD" if r >= 0.4 else "✗FRACO")
                row += f"  {r:>6.4f} {flag}"

        click.echo(row)


def _print_interpretation(ollama: dict, api: dict) -> None:
    click.echo("\n── Interpretação ────────────────────────────────────────")

    for ev in API_EVALUATORS:
        rs = []
        for metric in METRICS:
            ollama_vals = [ollama.get(qid, {}).get(metric) for qid in ollama]
            ev_vals     = [
                api.get(qid, {}).get(ev, {}).get(metric)
                if isinstance(api.get(qid, {}).get(ev), dict) else None
                for qid in ollama
            ]
            r, _, n = _pearson(ollama_vals, ev_vals)
            if not np.isnan(r):
                rs.append(r)

        if rs:
            avg_r = np.mean(rs)
            verdict = (
                "substituto viável para avaliação em escala"
                if avg_r >= 0.7 else
                "correlação moderada — usar com cautela"
                if avg_r >= 0.4 else
                "correlação fraca — não recomendado como substituto"
            )
            click.echo(f"  Ollama vs {ev.upper():6s}: r médio = {avg_r:.4f} → {verdict}")


@click.command()
@click.option(
    "--ollama-file", "ollama_file", required=True,
    type=click.Path(exists=True),
    help="JSON gerado pelo run_ollama_30.py",
)
def main(ollama_file: str) -> None:
    ollama = _load_ollama(Path(ollama_file))
    api    = _load_api(INPUT_30)

    click.echo("\n" + "=" * 70)
    click.echo("SLM vs LLM — CORRELAÇÃO DE AVALIADORES")
    click.echo(f"SLM: qwen2.5:7b (Ollama local) | LLM: GPT, Gemini, Claude | n={len(ollama)}")
    click.echo("=" * 70)

    click.echo("\n── Scores médios por avaliador ──────────────────────────")
    _print_summary_table(ollama, api)

    click.echo("\n── Correlação de Pearson (Ollama vs APIs) ───────────────")
    _print_correlation_table(ollama, api)

    _print_interpretation(ollama, api)

    click.echo("\n" + "=" * 70)


if __name__ == "__main__":
    main()
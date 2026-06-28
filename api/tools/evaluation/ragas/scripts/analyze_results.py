import json
from pathlib import Path
from typing import Any

import click


def load_results(file_path: str) -> dict[str, Any]:
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def print_summary(results: dict[str, Any]):
    click.echo("\n" + "=" * 70)
    click.echo("📊 RESUMO GERAL")
    click.echo("=" * 70)
    click.echo(f"Data: {results.get('generated_at', 'N/A')}")
    click.echo(f"Amostras avaliadas: {results.get('sample_count', 0)}")
    click.echo(f"Métricas: {', '.join(results.get('metrics', []))}")

    click.echo("\n📈 MÉDIAS POR AVALIADOR:")
    for evaluator, metrics in results.get("summary", {}).items():
        click.echo(f"\n  {evaluator.upper()}:")
        for metric, value in metrics.items():
            bar = "█" * int(value * 20) + "░" * (20 - int(value * 20))
            click.echo(f"    • {metric:20s}: [{bar}] {value:.4f}")


def print_detailed_scores(results: dict[str, Any], limit: int = 5):
    scores = results.get("scores", [])[:limit]
    
    if not scores:
        click.echo("❌ Nenhum score encontrado")
        return

    click.echo("\n" + "=" * 70)
    click.echo(f"📋 DETALHES DAS {len(scores)} PRIMEIRAS QUESTÕES")
    click.echo("=" * 70)

    for idx, score in enumerate(scores, 1):
        click.echo(f"\n[{idx}] Pergunta ID: {score.get('question_id')}")
        click.echo(f"    Q: {score.get('question', '')[:60]}...")
        
        results_data = score.get("results", {})
        for evaluator, metrics in results_data.items():
            click.echo(f"    \n    {evaluator.upper()}:")
            for metric, value in metrics.items():
                click.echo(f"      • {metric:20s}: {value:.4f}")


def print_comparison(results: dict[str, Any]):
    summary = results.get("summary", {})
    
    if len(summary) < 2:
        click.echo("⚠️  Necessário no mínimo 2 avaliadores para comparação")
        return

    click.echo("\n" + "=" * 70)
    click.echo("🔍 COMPARAÇÃO ENTRE AVALIADORES")
    click.echo("=" * 70)

    evaluators = list(summary.keys())
    for metric in results.get("metrics", []):
        click.echo(f"\n{metric.upper()}:")
        values = [summary[e].get(metric, 0) for e in evaluators]
        for evaluator, value in zip(evaluators, values):
            diff = ""
            if len(evaluators) > 1:
                avg = sum(v for v in values) / len(values)
                diff = f" (Δ {value - avg:+.4f})"
            click.echo(f"  • {evaluator:10s}: {value:.4f}{diff}")


def print_quality_assessment(results: dict[str, Any], thresholds: dict[str, float] | None = None):
    if thresholds is None:
        thresholds = {
            "faithfulness": 0.7,
            "answer_relevancy": 0.6,
            "context_precision": 0.75,
            "context_recall": 0.65,
        }

    click.echo("\n" + "=" * 70)
    click.echo("✅ AVALIAÇÃO DE QUALIDADE")
    click.echo("=" * 70)

    summary = results.get("summary", {})
    for evaluator, metrics in summary.items():
        click.echo(f"\n{evaluator.upper()}:")
        all_pass = True
        for metric, value in metrics.items():
            threshold = thresholds.get(metric, 0.5)
            status = "✅" if value >= threshold else "❌"
            gap = value - threshold
            click.echo(f"  {status} {metric:20s}: {value:.4f} (limiar: {threshold:.4f}) [Δ {gap:+.4f}]")
            if value < threshold:
                all_pass = False

        if all_pass:
            click.echo(f"  → {evaluator.upper()} PASSOU NA QUALIDADE ✨")
        else:
            click.echo(f"  → {evaluator.upper()} FALHOU EM ALGUNS CRITÉRIOS")


@click.group()
def cli():
    pass


@cli.command()
@click.argument("results_file", type=click.Path(exists=True))
@click.option("--limit", type=int, default=5, help="Número de questões detalhadas a exibir")
@click.option("--thresholds", type=str, default=None, help="Arquivo JSON com limiares customizados")
def analyze(results_file: str, limit: int, thresholds: str | None):
    click.echo(f"📂 Carregando {results_file}...")
    results = load_results(results_file)

    custom_thresholds = None
    if thresholds:
        with open(thresholds, "r") as f:
            custom_thresholds = json.load(f)

    print_summary(results)
    print_detailed_scores(results, limit=limit)
    print_comparison(results)
    print_quality_assessment(results, thresholds=custom_thresholds)

    click.echo("\n" + "=" * 70)


@cli.command()
@click.argument("output_dir", type=click.Path())
def latest(output_dir: str):
    latest_file = Path(output_dir) / "ragas_evaluation_latest.json"
    
    if not latest_file.exists():
        click.echo(f"❌ Arquivo não encontrado: {latest_file}")
        return

    click.echo(f"📂 Analisando resultado mais recente...")
    results = load_results(str(latest_file))
    print_summary(results)
    print_detailed_scores(results, limit=5)
    print_comparison(results)
    print_quality_assessment(results)


@cli.command()
@click.argument("results_file", type=click.Path(exists=True))
@click.argument("output_file", type=click.Path())
def export(results_file: str, output_file: str):
    import csv

    results = load_results(results_file)
    scores = results.get("scores", [])

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = None
        for score in scores:
            if writer is None:
                headers = ["question_id", "question", "ground_truth"]
                for evaluator, metrics in score.get("results", {}).items():
                    for metric in metrics.keys():
                        headers.append(f"{evaluator}_{metric}")
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()

            row = {
                "question_id": score.get("question_id"),
                "question": score.get("question", "")[:100],
                "ground_truth": score.get("ground_truth", "")[:100],
            }
            for evaluator, metrics in score.get("results", {}).items():
                for metric, value in metrics.items():
                    row[f"{evaluator}_{metric}"] = value
            writer.writerow(row)

    click.echo(f"✅ Exportado para {output_file}")


if __name__ == "__main__":
    cli()

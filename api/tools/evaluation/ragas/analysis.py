from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import click
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns


sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (14, 8)
plt.rcParams["font.size"] = 10


def load_results(file_path: str) -> dict[str, Any]:
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_dataframe(data_file: Path) -> tuple[pd.DataFrame, list[str], list[str]]:
    with open(data_file, "r", encoding="utf-8") as f:
        raw = json.load(f)

    metrics: list[str] = raw["metrics"]
    evaluators: list[str] = raw["evaluators"]

    records = []
    for score in raw["scores"]:
        row: dict = {"question_id": score["question_id"]}
        for ev in ["gpt", "gemini", "claude"]:
            if ev in score.get("results", {}):
                for metric in metrics:
                    row[f"{ev}_{metric}"] = score["results"][ev].get(metric)
        records.append(row)

    return pd.DataFrame(records), metrics, evaluators


def plot_histograms(df: pd.DataFrame, metrics: list[str], evaluators: list[str], output_dir: Path) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    fig.suptitle(f"Distribuição de Scores por Métrica ({len(df)} amostras)", fontsize=16, fontweight="bold")
    axes_flat = axes.flatten()

    for idx, metric in enumerate(metrics):
        ax = axes_flat[idx]
        values = []
        for ev in evaluators:
            col = f"{ev}_{metric}"
            if col in df.columns:
                values.extend(df[col].dropna().values)

        ax.hist(values, bins=30, alpha=0.7, color="steelblue", edgecolor="black")
        ax.set_xlabel("Score")
        ax.set_ylabel("Frequência")
        ax.set_title(metric.replace("_", " ").title())
        ax.grid(axis="y", alpha=0.3)

        mean_val = np.mean(values)
        median_val = np.median(values)
        ax.axvline(mean_val, color="red", linestyle="--", linewidth=2, label=f"Média: {mean_val:.3f}")
        ax.axvline(median_val, color="green", linestyle="--", linewidth=2, label=f"Mediana: {median_val:.3f}")
        ax.legend()

    axes_flat[-1].remove()
    plt.tight_layout()
    path = output_dir / "01_histogramas_metricas.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"[OK] Salvo: {path.name}")


def plot_scatter_precision_faithfulness(df: pd.DataFrame, output_dir: Path) -> None:
    mask = df["gemini_context_precision"].notna() & df["gemini_faithfulness"].notna()
    x_data = df.loc[mask, "gemini_context_precision"]
    y_data = df.loc[mask, "gemini_faithfulness"]

    fig, ax = plt.subplots(figsize=(12, 8))
    ax.scatter(x_data, y_data, alpha=0.5, s=50, color="steelblue", edgecolor="black", linewidth=0.5)

    z = np.polyfit(x_data, y_data, 1)
    x_line = np.linspace(x_data.min(), x_data.max(), 100)
    ax.plot(x_line, np.poly1d(z)(x_line), "r--", linewidth=2,
            label=f"Regressão linear: y={z[0]:.3f}x+{z[1]:.3f}")

    r = x_data.corr(y_data)
    ax.text(0.05, 0.95, f"Correlação de Pearson: r = {r:.4f}\nN = {len(x_data)}",
            transform=ax.transAxes, fontsize=12, verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8))

    ax.set_xlabel("Context Precision", fontsize=12, fontweight="bold")
    ax.set_ylabel("Faithfulness", fontsize=12, fontweight="bold")
    ax.set_title("Relação entre Context Precision e Faithfulness\n(Avaliador: Gemini)", fontsize=14, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=11)

    plt.tight_layout()
    path = output_dir / "02_dispersao_precision_faithfulness.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"[OK] Salvo: {path.name}")


def plot_cluster_context_recall(df: pd.DataFrame, metrics: list[str], output_dir: Path) -> None:
    clusters = {
        "Context Recall = 1.0":     df[df["gemini_context_recall"] == 1.0],
        "Context Recall = 0.0":     df[df["gemini_context_recall"] == 0.0],
        "Context Recall intermediário": df[(df["gemini_context_recall"] > 0.0) & (df["gemini_context_recall"] < 1.0)],
    }
    for label, group in clusters.items():
        print(f"  - {label}: {len(group)} amostras")

    metrics_to_plot = ["faithfulness", "answer_relevancy", "context_precision", "context_entity_recall"]
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Análise de Clusters: Context Recall = 1.0 vs 0.0 vs Intermediário", fontsize=14, fontweight="bold")

    for idx, metric in enumerate(metrics_to_plot):
        ax = axes.flatten()[idx]
        for label, group in clusters.items():
            col = f"gemini_{metric}"
            if col in group.columns:
                ax.hist(group[col].dropna(), bins=15, alpha=0.5, label=label)
        ax.set_xlabel(metric.replace("_", " ").title())
        ax.set_ylabel("Frequência")
        ax.set_title(metric.replace("_", " ").title())
        ax.legend()
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    path = output_dir / "03_cluster_context_recall.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"[OK] Salvo: {path.name}")


def plot_correlation_heatmap(df: pd.DataFrame, metrics: list[str], evaluators: list[str], output_dir: Path) -> None:
    fig, axes = plt.subplots(1, 5, figsize=(20, 4))
    fig.suptitle("Correlação entre Avaliadores por Métrica", fontsize=14, fontweight="bold")

    for idx, metric in enumerate(metrics):
        corr_data = pd.DataFrame({ev: df[f"{ev}_{metric}"] for ev in evaluators if f"{ev}_{metric}" in df.columns})
        sns.heatmap(corr_data.corr(), annot=True, fmt=".3f", cmap="coolwarm", center=0,
                    square=True, ax=axes[idx], cbar_kws={"shrink": 0.8}, vmin=-1, vmax=1)
        axes[idx].set_title(metric.replace("_", " ").title())

    plt.tight_layout()
    path = output_dir / "04_heatmap_correlacao_avaliadores.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"[OK] Salvo: {path.name}")


def plot_boxplots(df: pd.DataFrame, metrics: list[str], evaluators: list[str], output_dir: Path) -> None:
    fig, axes = plt.subplots(1, 5, figsize=(20, 5))
    fig.suptitle("Distribuição de Scores por Avaliador e Métrica (Boxplots)", fontsize=14, fontweight="bold")

    for idx, metric in enumerate(metrics):
        ax = axes[idx]
        boxplot_data = [df[f"{ev}_{metric}"].dropna().values for ev in evaluators if f"{ev}_{metric}" in df.columns]
        labels = [ev.upper() for ev in evaluators if f"{ev}_{metric}" in df.columns]

        bp = ax.boxplot(boxplot_data, labels=labels, patch_artist=True)
        for patch, color in zip(bp["boxes"], ["lightblue", "lightgreen", "lightcoral"]):
            patch.set_facecolor(color)

        ax.set_ylabel("Score")
        ax.set_title(metric.replace("_", " ").title())
        ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    path = output_dir / "05_boxplots_metricas_avaliadores.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"[OK] Salvo: {path.name}")


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


def print_statistics(df: pd.DataFrame, metrics: list[str], evaluators: list[str]) -> None:
    print("\n" + "=" * 80)
    print("RESUMO ESTATÍSTICO")
    print("=" * 80)
    for ev in evaluators:
        print(f"\n{ev.upper()}:")
        for metric in metrics:
            col = f"{ev}_{metric}"
            if col in df.columns:
                series = df[col].dropna()
                print(
                    f"  {metric:25s} — Média: {series.mean():.4f}, "
                    f"Mediana: {series.median():.4f}, "
                    f"Std: {series.std():.4f}, "
                    f"Min: {series.min():.4f}, Max: {series.max():.4f}"
                )


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


@cli.command()
@click.argument("data_file", type=click.Path(exists=True))
@click.option("--output-dir", type=click.Path(), default="api/tools/evaluation/ragas/graphs")
def visualize(data_file: str, output_dir: str):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("ANÁLISE RAGAS — Gerando Visualizações")
    print("=" * 80)

    print("\n[1/6] Carregando dados...")
    df, metrics, evaluators = load_dataframe(Path(data_file))
    print(f"[OK] {len(df)} registros | métricas: {metrics} | avaliadores: {evaluators}")

    print("\n[2/6] Histogramas de distribuição...")
    plot_histograms(df, metrics, evaluators, output_path)

    print("\n[3/6] Dispersão Context Precision × Faithfulness...")
    plot_scatter_precision_faithfulness(df, output_path)

    print("\n[4/6] Clusters por Context Recall...")
    plot_cluster_context_recall(df, metrics, output_path)

    print("\n[5/6] Heatmap de correlação entre avaliadores...")
    plot_correlation_heatmap(df, metrics, evaluators, output_path)

    print("\n[6/6] Boxplots por avaliador...")
    plot_boxplots(df, metrics, evaluators, output_path)

    print_statistics(df, metrics, evaluators)

    print(f"\n[OK] Gráficos salvos em: {output_path}")
    print("=" * 80)


if __name__ == "__main__":
    cli()

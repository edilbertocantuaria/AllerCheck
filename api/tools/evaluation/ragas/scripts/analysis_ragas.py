from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data" / "output" / "262 amostras" / "ragas_evaluation_262.json"
GRAPHS_DIR = BASE_DIR / "graphs"

sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (14, 8)
plt.rcParams["font.size"] = 10


def load_dataframe(data_file: Path = DATA_FILE) -> tuple[pd.DataFrame, list[str], list[str]]:
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


def plot_histograms(df: pd.DataFrame, metrics: list[str], evaluators: list[str]) -> None:
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
    path = GRAPHS_DIR / "01_histogramas_metricas.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"[OK] Salvo: {path.name}")


def plot_scatter_precision_faithfulness(df: pd.DataFrame) -> None:
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
    path = GRAPHS_DIR / "02_dispersao_precision_faithfulness.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"[OK] Salvo: {path.name}")


def plot_cluster_context_recall(df: pd.DataFrame, metrics: list[str]) -> None:
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
    path = GRAPHS_DIR / "03_cluster_context_recall.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"[OK] Salvo: {path.name}")


def plot_correlation_heatmap(df: pd.DataFrame, metrics: list[str], evaluators: list[str]) -> None:
    fig, axes = plt.subplots(1, 5, figsize=(20, 4))
    fig.suptitle("Correlação entre Avaliadores por Métrica", fontsize=14, fontweight="bold")

    for idx, metric in enumerate(metrics):
        corr_data = pd.DataFrame({ev: df[f"{ev}_{metric}"] for ev in evaluators if f"{ev}_{metric}" in df.columns})
        sns.heatmap(corr_data.corr(), annot=True, fmt=".3f", cmap="coolwarm", center=0,
                    square=True, ax=axes[idx], cbar_kws={"shrink": 0.8}, vmin=-1, vmax=1)
        axes[idx].set_title(metric.replace("_", " ").title())

    plt.tight_layout()
    path = GRAPHS_DIR / "04_heatmap_correlacao_avaliadores.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"[OK] Salvo: {path.name}")


def plot_boxplots(df: pd.DataFrame, metrics: list[str], evaluators: list[str]) -> None:
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
    path = GRAPHS_DIR / "05_boxplots_metricas_avaliadores.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"[OK] Salvo: {path.name}")


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


def main(data_file: Path = DATA_FILE) -> None:
    GRAPHS_DIR.mkdir(exist_ok=True)

    print("=" * 80)
    print("ANÁLISE RAGAS — Gerando Visualizações")
    print("=" * 80)

    print("\n[1/6] Carregando dados...")
    df, metrics, evaluators = load_dataframe(data_file)
    print(f"[OK] {len(df)} registros | métricas: {metrics} | avaliadores: {evaluators}")

    print("\n[2/6] Histogramas de distribuição...")
    plot_histograms(df, metrics, evaluators)

    print("\n[3/6] Dispersão Context Precision × Faithfulness...")
    plot_scatter_precision_faithfulness(df)

    print("\n[4/6] Clusters por Context Recall...")
    plot_cluster_context_recall(df, metrics)

    print("\n[5/6] Heatmap de correlação entre avaliadores...")
    plot_correlation_heatmap(df, metrics, evaluators)

    print("\n[6/6] Boxplots por avaliador...")
    plot_boxplots(df, metrics, evaluators)

    print_statistics(df, metrics, evaluators)

    print(f"\n[OK] Gráficos salvos em: {GRAPHS_DIR}")
    print("=" * 80)


if __name__ == "__main__":
    main()

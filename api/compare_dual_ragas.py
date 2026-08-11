#!/usr/bin/env python3
"""
📊 Script de Comparação: Analisa resultados COM vs SEM ontologia
"""

import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path("c:/Users/edilb/OneDrive/Documentos/AllerCheck/api")
OUTPUT_DIR = PROJECT_ROOT / "tools/data/processed/evaluation"

def find_latest_ragas_files():
    """Encontra o arquivo COM e SEM ontologia."""

    all_files = list(OUTPUT_DIR.glob("ragas_evaluation_2026*.json"))

    if len(all_files) < 2:
        print(f"[ERRO] Nao encontrei 2 arquivos RAGAS em {OUTPUT_DIR}/")
        print(f"   Encontrei: {len(all_files)} arquivo(s)")
        return None, None

    # Ordenar por data de modificação (mais recentes primeiro)
    sorted_files = sorted(all_files, key=lambda f: f.stat().st_mtime, reverse=True)

    # Pegar os 2 mais recentes (COM e SEM ontologia)
    return sorted_files[0], sorted_files[1]

def load_ragas(filepath):
    """Carrega resultado RAGAS."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def compare(file1, file2):
    """Compara dois resultados RAGAS."""

    data1 = load_ragas(file1)
    data2 = load_ragas(file2)

    # Determinar qual é com/sem ontologia
    # (pelo conteúdo ou timestamp)
    name1 = file1.name
    name2 = file2.name

    print(f"\n{'='*80}")
    print("COMPARACAO RAGAS: COM vs SEM ONTOLOGIA")
    print(f"{'='*80}\n")

    use_ontology1 = data1.get('use_ontology', False)
    use_ontology2 = data2.get('use_ontology', False)
    ontology_label1 = "COM ONTOLOGIA" if use_ontology1 else "SEM ONTOLOGIA"
    ontology_label2 = "COM ONTOLOGIA" if use_ontology2 else "SEM ONTOLOGIA"

    print(f"[ARQUIVO 1 - {ontology_label1}] {name1}")
    print(f"   Amostras: {data1.get('sample_count', '?')}")
    print(f"   Seed: {data1.get('seed', '?')}")
    print(f"   Avaliadores: {data1.get('evaluators', '?')}")
    print(f"   Gerado em: {data1.get('generated_at', '?')}")

    print(f"\n[ARQUIVO 2 - {ontology_label2}] {name2}")
    print(f"   Amostras: {data2.get('sample_count', '?')}")
    print(f"   Seed: {data2.get('seed', '?')}")
    print(f"   Avaliadores: {data2.get('evaluators', '?')}")
    print(f"   Gerado em: {data2.get('generated_at', '?')}")

    # Extrair sumários
    summary1 = data1.get("summary", {})
    summary2 = data2.get("summary", {})

    print(f"\n{'='*80}")
    print("COMPARACAO DE METRICAS")
    print(f"{'='*80}\n")

    # Assumir que temos múltiplos avaliadores em summary
    evaluators = list(summary1.keys())

    if not evaluators:
        print("⚠️  Nenhum avaliador encontrado nos sumários")
        return

    # Para cada avaliador
    for evaluator in evaluators:
        metrics1 = summary1.get(evaluator, {})
        metrics2 = summary2.get(evaluator, {})

        if not metrics1 or not metrics2:
            continue

        print(f"\n[AVALIADOR] {evaluator.upper()}")
        print(f"{'-'*80}")
        print(f"{'Métrica':<25} | {'Arquivo 1':>12} | {'Arquivo 2':>12} | {'Delta':>8} | {'Δ%':>7}")
        print(f"{'-'*80}")

        for metric in ["faithfulness", "answer_relevancy", "context_precision", "context_recall", "context_entity_recall"]:
            v1 = metrics1.get(metric)
            v2 = metrics2.get(metric)

            if v1 is None or v2 is None:
                continue

            delta = v2 - v1
            pct = (delta / v1 * 100) if v1 != 0 else 0

            sign = "+" if delta > 0 else ""
            arrow = "[UP]" if delta > 0 else ("[DOWN]" if delta < 0 else "[SAME]")

            arrow_str = f"{arrow:>6}"
            print(f"{metric:<25} | {v1:>12.6f} | {v2:>12.6f} | {sign}{delta:>7.6f} | {sign}{pct:>6.1f}% {arrow_str}")

    # Salvar comparação em JSON
    comparison = {
        "timestamp": datetime.now().isoformat(),
        "file1": name1,
        "file2": name2,
        "summary1": summary1,
        "summary2": summary2,
    }

    output_file = OUTPUT_DIR / "comparacao_ragas.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(comparison, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*80}")
    print(f"[OK] Comparacao salva em: {output_file.name}")
    print(f"{'='*80}\n")

def main():
    print("[INFO] Procurando arquivos RAGAS...")

    file1, file2 = find_latest_ragas_files()

    if file1 is None or file2 is None:
        return

    compare(file1, file2)

if __name__ == "__main__":
    main()

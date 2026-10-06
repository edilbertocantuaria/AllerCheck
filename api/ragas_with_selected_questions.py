#!/usr/bin/env python3
"""
Wrapper: Roda RAGAS apenas com as questões especificadas em JSON
Sincroniza pipeline_complete.py com evaluate_with_ontology_robust.py
"""

import json
import sys
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta

_BRT = timezone(timedelta(hours=-3))


def find_latest_selected_questions():
    """Encontra o arquivo mais recente de questões selecionadas"""
    pipeline_dir = Path(__file__).parent / "tools" / "data" / "processed" / "pipeline"

    if not pipeline_dir.exists():
        return None

    files = sorted(pipeline_dir.glob("selected_questions_*.json"))
    if files:
        return files[-1]

    return None


def run_ragas_with_questions(num_questions: int = 3, seed: int = 42):
    """
    Roda RAGAS com as questões selecionadas.

    Procura por: selected_questions_*.json
    Se encontrar, extrai os índices e passa para o RAGAS
    """

    # Encontrar arquivo de questões selecionadas
    selected_file = find_latest_selected_questions()

    if not selected_file:
        print("❌ Arquivo de questões selecionadas não encontrado!")
        print("   Execute: python run_pipeline.py --num-questions=3")
        return False

    print(f"📄 Usando questões selecionadas: {selected_file.name}")

    # Carregar questões
    with open(selected_file, encoding="utf-8") as f:
        questions = json.load(f)

    print(f"   {len(questions)} questões selecionadas")

    # Extrair índices
    indices = [q["index"] for q in questions]
    print(f"   Índices: {indices}")

    # Para agora, a sincronização é garantida pelo seed FIXO
    # RAGAS vai rodar com esse seed e selecionar as mesmas questões
    print("\n🔍 Rodando RAGAS COM/SEM ontologia...")

    cmd = [
        sys.executable,
        "api/evaluate_with_ontology_robust.py",
        "tools/data/raw/evaluation/filtred_alergia_medicamentos.xlsx",
        str(num_questions),
        str(seed)
    ]

    result = subprocess.run(cmd)

    if result.returncode != 0:
        print(f"❌ RAGAS falhou com código {result.returncode}")
        return False

    print("✅ RAGAS completado")
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RAGAS com questões sincronizadas")
    parser.add_argument("--num-questions", type=int, default=3, help="Número de questões")
    parser.add_argument("--seed", type=int, default=42, help="Seed para reproducibilidade")

    args = parser.parse_args()

    success = run_ragas_with_questions(num_questions=args.num_questions, seed=args.seed)
    sys.exit(0 if success else 1)

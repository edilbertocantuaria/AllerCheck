#!/usr/bin/env python3
"""
Pipeline Completo: RAGAS + LLM-as-Judge
1. Lê dataset (filtred_alergia_medicamentos.xlsx)
2. Seleciona N questões aleatórias (seed fixo = reproducível)
3. Roda RAGAS (COM + SEM ontologia)
4. Roda LLM-as-Judge nas mesmas questões
5. Consolida relatório com todas as métricas
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
import random
import pandas as pd

_BRT = timezone(timedelta(hours=-3))

def load_dataset(xlsx_path: str, num_samples: int = 3, seed: int = 42) -> list[dict]:
    """Carrega dataset e seleciona N questões aleatórias"""
    print(f"\n📊 Carregando dataset: {xlsx_path}")

    df = pd.read_excel(xlsx_path)
    print(f"   Total disponível: {len(df)} questões")

    random.seed(seed)
    selected_indices = sorted(random.sample(range(len(df)), min(num_samples, len(df))))
    print(f"   Selecionadas (seed={seed}): {selected_indices}")

    questions = []
    for idx in selected_indices:
        row = df.iloc[idx]
        questions.append({
            "question_id": idx + 1,
            "question": row.get("question", "") if "question" in df.columns else str(row),
        })

    return questions, selected_indices

def run_ragas(num_questions: int = 3, seed: int = 42):
    """Roda RAGAS COM/SEM ontologia com essas questões específicas"""
    print(f"\n🔍 Rodando RAGAS com {num_questions} questões...")

    # Roda script RAGAS existente com seed
    cmd = [
        sys.executable,
        "api/evaluate_with_ontology_robust.py",
        f"--num-samples={num_questions}",
        f"--seed={seed}"
    ]

    result = subprocess.run(cmd, cwd=Path(__file__).parent)

    if result.returncode != 0:
        print(f"   ❌ RAGAS falhou com código {result.returncode}")
        return None

    print(f"   ✅ RAGAS completado")
    return True

def run_llm_judge(num_questions: int = 3):
    """Roda LLM-as-Judge com essas questões"""
    print(f"\n⚖️  Rodando LLM-as-Judge com {num_questions} questões...")

    cmd = [
        sys.executable,
        "llm_as_judge_test_local.py",
        str(num_questions)
    ]

    result = subprocess.run(cmd, cwd=Path(__file__).parent)

    if result.returncode != 0:
        print(f"   ❌ LLM-as-Judge falhou com código {result.returncode}")
        return None

    print(f"   ✅ LLM-as-Judge completado")
    return True

def consolidate_report(num_questions: int = 3):
    """Consolida relatório com dados do RAGAS e LLM-as-Judge"""
    print(f"\n📋 Consolidando relatório...")

    timestamp = datetime.now(_BRT).strftime("%Y%m%d_%H%M%S")

    report = {
        "timestamp": datetime.now(_BRT).isoformat(),
        "pipeline": "RAGAS + LLM-as-Judge",
        "num_questions": num_questions,
        "status": "em_construção",
        "files": {
            "ragas": "api/tools/data/processed/evaluation/unified/evaluation_*.json",
            "llm_judge": "api/tools/data/processed/llm_judge/llm_judge_*.json"
        }
    }

    output_dir = Path("api/tools/data/processed/pipeline")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"pipeline_report_{timestamp}.json"
    output_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"   📄 Relatório: {output_file}")
    return output_file

def main(num_questions: int = 3, seed: int = 42):
    """Executa pipeline completo"""
    print("=" * 70)
    print("🚀 PIPELINE COMPLETO: RAGAS + LLM-as-Judge")
    print("=" * 70)

    # 1. Carregar dataset
    dataset_path = "tools/data/raw/evaluation/filtred_alergia_medicamentos.xlsx"
    questions, indices = load_dataset(dataset_path, num_samples=num_questions, seed=seed)

    print(f"\n✅ Questões selecionadas: {len(questions)}")
    for q in questions:
        print(f"   Q{q['question_id']}: {q['question'][:60]}...")

    # 2. Rodar RAGAS
    ragas_ok = run_ragas(num_questions=num_questions, seed=seed)

    if not ragas_ok:
        print("\n❌ Pipeline interrompido: RAGAS falhou")
        return

    # 3. Rodar LLM-as-Judge
    judge_ok = run_llm_judge(num_questions=num_questions)

    if not judge_ok:
        print("\n❌ Pipeline interrompido: LLM-as-Judge falhou")
        return

    # 4. Consolidar relatório
    report_file = consolidate_report(num_questions=num_questions)

    print("\n" + "=" * 70)
    print("✅ PIPELINE COMPLETO!")
    print("=" * 70)
    print(f"\nResultados:")
    print(f"  RAGAS:       api/tools/data/processed/evaluation/unified/")
    print(f"  LLM-Judge:   api/tools/data/processed/llm_judge/")
    print(f"  Relatório:   {report_file}")
    print("\n")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pipeline RAGAS + LLM-as-Judge")
    parser.add_argument("--num-questions", type=int, default=3, help="Número de questões (default: 3)")
    parser.add_argument("--seed", type=int, default=42, help="Seed para reproducibilidade (default: 42)")

    args = parser.parse_args()

    main(num_questions=args.num_questions, seed=args.seed)

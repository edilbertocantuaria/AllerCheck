#!/usr/bin/env python3
"""
Pipeline Rápido: Usa evaluation.json existente + LLM-as-Judge
Quando RAGAS já foi executado, roda apenas o LLM-as-Judge e consolida
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
import random

# Force UTF-8 on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

_BRT = timezone(timedelta(hours=-3))


def find_latest_evaluation_file():
    """Encontra o arquivo evaluation_*.json mais recente"""
    eval_dir = Path("api/tools/data/processed/evaluation/unified")

    if not eval_dir.exists():
        return None

    files = sorted(eval_dir.glob("evaluation_*.json"))
    if files:
        return files[-1]

    return None


def load_selected_questions(num_samples: int = 3, seed: int = 42):
    """Carrega as N questões selecionadas (não do arquivo, mas calcula os índices)"""
    eval_file = find_latest_evaluation_file()

    if not eval_file:
        print("❌ Arquivo evaluation não encontrado!")
        return None, None

    with open(eval_file, encoding="utf-8") as f:
        eval_data = json.load(f)

    # Extrair questões da condição COM ontologia
    com_items = eval_data.get("conditions", [{}])[0].get("items", [])

    # Selecionar índices usando o mesmo seed
    random.seed(seed)
    total_available = len(com_items)
    selected_indices = sorted(random.sample(range(total_available), min(num_samples, total_available)))

    print(f"📊 Dataset: {eval_file.name}")
    print(f"   Total disponível: {total_available} questões")
    print(f"   Selecionadas (seed={seed}): {selected_indices}\n")

    questions = []
    for idx in selected_indices:
        item = com_items[idx]
        questions.append({
            "question_id": item.get("question_id", idx + 1),
            "index": idx,
            "question": item.get("question", ""),
        })

    return questions, eval_file


def run_llm_judge(num_questions: int = 3):
    """Roda LLM-as-Judge com essas questões"""
    print(f"⚖️  Rodando LLM-as-Judge com {num_questions} questões...\n")

    cmd = [
        sys.executable,
        "llm_as_judge_test_local.py",
        str(num_questions)
    ]

    result = subprocess.run(cmd)

    if result.returncode != 0:
        print(f"\n❌ LLM-as-Judge falhou com código {result.returncode}")
        return False

    print(f"\n✅ LLM-as-Judge completado")
    return True


def find_latest_files():
    """Encontra os arquivos mais recentes de RAGAS e LLM-as-Judge"""
    ragas_dir = Path("api/tools/data/processed/evaluation/unified")
    judge_dir = Path("api/tools/data/processed/llm_judge")

    ragas_file = None
    judge_file = None

    if ragas_dir.exists():
        files = sorted(ragas_dir.glob("evaluation_*.json"))
        if files:
            ragas_file = files[-1]

    if judge_dir.exists():
        files = sorted(judge_dir.glob("llm_judge_*.json"))
        if files:
            judge_file = files[-1]

    return ragas_file, judge_file


def consolidate_report(num_questions: int = 3):
    """Consolida relatório com dados do RAGAS e LLM-as-Judge"""
    print(f"\n📋 Consolidando relatório...\n")

    timestamp = datetime.now(_BRT).strftime("%Y%m%d_%H%M%S")

    # Encontrar arquivos
    ragas_file, judge_file = find_latest_files()

    if not ragas_file or not judge_file:
        print(f"❌ Arquivos não encontrados!")
        print(f"   RAGAS: {ragas_file}")
        print(f"   Judge: {judge_file}")
        return None

    # Carregar dados
    with open(ragas_file, encoding="utf-8") as f:
        ragas_data = json.load(f)

    with open(judge_file, encoding="utf-8") as f:
        judge_data = json.load(f)

    # Consolidar por questão
    consolidated_items = []
    ragas_items = ragas_data.get("conditions", [{}])[0].get("items", [])
    judge_items = judge_data.get("results", [])

    for j_item in judge_items:
        q_id = j_item.get("question_id")

        # Encontrar item RAGAS correspondente
        r_item = None
        for r in ragas_items:
            if r.get("question_id") == q_id:
                r_item = r
                break

        consolidated = {
            "question_id": q_id,
            "question": j_item.get("question", ""),
            "responses": j_item.get("responses", {}),
            "ragas": {
                "results": r_item.get("results", {}) if r_item else {}
            },
            "llm_judge": {
                "votes": j_item.get("votes", []),
                "consensus": j_item.get("consensus"),
                "mapping": j_item.get("mapping", {}),
            },
            "analysis": {
                "judges_consensus": j_item.get("consensus"),
                "agreement": j_item.get("agreement", False)
            }
        }

        consolidated_items.append(consolidated)

    # Calcular estatísticas
    agreements = sum(1 for item in consolidated_items if item["analysis"]["agreement"])
    divergences = len(consolidated_items) - agreements

    # Placar de consensos
    consensus_scores = judge_data.get("summary", {}).get("consensus_scores", {})

    report = {
        "timestamp": datetime.now(_BRT).isoformat(),
        "pipeline": "RAGAS + LLM-as-Judge Consolidado",
        "num_questions": len(consolidated_items),
        "source_files": {
            "ragas": str(ragas_file),
            "llm_judge": str(judge_file)
        },
        "questions": consolidated_items,
        "summary": {
            "total_questions": len(consolidated_items),
            "agreements": agreements,
            "divergences": divergences,
            "agreement_rate": agreements / len(consolidated_items) if consolidated_items else 0,
            "consensus_scores": consensus_scores,
            "judges": judge_data.get("judges", [])
        }
    }

    output_dir = Path("api/tools/data/processed/pipeline")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"pipeline_consolidated_{timestamp}.json"
    output_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ Relatório consolidado gerado!")
    print(f"📄 Arquivo: {output_file}")
    print(f"📊 Questões: {len(consolidated_items)}")
    print(f"✅ Acordos: {agreements} | ❌ Divergências: {divergences}")
    print(f"🎯 Taxa de concordância: {(agreements/len(consolidated_items)*100):.1f}%" if consolidated_items else "N/A")

    return output_file


def main(num_questions: int = 3, seed: int = 42):
    """Executa pipeline rápido"""
    print("=" * 70)
    print("🚀 PIPELINE RÁPIDO: Usa evaluation.json existente + LLM-as-Judge")
    print("=" * 70)

    # 1. Carregar questões selecionadas
    questions, eval_file = load_selected_questions(num_samples=num_questions, seed=seed)

    if not questions:
        print("❌ Pipeline interrompido: não conseguiu carregar questões")
        return

    print(f"✅ Questões selecionadas: {len(questions)}")
    for q in questions:
        print(f"   Q{q['question_id']}: {q['question'][:60]}...")

    # 2. Rodar LLM-as-Judge
    judge_ok = run_llm_judge(num_questions=num_questions)

    if not judge_ok:
        print("\n❌ Pipeline interrompido: LLM-as-Judge falhou")
        return

    # 3. Consolidar relatório
    report_file = consolidate_report(num_questions=num_questions)

    print("\n" + "=" * 70)
    print("✅ PIPELINE RÁPIDO COMPLETO!")
    print("=" * 70)
    print(f"\nArquivos:")
    print(f"  RAGAS (reusado):       api/tools/data/processed/evaluation/unified/")
    print(f"  LLM-Judge (novo):      api/tools/data/processed/llm_judge/")
    print(f"  Relatório consolidado: {report_file}")
    print("\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pipeline Rápido: RAGAS (existente) + LLM-as-Judge")
    parser.add_argument("--num-questions", type=int, default=3, help="Número de questões (default: 3)")
    parser.add_argument("--seed", type=int, default=42, help="Seed para reproducibilidade (default: 42)")

    args = parser.parse_args()

    main(num_questions=args.num_questions, seed=args.seed)

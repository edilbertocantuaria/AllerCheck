#!/usr/bin/env python3
"""
🚀 PIPELINE COMPLETO EM UM COMANDO!

Fluxo:
1. Seleciona N questões aleatórias (seed fixo)
2. Roda RAGAS COM ontologia (via Docker)
3. Roda RAGAS SEM ontologia (via Docker)
4. Roda LLM-as-Judge (local, 3 juízes)
5. Consolida relatório único com todas as métricas

Uso:
  python pipeline.py                    # 262 questões
  python pipeline.py --num-questions=50 # 50 questões
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


def banner(title):
    """Exibe banner"""
    print("\n" + "=" * 75)
    print(f"  {title}")
    print("=" * 75 + "\n")


def check_docker():
    """Verifica se Docker está rodando"""
    try:
        result = subprocess.run(
            ["docker", "ps"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except:
        return False


def load_dataset_and_select(xlsx_path: str, num_samples: int = 262, seed: int = 42):
    """Carrega dataset Excel e seleciona N questões aleatórias"""
    import pandas as pd

    print(f"📊 Carregando dataset: {xlsx_path}")

    full_path = Path("api") / xlsx_path
    df = pd.read_excel(full_path)
    print(f"   Total disponível: {len(df)} questões")

    random.seed(seed)
    selected_indices = sorted(random.sample(range(len(df)), min(num_samples, len(df))))
    print(f"   Selecionadas (seed={seed}): {len(selected_indices)} questões\n")

    questions = []
    for idx in selected_indices:
        row = df.iloc[idx]
        questions.append({
            "question_id": idx + 1,
            "index": idx,
            "question": row.get("question", "") if "question" in df.columns else str(row),
        })

    return questions


def save_questions_json(questions, label="selecionadas"):
    """Salva questões em JSON"""
    output_dir = Path("api/tools/data/processed/pipeline")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(_BRT).strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"questoes_{label}_{timestamp}.json"

    output_file.write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"💾 Salvo: {output_file.name}\n")

    return output_file


def run_ragas_docker(num_questions: int, seed: int):
    """Roda RAGAS via Docker (sem problemas de dependência local)"""
    print("🔍 Rodando RAGAS COM/SEM ontologia via Docker...\n")

    # Comando dentro do container
    cmd = [
        "docker", "exec", "allercheck-api-1",
        "python", "api/evaluate_with_ontology_robust.py",
        "tools/data/raw/evaluation/filtred_alergia_medicamentos.xlsx",
        str(num_questions),
        str(seed)
    ]

    result = subprocess.run(cmd, timeout=600)

    if result.returncode != 0:
        print(f"\n❌ RAGAS falhou")
        return False

    print(f"\n✅ RAGAS completado")
    return True


def run_llm_judge(num_questions: int):
    """Roda LLM-as-Judge"""
    print(f"\n⚖️  Rodando LLM-as-Judge ({num_questions} questões)...\n")

    cmd = [sys.executable, "llm_as_judge_test_local.py", str(num_questions)]
    result = subprocess.run(cmd)

    if result.returncode != 0:
        print(f"\n❌ LLM-as-Judge falhou")
        return False

    print(f"\n✅ Avaliação completa")
    return True


def find_latest_files():
    """Encontra arquivos mais recentes gerados"""
    ragas_dir = Path("api/tools/data/processed/evaluation/unified")
    judge_dir = Path("api/tools/data/processed/llm_judge")

    ragas_file = None
    judge_file = None

    if ragas_dir.exists():
        files = sorted(ragas_dir.glob("evaluation_*.json"))
        ragas_file = files[-1] if files else None

    if judge_dir.exists():
        files = sorted(judge_dir.glob("llm_judge_*.json"))
        judge_file = files[-1] if files else None

    return ragas_file, judge_file


def consolidate_report(num_questions: int):
    """Consolida todos os dados em um relatório único"""
    print(f"\n📋 Consolidando relatório final...\n")

    timestamp = datetime.now(_BRT).strftime("%Y%m%d_%H%M%S")

    ragas_file, judge_file = find_latest_files()

    if not ragas_file or not judge_file:
        print(f"❌ Arquivos não encontrados!")
        print(f"   RAGAS: {ragas_file}")
        print(f"   Judge: {judge_file}")
        return None

    with open(ragas_file, encoding="utf-8") as f:
        ragas_data = json.load(f)

    with open(judge_file, encoding="utf-8") as f:
        judge_data = json.load(f)

    # Consolidar questão por questão
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

    # Estatísticas
    agreements = sum(1 for item in consolidated_items if item["analysis"]["agreement"])
    divergences = len(consolidated_items) - agreements
    consensus_scores = judge_data.get("summary", {}).get("consensus_scores", {})

    report = {
        "timestamp": datetime.now(_BRT).isoformat(),
        "pipeline": "RAGAS (COM+SEM) + LLM-as-Judge Consolidado",
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

    return output_file, report


def main(num_questions: int = 262, seed: int = 42):
    """Executa pipeline completo"""
    banner("🚀 PIPELINE COMPLETO: Questões → RAGAS → LLM-as-Judge → Consolidação")

    # 0. Verificar Docker
    if not check_docker():
        print("❌ Docker não está rodando!")
        print("\nPara iniciar:")
        print("  docker compose up -d api")
        print("\nOu use o pipeline_fast se já tem evaluation_*.json:")
        print("  python pipeline_fast.py --num-questions=262")
        sys.exit(1)

    print("✅ Docker disponível\n")

    # 1. Selecionar questões
    questions = load_dataset_and_select(
        "tools/data/raw/evaluation/filtred_alergia_medicamentos.xlsx",
        num_samples=num_questions,
        seed=seed
    )

    print(f"✅ Questões selecionadas: {len(questions)}")
    for q in questions[:3]:
        print(f"   • Q{q['question_id']}: {q['question'][:50]}...")
    if len(questions) > 3:
        print(f"   ... + {len(questions) - 3} mais")

    # 2. Salvar questões
    save_questions_json(questions, "selecionadas")

    # 3. Rodar RAGAS
    ragas_ok = run_ragas_docker(num_questions=num_questions, seed=seed)
    if not ragas_ok:
        print("\n❌ Pipeline interrompido: RAGAS falhou")
        sys.exit(1)

    # 4. Rodar LLM-as-Judge
    judge_ok = run_llm_judge(num_questions=num_questions)
    if not judge_ok:
        print("\n❌ Pipeline interrompido: LLM-as-Judge falhou")
        sys.exit(1)

    # 5. Consolidar
    result = consolidate_report(num_questions=num_questions)
    if not result:
        print("\n❌ Consolidação falhou")
        sys.exit(1)

    report_file, report = result

    # 6. RESUMO EXECUTIVO
    banner("✅ PIPELINE COMPLETO!")

    summary = report["summary"]
    print(f"📊 RESULTADOS:")
    print(f"   Total de questões: {summary['total_questions']}")
    print(f"   ✅ Acordos (RAGAS + Juízes): {summary['agreements']} ({summary['agreement_rate']*100:.1f}%)")
    print(f"   ❌ Divergências: {summary['divergences']} ({(1-summary['agreement_rate'])*100:.1f}%)")

    print(f"\n🗳️  VOTOS DOS JUÍZES:")
    scores = summary["consensus_scores"]
    print(f"   Preferem COM ontologia: {scores.get('com_ontologia', 0)} questões")
    print(f"   Preferem SEM ontologia: {scores.get('sem_ontologia', 0)} questões")
    print(f"   Preferem ground_truth: {scores.get('ground_truth', 0)} questões")

    print(f"\n📁 ARQUIVOS GERADOS:")
    print(f"   Relatório consolidado: {report_file}")
    print(f"   RAGAS: api/tools/data/processed/evaluation/unified/")
    print(f"   LLM-Judge: api/tools/data/processed/llm_judge/")

    print("\n" + "=" * 75 + "\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="🚀 Pipeline Completo: Um Comando Para Tudo!",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python pipeline.py                              # 262 questões (full)
  python pipeline.py --num-questions=50           # 50 questões
  python pipeline.py --num-questions=15 --seed=99 # 15 questões, seed diferente

Requisito:
  docker compose up -d api
        """
    )
    parser.add_argument("--num-questions", type=int, default=262,
                       help="Número de questões (default: 262)")
    parser.add_argument("--seed", type=int, default=42,
                       help="Seed para reproducibilidade (default: 42)")

    args = parser.parse_args()

    main(num_questions=args.num_questions, seed=args.seed)

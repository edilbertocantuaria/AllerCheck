#!/usr/bin/env python3
"""
🚀 PIPELINE UNIFICADO: Um comando para tudo!
python pipeline.py --num-questions=262

Fluxo automático:
1. Verifica se evaluation_*.json existe
2. Se não → aviso (precisa rodar RAGAS via Docker)
3. Roda LLM-as-Judge
4. Consolida relatório final
5. Mostra resumo executivo
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
    """Exibe banner colorido"""
    print("\n" + "=" * 75)
    print(f"  {title}")
    print("=" * 75 + "\n")


def find_latest_evaluation_file():
    """Encontra evaluation_*.json mais recente"""
    eval_dir = Path("api/tools/data/processed/evaluation/unified")
    if eval_dir.exists():
        files = sorted(eval_dir.glob("evaluation_*.json"))
        return files[-1] if files else None
    return None


def load_selected_questions(num_samples: int = 3, seed: int = 42):
    """Carrega questões selecionadas do evaluation_*.json"""
    eval_file = find_latest_evaluation_file()

    if not eval_file:
        print("❌ ERRO: evaluation_*.json não encontrado!")
        print("\n📝 Para gerar, rode:")
        print("   docker compose up -d api")
        print("   docker exec allercheck-api python api/evaluate_with_ontology_robust.py \\")
        print("     tools/data/raw/evaluation/filtred_alergia_medicamentos.xlsx 50 42")
        sys.exit(1)

    with open(eval_file, encoding="utf-8") as f:
        eval_data = json.load(f)

    com_items = eval_data.get("conditions", [{}])[0].get("items", [])

    random.seed(seed)
    total_available = len(com_items)
    selected_indices = sorted(random.sample(range(total_available), min(num_samples, total_available)))

    print(f"📊 Dataset carregado: {eval_file.name}")
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
    """Roda LLM-as-Judge"""
    print(f"⚖️  Rodando avaliação com 3 juízes LLM ({num_questions} questões)...\n")

    cmd = [sys.executable, "llm_as_judge_test_local.py", str(num_questions)]
    result = subprocess.run(cmd)

    if result.returncode != 0:
        print(f"\n❌ LLM-as-Judge falhou")
        return False

    print(f"\n✅ Avaliação completa")
    return True


def find_latest_files():
    """Encontra arquivos mais recentes"""
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


def consolidate_report(num_questions: int = 3):
    """Consolida relatório final"""
    print(f"\n📋 Consolidando relatório final...\n")

    timestamp = datetime.now(_BRT).strftime("%Y%m%d_%H%M%S")

    ragas_file, judge_file = find_latest_files()

    if not ragas_file or not judge_file:
        print(f"❌ Arquivos não encontrados!")
        return None

    with open(ragas_file, encoding="utf-8") as f:
        ragas_data = json.load(f)

    with open(judge_file, encoding="utf-8") as f:
        judge_data = json.load(f)

    # Consolidar
    consolidated_items = []
    ragas_items = ragas_data.get("conditions", [{}])[0].get("items", [])
    judge_items = judge_data.get("results", [])

    for j_item in judge_items:
        q_id = j_item.get("question_id")

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
        "pipeline": "RAGAS + LLM-as-Judge (Consolidado)",
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
    banner("🚀 PIPELINE UNIFICADO: RAGAS + LLM-as-Judge")

    # 1. Carregar questões
    questions, eval_file = load_selected_questions(num_samples=num_questions, seed=seed)

    print(f"✅ {len(questions)} questões selecionadas:")
    for q in questions[:5]:
        print(f"   • Q{q['question_id']}: {q['question'][:50]}...")
    if len(questions) > 5:
        print(f"   ... e mais {len(questions) - 5} questões")

    # 2. Rodar LLM-as-Judge
    judge_ok = run_llm_judge(num_questions=num_questions)

    if not judge_ok:
        print("\n❌ Pipeline falhou")
        return

    # 3. Consolidar
    result = consolidate_report(num_questions=num_questions)

    if not result:
        print("\n❌ Consolidação falhou")
        return

    report_file, report = result

    # 4. RESUMO EXECUTIVO
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
    print(f"   Relatório: {report_file}")
    print(f"   Tamanho: {report_file.stat().st_size / 1024:.1f} KB")

    print(f"\n📖 Para análise detalhada:")
    print(f"   cat {report_file}")

    print("\n" + "=" * 75 + "\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="🚀 Pipeline Unificado: Um comando para tudo!",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python pipeline.py                              # 262 questões (full)
  python pipeline.py --num-questions=50           # 50 questões (teste)
  python pipeline.py --num-questions=15 --seed=99 # 15 questões, seed diferente
        """
    )
    parser.add_argument("--num-questions", type=int, default=262,
                       help="Número de questões (default: 262)")
    parser.add_argument("--seed", type=int, default=42,
                       help="Seed para reproducibilidade (default: 42)")

    args = parser.parse_args()

    main(num_questions=args.num_questions, seed=args.seed)

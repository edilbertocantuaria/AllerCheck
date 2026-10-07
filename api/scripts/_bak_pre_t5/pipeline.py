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
    """Carrega dataset Excel e seleciona N questões aleatórias com dados completos"""
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
            "answer": row.get("answer", "") if "answer" in df.columns else "",
            "dataset_source": "filtred_alergia_medicamentos.xlsx",
            "row_number": idx,
        })

    return questions


def save_questions_json(questions, label="selecionadas"):
    """Salva questões em JSON com estrutura clara para RAGAS/Judge"""
    output_dir = Path("api/tools/data/processed/evaluation")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(_BRT).strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"questoes_{label}_{timestamp}.json"

    data_to_save = {
        "metadata": {
            "timestamp": datetime.now(_BRT).isoformat(),
            "total_questions": len(questions),
            "dataset_source": "filtred_alergia_medicamentos.xlsx",
        },
        "questions": questions
    }

    output_file.write_text(json.dumps(data_to_save, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"💾 Salvo: {output_file.name}")
    print(f"   📍 Path: {output_file}")
    print(f"   📊 Questões: {len(questions)}\n")

    return output_file


def run_ragas_docker(selected_questions_file: Path, seed: int, evaluators: str = "gemini"):
    """Roda RAGAS via Docker com lista específica de questões"""
    print(f"🔍 Rodando RAGAS COM/SEM ontologia via Docker...")
    print(f"   📍 Questões: {selected_questions_file.name}\n")

    # Converter para path absoluto dentro do container (/app/)
    # selected_questions_file é algo como: api/tools/data/processed/evaluation/questoes_*.json
    # Dentro do container, fica: /app/tools/data/processed/evaluation/questoes_*.json
    path_str = str(selected_questions_file).replace("\\", "/")  # Normalizar para forward slash
    container_path = "/app/" + path_str.replace("api/", "") if "api/" in path_str else "/app/" + path_str

    cmd = [
        "docker", "exec", "-w", "/app", "-e", "PYTHONPATH=/app", "allercheck-api-1",
        "python", "scripts/evaluate_with_ontology_robust.py",
        "tools/data/raw/evaluation/filtred_alergia_medicamentos.xlsx",
        container_path,
        str(seed),
        evaluators
    ]

    result = subprocess.run(cmd, timeout=3600)

    if result.returncode != 0:
        print(f"\n❌ RAGAS falhou")
        return False

    print(f"\n✅ RAGAS completado")
    return True


def run_llm_judge(selected_questions_file: Path, ragas_output_file: Path, seed: int = 42):
    """Roda LLM-as-Judge com as mesmas questões do RAGAS"""
    print(f"\n⚖️  Rodando LLM-as-Judge...")
    print(f"   📍 Questões: {selected_questions_file.name}")
    print(f"   📍 RAGAS output: {ragas_output_file.name}\n")

    cmd = [
        sys.executable,
        "api/scripts/llm_as_judge_test_local.py",
        str(selected_questions_file),
        str(ragas_output_file),
        str(seed)
    ]
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

    consolidated_items = []
    ragas_items = ragas_data.get("conditions", [{}])[0].get("items", [])
    judge_items = judge_data.get("results", [])

    if not judge_items:
        print("❌ Judge retornou 0 questões")
        return None

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
    import statistics

    agreements = sum(1 for item in consolidated_items if item["analysis"]["agreement"])
    divergences = len(consolidated_items) - agreements
    consensus_scores = judge_data.get("summary", {}).get("consensus_scores", {})

    # Calcular estatísticas descritivas por métrica RAGAS (COM vs SEM)
    metrics_stats = {}
    metric_names = ["faithfulness", "answer_relevancy", "context_precision", "context_recall", "context_entity_recall"]

    for metric in metric_names:
        values_com = []
        values_sem = []

        # Extrair valores das condições RAGAS
        ragas_conditions_com = ragas_data.get("conditions", [{}])[0].get("items", [])
        ragas_conditions_sem = ragas_data.get("conditions", [{}])[1].get("items", []) if len(ragas_data.get("conditions", [])) > 1 else []

        # Valores COM ontologia
        for item in ragas_conditions_com:
            ragas_results = item.get("results", {})
            for evaluator, metrics_dict in ragas_results.items():
                if metric in metrics_dict and metrics_dict[metric] is not None:
                    values_com.append(float(metrics_dict[metric]))

        # Valores SEM ontologia
        for item in ragas_conditions_sem:
            ragas_results = item.get("results", {})
            for evaluator, metrics_dict in ragas_results.items():
                if metric in metrics_dict and metrics_dict[metric] is not None:
                    values_sem.append(float(metrics_dict[metric]))

        metrics_stats[metric] = {}

        # Estatísticas COM ontologia
        if values_com:
            metrics_stats[metric]["com_ontologia"] = {
                "count": len(values_com),
                "mean": round(statistics.mean(values_com), 6),
                "median": round(statistics.median(values_com), 6),
                "stdev": round(statistics.stdev(values_com), 6) if len(values_com) > 1 else 0.0,
                "min": round(min(values_com), 6),
                "max": round(max(values_com), 6),
            }

        # Estatísticas SEM ontologia
        if values_sem:
            metrics_stats[metric]["sem_ontologia"] = {
                "count": len(values_sem),
                "mean": round(statistics.mean(values_sem), 6),
                "median": round(statistics.median(values_sem), 6),
                "stdev": round(statistics.stdev(values_sem), 6) if len(values_sem) > 1 else 0.0,
                "min": round(min(values_sem), 6),
                "max": round(max(values_sem), 6),
            }

        # Calcular delta (diferença: SEM - COM)
        if values_com and values_sem:
            delta_mean = round(statistics.mean(values_sem) - statistics.mean(values_com), 6)
            delta_median = round(statistics.median(values_sem) - statistics.median(values_com), 6)
            metrics_stats[metric]["delta"] = {
                "mean_diff": delta_mean,
                "median_diff": delta_median,
                "winner": "sem_ontologia" if delta_mean > 0 else "com_ontologia" if delta_mean < 0 else "empate"
            }

    # Estatísticas de confiança dos juízes (separadas por LLM para detectar viés)
    judge_stats_by_llm = {}
    judge_votes_by_llm = {}

    for item in consolidated_items:
        votes = item.get("llm_judge", {}).get("votes", [])
        mapping = item.get("llm_judge", {}).get("mapping", {})

        for vote in votes:
            judge_name = vote.get("judge")
            confidence = float(vote.get("confidence", 0)) if vote.get("confidence") is not None else 0
            choice = vote.get("choice")
            choice_source = mapping.get(choice, "unknown")

            if judge_name not in judge_stats_by_llm:
                judge_stats_by_llm[judge_name] = {
                    "com_ontologia": [],
                    "sem_ontologia": [],
                    "ground_truth": []
                }
                judge_votes_by_llm[judge_name] = {
                    "com_ontologia": 0,
                    "sem_ontologia": 0,
                    "ground_truth": 0
                }

            if choice_source in judge_stats_by_llm[judge_name]:
                judge_stats_by_llm[judge_name][choice_source].append(confidence)

            if choice_source in judge_votes_by_llm[judge_name]:
                judge_votes_by_llm[judge_name][choice_source] += 1

    # Converter em estatísticas descritivas POR LLM
    judge_confidence_stats = {}

    for judge_name in sorted(judge_stats_by_llm.keys()):
        conditions_data = judge_stats_by_llm[judge_name]
        judge_confidence_stats[judge_name] = {
            "votes_distribution": judge_votes_by_llm[judge_name],
            "confidence_by_condition": {}
        }

        for condition in ["com_ontologia", "sem_ontologia", "ground_truth"]:
            values = conditions_data[condition]
            if values:
                judge_confidence_stats[judge_name]["confidence_by_condition"][condition] = {
                    "count": len(values),
                    "mean": round(statistics.mean(values), 6),
                    "median": round(statistics.median(values), 6),
                    "stdev": round(statistics.stdev(values), 6) if len(values) > 1 else 0.0,
                    "min": round(min(values), 6),
                    "max": round(max(values), 6),
                }

    # Adicionar estatísticas agregadas (todos os juízes juntos)
    all_judge_stats = {
        "com_ontologia": [],
        "sem_ontologia": [],
        "ground_truth": []
    }

    for judge_name, conditions_data in judge_stats_by_llm.items():
        for condition, values in conditions_data.items():
            all_judge_stats[condition].extend(values)

    judge_confidence_stats["_aggregated"] = {}
    for condition, values in all_judge_stats.items():
        if values:
            judge_confidence_stats["_aggregated"][condition] = {
                "count": len(values),
                "mean": round(statistics.mean(values), 6),
                "median": round(statistics.median(values), 6),
                "stdev": round(statistics.stdev(values), 6) if len(values) > 1 else 0.0,
                "min": round(min(values), 6),
                "max": round(max(values), 6),
            }

    judge_cfg = judge_data.get("judge_config", {})
    consensus_strength_dist = judge_data.get("summary", {}).get("consensus_strength_distribution", {})

    report = {
        "timestamp": datetime.now(_BRT).isoformat(),
        "pipeline": "RAGAS (COM+SEM) + LLM-as-Judge Consolidado",
        "num_questions": len(consolidated_items),
        "source_files": {
            "ragas": str(ragas_file),
            "llm_judge": str(judge_file)
        },
        "questions": consolidated_items,
        "judge_config": judge_cfg,
        "summary": {
            "total_questions": len(consolidated_items),
            "agreements": agreements,
            "divergences": divergences,
            "agreement_rate": round(agreements / len(consolidated_items), 4) if consolidated_items else 0,
            "consensus_scores": consensus_scores,
            "consensus_strength_distribution": consensus_strength_dist,
            "judges": judge_data.get("judges", [])
        },
        "summary_metrics": metrics_stats,
        "judge_confidence_statistics": judge_confidence_stats
    }

    output_dir = Path("api/tools/data/processed/pipeline")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"pipeline_consolidated_{timestamp}.json"
    output_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return output_file, report


def main(num_questions: int = 262, seed: int = 42, evaluators: str = "gemini"):
    """Executa pipeline completo com seleção + RAGAS + Judge sincronizados"""
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

    # 2. Salvar questões em JSON
    selected_file = save_questions_json(questions, "selecionadas")

    # 3. Rodar RAGAS (passa o arquivo JSON!)
    ragas_ok = run_ragas_docker(selected_questions_file=selected_file, seed=seed, evaluators=evaluators)
    if not ragas_ok:
        print("\n❌ Pipeline interrompido: RAGAS falhou")
        sys.exit(1)

    ragas_dir = Path("api/tools/data/processed/evaluation/unified")
    ragas_files = [f for f in ragas_dir.glob("evaluation_*.json") if f.name != "evaluation_latest.json"]
    if not ragas_files:
        print("\n❌ Pipeline interrompido: RAGAS não gerou output")
        sys.exit(1)
    ragas_output_file = max(ragas_files, key=lambda f: f.stat().st_mtime)
    print(f"   ✅ RAGAS output: {ragas_output_file.name}\n")

    with open(ragas_output_file, 'r', encoding='utf-8') as f:
        ragas_data = json.load(f)

    selected_ids = set()
    with open(selected_file, 'r', encoding='utf-8') as f:
        selected_data = json.load(f)
        for q in selected_data.get("questions", []):
            selected_ids.add(q.get("question_id"))

    ragas_ids = set()
    for condition in ragas_data.get("conditions", []):
        for item in condition.get("items", []):
            if not item.get("errors"):
                ragas_ids.add(item.get("question_id"))

    missing_ids = selected_ids - ragas_ids
    if missing_ids:
        print(f"\n❌ Pipeline interrompido: questões faltam em RAGAS")
        print(f"   IDs esperados: {sorted(selected_ids)}")
        print(f"   IDs obtidos: {sorted(ragas_ids)}")
        print(f"   IDs faltantes: {sorted(missing_ids)}\n")
        sys.exit(1)

    # 4. Rodar LLM-as-Judge (passa tanto arquivo de questões quanto RAGAS output!)
    judge_ok = run_llm_judge(
        selected_questions_file=selected_file,
        ragas_output_file=ragas_output_file,
        seed=seed
    )
    if not judge_ok:
        print("\n❌ Pipeline interrompido: LLM-as-Judge falhou")
        sys.exit(1)

    # 5. Consolidar
    result = consolidate_report(num_questions=num_questions)
    if not result:
        print("\n❌ Consolidação falhou")
        sys.exit(1)

    report_file, report = result

    if len(report.get("questions", [])) == 0:
        print("\n❌ Consolidação retornou 0 questões")
        sys.exit(1)

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

    consensus_dist = summary.get("consensus_strength_distribution", {})
    if consensus_dist:
        print(f"\n💪 FORÇA DO CONSENSO:")
        print(f"   Unânime (3/3): {consensus_dist.get('unanimous', 0)} questões")
        print(f"   Maioria (2/3): {consensus_dist.get('majority', 0)} questões")
        print(f"   Nenhum: {consensus_dist.get('none', 0)} questões")

    judge_cfg = report.get("judge_config", {})
    if judge_cfg:
        print(f"\n⚖️  CONFIGURAÇÃO DOS JUÍZES:")
        print(f"   Seed: {judge_cfg.get('seed', 'N/A')}")
        print(f"   Avaliações por questão: {judge_cfg.get('evaluations_per_question', 'N/A')}")
        print(f"   Regra de consenso: {judge_cfg.get('consensus_rule', 'N/A')}")

    print(f"\n📁 ARQUIVOS GERADOS:")
    print(f"   Questões selecionadas: {selected_file.name}")
    print(f"   RAGAS output: {ragas_output_file.name}")
    print(f"   Relatório consolidado: {report_file.name}")
    print(f"   📍 Pasta: api/tools/data/processed/")

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
    parser.add_argument("--evaluators", type=str, default="gemini",
                       help="LLMs avaliadores RAGAS (comma-separated: gemini,gpt-4o-mini,claude). Default: gemini")

    args = parser.parse_args()

    main(num_questions=args.num_questions, seed=args.seed, evaluators=args.evaluators)

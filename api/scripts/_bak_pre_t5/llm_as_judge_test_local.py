#!/usr/bin/env python3
"""
LLM-as-Judge: roda localmente (não em container)
"""

import asyncio
import json
import random
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Force UTF-8 on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Load .env from project root
api_root = Path(__file__).resolve().parent.parent
project_root = api_root.parent
load_dotenv(project_root / ".env")

from openai import AsyncOpenAI

_BRT = timezone(timedelta(hours=-3))

TIE_EPSILON = {
    "faithfulness": 0.12,
    "answer_relevancy": 0.04,
    "context_precision": 0.0,
    "context_recall": 0.0,
    "context_entity_recall": 0.0,
}

JUDGES = {
    "gpt-4o-mini": {"provider": "openai", "model": "gpt-4o-mini"},
    "gemini": {"provider": "gemini", "model": "gemini-2.5-flash-lite"},
    "claude": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
}

# Load prompt from template file
PROMPT_TEMPLATE_FILE = api_root / "app" / "prompts" / "templates" / "llm_judge_prompt.md"
PROMPT_TEMPLATE = PROMPT_TEMPLATE_FILE.read_text(encoding="utf-8")


async def judge_responses(question: str, responses: dict, judge_name: str, judge_config: dict) -> dict:
    """Envia para um juiz avaliar as 3 respostas"""

    # Construir prompt
    prompt_content = PROMPT_TEMPLATE.format(
        question=question,
        response_a=responses["A"],
        response_b=responses["B"],
        response_c=responses["C"],
    )

    if judge_config["provider"] == "openai":
        try:
            client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        except Exception as e:
            print(f"   ⚠️  OpenAI falhou: {e}")
            return {"judge": judge_name, "choice": "A", "confidence": 0.0, "reasoning": "API error", "raw_response": str(e)}

        response = await client.chat.completions.create(
            model=judge_config["model"],
            messages=[{"role": "user", "content": prompt_content}],
            temperature=0.7,
        )
        text = response.choices[0].message.content

    elif judge_config["provider"] == "gemini":
        try:
            import google.generativeai as genai
        except ImportError:
            print(f"   ⚠️  Gemini SDK não instalado - pulando juiz Gemini")
            return {"judge": judge_name, "choice": "A", "confidence": 0.0, "reasoning": "SDK não disponível", "raw_response": "SDK not available"}

        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel(judge_config["model"])
        response = await asyncio.to_thread(
            model.generate_content,
            prompt_content
        )
        text = response.text

    elif judge_config["provider"] == "anthropic":
        try:
            from anthropic import Anthropic
        except ImportError:
            print(f"   ⚠️  Anthropic SDK não instalado - pulando juiz Claude")
            return {"judge": judge_name, "choice": "A", "confidence": 0.0, "reasoning": "SDK não disponível", "raw_response": "SDK not available"}

        client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = await asyncio.to_thread(
            client.messages.create,
            model=judge_config["model"],
            max_tokens=500,
            messages=[{"role": "user", "content": prompt_content}]
        )
        text = response.content[0].text

    # Parse JSON response
    try:
        import re
        json_match = re.search(r'\{[^{}]*"choice"[^{}]*\}', text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
        else:
            result = {"choice": "A", "confidence": 0.5, "reasoning": "Parse error"}
    except:
        result = {"choice": "A", "confidence": 0.5, "reasoning": "Parse error"}

    return {
        "judge": judge_name,
        "prompt_sent": prompt_content,
        "raw_response": text,
        **result
    }


async def main(selected_questions_file: str = None, ragas_output_file: str = None, seed: int = 42):
    # Load selected questions
    if selected_questions_file:
        print(f"📋 Carregando questões selecionadas: {Path(selected_questions_file).name}")
        try:
            with open(selected_questions_file, encoding="utf-8") as f:
                selected_data = json.load(f)
                # Suporta ambos os formatos
                if isinstance(selected_data, dict) and "questions" in selected_data:
                    selected_questions = selected_data["questions"]
                else:
                    selected_questions = selected_data
            print(f"   ✅ {len(selected_questions)} questões carregadas\n")
        except Exception as e:
            print(f"   ❌ Erro: {e}")
            sys.exit(1)
    else:
        print("❌ selected_questions_file não foi fornecido!")
        sys.exit(1)

    # Load RAGAS output
    if ragas_output_file:
        print(f"📊 Carregando RAGAS output: {Path(ragas_output_file).name}")
        try:
            with open(ragas_output_file, encoding="utf-8") as f:
                eval_data = json.load(f)
            print(f"   ✅ Carregado\n")
        except Exception as e:
            print(f"   ❌ Erro: {e}")
            sys.exit(1)
    else:
        print("❌ ragas_output_file não foi fornecido!")
        sys.exit(1)

    # Map RAGAS items by question_id
    com_items_map = {}
    sem_items_map = {}

    for item in eval_data['conditions'][0]['items']:
        if not item.get('errors'):
            q_id = item.get('question_id')
            if q_id:
                com_items_map[q_id] = item

    for item in eval_data['conditions'][1]['items']:
        if not item.get('errors'):
            q_id = item.get('question_id')
            if q_id:
                sem_items_map[q_id] = item

    print(f"✅ RAGAS items:")
    print(f"   COM: {len(com_items_map)} questões")
    print(f"   SEM: {len(sem_items_map)} questões\n")

    # Use only questions that have both COM and SEM results
    test_questions = []
    for q in selected_questions:
        q_id = q.get("question_id")
        if q_id in com_items_map and q_id in sem_items_map:
            test_questions.append({
                "question_data": q,
                "question_id": q_id,
                "item_com": com_items_map[q_id],
                "item_sem": sem_items_map[q_id],
            })
        else:
            missing = []
            if q_id not in com_items_map:
                missing.append("COM")
            if q_id not in sem_items_map:
                missing.append("SEM")
            print(f"⚠️  Q{q_id}: sem resultado RAGAS ({'/'.join(missing)})")

    print(f"🎯 Avaliando {len(test_questions)} questões sincronizadas\n")

    if not test_questions:
        print("❌ Nenhuma questão sincronizada entre selecionadas e RAGAS results")
        print(f"   IDs esperados: {[q.get('question_id') for q in selected_questions]}")
        sys.exit(1)

    random.seed(seed)
    llm_judge_results = []

    for pos, test_q in enumerate(test_questions, 1):
        q_id = test_q["question_id"]
        item_com = test_q["item_com"]
        item_sem = test_q["item_sem"]

        question = item_com.get("question", "")
        ground_truth = item_com.get("ground_truth", "")
        answer_com = item_com.get("answer", "")
        answer_sem = item_sem.get("answer", "")

        print(f"🔬 QUESTÃO {pos}/{len(test_questions)}:")
        print(f"   {question[:80]}...")

        # Duas ordens de avaliação para detectar viés posicional
        all_order_results = []
        for order_num in [1, 2]:
            responses_shuffled = [
                ("ground_truth", ground_truth),
                ("com_ontologia", answer_com),
                ("sem_ontologia", answer_sem),
            ]
            random.shuffle(responses_shuffled)

            # Map para A, B, C
            responses_dict = {}
            mapping = {}
            for p, (source, text) in enumerate(responses_shuffled):
                letter = chr(ord('A') + p)
                responses_dict[letter] = text
                mapping[letter] = source

            # Collect votes from 3 judges
            votes = await asyncio.gather(*[
                judge_responses(question, responses_dict, judge_name, judge_config)
                for judge_name, judge_config in JUDGES.items()
            ])

            # Map back to sources
            for vote in votes:
                vote["choice_source"] = mapping.get(vote["choice"], "unknown")

            all_order_results.append({
                "order": order_num,
                "mapping": mapping,
                "votes": votes,
            })

        # Consolidar dois votos por juiz (order_1 + order_2)
        consolidated_votes = {}
        for judge_name in JUDGES.keys():
            choices_by_order = [
                all_order_results[0]["votes"][i]["choice_source"]
                for i in range(len(JUDGES))
                if all_order_results[0]["votes"][i]["judge"] == judge_name
            ] + [
                all_order_results[1]["votes"][i]["choice_source"]
                for i in range(len(JUDGES))
                if all_order_results[1]["votes"][i]["judge"] == judge_name
            ]
            # Consenso por juiz: 2/2 ou 1/2
            consolidated_votes[judge_name] = max(set(choices_by_order), key=choices_by_order.count) if choices_by_order else None

        # Consenso final entre juízes (maioria 2/3)
        all_choices = list(consolidated_votes.values())
        choice_counts = {}
        for c in all_choices:
            choice_counts[c] = choice_counts.get(c, 0) + 1

        if choice_counts:
            consensus = max(choice_counts, key=choice_counts.get)
            consensus_count = choice_counts[consensus]
            consensus_strength = "unanimous" if consensus_count == 3 else "majority" if consensus_count == 2 else "none"
        else:
            consensus = None
            consensus_count = 0
            consensus_strength = "none"

        print(f"\n   VOTOS (2 ORDENS):")
        for judge_name in JUDGES.keys():
            votes_judge_o1 = [v for v in all_order_results[0]["votes"] if v["judge"] == judge_name][0]["choice_source"]
            votes_judge_o2 = [v for v in all_order_results[1]["votes"] if v["judge"] == judge_name][0]["choice_source"]
            print(f"     {judge_name:15} order1={votes_judge_o1} order2={votes_judge_o2} → {consolidated_votes[judge_name]}")

        print(f"   CONSENSO: {consensus} ({consensus_count}/3) [{consensus_strength}]")

        # RAGAS verdict
        ragas_com = item_com.get("results", {}).get("gemini", {})
        ragas_sem = item_sem.get("results", {}).get("gemini", {})

        cr_com = ragas_com.get("context_recall", 0)
        cr_sem = ragas_sem.get("context_recall", 0)
        ragas_winner = "com_ontologia" if cr_com > cr_sem else "sem_ontologia" if cr_sem > cr_com else "empate"

        print(f"   RAGAS:    context_recall COM={cr_com:.3f} vs SEM={cr_sem:.3f} → {ragas_winner}")

        agreement = "✅ ACORDÂNCIA" if consensus == ragas_winner else "❌ DIVERGÂNCIA"
        print(f"   {agreement}\n")

        llm_judge_results.append({
            "question_id": q_id,
            "question": question,
            "responses": {
                "ground_truth": ground_truth,
                "com_ontologia": answer_com,
                "sem_ontologia": answer_sem,
            },
            "judge_orders": all_order_results,
            "consolidated_votes": consolidated_votes,
            "consensus": consensus,
            "consensus_strength": consensus_strength,
            "ragas_winner": ragas_winner,
            "agreement": consensus == ragas_winner,
        })

    # Save results com DATA E HORA
    timestamp_iso = datetime.now(_BRT).isoformat()
    timestamp_file = datetime.now(_BRT).strftime("%Y%m%d_%H%M%S")

    # Contar consensos por tipo
    consensus_scores = {
        "com_ontologia": sum(1 for r in llm_judge_results if r["consensus"] == "com_ontologia"),
        "sem_ontologia": sum(1 for r in llm_judge_results if r["consensus"] == "sem_ontologia"),
        "ground_truth": sum(1 for r in llm_judge_results if r["consensus"] == "ground_truth"),
    }

    # Calcular RAGAS direction por avaliador e métrica
    ragas_directions = {}
    for evaluator in ["gemini"]:  # Análise apenas por Gemini para agora
        ragas_directions[evaluator] = {}
        for metric in ["faithfulness", "answer_relevancy", "context_precision", "context_recall", "context_entity_recall"]:
            com_values = []
            sem_values = []
            for test_q in test_questions:
                com_val = test_q["item_com"].get("results", {}).get(evaluator, {}).get(metric)
                sem_val = test_q["item_sem"].get("results", {}).get(evaluator, {}).get(metric)
                if com_val is not None:
                    com_values.append(com_val)
                if sem_val is not None:
                    sem_values.append(sem_val)

            if com_values and sem_values:
                com_avg = sum(com_values) / len(com_values)
                sem_avg = sum(sem_values) / len(sem_values)
                epsilon = TIE_EPSILON.get(metric, 0.0)

                if abs(com_avg - sem_avg) <= epsilon:
                    direction = "tie"
                elif com_avg > sem_avg:
                    direction = "com_ontologia"
                else:
                    direction = "sem_ontologia"

                ragas_directions[evaluator][metric] = {
                    "com_avg": round(com_avg, 6),
                    "sem_avg": round(sem_avg, 6),
                    "delta": round(sem_avg - com_avg, 6),
                    "direction": direction,
                }

    # Matriz de concordância (avaliador × métrica)
    judge_by_metric_matrix = {}
    for evaluator in ["gemini"]:
        judge_by_metric_matrix[evaluator] = {}
        for metric in ["faithfulness", "answer_relevancy", "context_precision", "context_recall", "context_entity_recall"]:
            judge_by_metric_matrix[evaluator][metric] = {
                "agree": 0,
                "opposite": 0,
                "not_comparable": 0,
            }

            if metric in ragas_directions.get(evaluator, {}):
                ragas_direction = ragas_directions[evaluator][metric]["direction"]

                # Contar votos dos juízes por consenso
                for result in llm_judge_results:
                    judge_consensus = result.get("consensus")

                    if judge_consensus == "empate" or ragas_direction == "tie":
                        judge_by_metric_matrix[evaluator][metric]["not_comparable"] += 1
                    elif judge_consensus == ragas_direction or (ragas_direction == "empate" and judge_consensus is None):
                        judge_by_metric_matrix[evaluator][metric]["agree"] += 1
                    else:
                        judge_by_metric_matrix[evaluator][metric]["opposite"] += 1

                # Calcular divergence_rate
                agree = judge_by_metric_matrix[evaluator][metric]["agree"]
                opposite = judge_by_metric_matrix[evaluator][metric]["opposite"]
                total = agree + opposite
                if total > 0:
                    judge_by_metric_matrix[evaluator][metric]["divergence_rate"] = round(opposite / total, 4)
                else:
                    judge_by_metric_matrix[evaluator][metric]["divergence_rate"] = 0.0

    # Judge config
    judge_config = {
        "seed": seed,
        "evaluations_per_question": 2,  # 2 ordens
        "judges": list(JUDGES.keys()),
        "consensus_rule": "majority (2/3)",
    }

    output = {
        "timestamp": timestamp_iso,
        "test_type": f"LLM-as-Judge ({len(test_questions)} questões sincronizadas)",
        "judges": list(JUDGES.keys()),
        "judge_config": judge_config,
        "source_file": str(ragas_output_file),
        "results": llm_judge_results,
        "ragas_directions": ragas_directions,
        "judge_metric_agreement": judge_by_metric_matrix,
        "summary": {
            "total_questions": len(llm_judge_results),
            "agreements": sum(1 for r in llm_judge_results if r["agreement"]),
            "divergences": sum(1 for r in llm_judge_results if not r["agreement"]),
            "consensus_scores": consensus_scores,
            "consensus_strength_distribution": {
                "unanimous": sum(1 for r in llm_judge_results if r.get("consensus_strength") == "unanimous"),
                "majority": sum(1 for r in llm_judge_results if r.get("consensus_strength") == "majority"),
                "none": sum(1 for r in llm_judge_results if r.get("consensus_strength") == "none"),
            }
        }
    }

    # Criar subpasta llm_judge em api/tools/data/processed/
    output_dir = project_root / "api" / "tools" / "data" / "processed" / "llm_judge"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"llm_judge_{timestamp_file}.json"
    output_file.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{'='*70}")
    print(f"✅ RESUMO:")
    print(f"   Total: {output['summary']['total_questions']} questões")
    print(f"   Acordos: {output['summary']['agreements']}")
    print(f"   Divergências: {output['summary']['divergences']}")
    print(f"   Arquivo: {output_file.name}")
    print(f"   Caminho: {output_file}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    selected_questions_file = sys.argv[1] if len(sys.argv) > 1 else None
    ragas_output_file = sys.argv[2] if len(sys.argv) > 2 else None
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 42
    asyncio.run(main(selected_questions_file, ragas_output_file, seed))

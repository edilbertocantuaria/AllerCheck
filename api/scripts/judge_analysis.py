"""Lógica pura de votação dos juízes e da Definição A (sem I/O)."""

import random
from collections import Counter

import eval_config

SOURCES = ("ground_truth", "com_ontologia", "sem_ontologia")
LETTERS = ("A", "B", "C")

METRICS_RESPONSE = ("faithfulness", "answer_relevancy")
METRICS_RETRIEVAL = ("context_recall", "context_precision", "context_entity_recall")
METRICS = METRICS_RESPONSE + METRICS_RETRIEVAL

TIE_EPSILON = eval_config.tie_epsilon()
_EPS_SLACK = 1e-9

COMPARABLE_CONSENSUS = ("com_ontologia", "sem_ontologia")


def build_orders(seed, question_id):
    """Duas ordens por questão: sorteio com seed por questão e rotação de uma posição.

    A rotação garante que toda condição mude de posição entre as duas ordens.
    """
    rng = random.Random(f"{seed}-{question_id}")
    first = list(SOURCES)
    rng.shuffle(first)
    second = [first[-1]] + first[:-1]
    return [dict(zip(LETTERS, first)), dict(zip(LETTERS, second))]


def judge_status(source_order_1, source_order_2):
    if source_order_1 is None or source_order_2 is None:
        return "error", None
    if source_order_1 != source_order_2:
        return "inconsistent", None
    return "valid", source_order_1


def consensus_from_votes(valid_votes):
    """valid_votes: {juiz: condição}, só votos válidos."""
    counts = Counter(valid_votes.values())
    if not counts:
        return None, "none"
    source, n = counts.most_common(1)[0]
    if n >= 3:
        return source, "unanimous"
    if n == 2:
        return source, "majority"
    return None, "none"


def same_letter_both_orders(judge_orders, judge_name):
    """Quantas vezes o juiz escolheu a mesma letra nas duas ordens (sinal de viés de posição)."""
    letters = []
    for order in judge_orders:
        vote = next((v for v in order["votes"] if v["judge"] == judge_name), None)
        letters.append(vote.get("choice") if vote else None)
    return 1 if len(letters) == 2 and letters[0] is not None and letters[0] == letters[1] else 0


def pooled_consensus(sources):
    """Sensibilidade: soma todos os votos legíveis (juízes × ordens), inclusive os de juiz inconsistente.

    sources: lista de condições escolhidas (None = erro, ignorado). Vence a pluralidade estrita; empate no topo = None.
    """
    counts = Counter(x for x in sources if x is not None)
    total = sum(counts.values())
    if not total:
        return {"counts": {}, "total_votes": 0, "consensus": None, "share": None}
    ranked = counts.most_common()
    tied = len(ranked) > 1 and ranked[0][1] == ranked[1][1]
    top_source, top_n = ranked[0]
    return {
        "counts": dict(counts),
        "total_votes": total,
        "consensus": None if tied else top_source,
        "share": round(top_n / total, 4),
    }


def ragas_direction(com_value, sem_value, metric):
    if com_value is None or sem_value is None:
        return None, None
    delta = com_value - sem_value
    if abs(delta) <= TIE_EPSILON[metric] + _EPS_SLACK:
        return delta, "tie"
    return delta, "com_ontologia" if delta > 0 else "sem_ontologia"


def classify(direction, consensus):
    if direction in (None, "tie") or consensus not in COMPARABLE_CONSENSUS:
        return "not_comparable"
    return "agree" if direction == consensus else "opposite"


def present_evaluators(items):
    names = set()
    for item in items:
        for side in ("com_results", "sem_results"):
            names.update((item.get(side) or {}).keys())
    return sorted(names)


def compare_ragas_with_judges(items):
    """items: [{question_id, consensus, com_results, sem_results}].

    Retorna (por_questão, tabela). Direção calculada por questão, nunca por média.
    """
    evaluators = present_evaluators(items)
    per_question = {}
    table = {
        ev: {
            m: {
                "level": "answer" if m in METRICS_RESPONSE else "retrieval",
                "agree": 0,
                "opposite": 0,
                "not_comparable": 0,
                "divergence_rate": None,
            }
            for m in METRICS
        }
        for ev in evaluators
    }

    for item in items:
        qid = item["question_id"]
        per_question[qid] = {}
        for ev in evaluators:
            com = (item.get("com_results") or {}).get(ev) or {}
            sem = (item.get("sem_results") or {}).get(ev) or {}
            per_question[qid][ev] = {}
            for m in METRICS:
                delta, direction = ragas_direction(com.get(m), sem.get(m), m)
                outcome = classify(direction, item.get("consensus"))
                per_question[qid][ev][m] = {
                    "com": com.get(m),
                    "sem": sem.get(m),
                    "delta_com_minus_sem": None if delta is None else round(delta, 6),
                    "direction": direction,
                    "vs_judges": outcome,
                }
                table[ev][m][outcome] += 1

    for ev in evaluators:
        for m in METRICS:
            cell = table[ev][m]
            denom = cell["agree"] + cell["opposite"]
            cell["divergence_rate"] = round(cell["opposite"] / denom, 4) if denom else None

    return per_question, table

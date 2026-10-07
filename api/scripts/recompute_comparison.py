"""Recalcula a tabela RAGAS contra juízes de um llm_judge_*.json usando um evaluation_*.json atualizado.

Uso (host, a partir de api/):
  python scripts/recompute_comparison.py <llm_judge_*.json> <evaluation_*.json>

Não chama nenhum juiz nem avaliador (custo zero): os votos e consensos ficam como estão; só `ragas_vs_judges`
e `ragas_vs_judges_pooled` são refeitos com os valores RAGAS do arquivo novo. Grava um llm_judge_*.json novo.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from judge_analysis import compare_ragas_with_judges

_BRT = timezone(timedelta(hours=-3))


def main(judge_file, evaluation_file):
    judge = json.loads(Path(judge_file).read_text(encoding="utf-8"))
    evaluation = json.loads(Path(evaluation_file).read_text(encoding="utf-8"))
    items = {c["name"]: {it["question_id"]: it for it in c["items"]} for c in evaluation["conditions"]}

    strict, pooled = [], []
    for r in judge["results"]:
        q = r["question_id"]
        com, sem = items["com_ontologia"].get(q), items["sem_ontologia"].get(q)
        if com is None or sem is None or com.get("errors") or sem.get("errors"):
            print(f"⚠️  Q{q}: sem resultado RAGAS no arquivo novo; mantida fora da comparação")
            continue
        base = {"question_id": q, "com_results": com.get("results") or {}, "sem_results": sem.get("results") or {}}
        strict.append({**base, "consensus": r["consensus"]})
        pooled.append({**base, "consensus": r["pooled"]["consensus"]})

    per_q, table = compare_ragas_with_judges(strict)
    per_q_pooled, table_pooled = compare_ragas_with_judges(pooled)
    for r in judge["results"]:
        if r["question_id"] in per_q:
            r["ragas_vs_judges"] = per_q[r["question_id"]]
            r["ragas_vs_judges_pooled"] = per_q_pooled[r["question_id"]]
    judge["summary"]["ragas_vs_judges"] = table
    judge["summary"]["ragas_vs_judges_pooled"] = table_pooled
    judge["ragas_evaluators"] = sorted(table.keys())
    judge["recomputed"] = {
        "timestamp": datetime.now(_BRT).isoformat(),
        "from_judge_file": Path(judge_file).name,
        "ragas_file": Path(evaluation_file).name,
        "note": "tabelas RAGAS contra juízes refeitas; votos e consensos dos juízes não foram alterados",
    }
    judge["source_file"] = str(evaluation_file)
    out = Path(judge_file).parent / f"llm_judge_{datetime.now(_BRT).strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(judge, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Recalculado ({len(strict)} questões). Arquivo: {out.name}")
    for ev, mets in table.items():
        for m, row in mets.items():
            print(f"   {ev:7} {m:22} agree={row['agree']:2} opposite={row['opposite']:2} n/c={row['not_comparable']:2} divergência={row['divergence_rate']}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python scripts/recompute_comparison.py <llm_judge_*.json> <evaluation_*.json>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])

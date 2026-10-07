"""Seleciona a amostra final (262 perguntas, seed fixa) e grava um arquivo imutável.

n = 262: Cochran (1977), N=821, z=1,96, p=0,5, e=0,05. A ordem do sorteio é preservada; os subconjuntos
(piloto de 20, 60 e 100) são os primeiros k itens dessa ordem, portanto também são amostras aleatórias
e estão contidos uns nos outros. O arquivo não é sobrescrito: se já existir um de 262, o script para.
"""
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import openpyxl

SEED = 42
N = 262
SUBSETS = {"pilot_20": 20, "sub_60": 60, "sub_100": 100}

api_root = Path(__file__).resolve().parent.parent
xlsx = api_root / "tools" / "data" / "raw" / "evaluation" / "filtred_alergia_medicamentos.xlsx"
out_dir = api_root / "tools" / "data" / "processed" / "evaluation"

existing = sorted(out_dir.glob("questoes_selecionadas_262_*.json"))
if existing:
    print(f"❌ Já existe {existing[-1].name}. A amostra final é imutável; apague manualmente só se for refazer tudo.")
    sys.exit(1)

ws = openpyxl.load_workbook(xlsx).active
headers = [c.value for c in ws[1]]
rows = [dict(zip(headers, r)) for r in ws.iter_rows(min_row=2, values_only=True) if any(v is not None for v in r)]
print(f"{len(rows)} linhas no xlsx; colunas: {headers}")
if len(rows) < N:
    print("❌ Menos linhas que a amostra pedida.")
    sys.exit(1)

random.seed(SEED)
picked = random.sample(range(len(rows)), N)

# colunas de pergunta/resposta: as mesmas usadas na seleção anterior
qk = next(h for h in headers if h and "perg" in str(h).lower() or h in ("question", "pergunta"))
ak = next(h for h in headers if h and ("resp" in str(h).lower() or h in ("answer", "ground_truth")))

questions = []
for pos, idx in enumerate(picked):
    r = rows[idx]
    questions.append({
        "question_id": idx + 1,
        "index": idx,
        "sample_order": pos + 1,
        "question": r[qk],
        "answer": r[ak],
        "dataset_source": xlsx.name,
        "row_number": idx,
        "subsets": [name for name, k in SUBSETS.items() if pos < k],
    })

ts = datetime.now(timezone(timedelta(hours=-3)))
payload = {
    "metadata": {
        "timestamp": ts.isoformat(),
        "total_questions": N,
        "seed": SEED,
        "method": "random.seed(42); random.sample(range(N_total), 262)",
        "cochran": {"N": 821, "z": 1.96, "p": 0.5, "e": 0.05},
        "subsets": SUBSETS,
        "dataset_source": xlsx.name,
    },
    "questions": questions,
}
out = out_dir / f"questoes_selecionadas_262_{ts.strftime('%Y%m%d_%H%M%S')}.json"
out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

# conferência contra a seleção antiga de 50 (mesma seed): todas devem estar dentro das 262
old = sorted(out_dir.glob("questoes_selecionadas_2026*.json"))
old = [p for p in old if "_262_" not in p.name]
if old:
    old_ids = {q["question_id"] for q in json.loads(old[-1].read_text(encoding="utf-8"))["questions"]}
    new_ids = {q["question_id"] for q in questions}
    print(f"Seleção antiga ({old[-1].name}): {len(old_ids & new_ids)}/{len(old_ids)} dentro das 262")
print(f"✅ {len(questions)} perguntas → {out}")

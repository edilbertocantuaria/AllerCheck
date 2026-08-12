#!/usr/bin/env python3
import json

with open("tools/data/processed/evaluation/ontologia/ontologia_raw.json", encoding="utf-8") as f:
    data = json.load(f)

candidatos = [d for d in data if "nimesulid" in d.get("nome_original", "").lower()
              or "nimesulid" in d.get("nome_ingles", "").lower()]

print("TAREFA 1: REGISTRO COMPLETO DA NIMESULIDA\n")
for c in candidatos:
    print(json.dumps(c, indent=2, ensure_ascii=False))
    print("\n" + "="*80 + "\n")

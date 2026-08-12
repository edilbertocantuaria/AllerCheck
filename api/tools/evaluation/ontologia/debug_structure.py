#!/usr/bin/env python3
"""Verifica a estrutura bruta da aspirina e nimesulida no ontologia_raw.json"""

import json
from pathlib import Path

onto_path = Path("tools/data/processed/evaluation/ontologia/ontologia_raw.json")

with open(onto_path, encoding="utf-8") as f:
    data = json.load(f)

# Procurar aspirina e nimesulida
aspirina = None
nimesulida = None

for med in data:
    nome_ing = (med.get("nome_ingles") or "").lower()
    nome_orig = (med.get("nome_original") or "").lower()

    if "aspirin" in nome_ing or "aspirin" in nome_orig:
        aspirina = med
        print("="*100)
        print("ASPIRINA ENCONTRADA:")
        print("="*100)
        print(json.dumps(med, ensure_ascii=False, indent=2))
        print("\n")

    if "nimesulida" in nome_ing or "nimesulida" in nome_orig:
        nimesulida = med
        print("="*100)
        print("NIMESULIDA ENCONTRADA:")
        print("="*100)
        print(json.dumps(med, ensure_ascii=False, indent=2))
        print("\n")

if not aspirina:
    print("❌ Aspirina NÃO encontrada")
if not nimesulida:
    print("❌ Nimesulida NÃO encontrada")

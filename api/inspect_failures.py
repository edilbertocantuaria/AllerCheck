#!/usr/bin/env python3
import json
from pathlib import Path

# Verificar os dois arquivos mais recentes de RAGAS
eval_dir = Path('tools/data/processed/evaluation')
ragas_files = sorted(eval_dir.glob('ragas_evaluation_2026*.json'), key=lambda f: f.stat().st_mtime, reverse=True)[:2]

for ragas_file in ragas_files:
    print(f"\n{'='*80}")
    print(f"ARQUIVO: {ragas_file.name}")
    print(f"{'='*80}\n")

    with open(ragas_file, encoding='utf-8') as f:
        data = json.load(f)

    print(f"sample_count: {data.get('sample_count')}")
    print(f"use_ontology: {data.get('use_ontology')}")
    print(f"generated_at: {data.get('generated_at')}\n")

    # Procurar pelos itens que falharam
    for item in data['scores']:
        if item['question_id'] in [11, 29]:
            print(f"\n[question_id {item['question_id']}]")
            print(f"  Question: {item['question'][:70]}...")
            print(f"  Contexts count: {len(item.get('contexts', []))}")
            print(f"  Has results: {bool(item.get('results'))}")
            print(f"  Errors: {item.get('errors')}")

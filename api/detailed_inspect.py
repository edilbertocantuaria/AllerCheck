#!/usr/bin/env python3
import json
from pathlib import Path

eval_dir = Path('tools/data/processed/evaluation')
ragas_files = sorted(eval_dir.glob('ragas_evaluation_2026*.json'), key=lambda f: f.stat().st_mtime, reverse=True)[:2]

for ragas_file in ragas_files:
    print(f"\n{'='*100}")
    print(f"ARQUIVO: {ragas_file.name}")
    print(f"{'='*100}")

    with open(ragas_file, encoding='utf-8') as f:
        data = json.load(f)

    print(f"\nsample_count: {data.get('sample_count')}")
    print(f"use_ontology: {data.get('use_ontology')}\n")

    # Encontrar TODOS os itens com contexts vazio/ausente ou com erros
    items_with_issues = []
    for item in data['scores']:
        contexts = item.get('contexts', [])
        errors = item.get('errors', [])

        if len(contexts) == 0 or errors:
            items_with_issues.append({
                'id': item['question_id'],
                'question': item['question'],
                'contexts_count': len(contexts),
                'contexts_field': item.get('contexts'),
                'errors': errors,
                'has_results': bool(item.get('results'))
            })

    print(f"Itens com contexts=0 ou com errors: {len(items_with_issues)}\n")
    for issue in items_with_issues:
        print(f"[Q{issue['id']}] {issue['question'][:75]}")
        print(f"     contexts count: {issue['contexts_count']}")
        print(f"     contexts field: {issue['contexts_field']}")
        print(f"     errors: {issue['errors']}")
        print(f"     has_results: {issue['has_results']}")
        print()

#!/usr/bin/env python3
"""
Quick test: compare RAG response WITH vs WITHOUT ontology expansion.
Shows impact on retrieved chunks and answer quality.
"""

import asyncio
import json
from pathlib import Path
from app.services.rag_service import RAGService
from app.schemas import ChatRequest

# Sample questions with medications
TEST_CASES = [
    {
        "question": "Patient allergic to amoxicillin - can they take augmentin?",
        "medication": "amoxicillin",
    },
    {
        "question": "Is mirtazapine safe if allergic to tricyclic antidepressants?",
        "medication": "mirtazapine",
    },
    {
        "question": "Ibuprofen allergy - what are the alternatives?",
        "medication": "ibuprofen",
    },
]


async def test_ontology_impact():
    """Compare RAG results with vs without ontology."""

    print("\n" + "="*70)
    print("ONTOLOGY IMPACT TEST: With vs Without RxNorm Expansion")
    print("="*70)

    for idx, test_case in enumerate(TEST_CASES, 1):
        question = test_case["question"]
        medication = test_case["medication"]

        print(f"\n\n📋 Test {idx}: {question}")
        print(f"   Medication: {medication}\n")

        # Test WITH ontology
        print("   ✅ WITH Ontology Expansion (RxNorm):")
        rag_with = RAGService(use_ontology=True, use_hyde=False)
        history_str = rag_with.build_history_str([])
        rewritten_q, in_scope = rag_with._rewrite_query(question, history_str)

        if in_scope:
            from app.services.ontology_expander import expand_query_from_rxnorm
            expansion = await expand_query_from_rxnorm(rewritten_q, max_terms=5)

            docs_with, ont_added = await rag_with._retrieve(rewritten_q, expansion)
            print(f"      - Expansion terms: {len(expansion)}")
            if expansion:
                terms = [t.get('en') for t in expansion[:3]]
                print(f"        {', '.join(terms)}")
            print(f"      - Retrieved chunks: {len(docs_with)}")
            print(f"      - From ontology: {ont_added}")
        else:
            print(f"      - Out of scope")

        # Test WITHOUT ontology
        print("\n   ❌ WITHOUT Ontology (baseline):")
        rag_without = RAGService(use_ontology=False, use_hyde=False)
        history_str = rag_without.build_history_str([])
        rewritten_q, in_scope = rag_without._rewrite_query(question, history_str)

        if in_scope:
            docs_without, _ = await rag_without._retrieve(rewritten_q, [])
            print(f"      - Expansion terms: 0")
            print(f"      - Retrieved chunks: {len(docs_without)}")
        else:
            print(f"      - Out of scope")

        # Compare
        if in_scope:
            delta = len(docs_with) - len(docs_without)
            pct = (delta / len(docs_without) * 100) if len(docs_without) > 0 else 0
            print(f"\n   📊 Impact: +{delta} chunks ({pct:+.1f}%)")


if __name__ == "__main__":
    asyncio.run(test_ontology_impact())
    print("\n" + "="*70 + "\n")

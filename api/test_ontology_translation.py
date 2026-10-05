#!/usr/bin/env python3
"""
Teste de tradução de termos de ontologia via LLM.
"""

import asyncio
from app.services.ontology_translator import translate_ontology_terms_async

# Termos da ontologia que vieram do último teste
test_terms = [
    "carbenicillina",
    "temocillin",
    "duloxetina",
    "gepirone",
    "tryptophan",
    "amoxicillin",
    "vilazodone",
    "ticarcillin",
]

async def main():
    print("=" * 80)
    print("🧪 TESTE DE TRADUÇÃO DE TERMOS DE ONTOLOGIA VIA LLM")
    print("=" * 80)
    print(f"\nTermos a traduzir ({len(test_terms)}):")
    for term in test_terms:
        print(f"  - {term}")

    print("\n" + "=" * 80)
    print("⏳ Traduzindo via LLM (gpt-4o-mini)...\n")

    translations = await translate_ontology_terms_async(test_terms)

    print("=" * 80)
    print("✅ RESULTADO DAS TRADUÇÕES")
    print("=" * 80)

    for original, translated in sorted(translations.items()):
        print(f"  {original:20} → {translated}")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    asyncio.run(main())

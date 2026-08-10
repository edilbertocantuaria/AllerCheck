#!/usr/bin/env python3
"""
Contagem de mentions de medicamentos no corpus Pinecone.
Compara densidade de aspirina vs dipirona.
"""

import os
import sys
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parents[4] / "OneDrive" / "Documentos" / "AllerCheck"
sys.path.insert(0, str(PROJECT_ROOT / "api"))

from langchain_community.vectorstores import Pinecone as PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from app.config import INDEX_NAME

print(f"📍 Conectando ao Pinecone index: {INDEX_NAME}")

embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

try:
    vectorstore = PineconeVectorStore.from_existing_index(
        index_name=INDEX_NAME,
        embedding=embeddings,
    )
except Exception as e:
    print(f"❌ Erro ao conectar: {e}")
    sys.exit(1)

# Termos para buscar
aspirina_terms = ["aspirina", "AAS", "ácido acetilsalicílico", "acetilsalicílico"]
dipirona_terms = ["dipirona", "metamizol", "dipyrone"]

def search_terms(terms, label):
    """Busca múltiplos termos e retorna chunks únicos."""
    all_docs = {}

    for term in terms:
        print(f"\n  🔍 Buscando '{term}'...")
        try:
            # Buscar com alta k para capturar mais mentions
            results = vectorstore.similarity_search(term, k=50)

            for doc in results:
                key = doc.page_content[:150]  # Usar primeiras 150 chars como ID único
                if key not in all_docs:
                    all_docs[key] = {
                        "content": doc.page_content[:200],
                        "source": doc.metadata.get("source", "?"),
                        "terms_matched": []
                    }
                all_docs[key]["terms_matched"].append(term)

            print(f"     → {len(results)} chunks recuperados")
        except Exception as e:
            print(f"     ⚠️  Erro: {e}")

    # Contar mentions totais
    total_mentions = sum(len(doc["terms_matched"]) for doc in all_docs.values())

    print(f"\n📊 {label}:")
    print(f"   • Chunks únicos: {len(all_docs)}")
    print(f"   • Mentions totais (com duplicatas por termo): {total_mentions}")

    if all_docs:
        # Top 5 chunks
        print(f"\n   Top 3 chunks por relevância:")
        for i, (key, doc) in enumerate(list(all_docs.items())[:3], 1):
            print(f"\n     [{i}] {doc['source']}")
            print(f"         Termos: {doc['terms_matched']}")
            print(f"         Preview: {doc['content'][:100]}...")

    return all_docs

print("\n" + "="*70)
print("🩺 CONTAGEM DE MENTIONS - ASPIRINA")
print("="*70)
aspirina_docs = search_terms(aspirina_terms, "ASPIRINA")

print("\n" + "="*70)
print("🩺 CONTAGEM DE MENTIONS - DIPIRONA")
print("="*70)
dipirona_docs = search_terms(dipirona_terms, "DIPIRONA")

# Comparação
print("\n" + "="*70)
print("📈 COMPARAÇÃO")
print("="*70)
aspirina_count = len(aspirina_docs)
dipirona_count = len(dipirona_docs)

print(f"\n  Aspirina:  {aspirina_count} chunks únicos")
print(f"  Dipirona:  {dipirona_count} chunks únicos")

if dipirona_count > 0:
    ratio = aspirina_count / dipirona_count
    print(f"  Razão:     {ratio:.2f}x")
    if ratio < 1:
        print(f"  ➜ Dipirona tem {dipirona_count/aspirina_count:.1f}x mais conteúdo")
    else:
        print(f"  ➜ Aspirina tem {ratio:.1f}x mais conteúdo")

print("\n✅ Contagem concluída!")

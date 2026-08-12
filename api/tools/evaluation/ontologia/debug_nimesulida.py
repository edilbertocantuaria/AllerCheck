#!/usr/bin/env python3
"""Investigação profunda da nimesulida"""

import json
import networkx as nx
from pathlib import Path

print("="*100)
print("TAREFA 1: REGISTRO COMPLETO DA NIMESULIDA NO ONTOLOGIA_RAW.JSON")
print("="*100)

with open("tools/data/processed/evaluation/ontologia/ontologia_raw.json", encoding="utf-8") as f:
    raw_data = json.load(f)

candidatos = [d for d in raw_data if "nimesulid" in d.get("nome_original", "").lower()
              or "nimesulid" in d.get("nome_ingles", "").lower()]

print(f"\nEncontrados {len(candidatos)} registro(s):\n")
for c in candidatos:
    print(json.dumps(c, indent=2, ensure_ascii=False))
    print("\n")

# Extrair RxCUI da nimesulida
nimesulida_rxcui = candidatos[0].get("rxcui") if candidatos else None
print(f"\n✅ RxCUI da nimesulida no nosso dado: {nimesulida_rxcui}")

print("\n" + "="*100)
print("TAREFA 3: INSPEÇÃO DO NÓ NIMESULIDA NO GRAFO (ontologia_farma.json)")
print("="*100)

grafo_path = Path("tools/data/processed/evaluation/ontologia/ontologia_farma.json")
if grafo_path.exists():
    with open(grafo_path, encoding="utf-8") as f:
        grafo_data = json.load(f)

    graph = nx.node_link_graph(grafo_data)

    # Buscar nós que contenham "nimesulid"
    nos_nimesulida = [n for n in graph.nodes if "nimesulid" in str(n).lower()]
    print(f"\n🔍 Nós encontrados no grafo: {len(nos_nimesulida)}")
    print(f"   {nos_nimesulida}\n")

    for no in nos_nimesulida:
        print(f"\n{'='*100}")
        print(f"NÓ: {no}")
        print(f"{'='*100}")

        # Vizinhos (arestas saindo)
        vizinhos_saida = list(graph.successors(no))
        print(f"\n📤 ARESTAS SAINDO ({len(vizinhos_saida)} vizinhos):")
        for vizinho in vizinhos_saida[:20]:  # Primeiros 20
            edge_data = graph.get_edge_data(no, vizinho)
            print(f"   → {vizinho}")
            print(f"     Dados: {edge_data}")

        if len(vizinhos_saida) > 20:
            print(f"   ... e mais {len(vizinhos_saida) - 20} vizinhos")

        # Predecessores (arestas entrando)
        predecessores = list(graph.predecessors(no))
        print(f"\n📥 ARESTAS ENTRANDO ({len(predecessores)} predecessores):")
        for pred in predecessores[:20]:
            edge_data = graph.get_edge_data(pred, no)
            print(f"   ← {pred}")
            print(f"     Dados: {edge_data}")

        if len(predecessores) > 20:
            print(f"   ... e mais {len(predecessores) - 20} predecessores")
else:
    print(f"❌ Arquivo não encontrado: {grafo_path}")

print("\n" + "="*100)
print("FIM DA INVESTIGAÇÃO")
print("="*100)

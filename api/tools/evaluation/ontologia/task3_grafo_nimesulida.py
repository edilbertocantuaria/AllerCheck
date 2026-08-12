#!/usr/bin/env python3
import json
import networkx as nx

print("TAREFA 3: INSPEÇÃO DO NÓ NIMESULIDA NO GRAFO\n")

try:
    with open("tools/data/processed/evaluation/ontologia/ontologia_farma.json", encoding="utf-8") as f:
        grafo_data = json.load(f)

    graph = nx.node_link_graph(grafo_data)
    print(f"Grafo carregado: {len(graph.nodes)} nós, {len(graph.edges)} arestas\n")

    # Buscar nós com "nimesulid"
    nos_nimesulida = [n for n in graph.nodes if "nimesulid" in str(n).lower()]
    print(f"Nós encontrados: {nos_nimesulida}\n")

    if not nos_nimesulida:
        print("❌ Nenhum nó com 'nimesulida' encontrado no grafo!")
        exit(1)

    for no in nos_nimesulida:
        print(f"\n{'='*80}")
        print(f"NÓ: {no}")
        print(f"{'='*80}")

        # Vizinhos (successors = arestas saindo)
        vizinhos = list(graph.successors(no))
        print(f"\n📤 ARESTAS SAINDO ({len(vizinhos)} vizinhos):")

        if vizinhos:
            for viz in vizinhos[:30]:  # Primeiros 30
                edge = graph.get_edge_data(no, viz)
                print(f"   → {viz}")
                if edge:
                    print(f"      Dados: {json.dumps(edge, ensure_ascii=False)}")
            if len(vizinhos) > 30:
                print(f"   ... e mais {len(vizinhos) - 30}")
        else:
            print("   (nenhum)")

        # Predecessores (arestas entrando)
        predecessores = list(graph.predecessors(no))
        print(f"\n📥 ARESTAS ENTRANDO ({len(predecessores)} predecessores):")

        if predecessores:
            for pred in predecessores[:30]:
                edge = graph.get_edge_data(pred, no)
                print(f"   ← {pred}")
                if edge:
                    print(f"      Dados: {json.dumps(edge, ensure_ascii=False)}")
            if len(predecessores) > 30:
                print(f"   ... e mais {len(predecessores) - 30}")
        else:
            print("   (nenhum)")

except Exception as e:
    print(f"❌ Erro: {e}")
    import traceback
    traceback.print_exc()

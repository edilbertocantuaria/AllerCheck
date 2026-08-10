"""
Constrói grafo ontológico de medicamentos usando NetworkX.
Lê ontologia_raw.json e exporta em formatos node-link JSON e GraphML.
"""

import json
import logging
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple
import networkx as nx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def normalize_node_name(name: str) -> str:
    """Normaliza nome de nó: lowercase, sem espaços extras."""
    if not name:
        return ""
    return name.strip().lower()


def load_ontologia(input_path: Path) -> List[Dict]:
    """Carrega ontologia_raw.json."""
    logger.info(f"Carregando ontologia de {input_path}")
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    logger.info(f"Total de medicamentos carregados: {len(data)}")
    return data


def build_grafo(ontologia: List[Dict]) -> nx.DiGraph:
    """
    Constrói grafo direcional com nós e arestas conforme as regras.
    """
    G = nx.DiGraph()

    # Rastrear arestas já adicionadas para deduplicação
    arestas_adicionadas: Set[Tuple] = set()

    # Estatísticas de arestas por tipo
    edge_counts = defaultdict(int)

    logger.info("Processando medicamentos e construindo grafo...")

    for med_idx, med in enumerate(ontologia):
        if med_idx % 50 == 0:
            logger.info(f"  Processados {med_idx}/{len(ontologia)} medicamentos")

        nome_norm = normalize_node_name(med.get("nome_normalizado", ""))
        if not nome_norm:
            continue

        nome_original = med.get("nome_original", "")
        rxcui = med.get("rxcui", "")

        # Atributos do nó principal
        node_attrs = {
            "nome_original": nome_original,
        }
        if rxcui:
            node_attrs["rxcui"] = rxcui

        # Classes ATC (pode haver múltiplas)
        classes_atc = med.get("classes_atc", []) or []
        if classes_atc:
            # Atribuir a primeira classe como principal (mais relevante)
            class_id_principal = classes_atc[0].get("classId", "")
            class_name_principal = classes_atc[0].get("className", "")
            if class_id_principal:
                node_attrs["classe_atc"] = class_id_principal
            if class_name_principal:
                node_attrs["classe_atc_nome"] = class_name_principal

        # Adicionar nó
        G.add_node(nome_norm, **node_attrs)

        # ===== 1. SYNONYMOF (sinonimos_en + sinonimos_rxnorm, bidirecional) =====
        sinonimos_en = med.get("sinonimos_en", []) or []
        sinonimos_rxnorm = med.get("sinonimos_rxnorm", []) or []

        # Limitar sinonimos_rxnorm a 10
        sinonimos_rxnorm = sinonimos_rxnorm[:10]

        todos_sinonimos_en = list(set(sinonimos_en + sinonimos_rxnorm))

        for sin in todos_sinonimos_en:
            sin_norm = normalize_node_name(sin)
            if not sin_norm or sin_norm == nome_norm:
                continue

            G.add_node(sin_norm, tipo="sinonimo")

            # Aresta bidirecional
            edge_tuple_fw = (nome_norm, sin_norm, "synonymOf")
            edge_tuple_bw = (sin_norm, nome_norm, "synonymOf")

            if edge_tuple_fw not in arestas_adicionadas:
                G.add_edge(nome_norm, sin_norm, relation="synonymOf", source="whodrug_rxnorm")
                arestas_adicionadas.add(edge_tuple_fw)
                edge_counts["synonymOf"] += 1

            if edge_tuple_bw not in arestas_adicionadas:
                G.add_edge(sin_norm, nome_norm, relation="synonymOf", source="whodrug_rxnorm")
                arestas_adicionadas.add(edge_tuple_bw)
                edge_counts["synonymOf"] += 1

        # ===== 2. SAMECLASSAS + CROSSREACTSWITH (membros_classe, bidirecional) =====
        membros_classe = med.get("membros_classe", []) or []

        for membro in membros_classe:
            if not isinstance(membro, dict):
                continue

            membro_name = normalize_node_name(membro.get("name", ""))
            if not membro_name or membro_name == nome_norm:
                continue

            membro_rxcui = membro.get("rxcui", "")
            membro_tty = membro.get("tty", "")
            membro_from_class = membro.get("from_class", "")

            G.add_node(membro_name, nome_original=membro.get("name", ""))
            if membro_rxcui:
                G.nodes[membro_name]["rxcui"] = membro_rxcui

            # sameClassAs (sempre bidirecional)
            edge_tuple_fw = (nome_norm, membro_name, "sameClassAs")
            edge_tuple_bw = (membro_name, nome_norm, "sameClassAs")

            if edge_tuple_fw not in arestas_adicionadas:
                G.add_edge(
                    nome_norm, membro_name,
                    relation="sameClassAs",
                    classId=membro_from_class,
                    source="rxclass"
                )
                arestas_adicionadas.add(edge_tuple_fw)
                edge_counts["sameClassAs"] += 1

            if edge_tuple_bw not in arestas_adicionadas:
                G.add_edge(
                    membro_name, nome_norm,
                    relation="sameClassAs",
                    classId=membro_from_class,
                    source="rxclass"
                )
                arestas_adicionadas.add(edge_tuple_bw)
                edge_counts["sameClassAs"] += 1

            # crossReactsWith (apenas tty = "IN" ou "PIN", bidirecional)
            if membro_tty in ("IN", "PIN"):
                edge_tuple_fw_cr = (nome_norm, membro_name, "crossReactsWith")
                edge_tuple_bw_cr = (membro_name, nome_norm, "crossReactsWith")

                if edge_tuple_fw_cr not in arestas_adicionadas:
                    G.add_edge(
                        nome_norm, membro_name,
                        relation="crossReactsWith",
                        classId=membro_from_class,
                        source="rxclass"
                    )
                    arestas_adicionadas.add(edge_tuple_fw_cr)
                    edge_counts["crossReactsWith"] += 1

                if edge_tuple_bw_cr not in arestas_adicionadas:
                    G.add_edge(
                        membro_name, nome_norm,
                        relation="crossReactsWith",
                        classId=membro_from_class,
                        source="rxclass"
                    )
                    arestas_adicionadas.add(edge_tuple_bw_cr)
                    edge_counts["crossReactsWith"] += 1

        # ===== 3. PARTOFCLASS (classes ATC como nós especiais) =====
        for classe in classes_atc:
            classe_atc_id = classe.get("classId", "")
            classe_atc_nome = classe.get("className", "")
            if classe_atc_id:
                G.add_node(classe_atc_id, tipo="classe_atc", classe_atc_nome=classe_atc_nome)

                edge_tuple = (nome_norm, classe_atc_id, "partOfClass")
                if edge_tuple not in arestas_adicionadas:
                    G.add_edge(nome_norm, classe_atc_id, relation="partOfClass")
                    arestas_adicionadas.add(edge_tuple)
                    edge_counts["partOfClass"] += 1

        # ===== 4. PHARMCLASSEPC (pharm_class com sufixo [EPC]) =====
        pharm_class = med.get("pharm_class", []) or []
        for pc in pharm_class:
            if not isinstance(pc, str):
                continue

            if "[EPC]" in pc:
                # Remover sufixo [EPC] e normalizar
                pc_clean = pc.replace("[EPC]", "").strip()
                pc_norm = normalize_node_name(pc_clean)

                if not pc_norm or pc_norm == nome_norm:
                    continue

                G.add_node(pc_norm, tipo="pharm_class_epc", pharm_class_original=pc)

                edge_tuple = (nome_norm, pc_norm, "pharmClassEPC")
                if edge_tuple not in arestas_adicionadas:
                    G.add_edge(nome_norm, pc_norm, relation="pharmClassEPC", source="openfda")
                    arestas_adicionadas.add(edge_tuple)
                    edge_counts["pharmClassEPC"] += 1

    logger.info(f"Grafo construído: {G.number_of_nodes()} nós, {G.number_of_edges()} arestas")
    logger.info(f"Arestas por tipo: {dict(edge_counts)}")

    return G, edge_counts


def compute_statistics(G: nx.DiGraph, ontologia: List[Dict], edge_counts: Dict) -> Dict:
    """Calcula estatísticas do grafo."""

    stats = {
        "total_nodes": G.number_of_nodes(),
        "total_edges": G.number_of_edges(),
        "edges_by_type": dict(edge_counts),
    }

    # Top 10 nós com mais conexões (grau total in + out)
    node_degrees = dict(G.degree())
    top_10_nodes = sorted(node_degrees.items(), key=lambda x: x[1], reverse=True)[:10]
    stats["top_10_nodes_by_degree"] = [
        {"node": node, "degree": deg} for node, deg in top_10_nodes
    ]

    # % de medicamentos com pelo menos 1 aresta
    meds_no_grafo = set(
        normalize_node_name(med.get("nome_normalizado", ""))
        for med in ontologia
        if med.get("nome_normalizado")
    )
    meds_com_aresta = set(
        node for node in meds_no_grafo
        if G.degree(node) > 0
    )
    pct_com_aresta = (len(meds_com_aresta) / len(meds_no_grafo) * 100) if meds_no_grafo else 0
    stats["medicamentos_com_aresta_pct"] = round(pct_com_aresta, 2)

    # Número de componentes conectados (tratando como grafo não-direcional para análise)
    G_undirected = G.to_undirected()
    num_components = nx.number_connected_components(G_undirected)
    stats["num_connected_components"] = num_components

    return stats


def export_grafo(G: nx.DiGraph, output_dir: Path) -> None:
    """Exporta grafo em JSON (node-link) e GraphML."""

    output_dir.mkdir(parents=True, exist_ok=True)

    # JSON node-link
    json_path = output_dir / "ontologia_farma.json"
    logger.info(f"Exportando para {json_path}")
    node_link_data = nx.node_link_data(G)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(node_link_data, f, ensure_ascii=False, indent=2)
    logger.info(f"✓ Exportado: {json_path}")

    # GraphML
    graphml_path = output_dir / "ontologia_farma.graphml"
    logger.info(f"Exportando para {graphml_path}")
    nx.write_graphml(G, graphml_path)
    logger.info(f"✓ Exportado: {graphml_path}")


def print_statistics(stats: Dict) -> None:
    """Imprime estatísticas formatadas."""

    print("\n" + "=" * 60)
    print("ESTATÍSTICAS DO GRAFO ONTOLÓGICO")
    print("=" * 60)

    print(f"\nTotal de nós: {stats['total_nodes']}")
    print(f"Total de arestas: {stats['total_edges']}")

    print("\nArestas por tipo de relação:")
    for rel_type, count in sorted(stats['edges_by_type'].items()):
        print(f"  {rel_type:20s}: {count:6d}")

    print("\nTop 10 nós com mais conexões (degree):")
    for i, item in enumerate(stats['top_10_nodes_by_degree'], 1):
        print(f"  {i:2d}. {item['node']:40s} → {item['degree']:4d}")

    print(f"\nMedicamentos com pelo menos 1 aresta: {stats['medicamentos_com_aresta_pct']:.2f}%")
    print(f"Componentes conectados: {stats['num_connected_components']}")

    print("\n" + "=" * 60 + "\n")


def main():
    """Função principal."""

    # Caminhos
    api_dir = Path(__file__).parent.parent.parent.parent
    input_path = api_dir / "tools" / "data" / "processed" / "evaluation" / "ontologia" / "ontologia_raw.json"
    output_dir = api_dir / "tools" / "data" / "processed" / "evaluation" / "ontologia"

    logger.info(f"API dir: {api_dir}")
    logger.info(f"Input: {input_path}")
    logger.info(f"Output dir: {output_dir}")

    # Executar pipeline
    ontologia = load_ontologia(input_path)
    grafo, edge_counts = build_grafo(ontologia)
    stats = compute_statistics(grafo, ontologia, edge_counts)
    export_grafo(grafo, output_dir)
    print_statistics(stats)

    logger.info("✓ Pipeline concluído com sucesso!")


if __name__ == "__main__":
    main()

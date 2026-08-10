"""
Query expansion using pharmaceutical ontology graph.
Detects medication names in queries and expands them with related terms.
"""

import json
import logging
import unicodedata
from pathlib import Path
from typing import Optional

import networkx as nx

logger = logging.getLogger(__name__)


def remove_accents(text: str) -> str:
    """Remove accents and diacritics from text."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def normalize_query(query: str) -> str:
    """Normalize query: lowercase, remove accents."""
    return remove_accents(query.lower())


def load_ontology(path: str) -> Optional[nx.DiGraph]:
    """
    Load pharmaceutical ontology graph from node-link JSON format.

    Args:
        path: Path to ontologia_farma.json

    Returns:
        NetworkX DiGraph or None if file not found/invalid
    """
    try:
        path_obj = Path(path)
        if not path_obj.exists():
            logger.warning(f"Ontology file not found: {path}")
            return None

        logger.info(f"Loading ontology from {path}")
        with open(path_obj, "r", encoding="utf-8") as f:
            data = json.load(f)

        graph = nx.node_link_graph(data, directed=True)
        logger.info(f"✓ Ontology loaded: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
        return graph

    except Exception as exc:
        logger.error(f"Failed to load ontology: {exc}")
        return None


def expand_query(
    query: str,
    graph: nx.DiGraph,
    max_terms: int = 5
) -> list[str]:
    """
    Expand query with related medication terms from ontology.

    Detects medication names via substring matching on normalized query,
    then retrieves related terms via:
    - synonymOf: synonyms
    - crossReactsWith: cross-reactive medications
    - sameClassAs: same pharmacological class

    Args:
        query: User query text
        graph: Loaded ontology graph
        max_terms: Maximum number of expansion terms to return

    Returns:
        List of expansion terms (excluding original query terms)
    """
    if graph is None or graph.number_of_nodes() == 0:
        logger.warning("Ontology graph is empty or None")
        return []

    query_normalized = normalize_query(query)
    detected_meds = []
    expansion_terms = set()
    query_terms_set = set(query_normalized.split())

    # Step 1: Detect medication names in query via substring matching
    for node in graph.nodes():
        # Skip short nodes to avoid spurious matches (but allow "aas")
        if len(node) < 3:
            continue

        node_normalized = normalize_query(node)

        # Check if node name appears as substring or word in normalized query
        if node_normalized in query_normalized or node_normalized in query_terms_set:
            detected_meds.append(node)
            logger.debug(f"Detected medication: {node}")

    # Step 2: For each detected medication, find neighbors (prioritize by relation type)
    # Organize by priority: crossReactsWith (highest - alternative medications) > synonymOf > sameClassAs
    priority_terms = {
        "crossReactsWith": set(),
        "synonymOf": set(),
        "sameClassAs": set(),
    }

    for med in detected_meds:
        if med not in graph:
            continue

        # Get neighbors via specific relation types
        for neighbor in graph.neighbors(med):
            # Allow "aas" (3 letters) explicitly for aspirin/AAS
            if len(neighbor) < 4 and neighbor != "aas":
                continue

            # Get edge data to check relation type
            edge_data = graph.get_edge_data(med, neighbor)
            if not isinstance(edge_data, dict):
                continue

            relation = edge_data.get("relation", "")

            # Include neighbors with relevant relations, respecting priority
            if relation in priority_terms:
                # Exclude the detected med itself and terms already in query
                if neighbor != med and neighbor not in query_terms_set:
                    priority_terms[relation].add(neighbor)

    # Step 3: Build result respecting priority order (cross-reactivity > synonyms > same class)
    result = []
    for rel_type in ("crossReactsWith", "synonymOf", "sameClassAs"):
        result.extend(list(priority_terms[rel_type]))
        if len(result) >= max_terms:
            break

    result = result[:max_terms]

    if detected_meds or result:
        logger.info(
            f"Query expansion: detected={detected_meds}, "
            f"expanded={result} (limit={max_terms})"
        )

    return result

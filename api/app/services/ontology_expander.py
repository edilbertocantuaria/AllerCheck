"""
Query expansion using RxNorm API directly.
No local ontology file — all data comes from official RxNorm.
"""

import json
import logging
import unicodedata
from pathlib import Path
from typing import Optional

import httpx
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


_MEDICATION_TRANSLATION_CACHE = {
    "amoxicillin": "amoxicilina",
    "ampicillin": "ampicilina",
    "penicillin": "penicilina",
    "cephalosporin": "cefalosporina",
    "aspirin": "aspirina",
    "ibuprofen": "ibuprofeno",
    "paracetamol": "paracetamol",
    "acetaminophen": "paracetamol",
    "dipyrone": "dipirona",
    "metamizole": "metamizol",
    "duloxetine": "duloxetina",
    "venlafaxine": "venlafaxina",
    "paroxetine": "paroxetina",
    "sertraline": "sertralina",
    "fluoxetine": "fluoxetina",
    "mirtazapine": "mirtazapina",
    "vilazodone": "vilazodona",
    "bupropion": "bupropiona",
    "trazodone": "trazodona",
    "ticarcillin": "ticarcilina",
    "bacampicillin": "bacampicilina",
    "hetacillin": "hetacilina",
    "methampicillin": "metampicilina",
    "levomilnacipran": "levomilnaciprã",
}


async def expand_query_from_rxnorm(
    query: str,
    max_terms: int = 5,
) -> list[dict]:
    """
    Expand query with related medications from RxNorm API (no local file).

    Steps:
    1. Detect medication names in query
    2. Look up each medication in RxNorm (/rxcui?name=...)
    3. Get related medications (/related)
    4. Translate to Portuguese
    5. Return bilingual format: [{"en": "...", "pt": "..."}]

    Args:
        query: User query text
        max_terms: Maximum number of expansion terms

    Returns:
        List of bilingual dicts: [{"en": term_en, "pt": term_pt}]
    """
    import xml.etree.ElementTree as ET

    base_url = "https://rxnav.nlm.nih.gov/REST"
    result = []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Step 1: Extract medication names from query
            query_lower = query.lower()
            words = query_lower.split()
            logger.info(f"RxNorm expansion starting for: {query_lower}, words={words}")

            # Step 2: For each word, try to find RXCUI in RxNorm
            for word in words:
                if len(word) < 4:
                    logger.debug(f"Skipping word (too short): {word}")
                    continue

                try:
                    # Lookup medication in RxNorm (returns XML!)
                    lookup_url = f"{base_url}/rxcui?name={word}"
                    logger.debug(f"Looking up: {lookup_url}")
                    lookup_response = await client.get(lookup_url)
                    lookup_response.raise_for_status()

                    # Parse XML to get RXCUI
                    root = ET.fromstring(lookup_response.text)
                    rxcui = root.findtext(".//rxnormId")

                    if not rxcui:
                        logger.debug(f"No RXCUI found for: {word}, raw response: {lookup_response.text[:200]}")
                        continue

                    logger.info(f"Found RXCUI {rxcui} for medication: {word}")

                    # Step 3: Get related medications (returns XML!)
                    related_url = f"{base_url}/rxcui/{rxcui}/related?tty=IN+PIN+BN"
                    related_response = await client.get(related_url)
                    related_response.raise_for_status()

                    # Parse XML to get related medications
                    root = ET.fromstring(related_response.text)

                    # Step 4: Extract medication names from related groups
                    for concept_group in root.findall(".//conceptGroup"):
                        tty = concept_group.findtext("tty", "")
                        # Include all meaningful types: BN (brand), IN (ingredient), PIN (prescribable)
                        if tty not in ["BN", "IN", "PIN"]:
                            continue

                        for concept in concept_group.findall("conceptProperties"):
                            med_name = concept.findtext("name", "").lower().strip()
                            # Skip empty, too short, or exact duplicates of original word
                            if not med_name or len(med_name) < 3:
                                continue
                            if med_name == word:
                                logger.debug(f"Skipping exact duplicate: {med_name}")
                                continue

                            # Avoid duplicate entries in result
                            if any(r["en"] == med_name for r in result):
                                logger.debug(f"Skipping duplicate expansion: {med_name}")
                                continue

                            if len(result) < max_terms:
                                # Step 5: Translate to Portuguese
                                pt_name = _translate_medication_to_portuguese(med_name)
                                logger.debug(f"Adding expansion: {med_name} -> {pt_name}")
                                result.append({
                                    "en": med_name,
                                    "pt": pt_name
                                })

                    if len(result) >= max_terms:
                        break

                except Exception as e:
                    logger.debug(f"Error looking up medication '{word}': {e}")
                    continue

        logger.info(f"RxNorm expansion: found {len(result)} related medications")
        return result[:max_terms]

    except Exception as e:
        logger.error(f"Error in RxNorm expansion: {e}")
        return []


def _translate_medication_to_portuguese(med_name: str) -> str:
    """Translate medication name to Portuguese using cache + heuristics."""
    med_lower = med_name.lower()

    # Try cache first
    if med_lower in _MEDICATION_TRANSLATION_CACHE:
        return _MEDICATION_TRANSLATION_CACHE[med_lower]

    # Apply heuristic rules
    if med_lower.endswith("in"):
        return med_lower.replace("in", "ina")
    elif med_lower.endswith("ine"):
        return med_lower.replace("ine", "ina")
    elif med_lower.endswith("one"):
        return med_lower.replace("one", "ona")
    elif med_lower.endswith("ate"):
        return med_lower.replace("ate", "ato")

    return med_name


def _get_node_id_portuguese(graph: nx.DiGraph, node_id: str) -> str:
    """
    Translates node ID to Portuguese variant.

    Priority:
    1. Look for direct translation in cache
    2. Try to find Portuguese variant in graph
    3. Apply heuristic rules
    4. Return original if all fail
    """
    node_lower = node_id.lower()

    # Priority 1: Check translation cache
    if node_lower in _MEDICATION_TRANSLATION_CACHE:
        return _MEDICATION_TRANSLATION_CACHE[node_lower]

    # Priority 2: Check if Portuguese variant exists in graph
    if node_id in graph:
        pt_candidates = [
            node_id.replace("in", "ina").lower(),
            node_id.replace("en", "ena").lower(),
            node_id.replace("e", "a").lower() if node_id.endswith("e") else None,
        ]
        for candidate in pt_candidates:
            if candidate and candidate in graph:
                return candidate

    # Priority 3: Apply heuristic rules for common patterns
    if node_lower.endswith("in"):
        return node_lower.replace("in", "ina")
    elif node_lower.endswith("ine"):
        return node_lower.replace("ine", "ina")
    elif node_lower.endswith("one"):
        return node_lower.replace("one", "ona")
    elif node_lower.endswith("ate"):
        return node_lower.replace("ate", "ato")

    return node_id


def expand_query(
    query: str,
    graph: nx.DiGraph,
    max_terms: int = 5,
    prefer_portuguese: bool = True,
    bilingual: bool = False,
) -> list[str] | list[dict]:
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
        prefer_portuguese: Try to return Portuguese variants of terms
        bilingual: If True, return dicts with 'en' and 'pt' fields

    Returns:
        List of expansion terms (or dicts if bilingual=True)
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
                    # Try to get Portuguese variant if enabled
                    neighbor_id = neighbor
                    if prefer_portuguese:
                        neighbor_id = _get_node_id_portuguese(graph, neighbor)
                    priority_terms[relation].add(neighbor_id)

    # Step 3: Build result respecting priority order (cross-reactivity > synonyms > same class)
    result = []
    for rel_type in ("crossReactsWith", "synonymOf", "sameClassAs"):
        result.extend(list(priority_terms[rel_type]))
        if len(result) >= max_terms:
            break

    result = result[:max_terms]

    if bilingual:
        result = [
            {"en": term, "pt": _get_node_id_portuguese(graph, term)}
            if prefer_portuguese else {"en": term, "pt": term}
            for term in result
        ]

    if detected_meds or result:
        logger.info(
            f"Query expansion: detected={detected_meds}, "
            f"expanded={result} (limit={max_terms})"
        )

    return result

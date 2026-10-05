"""
Tradução de termos de ontologia via LLM para PT-BR.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_llm_for_translation():
    """Get LLM instance for translation tasks."""
    from langchain_openai import ChatOpenAI
    import os

    model = os.getenv("REWRITE_MODEL", "gpt-4o-mini")
    return ChatOpenAI(model=model, temperature=0)


async def translate_ontology_terms_async(terms: list[str]) -> dict[str, str]:
    """
    Translate medication terms from English to Portuguese using LLM.

    Args:
        terms: List of medication names in English

    Returns:
        Dict mapping original term → Portuguese translation
    """
    if not terms:
        return {}

    llm = get_llm_for_translation()

    terms_str = ", ".join(terms)

    prompt = f"""Você é um especialista em tradução de nomes de medicamentos do inglês para o português brasileiro.

Traduza os seguintes nomes de medicamentos para português brasileiro:

TERMOS: {terms_str}

REGRAS:
1. Use nomes técnicos reconhecidos em português
2. Se não houver tradução conhecida, deixe em inglês (entre parênteses)
3. Formato: "original_en" → "tradução_pt"
4. Uma tradução por linha

EXEMPLO:
amoxicillin → amoxicilina
duloxetine → duloxetina
tryptophan → triptofano
temocillin → temocilina (não há tradução, manter em inglês)

Agora traduza os termos fornecidos (formato: original → tradução):"""

    try:
        response = await llm.ainvoke(prompt)
        result_text = response.content
        logger.info(f"[LLM TRANSLATION] Response:\n{result_text}")

        # Parse response
        translations = {}
        for line in result_text.strip().split("\n"):
            if "→" in line:
                parts = line.split("→")
                if len(parts) == 2:
                    original = parts[0].strip()
                    translated = parts[1].strip()
                    translations[original] = translated

        return translations

    except Exception as e:
        logger.error(f"[LLM TRANSLATION] Erro ao traduzir: {e}")
        return {term: term for term in terms}  # Fallback


def translate_ontology_terms(terms: list[str]) -> dict[str, str]:
    """Sync wrapper for translation."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Se estiver em event loop async, criar task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, translate_ontology_terms_async(terms))
                return future.result(timeout=10)
        else:
            return asyncio.run(translate_ontology_terms_async(terms))
    except Exception as e:
        logger.error(f"[LLM TRANSLATION SYNC] Erro: {e}")
        return {term: term for term in terms}

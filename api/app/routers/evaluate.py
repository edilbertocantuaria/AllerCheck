import os
import time
from fastapi import APIRouter, Depends

from app.schemas import (
    ChatRequest, EvaluateChunksResponse, DetailedEvaluationResponse,
    PromptUsed, LLMInfo, ComparisonEvaluationResponse, ComparisonResult
)
from app.services.chat import select_sources, format_sources_block, _CITATION_FLAG_RE
from app.services.rag_service import get_rag_service
from app.prompts import QUESTION_REWRITE, QUESTION_INIT

_MODEL_PRICING = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "gemini-2.5-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-pro": {"input": 0.50, "output": 1.50},
    "claude-3-opus": {"input": 15.00, "output": 75.00},
    "claude-3-sonnet": {"input": 3.00, "output": 15.00},
    "claude-haiku": {"input": 0.25, "output": 1.25},
    "mistral": {"input": 0.0, "output": 0.0},
    "mistral:latest": {"input": 0.0, "output": 0.0},
    "qwen2.5:7b": {"input": 0.0, "output": 0.0},
    "llama2": {"input": 0.0, "output": 0.0},
}


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _calculate_cost(provider: str, model: str, input_text: str, output_text: str) -> tuple[int, int, float]:
    input_tokens = _estimate_tokens(input_text)
    output_tokens = _estimate_tokens(output_text)
    pricing = _MODEL_PRICING.get(model.lower(), {"input": 0.0, "output": 0.0})
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    total_cost = input_cost + output_cost
    return input_tokens, output_tokens, round(total_cost, 6)


router = APIRouter(prefix="/evaluate", tags=["evaluate"])


@router.post("/ontology", tags=["debug-ontology"])
async def evaluate_ontology_debug(payload: ChatRequest):
    """Debug endpoint para visualizar o pipeline completo da ontologia."""
    try:
        from app.services.ontology_expander import expand_query_from_rxnorm

        rag_service = get_rag_service(use_hyde=False)
        history_str = rag_service.build_history_str(payload.history or [])
        query_rewritten, is_in_scope = rag_service._rewrite_query(payload.question, history_str)

        ontology_expansion_en = []
        ontology_expansion_pt = []
        if payload.use_ontology:
            ontology_expansion_en = await expand_query_from_rxnorm(query_rewritten, max_terms=5)
            if ontology_expansion_en:
                ontology_expansion_pt = await rag_service._translate_ontology_terms(ontology_expansion_en)

        chunks_by_source = {"original_query": 0, "ontology_expansion": 0, "hyde": 0, "hybrid": 0}
        if is_in_scope and payload.use_ontology:
            vector_docs, ont_chunks_added = await rag_service._retrieve(query_rewritten, ontology_expansion_en)
            for doc in vector_docs:
                source = doc.metadata.get("retrieval_source", "unknown")
                if source in chunks_by_source:
                    chunks_by_source[source] += 1

        return {
            "question": payload.question,
            "question_rewritten": query_rewritten,
            "is_in_scope": is_in_scope,
            "ontology_pipeline": {
                "step_1_input": payload.question,
                "step_2_rewritten": query_rewritten,
                "step_3_detected_medications": [],
                "step_4_expanded_en": [
                    t.get("en") if isinstance(t, dict) else t
                    for t in ontology_expansion_en
                ],
                "step_5_translated_pt": [
                    t.get("pt") if isinstance(t, dict) else t
                    for t in ontology_expansion_pt
                ],
                "step_6_bilingual_terms": ontology_expansion_pt,
            },
            "retrieval_results": {
                "original_query_chunks": chunks_by_source["original_query"],
                "ontology_expansion_chunks": chunks_by_source["ontology_expansion"],
                "hyde_chunks": chunks_by_source["hyde"],
                "hybrid_chunks": chunks_by_source["hybrid"],
                "total_chunks": sum(chunks_by_source.values()),
            }
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "error": str(e),
            "question": payload.question,
        }


@router.post("/chunks", response_model=EvaluateChunksResponse)
async def evaluate_chunks(payload: ChatRequest):
    try:
        rag_service = get_rag_service(use_hyde=payload.use_hyde)
        chunks = await rag_service.get_chunks_for_question(
            question=payload.question,
            history=payload.history if payload.history else None,
            use_ontology=payload.use_ontology,
        )
        return EvaluateChunksResponse(
            question=payload.question,
            chunks=chunks,
            total_chunks=len(chunks),
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return EvaluateChunksResponse(
            question=payload.question,
            chunks=[],
            total_chunks=0,
        )


@router.post("/detailed", response_model=DetailedEvaluationResponse)
async def evaluate_detailed(payload: ChatRequest):
    try:
        rag_service = get_rag_service(use_hyde=payload.use_hyde)

        internals = await rag_service.get_pipeline_internals(
            question=payload.question,
            history=payload.history if payload.history else None,
            use_ontology=payload.use_ontology,
        )

        contexts = internals.get("contexts", [])
        answer_raw = None
        answer_formatted = None
        prompts_used = []

        rewrite_provider = os.getenv("REWRITE_PROVIDER", "openai").lower()
        rewrite_model = os.getenv("REWRITE_MODEL", "gpt-4o-mini")
        answer_provider = os.getenv("ANSWER_PROVIDER", "openai").lower()
        answer_model = os.getenv("ANSWER_MODEL", "gpt-4o")

        rewrite_llm_info = LLMInfo(provider=rewrite_provider, model=rewrite_model)
        answer_llm_info = LLMInfo(provider=answer_provider, model=answer_model)

        if internals.get("is_in_scope"):
            try:
                history_str = rag_service.build_history_str(payload.history or [])

                chain_input, sources, is_emergency, emergency_content, _ = await rag_service.build_chain_input(
                    question=payload.question,
                    history_str=history_str,
                    use_ontology=payload.use_ontology,
                )

                prompts_used = [
                    PromptUsed(name="QUESTION_REWRITE", template=QUESTION_REWRITE),
                    PromptUsed(name="QUESTION_INIT", template=QUESTION_INIT),
                ]
                if payload.use_hyde:
                    from app.services.rag_service import _HYDE_PROMPT
                    prompts_used.insert(1, PromptUsed(name="HYDE", template=_HYDE_PROMPT))

                if not is_emergency:
                    answer_raw = rag_service.answer_llm.invoke(chain_input).content
                    answer_formatted = _CITATION_FLAG_RE.sub("", answer_raw).lstrip("\n").rstrip()
                    selected_sources = select_sources(answer_formatted, sources)
                    sources_block = format_sources_block(selected_sources)
                    if sources_block:
                        answer_formatted += "\n\n" + sources_block
                else:
                    answer_formatted = emergency_content

            except Exception as e:
                import traceback
                traceback.print_exc()

        return DetailedEvaluationResponse(
            question=payload.question,
            question_rewrite=internals.get("question_rewrite"),
            hyde_reformulation=internals.get("hyde_reformulation"),
            ontology_expansion=internals.get("ontology_expansion"),
            ontology_chunks_added=internals.get("ontology_chunks_added", 0),
            chunks=contexts,
            total_chunks=len(contexts),
            use_hyde=payload.use_hyde,
            prompts_used=prompts_used if prompts_used else None,
            answer_raw=answer_raw,
            answer_formatted=answer_formatted,
            rewrite_llm=rewrite_llm_info,
            answer_llm=answer_llm_info,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        rewrite_provider = os.getenv("REWRITE_PROVIDER", "openai").lower()
        rewrite_model = os.getenv("REWRITE_MODEL", "gpt-4o-mini")
        answer_provider = os.getenv("ANSWER_PROVIDER", "openai").lower()
        answer_model = os.getenv("ANSWER_MODEL", "gpt-4o")
        return DetailedEvaluationResponse(
            question=payload.question,
            question_rewrite=None,
            hyde_reformulation=None,
            chunks=[],
            total_chunks=0,
            use_hyde=payload.use_hyde,
            prompts_used=None,
            answer_raw=None,
            answer_formatted=None,
            rewrite_llm=LLMInfo(provider=rewrite_provider, model=rewrite_model),
            answer_llm=LLMInfo(provider=answer_provider, model=answer_model),
        )


async def _generate_answer(rag_service, chain_input, sources) -> tuple[str, str | None]:
    try:
        answer_raw = rag_service.answer_llm.invoke(chain_input).content
        answer_formatted = _CITATION_FLAG_RE.sub("", answer_raw).lstrip("\n").rstrip()
        selected_sources = select_sources(answer_formatted, sources)
        sources_block = format_sources_block(selected_sources)
        if sources_block:
            answer_formatted += "\n\n" + sources_block
        return answer_formatted, None
    except Exception as e:
        return "", str(e)


@router.post("/comparison", response_model=ComparisonEvaluationResponse)
async def evaluate_comparison(payload: ChatRequest):
    try:
        rag_service = get_rag_service(use_hyde=payload.use_hyde)
        history_str = rag_service.build_history_str(payload.history or [])
        internals = await rag_service.get_pipeline_internals(
            question=payload.question,
            history=payload.history if payload.history else None,
        )
        contexts = internals.get("contexts", [])

        if not internals.get("is_in_scope"):
            raise ValueError("Pergunta fora do escopo")

        chain_input, sources, _, _, _ = await rag_service.build_chain_input(
            question=payload.question,
            history_str=history_str,
        )

        t0_llm = time.perf_counter()
        try:
            llm_answer, llm_error = await _generate_answer(rag_service, chain_input, sources)
            llm_time_ms = (time.perf_counter() - t0_llm) * 1000
            llm_provider = os.getenv("ANSWER_PROVIDER").lower()
            llm_model = os.getenv("ANSWER_MODEL")
            chain_input_text = str(chain_input) if chain_input else ""
            input_tokens, output_tokens, cost_usd = _calculate_cost(
                llm_provider, llm_model, chain_input_text, llm_answer
            )
            llm_result = ComparisonResult(
                provider=llm_provider,
                model=llm_model,
                answer=llm_answer,
                time_ms=round(llm_time_ms, 2),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                error=llm_error,
            )
        except Exception as e:
            llm_time_ms = (time.perf_counter() - t0_llm) * 1000
            llm_provider = os.getenv("ANSWER_PROVIDER", "openai").lower()
            llm_model = os.getenv("ANSWER_MODEL", "gpt-4o")
            llm_result = ComparisonResult(
                provider=llm_provider,
                model=llm_model,
                answer="",
                time_ms=round(llm_time_ms, 2),
                cost_usd=0.0,
                error=str(e),
            )

        t0_slm = time.perf_counter()
        try:
            orig_answer_provider = os.getenv("ANSWER_PROVIDER")
            orig_answer_model = os.getenv("ANSWER_MODEL")

            os.environ["ANSWER_PROVIDER"] = os.getenv("SLM_PROVIDER")
            os.environ["ANSWER_MODEL"] = os.getenv("SLM_MODEL")

            from app.services.rag_service import RagService
            slm_rag_service = RagService(use_hyde=payload.use_hyde)
            slm_answer, slm_error = await _generate_answer(slm_rag_service, chain_input, sources)
            slm_time_ms = (time.perf_counter() - t0_slm) * 1000
            slm_provider = os.getenv("SLM_PROVIDER", "ollama").lower()
            slm_model = os.getenv("SLM_MODEL", "mistral")
            chain_input_text = str(chain_input) if chain_input else ""
            input_tokens, output_tokens, cost_usd = _calculate_cost(
                slm_provider, slm_model, chain_input_text, slm_answer
            )
            slm_result = ComparisonResult(
                provider=slm_provider,
                model=slm_model,
                answer=slm_answer,
                time_ms=round(slm_time_ms, 2),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                error=slm_error,
            )

            os.environ["ANSWER_PROVIDER"] = orig_answer_provider
            os.environ["ANSWER_MODEL"] = orig_answer_model

        except Exception as e:
            slm_time_ms = (time.perf_counter() - t0_slm) * 1000
            slm_provider = os.getenv("SLM_PROVIDER", "ollama").lower()
            slm_model = os.getenv("SLM_MODEL", "mistral")
            slm_result = ComparisonResult(
                provider=slm_provider,
                model=slm_model,
                answer="",
                time_ms=round(slm_time_ms, 2),
                cost_usd=0.0,
                error=str(e),
            )

        time_diff = llm_result.time_ms - slm_result.time_ms
        faster_provider = "llm" if time_diff > 0 else "slm"

        return ComparisonEvaluationResponse(
            question=payload.question,
            question_rewrite=internals.get("question_rewrite"),
            chunks=contexts,
            total_chunks=len(contexts),
            use_hyde=payload.use_hyde,
            llm_result=llm_result,
            slm_result=slm_result,
            time_difference_ms=round(abs(time_diff), 2),
            faster_provider=faster_provider,
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return ComparisonEvaluationResponse(
            question=payload.question,
            question_rewrite=None,
            chunks=[],
            total_chunks=0,
            use_hyde=payload.use_hyde,
            llm_result=ComparisonResult(
                provider="error",
                model="error",
                answer="",
                time_ms=0,
                error=str(e),
            ),
            slm_result=ComparisonResult(
                provider="error",
                model="error",
                answer="",
                time_ms=0,
                error=str(e),
            ),
            time_difference_ms=0,
            faster_provider="unknown",
        )


@router.post("/debug/ontology-services", tags=["debug-ontology"])
async def debug_ontology_services(payload: ChatRequest):
    """Chamadas diretas aos serviços de ontologia (RxNorm + tradução)."""
    try:
        from app.services.ontology_expander import expand_query_from_rxnorm

        rag_service = get_rag_service(use_hyde=False)

        ontology_expanded = await expand_query_from_rxnorm(payload.question, max_terms=5)

        ontology_translated = await rag_service._translate_ontology_terms(ontology_expanded) if ontology_expanded else []

        pinecone_results = []
        if ontology_translated:
            translated_terms = " ".join([
                t.get("pt") if isinstance(t, dict) else t
                for t in ontology_translated
            ])

            try:
                import asyncio, functools
                loop = asyncio.get_running_loop()
                func = functools.partial(
                    rag_service._vectorstore.similarity_search_with_relevance_scores,
                    translated_terms, k=5, score_threshold=0.60
                )
                results = await loop.run_in_executor(None, func)
                pinecone_results = [
                    {"content": doc.page_content[:150], "score": round(score, 4), "source": doc.metadata.get("source")}
                    for doc, score in results
                ]
            except Exception as pe:
                pinecone_results = [{"error": str(pe)}]

        return {
            "1_question_input": payload.question,
            "2_ontology_expand_output": ontology_expanded,
            "3_llm_translate_output": ontology_translated,
            "4_pinecone_search_output": pinecone_results,
        }

    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@router.post("/debug/raw-medication-only", tags=["debug-ontology"])
async def debug_raw_medication_only(medication: str = "mirtazapine"):
    """Resultado BRUTO: manda medicamento (EN) e vê o que volta da ontologia."""
    try:
        from app.services.ontology_expander import expand_query_from_rxnorm

        result = await expand_query_from_rxnorm(medication.lower().strip(), max_terms=10)

        return {
            "input_medication_en": medication,
            "ontology_expansion_raw": result,
            "total_results": len(result),
        }

    except Exception as e:
        import traceback
        return {"error": str(e), "details": traceback.format_exc()}


@router.post("/debug/medication-with-llm", tags=["debug-ontology"])
async def debug_medication_with_llm(medication: str = "mirtazapine"):
    """Resultado BRUTO: medicamento → RxNorm → LLM translation."""
    try:
        from app.services.ontology_expander import expand_query_from_rxnorm

        rag_service = get_rag_service(use_hyde=False)

        ontology_raw = await expand_query_from_rxnorm(
            medication.lower().strip(),
            max_terms=10
        )

        llm_raw = await rag_service._translate_ontology_terms(ontology_raw) if ontology_raw else []

        return {
            "input_medication": medication,
            "ontology_raw_output": ontology_raw,
            "llm_translation_raw_output": llm_raw,
        }

    except Exception as e:
        import traceback
        return {"error": str(e), "details": traceback.format_exc()}


def _parse_lookup_xml(xml_text: str) -> dict:
    """Parse lookup response XML."""
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_text)
        rxcui = root.findtext(".//rxnormId")
        return {"rxcui": rxcui, "status": "found" if rxcui else "not_found"}
    except:
        return {"error": "Falha ao parsear XML"}


def _parse_related_xml(xml_text: str) -> list:
    """Parse related medicamentos XML — retorna lista estruturada."""
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_text)
        results = []

        for group in root.findall(".//conceptGroup"):
            tty = group.findtext("tty", "UNKNOWN")
            concepts = []

            for prop in group.findall("conceptProperties"):
                rxcui = prop.findtext("rxcui")
                name = prop.findtext("name")
                concepts.append({"rxcui": rxcui, "name": name})

            if concepts:
                results.append({
                    "tty": tty,
                    "count": len(concepts),
                    "concepts": concepts
                })

        return results
    except:
        return []


def _parse_properties_xml(xml_text: str) -> dict:
    """Parse properties XML — retorna dict estruturado por categoria."""
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_text)
        properties = {}

        for concept in root.findall(".//propConcept"):
            category = concept.findtext("propCategory", "OTHER")
            prop_name = concept.findtext("propName", "UNKNOWN")
            prop_value = concept.findtext("propValue", "")

            if category not in properties:
                properties[category] = {}

            if prop_name not in properties[category]:
                properties[category][prop_name] = []

            properties[category][prop_name].append(prop_value)

        return properties
    except:
        return {}


@router.get("/debug/rxnorm-lookup", tags=["debug-rxnorm"])
async def debug_rxnorm_lookup(medication: str = "mirtazapine"):
    """Busca RXCUI por nome — resultado estruturado em JSON."""
    import httpx

    base_url = "https://rxnav.nlm.nih.gov/REST"
    url = f"{base_url}/rxcui?name={medication}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()

            parsed = _parse_lookup_xml(response.text)

            return {
                "operation": "lookup",
                "input_medication": medication,
                "result": parsed,
            }
    except Exception as e:
        return {"error": str(e), "medication": medication}


@router.get("/debug/rxnorm-related", tags=["debug-rxnorm"])
async def debug_rxnorm_related(rxcui: str):
    """Medicamentos relacionados — resultado estruturado em JSON."""
    import httpx

    base_url = "https://rxnav.nlm.nih.gov/REST"
    url = f"{base_url}/rxcui/{rxcui}/related?tty=IN+PIN+BN+SBD+SCD+SBDC+SBDF+SBDG+SCDC+SCDF+SCDG"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()

            parsed = _parse_related_xml(response.text)
            total = sum(item["count"] for item in parsed)

            return {
                "operation": "related",
                "rxcui": rxcui,
                "total_concepts": total,
                "by_tty": parsed,
            }
    except Exception as e:
        return {"error": str(e), "rxcui": rxcui}


@router.get("/debug/rxnorm-properties", tags=["debug-rxnorm"])
async def debug_rxnorm_properties(rxcui: str):
    """Todas as propriedades — resultado estruturado em JSON."""
    import httpx

    base_url = "https://rxnav.nlm.nih.gov/REST"
    url = f"{base_url}/rxcui/{rxcui}/allProperties?prop=all"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()

            parsed = _parse_properties_xml(response.text)

            return {
                "operation": "properties",
                "rxcui": rxcui,
                "categories": list(parsed.keys()),
                "properties": parsed,
            }
    except Exception as e:
        return {"error": str(e), "rxcui": rxcui}

import os
import time
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.dependencies import get_optional_current_user
from app.models import User
from app.schemas import (
    ChatRequest, EvaluateChunksResponse, ChunkResponse, DetailedEvaluationResponse,
    PromptUsed, LLMInfo, ComparisonEvaluationResponse, ComparisonResult
)
from app.services.chat import build_chat_stream, format_sources_block, select_sources, _CITATION_FLAG_RE
from app.services.rag_service import get_rag_service
from app.unit_of_work import SqlAlchemyUnitOfWork, get_uow
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

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    current_user: User | None = Depends(get_optional_current_user),
):
    stream = build_chat_stream(payload=payload, uow=uow, current_user=current_user)
    return StreamingResponse(stream, media_type="text/plain")


@router.post("/evaluate/chunks", response_model=EvaluateChunksResponse)
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


@router.post("/evaluate/detailed", response_model=DetailedEvaluationResponse)
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


@router.post("/evaluate/comparison", response_model=ComparisonEvaluationResponse)
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
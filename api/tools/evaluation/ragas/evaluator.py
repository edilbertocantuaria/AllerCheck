from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
    _env = Path(__file__).parent / ".env"
    if _env.exists():
        load_dotenv(_env)
except ImportError:
    pass

import httpx
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion
from ragas.embeddings.base import embedding_factory
from ragas.llms import llm_factory
from ragas.metrics.collections import (
    AnswerRelevancy,
    ContextEntityRecall,
    ContextPrecision,
    ContextRecall,
    Faithfulness,
)

from .helpers import get_iso_timestamp

_GEMINI_BASE_URL  = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
_SLM_BASE_URL  = os.getenv("SLM_BASE_URL")

_UNICODE_ESCAPE_RE   = re.compile(r'\\u([0-9a-fA-F]{4})')
_CONTROL_CHARS_RE    = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')
_MISSING_KEY_QUOTE   = re.compile(r'(^|\n)(\s+)([a-zA-Z_][a-zA-Z0-9_]*)(":\s)')
_OVER_ESCAPED_QUOTES = re.compile(r'\\{2,}"')


def _clean_gemini_content(text: str) -> str:
    text = _UNICODE_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), text)
    text = _CONTROL_CHARS_RE.sub('', text)
    text = _MISSING_KEY_QUOTE.sub(r'\1\2"\3\4', text)
    text = _OVER_ESCAPED_QUOTES.sub('\\"', text)
    return text


def _fix_completion(completion: ChatCompletion) -> ChatCompletion:
    for choice in completion.choices:
        if choice.message.content:
            choice.message.content = _clean_gemini_content(choice.message.content)
    return completion


class _GeminiAsyncOpenAI(AsyncOpenAI):
    class _CompletionsProxy:
        def __init__(self, completions):
            self._c = completions

        async def create(self, *args, **kwargs) -> ChatCompletion:
            return _fix_completion(await self._c.create(*args, **kwargs))

    class _ChatProxy:
        def __init__(self, chat):
            self.completions = _GeminiAsyncOpenAI._CompletionsProxy(chat.completions)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.chat = self._ChatProxy(super().chat)


def _strip_citation_flag(text: str) -> str:
    return re.sub(
        r'^\[CITATION_REQUIRED:\s*(true|false)\]\s*\n?',
        '',
        text.strip(),
        flags=re.IGNORECASE,
    ).strip()


def _sanitize(text: str) -> str:
    return _CONTROL_CHARS_RE.sub('', text).strip()


def _parse_answer(raw: str) -> str:
    text = _strip_citation_flag(raw)
    fonte_match = re.search(r'\n\nFonte:\n', text, flags=re.IGNORECASE)
    if fonte_match:
        text = text[:fonte_match.start()].strip()
    return _sanitize(text)


_MIN_ANSWER_LENGTH = 50


async def _collect_chunks(
    client: httpx.AsyncClient,
    api_base_url: str,
    payload: dict,
    headers: dict,
    max_retries: int = 3,
    backoff_base: float = 2.0,
) -> list[str]:
    for attempt in range(1, max_retries + 1):
        try:
            resp = await client.post(
                f"{api_base_url}/evaluate/chunks",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            chunks = [c["content"] for c in data.get("chunks", [])]
            total = data.get("total_chunks", 0)
            if chunks:
                print(f"    [OK] {total} chunk(s) recuperado(s)")
            else:
                print("    [AVISO] Nenhum chunk recuperado")
            return chunks

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                print("    [AVISO] /evaluate/chunks não encontrado (404)")
                return []
            if attempt == max_retries:
                print(f"    [ERRO] HTTP {e.response.status_code} após {max_retries} tentativas")
                raise
            wait = backoff_base ** attempt
            print(f"    [RETRY] HTTP {e.response.status_code} — tentativa {attempt}/{max_retries}, aguardando {wait:.0f}s...")
            await asyncio.sleep(wait)

        except Exception as e:
            if attempt == max_retries:
                print(f"    [ERRO] Falha ao recuperar chunks após {max_retries} tentativas: {e}")
                raise
            wait = backoff_base ** attempt
            print(f"    [RETRY] {type(e).__name__} — tentativa {attempt}/{max_retries}, aguardando {wait:.0f}s...")
            await asyncio.sleep(wait)

    return []


async def _collect_chat(
    client: httpx.AsyncClient,
    api_base_url: str,
    payload: dict,
    headers: dict,
) -> str | None:
    chunks: list[str] = []
    async with client.stream("POST", f"{api_base_url}/chat", json=payload, headers=headers) as resp:
        resp.raise_for_status()
        async for chunk in resp.aiter_text():
            chunks.append(chunk)
    answer = _parse_answer("".join(chunks))
    if len(answer) < _MIN_ANSWER_LENGTH:
        print(f"    [AVISO] Resposta suspeita após sanitização ({len(answer)} chars) — descartando item.")
        return None
    return answer


async def collect_api_responses(
    questions: list[dict[str, Any]],
    api_base_url: str = "http://localhost:8000",
    jwt_token: str | None = None,
    timeout: int = 30,
    use_hyde: bool = True,
    use_ontology: bool = False,
    max_retries: int = 3,
) -> list[dict[str, Any]]:
    """
    Coleta respostas da API com retry automático.

    Args:
        max_retries: Número máximo de tentativas por pergunta (padrão: 3)
    """
    results = []
    headers = {"Authorization": f"Bearer {jwt_token}"} if jwt_token else {}

    async with httpx.AsyncClient(timeout=timeout) as client:
        for idx, item in enumerate(questions, 1):
            question = item.get("question", "")
            ground_truth = item.get("answer", "")

            if not question:
                print(f"[AVISO] Pergunta {idx} vazia, pulando...")
                continue

            print(f"[COLLECT] Coletando resposta {idx}/{len(questions)}: {question[:50]}... (use_hyde={use_hyde}, use_ontology={use_ontology})")

            payload = {"conversation_id": None, "question": question, "history": [], "use_hyde": use_hyde, "use_ontology": use_ontology}

            success = False
            last_error = None

            # Tentar com retry automático
            for attempt in range(1, max_retries + 1):
                try:
                    detailed_resp = await client.post(
                        f"{api_base_url}/evaluate/detailed",
                        json=payload,
                        headers=headers,
                    )
                    detailed_data = detailed_resp.json() if detailed_resp.status_code == 200 else {}

                    contexts = [c.get("content") for c in detailed_data.get("chunks", [])] if detailed_data.get("chunks") else []
                    clean_answer = await _collect_chat(client, api_base_url, payload, headers)

                    ontology_exp = detailed_data.get("ontology_expansion", [])
                    ontology_str = f" [ONTOLOGIA] {' | '.join(ontology_exp)}" if ontology_exp else ""

                    results.append({
                        "question_id":         idx,
                        "question":            question,
                        "question_rewrite":    detailed_data.get("question_rewrite"),
                        "hyde_reformulation":  detailed_data.get("hyde_reformulation"),
                        "ontology_expansion":  ontology_exp,
                        "answer":              clean_answer,
                        "ground_truth":        ground_truth,
                        "contexts":            contexts,
                        "collected_at":        get_iso_timestamp(),
                        "retry_attempts":      attempt,
                    })
                    print(f"[OK] Resposta {idx} coletada com sucesso{ontology_str}")
                    success = True
                    break

                except httpx.TimeoutException as e:
                    last_error = f"TimeoutException (tentativa {attempt}/{max_retries}): {type(e).__name__}"
                    if attempt < max_retries:
                        wait = 0.5 * (2 ** (attempt - 1))  # Backoff reduzido: 0.5s, 1s, 2s
                        print(f"[RETRY] Q{idx} timeout, aguardando {wait}s antes de retry...")
                        await asyncio.sleep(wait)
                    else:
                        print(f"[ERRO] Q{idx} timeout após {max_retries} tentativas")

                except httpx.HTTPStatusError as e:
                    last_error = f"HTTP {e.response.status_code}: {e.response.reason_phrase}"
                    print(f"[ERRO] Q{idx} HTTP {e.response.status_code} (tentativa {attempt}/{max_retries})")
                    if attempt == max_retries:
                        print(f"        Erro: {last_error}")

                except httpx.HTTPError as e:
                    last_error = f"{type(e).__name__}: {str(e)}"
                    if attempt < max_retries:
                        wait = 0.5 * (2 ** (attempt - 1))
                        print(f"[RETRY] Q{idx} erro HTTP, aguardando {wait}s...")
                        await asyncio.sleep(wait)
                    else:
                        print(f"[ERRO] Q{idx}: {last_error}")

                except Exception as e:
                    last_error = f"{type(e).__name__}: {str(e)}"
                    print(f"[ERRO] Q{idx} erro inesperado (tentativa {attempt}/{max_retries}): {last_error}")
                    if attempt < max_retries:
                        wait = 0.5 * (2 ** (attempt - 1))
                        await asyncio.sleep(wait)

            # Se falhou após todos os retries
            if not success:
                results.append({
                    "question_id":      idx,
                    "question":         question,
                    "answer":           None,
                    "ground_truth":     ground_truth,
                    "contexts":         [],
                    "error":            last_error or "Falha desconhecida",
                    "collected_at":     get_iso_timestamp(),
                    "retry_attempts":   max_retries,
                })

    return results


@dataclass
class EvalResult:
    faithfulness:          dict[str, float] = field(default_factory=dict)
    context_precision:     dict[str, float] = field(default_factory=dict)
    context_recall:        dict[str, float] = field(default_factory=dict)
    context_entity_recall: dict[str, float] = field(default_factory=dict)
    noise_sensitivity:     dict[str, float] = field(default_factory=dict)
    answer_relevancy:      dict[str, float] = field(default_factory=dict)

    def __repr__(self) -> str:
        lines = ["EvalResult:"]
        for metric, scores in self.__dict__.items():
            if scores:
                row = "  |  ".join(f"{ev}: {v:.4f}" for ev, v in scores.items())
                lines.append(f"  {metric:<26} {row}")
        return "\n".join(lines)


class RagasEvaluator:

    _claude_sem = asyncio.Semaphore(3)
    _ollama_sem = asyncio.Semaphore(3)

    def __init__(
        self,
        openai_llm_model: str | None = None,
        openai_embedding_model: str | None = None,
        gemini_model: str | None = None,
        claude_model: str | None = None,
        SLM_MODEL: str | None = None,
        SLM_BASE_URL: str | None = None,
        openai_api_key: str | None = None,
        gemini_api_key: str | None = None,
        anthropic_api_key: str | None = None,
        evaluators: list[str] | None = None,
    ):
        openai_llm_model = openai_llm_model or os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini")
        openai_embedding_model = openai_embedding_model or os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        gemini_model = gemini_model or os.getenv("GEMINI_LLM_MODEL", "gemini-2.5-flash-lite")
        claude_model = claude_model or os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
        SLM_MODEL = SLM_MODEL or os.getenv("SLM_MODEL", "mistral")
        SLM_BASE_URL = SLM_BASE_URL or _SLM_BASE_URL
        evaluator_temperature = float(os.environ["EVALUATOR_TEMPERATURE"])

        _oai_key    = openai_api_key or os.getenv("OPENAI_API_KEY")
        _oai_client = AsyncOpenAI(api_key=_oai_key)
        _gpt_llm    = llm_factory(openai_llm_model, client=_oai_client, max_tokens=4096, temperature=evaluator_temperature)

        try:
            _embeddings = embedding_factory(
                "huggingface",
                model="neuralmind/bert-base-portuguese-cased",
            )
        except Exception:
            try:
                _embeddings = embedding_factory(
                    "huggingface",
                    model="rufimelo/bert-large-portuguese-cased-sts",
                )
            except Exception:
                _embeddings = embedding_factory(
                    "openai", model=openai_embedding_model, client=_oai_client,
                )

        _gem_key    = gemini_api_key or os.getenv("GEMINI_API_KEY")
        _gem_client = _GeminiAsyncOpenAI(api_key=_gem_key, base_url=_GEMINI_BASE_URL)
        _gemini_llm = llm_factory(gemini_model, client=_gem_client, max_tokens=4096, temperature=evaluator_temperature)

        _ant_key    = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        import anthropic
        _ant_client = anthropic.AsyncAnthropic(api_key=_ant_key)
        _claude_llm = llm_factory(
            claude_model,
            provider="anthropic",
            client=_ant_client,
            max_tokens=4096,
            temperature=evaluator_temperature,
        )
        _claude_llm.model_args.pop("top_p", None)

        _ollama_client = AsyncOpenAI(
            api_key="ollama",
            base_url=SLM_BASE_URL,
        )
        _ollama_llm = llm_factory(SLM_MODEL, client=_ollama_client, max_tokens=2048, temperature=evaluator_temperature)

        self._metrics: dict[str, dict] = {
            "gpt": {
                "faithfulness":          Faithfulness(llm=_gpt_llm),
                "context_precision":     ContextPrecision(llm=_gpt_llm),
                "context_recall":        ContextRecall(llm=_gpt_llm),
                "context_entity_recall": ContextEntityRecall(llm=_gpt_llm),
                "answer_relevancy":      AnswerRelevancy(llm=_gpt_llm, embeddings=_embeddings),
            },
            "gemini": {
                "faithfulness":          Faithfulness(llm=_gemini_llm),
                "context_precision":     ContextPrecision(llm=_gemini_llm),
                "context_recall":        ContextRecall(llm=_gemini_llm),
                "context_entity_recall": ContextEntityRecall(llm=_gemini_llm),
                "answer_relevancy":      AnswerRelevancy(llm=_gemini_llm, embeddings=_embeddings),
            },
            "claude": {
                "faithfulness":          Faithfulness(llm=_claude_llm),
                "context_precision":     ContextPrecision(llm=_claude_llm),
                "context_recall":        ContextRecall(llm=_claude_llm),
                "context_entity_recall": ContextEntityRecall(llm=_claude_llm),
                "answer_relevancy":      AnswerRelevancy(llm=_claude_llm, embeddings=_embeddings),
            },
            "ollama": {
                "faithfulness":          Faithfulness(llm=_ollama_llm),
                "context_precision":     ContextPrecision(llm=_ollama_llm),
                "context_recall":        ContextRecall(llm=_ollama_llm),
                "context_entity_recall": ContextEntityRecall(llm=_ollama_llm),
                "answer_relevancy":      AnswerRelevancy(llm=_ollama_llm, embeddings=_embeddings),
            },
        }

        if evaluators:
            self._metrics = {k: v for k, v in self._metrics.items() if k in set(evaluators)}

    async def _score(self, metric_name: str, **kwargs) -> dict[str, float | None]:

        async def _run_claude_with_backoff(metric_name: str, **kwargs) -> float | None:
            max_retries = 3
            base_wait   = 0.5
            for attempt in range(max_retries):
                try:
                    async with RagasEvaluator._claude_sem:
                        result = await self._metrics["claude"][metric_name].ascore(**kwargs)
                        return result.value
                except Exception:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(base_wait * (2 ** attempt))
                    else:
                        raise

        async def _run_ollama_with_backoff(metric_name: str, **kwargs) -> float | None:
            max_retries = 3
            base_wait   = 2.0
            for attempt in range(max_retries):
                try:
                    async with RagasEvaluator._ollama_sem:
                        result = await self._metrics["ollama"][metric_name].ascore(**kwargs)
                        return result.value
                except Exception:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(base_wait * (2 ** attempt))
                    else:
                        raise

        async def _run(evaluator: str) -> tuple[str, float | None]:
            try:
                if evaluator == "claude":
                    return evaluator, await _run_claude_with_backoff(metric_name, **kwargs)
                elif evaluator == "ollama":
                    return evaluator, await _run_ollama_with_backoff(metric_name, **kwargs)
                else:
                    result = await self._metrics[evaluator][metric_name].ascore(**kwargs)
                    return evaluator, result.value
            except ValueError as e:
                if "broadcast" in str(e):
                    import click
                    click.echo(
                        f"      [AVISO] {metric_name}/{evaluator}: ragas broadcast bug "
                        f"— retornando None para este item. ({e})",
                        err=True,
                    )
                    return evaluator, None
                raise

        pairs = await asyncio.gather(*[_run(ev) for ev in self._metrics])
        return dict(pairs)

    async def evaluate_faithfulness(
        self, question: str, answer: str, contexts: list[str],
    ) -> dict[str, float | None]:
        return await self._score(
            "faithfulness",
            user_input=question, response=answer, retrieved_contexts=contexts,
        )

    async def evaluate_context_precision(
        self, question: str, contexts: list[str], ground_truth: str,
    ) -> dict[str, float | None]:
        return await self._score(
            "context_precision",
            user_input=question, reference=ground_truth, retrieved_contexts=contexts,
        )

    async def evaluate_context_recall(
        self, question: str, contexts: list[str], ground_truth: str,
    ) -> dict[str, float | None]:
        return await self._score(
            "context_recall",
            user_input=question, retrieved_contexts=contexts, reference=ground_truth,
        )

    async def evaluate_context_entity_recall(
        self, contexts: list[str], ground_truth: str,
    ) -> dict[str, float | None]:
        return await self._score(
            "context_entity_recall",
            reference=ground_truth, retrieved_contexts=contexts,
        )

    async def evaluate_answer_relevancy(
        self, question: str, answer: str,
    ) -> dict[str, float | None]:
        return await self._score(
            "answer_relevancy",
            user_input=question, response=answer,
        )

    @staticmethod
    def _sanitize(text: str) -> str:
        return _CONTROL_CHARS_RE.sub('', text).strip()

    async def evaluate_all(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str,
        log_prefix: str = "",
    ) -> EvalResult:
        question     = self._sanitize(question)
        answer       = self._sanitize(answer)
        ground_truth = self._sanitize(ground_truth)
        contexts     = [self._sanitize(c) for c in contexts]

        async def _timed(coro, label: str):
            import click
            result = await coro
            if log_prefix:
                click.echo(f"{log_prefix} ✓ {label}")
            return result

        evaluators = "/".join(self._metrics.keys())
        faith, cp, cr, cer, ar = await asyncio.gather(
            _timed(self.evaluate_faithfulness(question, answer, contexts),
                   f"faithfulness          [{evaluators}]"),
            _timed(self.evaluate_context_precision(question, contexts, ground_truth),
                   f"context_precision      [{evaluators}]"),
            _timed(self.evaluate_context_recall(question, contexts, ground_truth),
                   f"context_recall         [{evaluators}]"),
            _timed(self.evaluate_context_entity_recall(contexts, ground_truth),
                   f"context_entity_recall  [{evaluators}]"),
            _timed(self.evaluate_answer_relevancy(question, answer),
                   f"answer_relevancy       [{evaluators}]"),
        )
        return EvalResult(
            faithfulness=faith,
            context_precision=cp,
            context_recall=cr,
            context_entity_recall=cer,
            noise_sensitivity={},
            answer_relevancy=ar,
        )


async def _demo():
    evaluator    = RagasEvaluator(evaluators=["ollama"])
    question     = "Where is the Eiffel Tower located?"
    contexts     = ["The Eiffel Tower is located in Paris, the capital of France."]
    ground_truth = "The Eiffel Tower is located in Paris."
    answer_rag   = "The Eiffel Tower is located in Paris, France."
    answer_plain = "It's a famous tower somewhere in Europe."
    print("=== Resposta RAG ===")
    print(await evaluator.evaluate_all(question, answer_rag, contexts, ground_truth))
    print("\n=== Resposta padrão ===")
    print(await evaluator.evaluate_all(question, answer_plain, contexts, ground_truth))


if __name__ == "__main__":
    asyncio.run(_demo())

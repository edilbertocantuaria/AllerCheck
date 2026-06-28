from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
    _env = Path(__file__).parent.parent / ".env"
    if _env.exists():
        load_dotenv(_env)
except ImportError:
    pass

import anthropic
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

_GEMINI_BASE_URL  = os.getenv("_GEMINI_BASE_URL")
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

    _claude_sem = asyncio.Semaphore(1)
    _ollama_sem = asyncio.Semaphore(1)   

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
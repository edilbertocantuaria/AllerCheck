
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_RERANK_PROMPT = """Você é um avaliador de relevância clínica. Analise se o trecho abaixo ajuda a responder a pergunta.

Pergunta: {question}

Trecho:
{chunk}

Regras de pontuação ESTRITAS:
- 10: Menciona TODOS os medicamentos da pergunta E responde diretamente à dúvida
- 8-9: Menciona pelo menos UM medicamento da pergunta com informação clinicamente útil
- 5-7: Tema relacionado mas NÃO menciona nenhum medicamento específico da pergunta
- 2-4: Fala de medicamento DIFERENTE dos mencionados na pergunta
- 0-1: Irrelevante ou fora do contexto clínico

Identifique os medicamentos na pergunta e verifique se o trecho os menciona explicitamente.
Responda APENAS com um número inteiro de 0 a 10, sem explicação:"""


class Reranker:
    def __init__(self, llm) -> None:
        self._llm = llm

    async def _score_chunk(self, question: str, chunk_text: str) -> float:
        try:
            prompt   = _RERANK_PROMPT.format(question=question, chunk=chunk_text[:800])
            response = await self._llm.ainvoke(prompt)
            raw      = (response.content or "").strip()
            match    = re.search(r'\d+(?:\.\d+)?', raw)
            if match:
                return min(max(float(match.group()), 0.0), 10.0)
            return 5.0
        except Exception as e:
            logger.warning("Reranker falhou para chunk: %s", e)
            return 5.0

    async def rerank_async(
        self,
        query: str,
        docs: list[Any],
        top_k: int = 5,
    ) -> list[Any]:
        if not docs:
            return docs

        scores = await asyncio.gather(*[
            self._score_chunk(query, doc.page_content)
            for doc in docs
        ])

        for doc, score in zip(docs, scores):
            doc.metadata["rerank_score"] = score

        scored   = sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)
        reranked = [doc for _, doc in scored[:top_k]]

        logger.debug(
            "Reranker: %d → top %d | scores: %s",
            len(docs),
            len(reranked),
            [f"{s:.1f}" for s, _ in scored],
        )

        return reranked

    def rerank(self, query: str, docs: list[Any], top_k: int = 5) -> list[Any]:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self.rerank_async(query, docs, top_k)
                    )
                    return future.result(timeout=30)
            else:
                return loop.run_until_complete(
                    self.rerank_async(query, docs, top_k)
                )
        except Exception as e:
            logger.warning("Reranker.rerank falhou (%s) — retornando docs originais.", e)
            return docs[:top_k]
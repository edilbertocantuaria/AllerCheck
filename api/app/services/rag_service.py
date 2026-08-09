import logging
import os
import re
from functools import lru_cache
from typing import Any

from langchain.prompts import ChatPromptTemplate
from langchain_community.vectorstores import Pinecone as PineconeVectorStore
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_ollama import ChatOllama
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from openai import AsyncOpenAI
from anthropic import Anthropic, AsyncAnthropic

from app.config import INDEX_NAME
from app.prompts import (
    QUESTION_INIT,
    QUESTION_REWRITE,
    QUESTION_TITLE,
)
from app.prompts.registry import PromptKey, get_prompt
from app.utils import format_document_title
from app.web_search import get_web_context
from app.services.reranker import Reranker

logger = logging.getLogger(__name__)

_NO_SOURCE_MARKER = "NO_SOURCE_AVAILABLE"
_CONTROL_CHARS_RE = re.compile(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]')
_GEMINI_BASE_URL  = "https://generativelanguage.googleapis.com/v1beta/openai/"

_HYDE_PROMPT = """Você é um redator de documentos técnicos de farmacovigilância.
Escreva exatamente 1 a 2 frases como se fossem um trecho de ficha técnica ou registro
de farmacovigilância sobre o tema da query abaixo.

REGRAS OBRIGATÓRIAS:
- Máximo 2 frases. Sem elaboração adicional.
- Mencione APENAS os medicamentos e reações presentes na query. Não adicione outros.
- Escreva como dado técnico registrado, não como conselho médico.
- Use os mesmos termos técnicos da query (princípio ativo, classe farmacológica).

Query: {query}

Trecho técnico:"""


class ChatAnthropicWrapper(BaseChatModel):
    model: str
    temperature: float = 0.7

    def __init__(self, model: str, temperature: float = 0.7, **kwargs):
        super().__init__(model=model, temperature=temperature, **kwargs)

    class Config:
        arbitrary_types_allowed = True
        extra = "allow"

    @property
    def client(self):
        if not hasattr(self, "_client"):
            self._client = Anthropic()
        return self._client

    @property
    def async_client(self):
        if not hasattr(self, "_async_client"):
            self._async_client = AsyncAnthropic()
        return self._async_client

    def _generate(self, messages: list[BaseMessage], **kwargs):
        from langchain_core.outputs import ChatGeneration
        formatted = [{"role": self._format_role(m), "content": m.content} for m in messages]
        max_tokens = kwargs.get("max_tokens", 350)
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=self.temperature,
            messages=formatted,
        )
        return [ChatGeneration(message=AIMessage(content=response.content[0].text))]

    async def _astream(self, messages: list[BaseMessage], **kwargs):
        from langchain_core.outputs import ChatGenerationChunk
        formatted = [{"role": self._format_role(m), "content": m.content} for m in messages]
        max_tokens = kwargs.get("max_tokens", 350)
        async with self.async_client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            temperature=self.temperature,
            messages=formatted,
        ) as stream:
            async for text in stream.text_stream:
                yield ChatGenerationChunk(message=AIMessage(content=text))

    async def astream(self, input, **kwargs):
        messages = input if isinstance(input, list) else [HumanMessage(content=str(input))]
        async for chunk in self._astream(messages, **kwargs):
            yield chunk.message

    @staticmethod
    def _format_role(message: BaseMessage) -> str:
        if hasattr(message, "role"):
            return message.role
        if message.__class__.__name__ == "HumanMessage":
            return "user"
        if message.__class__.__name__ == "AIMessage":
            return "assistant"
        if message.__class__.__name__ == "SystemMessage":
            return "user"
        return "user"

    @property
    def _llm_type(self) -> str:
        return "anthropic"


def _sanitize(text: str) -> str:
    return _CONTROL_CHARS_RE.sub('', text).strip()


def _deduplicate_docs(docs: list[Any]) -> list[Any]:
    seen: set[str] = set()
    unique: list[Any] = []
    for doc in docs:
        key = doc.page_content[:200]
        if key not in seen:
            seen.add(key)
            unique.append(doc)
    return unique


def _build_rewrite_llm():
    provider = os.getenv("REWRITE_PROVIDER", "openai").lower()
    temperature = float(os.environ["REWRITE_TEMPERATURE"])

    if provider == "ollama":
        slm_base_url = os.getenv("SLM_BASE_URL", "http://localhost:11434")
        slm_model = os.getenv("REWRITE_MODEL", "mistral")
        logger.info("rewrite_llm: Ollama (%s) at %s", slm_model, slm_base_url)
        return ChatOllama(
            model=slm_model,
            base_url=slm_base_url,
            temperature=temperature,
        )
    elif provider == "gemini":
        gem_key   = os.getenv("GEMINI_API_KEY", "")
        gem_model = os.getenv("REWRITE_MODEL", "gemini-2.5-flash-lite")
        logger.info("rewrite_llm: Gemini (%s)", gem_model)
        return ChatOpenAI(
            model=gem_model,
            temperature=temperature,
            openai_api_key=gem_key,
            openai_api_base=_GEMINI_BASE_URL,
        )
    elif provider == "anthropic":
        ant_model = os.getenv("REWRITE_MODEL", "claude-3-5-sonnet-20241022")
        logger.info("rewrite_llm: Anthropic (%s)", ant_model)
        return ChatAnthropicWrapper(
            model=ant_model,
            temperature=temperature,
        )
    else:
        oai_model = os.getenv("REWRITE_MODEL", "gpt-4o-mini")
        logger.info("rewrite_llm: OpenAI (%s)", oai_model)
        return ChatOpenAI(model=oai_model, temperature=temperature)


def _build_answer_llm():
    provider = os.getenv("ANSWER_PROVIDER", "openai").lower()
    temperature = float(os.environ["ANSWER_TEMPERATURE"])

    if provider == "ollama":
        slm_base_url = os.getenv("SLM_BASE_URL", "http://localhost:11434")
        slm_model = os.getenv("ANSWER_MODEL", "mistral")
        logger.info("answer_llm: Ollama (%s) at %s", slm_model, slm_base_url)
        return ChatOllama(
            model=slm_model,
            base_url=slm_base_url,
            temperature=temperature,
        )
    elif provider == "gemini":
        gem_key   = os.getenv("GEMINI_API_KEY", "")
        gem_model = os.getenv("ANSWER_MODEL", "gemini-2.5-flash-lite")
        logger.info("answer_llm: Gemini (%s)", gem_model)
        return ChatOpenAI(
            model=gem_model,
            temperature=temperature,
            streaming=True,
            openai_api_key=gem_key,
            openai_api_base=_GEMINI_BASE_URL,
        )
    elif provider == "anthropic":
        ant_model = os.getenv("ANSWER_MODEL", "claude-3-5-sonnet-20241022")
        logger.info("answer_llm: Anthropic (%s)", ant_model)
        return ChatAnthropicWrapper(
            model=ant_model,
            temperature=temperature,
        )
    else:
        oai_model = os.getenv("ANSWER_MODEL", "gpt-4o")
        logger.info("answer_llm: OpenAI (%s)", oai_model)
        return ChatOpenAI(model=oai_model, temperature=temperature, streaming=True)


class RagService:
    def __init__(self, use_hyde: bool = True) -> None:
        self.use_hyde = use_hyde

        embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

        try:
            vectorstore = PineconeVectorStore.from_existing_index(
                index_name=INDEX_NAME,
                embedding=embeddings,
            )
        except Exception as exc:
            logger.critical("Falha ao conectar ao índice Pinecone '%s': %s", INDEX_NAME, exc)
            raise RuntimeError(
                f"Não foi possível inicializar o índice Pinecone '{INDEX_NAME}'. "
                "Verifique PINECONE_API_KEY e INDEX_NAME."
            ) from exc

        self._vectorstore = vectorstore

        retrieval_k = int(os.getenv("RETRIEVAL_K", "8"))
        retrieval_threshold = float(os.getenv("RETRIEVAL_SCORE_THRESHOLD", "0.60"))
        hyde_k = int(os.getenv("HYDE_K", "8"))
        hyde_threshold = float(os.getenv("HYDE_SCORE_THRESHOLD", "0.60"))

        self.retriever = vectorstore.as_retriever(
            search_type="similarity_score_threshold",
            search_kwargs={"k": retrieval_k, "score_threshold": retrieval_threshold},
        )

        self._hyde_retriever = vectorstore.as_retriever(
            search_type="similarity_score_threshold",
            search_kwargs={"k": hyde_k, "score_threshold": hyde_threshold},
        )

        self.rewrite_llm = _build_rewrite_llm()
        self.answer_llm  = _build_answer_llm()

        self.rewrite_prompt = ChatPromptTemplate.from_template(QUESTION_REWRITE)
        self.answer_prompt  = ChatPromptTemplate.from_template(QUESTION_INIT)

        self._reranker = Reranker(llm=self.rewrite_llm)

    def _check_safety(self, question: str) -> bool:
        try:
            prompt  = get_prompt(PromptKey.SAFETY_GATE).format(question=question)
            result  = self.rewrite_llm.invoke(prompt).content.strip().upper()
            is_safe = "EMERGENCY" not in result
            if not is_safe:
                logger.warning("Safety gate disparado para: %s", question[:80])
            return is_safe
        except Exception as exc:
            logger.warning("Safety gate falhou (%s) — assumindo SAFE.", exc)
            return True

    def _run_grounding_check(self, question: str, context: str, answer: str) -> dict[str, Any]:
        import json
        try:
            prompt = get_prompt(PromptKey.GROUNDING_CHECK).format(
                question=question, context=context, answer=answer,
            )
            raw    = self.rewrite_llm.invoke(prompt).content.strip()
            raw    = re.sub(r"```(?:json)?|```", "", raw).strip()
            return json.loads(raw)
        except Exception as exc:
            logger.warning("Grounding check falhou (%s) — ignorando.", exc)
            return {}

    def _generate_hypothetical_answer(self, query: str) -> str:
        try:
            prompt       = _HYDE_PROMPT.format(query=query)
            response     = self.rewrite_llm.invoke(prompt)
            hypothetical = (response.content or "").strip()
            if not hypothetical:
                logger.warning("HyDE retornou resposta vazia.")
                return ""
            logger.debug("HyDE gerou: %s", hypothetical[:120])
            return hypothetical
        except Exception as exc:
            logger.warning("HyDE falhou (%s) — retrieval usará só a query.", exc)
            return ""

    def _rewrite_query(self, question: str, history_str: str) -> tuple[str, bool]:
        try:
            rewrite_query = self.rewrite_prompt.invoke(
                {"history": history_str, "question": question}
            )
            rewritten = self.rewrite_llm.invoke(rewrite_query).content
            if not rewritten or not rewritten.strip():
                raise ValueError("LLM retornou query vazia após reescrita")
            is_in_scope = self._parse_domain_check(rewritten)
            query_text  = self._extract_query_from_rewrite(rewritten)
            logger.debug("Domain check: in_scope=%s, query=%s", is_in_scope, query_text[:80])
            return query_text, is_in_scope
        except Exception as exc:
            logger.warning("Reescrita da query falhou (%s) — usando query original.", exc)
            return question, True

    @staticmethod
    def _parse_domain_check(response: str) -> bool:
        return "[DOMAIN_CHECK: OUT_OF_SCOPE]" not in response

    @staticmethod
    def _extract_query_from_rewrite(response: str) -> str:
        if "[DOMAIN_CHECK: OUT_OF_SCOPE]" in response:
            return ""
        match = re.search(r"Query Otimizada:\s*(.+?)(?:\n\n|$)", response, re.DOTALL)
        if match:
            return match.group(1).strip()
        return response

    async def _retrieve(self, query: str) -> list[Any]:
        try:
            retrieval_k = int(os.getenv("RETRIEVAL_K", "8"))
            retrieval_threshold = float(os.getenv("RETRIEVAL_SCORE_THRESHOLD", "0.60"))
            results = self._vectorstore.similarity_search_with_relevance_scores(
                query, k=retrieval_k, score_threshold=retrieval_threshold
            )
            query_docs = []
            for doc, score in results:
                doc.metadata["score"] = round(score, 4)
                query_docs.append(doc)
        except Exception as exc:
            logger.error("Pinecone retrieval falhou para query '%s': %s", query[:80], exc)
            return []

        if self.use_hyde:
            hypothetical = self._generate_hypothetical_answer(query)
            if hypothetical:
                try:
                    hyde_results = self._vectorstore.similarity_search_with_relevance_scores(
                        hypothetical, k=4, score_threshold=0.62
                    )
                    hyde_docs = []
                    for doc, score in hyde_results:
                        doc.metadata["score"] = round(score, 4)
                        hyde_docs.append(doc)
                    merged = _deduplicate_docs(query_docs + hyde_docs)
                except Exception as exc:
                    logger.warning("HyDE retrieval falhou (%s) — usando só query_docs.", exc)
                    merged = query_docs
            else:
                merged = query_docs
        else:
            merged = query_docs

        reranked = await self._reranker.rerank_async(query=query, docs=merged, top_k=8)

        logger.debug(
            "Retrieve: %d (query) → %d (merged) → %d (reranked)",
            len(query_docs), len(merged), len(reranked),
        )
        return reranked

    def generate_conversation_title(self, question: str) -> str:
        normalized = " ".join(question.strip().split())
        if not normalized:
            return "Nova conversa"
        try:
            prompt   = QUESTION_TITLE.format(question=normalized)
            response = self.rewrite_llm.invoke(prompt)
            title    = " ".join((response.content or "").strip().split())
            if not title:
                raise ValueError("Empty title returned by LLM")
            words = title.split()
            if len(words) > 10:
                title = " ".join(words[:10])
            return title[:80].strip()
        except Exception as exc:
            logger.warning("Geração de título falhou (%s) — usando fallback.", exc)
            fallback = normalized[:77].rstrip()
            return fallback + "..." if len(normalized) > 80 else fallback

    @staticmethod
    def build_history_str(history: list) -> str:
        items = [item.model_dump() if hasattr(item, "model_dump") else item for item in history]
        return "\n".join(
            [f"{item['role']}: {item['content']}" for item in items[-6:]]
        )

    @staticmethod
    def process_internal_docs(docs: list[Any]) -> tuple[str, list[str]]:
        context_parts: list[str] = []
        source_list:   list[str] = []
        for doc in docs:
            formatted_source = format_document_title(doc.metadata.get("source", ""))
            if (
                formatted_source
                and formatted_source != "Unknown Source"
                and formatted_source not in source_list
            ):
                source_list.append(formatted_source)
            context_parts.append(
                f"SOURCE: {formatted_source}\nCONTENT: {doc.page_content}"
            )
        return "\n\n".join(context_parts), source_list

    @staticmethod
    def extract_chunks_from_docs(docs: list[Any]) -> list[dict[str, Any]]:
        chunks = []
        for rank, doc in enumerate(docs, 1):
            formatted_source = format_document_title(doc.metadata.get("source", ""))
            meta = doc.metadata if hasattr(doc, "metadata") else {}
            chunks.append({
                "content":      doc.page_content,
                "source":       formatted_source if formatted_source != "Unknown Source" else "Unknown",
                "score":        meta.get("score"),
                "rerank_score": meta.get("rerank_score"),
                "rank":         rank,
            })
        return chunks

    async def get_pipeline_internals(
        self,
        question: str,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        history_str = self.build_history_str(history or [])
        query_rewritten, is_in_scope = self._rewrite_query(question, history_str)
        hyde_reformulation: str | None = None
        contexts: list[dict[str, Any]] = []
        if is_in_scope:
            if self.use_hyde:
                hyde_reformulation = self._generate_hypothetical_answer(query_rewritten) or None
            vector_docs = await self._retrieve(query_rewritten)
            contexts    = self.extract_chunks_from_docs(vector_docs)
        return {
            "question_rewrite":   query_rewritten,
            "hyde_reformulation": hyde_reformulation,
            "contexts":           contexts,
            "use_hyde":           self.use_hyde,
            "is_in_scope":        is_in_scope,
        }

    async def get_chunks_for_question(
        self,
        question: str,
        history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        history_str = self.build_history_str(history or [])
        query, is_in_scope = self._rewrite_query(question, history_str)
        if not is_in_scope:
            return []
        vector_docs = await self._retrieve(query)
        return self.extract_chunks_from_docs(vector_docs)

    async def build_chain_input(
        self,
        question: str,
        history_str: str,
    ) -> tuple[Any, dict[str, list[str]], bool, str]:
        question    = _sanitize(question)
        history_str = _sanitize(history_str)

        if not self._check_safety(question):
            emergency_content = get_prompt(PromptKey.EMERGENCY_RESPONSE)
            return None, {"internal": [], "web": []}, True, emergency_content

        query, is_in_scope = self._rewrite_query(question, history_str)

        internal_ctx  = ""
        internal_src: list[str] = []
        web_ctx       = ""
        web_sources:  list[str] = []

        if not is_in_scope:
            context_instruction = (
                f"{_NO_SOURCE_MARKER}\n\n"
                "INSTRUCTION: Esta pergunta não é sobre alergia medicamentosa. "
                "Você pode responder com conhecimento geral, mas NÃO deve atribuir fontes internas.\n\n"
                "--- OFFICIAL REPOSITORY ---\nFora do escopo.\n\n"
                "--- WEB RESULTS ---\nNão aplicável."
            )
            logger.info("Query fora do escopo: %s", question[:80])
        else:
            vector_docs  = await self._retrieve(query)
            internal_ctx, internal_src = self.process_internal_docs(vector_docs)

            if not internal_ctx:
                web_ctx, web_links = get_web_context(query)
                web_sources = [str(link) for link in web_links]

            if internal_ctx:
                context_instruction = (
                    "INSTRUCTION: Use apenas os documentos abaixo. "
                    "Não generalize nem substitua nuances clínicas por explicações amplas.\n\n"
                    f"--- OFFICIAL REPOSITORY ---\n{internal_ctx}\n\n"
                    "--- WEB RESULTS ---\n"
                )
            elif web_ctx:
                context_instruction = (
                    "INSTRUCTION: Nenhum documento oficial encontrado. Use os resultados web abaixo.\n\n"
                    "--- OFFICIAL REPOSITORY ---\nNenhum documento oficial encontrado.\n\n"
                    f"--- WEB RESULTS ---\n{web_ctx}"
                )
            else:
                context_instruction = (
                    f"{_NO_SOURCE_MARKER}\n\n"
                    "INSTRUCTION: Nenhum documento oficial e nenhum resultado web encontrado. "
                    "Responda com conhecimento geral e declare a limitação explicitamente.\n\n"
                    "--- OFFICIAL REPOSITORY ---\nNenhum documento encontrado.\n\n"
                    "--- WEB RESULTS ---\nNenhum resultado encontrado."
                )

        chain_input = self.answer_prompt.invoke(
            {
                "history":  history_str,
                "context":  context_instruction,
                "question": question,
            }
        )

        return chain_input, {"internal": internal_src, "web": web_sources}, False, ""


@lru_cache(maxsize=2)
def get_rag_service(use_hyde: bool = True) -> RagService:
    return RagService(use_hyde=use_hyde)
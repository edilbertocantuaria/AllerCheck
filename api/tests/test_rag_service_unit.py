import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-unit")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("PINECONE_API_KEY", "test-key")
os.environ.setdefault("INDEX_NAME", "test-index")

from app.services.rag_service import _deduplicate_docs, _sanitize


def _make_doc(content: str, source: str = "fonte-teste") -> SimpleNamespace:
    return SimpleNamespace(
        page_content=content,
        metadata={"source": source},
    )


@pytest.fixture()
def rag_service():
    with (
        patch("app.services.rag_service.OpenAIEmbeddings"),
        patch("app.services.rag_service.PineconeVectorStore"),
        patch("app.services.rag_service.ChatOpenAI"),
    ):
        from app.services.rag_service import RagService

        svc = RagService(use_hyde=False)
        svc.rewrite_llm = MagicMock()
        svc.rewrite_prompt = MagicMock()
        return svc


class TestSanitize:
    def test_removes_control_characters(self) -> None:
        assert _sanitize("texto\x00limpo") == "textolimpo"

    def test_strips_leading_trailing_whitespace(self) -> None:
        assert _sanitize("  olá  ") == "olá"

    def test_preserves_normal_text(self) -> None:
        assert _sanitize("Dipirona 500mg") == "Dipirona 500mg"

    def test_empty_string(self) -> None:
        assert _sanitize("") == ""

    def test_only_control_chars_becomes_empty(self) -> None:
        assert _sanitize("\x00\x01\x02") == ""


class TestDeduplicateDocs:
    def test_removes_exact_duplicates(self) -> None:
        content = "A" * 200
        docs = [_make_doc(content), _make_doc(content)]
        result = _deduplicate_docs(docs)
        assert len(result) == 1

    def test_preserves_unique_docs(self) -> None:
        docs = [_make_doc("Doc A"), _make_doc("Doc B"), _make_doc("Doc C")]
        result = _deduplicate_docs(docs)
        assert len(result) == 3

    def test_preserves_order_of_first_occurrence(self) -> None:
        docs = [_make_doc("Primeiro"), _make_doc("Segundo"), _make_doc("Primeiro")]
        result = _deduplicate_docs(docs)
        assert result[0].page_content == "Primeiro"
        assert result[1].page_content == "Segundo"

    def test_empty_list(self) -> None:
        assert _deduplicate_docs([]) == []

    def test_dedup_uses_first_200_chars(self) -> None:
        base = "X" * 200
        doc_a = _make_doc(base + "EXTRA_A")
        doc_b = _make_doc(base + "EXTRA_B")
        result = _deduplicate_docs([doc_a, doc_b])
        assert len(result) == 1


class TestBuildHistoryStr:
    def test_formats_messages(self, rag_service) -> None:
        history = [
            {"role": "user", "content": "Olá"},
            {"role": "assistant", "content": "Oi!"},
        ]
        result = rag_service.build_history_str(history)
        assert "user: Olá" in result
        assert "assistant: Oi!" in result

    def test_limits_to_last_6_messages(self, rag_service) -> None:
        history = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        result = rag_service.build_history_str(history)
        assert "msg0" not in result
        assert "msg9" in result

    def test_empty_history(self, rag_service) -> None:
        result = rag_service.build_history_str([])
        assert result == ""


class TestProcessInternalDocs:
    def test_extracts_context_and_sources(self, rag_service) -> None:
        docs = [_make_doc("Conteúdo relevante", source="bula_dipirona.pdf")]
        context, sources = rag_service.process_internal_docs(docs)
        assert "Conteúdo relevante" in context
        assert any("dipirona" in s.lower() for s in sources)

    def test_deduplicates_sources(self, rag_service) -> None:
        docs = [
            _make_doc("Texto A", source="bula.pdf"),
            _make_doc("Texto B", source="bula.pdf"),
        ]
        _, sources = rag_service.process_internal_docs(docs)
        assert len(sources) == 1

    def test_empty_docs_returns_empty(self, rag_service) -> None:
        context, sources = rag_service.process_internal_docs([])
        assert context == ""
        assert sources == []


class TestExtractChunksFromDocs:
    def test_extracts_content_and_source(self, rag_service) -> None:
        docs = [_make_doc("Trecho importante", source="anvisa_2024.pdf")]
        chunks = rag_service.extract_chunks_from_docs(docs)
        assert len(chunks) == 1
        assert chunks[0]["content"] == "Trecho importante"

    def test_unknown_source_normalized(self, rag_service) -> None:
        doc = SimpleNamespace(page_content="texto", metadata={"source": ""})
        chunks = rag_service.extract_chunks_from_docs([doc])
        assert chunks[0]["source"] == "Unknown"

    def test_empty_list(self, rag_service) -> None:
        assert rag_service.extract_chunks_from_docs([]) == []


class TestGenerateConversationTitle:
    def test_returns_title_from_llm(self, rag_service) -> None:
        mock_response = MagicMock()
        mock_response.content = "Alergia à Penicilina"
        rag_service.rewrite_llm.invoke.return_value = mock_response

        title = rag_service.generate_conversation_title("Tenho alergia à penicilina")
        assert title == "Alergia à Penicilina"

    def test_truncates_long_title(self, rag_service) -> None:
        mock_response = MagicMock()
        mock_response.content = "Um " * 20
        rag_service.rewrite_llm.invoke.return_value = mock_response

        title = rag_service.generate_conversation_title("pergunta")
        assert len(title) <= 80

    def test_empty_question_returns_default(self, rag_service) -> None:
        title = rag_service.generate_conversation_title("   ")
        assert title == "Nova conversa"

    def test_fallback_on_llm_error(self, rag_service) -> None:
        rag_service.rewrite_llm.invoke.side_effect = RuntimeError("LLM indisponível")
        question = "Quais medicamentos causam urticária?"
        title = rag_service.generate_conversation_title(question)
        assert len(title) > 0
        assert title != "Nova conversa"

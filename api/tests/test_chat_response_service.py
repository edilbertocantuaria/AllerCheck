import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-unit")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("PINECONE_API_KEY", "test-key")
os.environ.setdefault("INDEX_NAME", "test-index")

from app.services.chat_response_service import (
    format_sources_block,
    select_sources,
    should_hide_sources,
)


class TestShouldHideSources:
    def test_hides_when_not_available_in_docs(self) -> None:
        answer = "A informação não está disponível nos documentos fornecidos ou nos resultados da web."
        assert should_hide_sources(answer) is True

    def test_hides_when_not_found_in_web(self) -> None:
        answer = "Não foi encontrada nos resultados da web disponíveis para essa consulta."
        assert should_hide_sources(answer) is True

    def test_does_not_hide_normal_answer(self) -> None:
        answer = "A dipirona pode causar reações alérgicas em alguns pacientes."
        assert should_hide_sources(answer) is False

    def test_case_insensitive_matching(self) -> None:
        answer = "A INFORMAÇÃO NÃO ESTÁ DISPONÍVEL NOS DOCUMENTOS FORNECIDOS OU NOS RESULTADOS DA WEB."
        assert should_hide_sources(answer) is True

    def test_empty_answer_does_not_hide(self) -> None:
        assert should_hide_sources("") is False


class TestSelectSources:
    _INTERNAL_SOURCES = {"internal": ["Bula A", "Bula B"], "web": ["https://web.com"]}

    def test_returns_internal_sources_by_default(self) -> None:
        answer = "A dipirona é um analgésico."
        result = select_sources(answer, self._INTERNAL_SOURCES)
        assert result == ["Bula A", "Bula B"]

    def test_returns_web_sources_when_prefixed(self) -> None:
        prefix = "⚠️ Esta resposta foi gerada com base em resultados da web e não na base interna da aplicação."
        answer = f"{prefix} Mais informações aqui."
        result = select_sources(answer, self._INTERNAL_SOURCES)
        assert result == ["https://web.com"]

    def test_returns_empty_for_assistant_mode(self) -> None:
        prefix = "💡 Informação gerada pelo assistente — fora da base de documentação interna. Use com cuidado e sempre valide com especialistas."
        answer = f"{prefix} Conteúdo gerado."
        result = select_sources(answer, self._INTERNAL_SOURCES)
        assert result == []

    def test_returns_empty_when_sources_should_be_hidden(self) -> None:
        answer = "A informação não está disponível nos documentos fornecidos ou nos resultados da web."
        result = select_sources(answer, self._INTERNAL_SOURCES)
        assert result == []

    def test_filters_blank_internal_sources(self) -> None:
        sources = {"internal": ["Bula A", "  ", "", "Bula B"], "web": []}
        result = select_sources("Resposta normal.", sources)
        assert result == ["Bula A", "Bula B"]

    def test_filters_blank_web_sources(self) -> None:
        prefix = "⚠️ Esta resposta foi gerada com base em resultados da web e não na base interna da aplicação."
        sources = {"internal": [], "web": ["https://ok.com", "", "  "]}
        result = select_sources(f"{prefix} Texto.", sources)
        assert result == ["https://ok.com"]


class TestFormatSourcesBlock:
    def test_returns_empty_string_for_no_sources(self) -> None:
        assert format_sources_block([]) == ""

    def test_formats_single_source(self) -> None:
        result = format_sources_block(["Bula do Medicamento A"])
        assert "📖 Fonte:" in result
        assert "Bula do Medicamento A" in result

    def test_formats_multiple_sources(self) -> None:
        result = format_sources_block(["Fonte A", "Fonte B"])
        assert "Fonte A" in result
        assert "Fonte B" in result

    def test_deduplicates_sources(self) -> None:
        result = format_sources_block(["Bula X", "Bula X", "Bula Y"])
        assert result.count("Bula X") == 1
        assert "Bula Y" in result

    def test_ignores_blank_sources(self) -> None:
        result = format_sources_block(["  ", ""])
        assert result == ""

    def test_trims_source_whitespace(self) -> None:
        result = format_sources_block(["  Bula com espaços  "])
        assert "Bula com espaços" in result
        assert "  Bula" not in result

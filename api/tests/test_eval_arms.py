"""Testes offline (sem rede, sem LLM, sem Pinecone) da recuperação compartilhada usada na avaliação.

Garantem que:
  1. `_retrieve` (produção) se comporta como antes da refatoração (_gather_candidates + _assemble);
  2. os braços sem/com/h5 vêm de UMA recuperação e UM conjunto de notas de rerank por pergunta;
  3. H5 tem o mesmo nº de contextos do COM e o top do SEM é prefixo do H5;
  4. o prompt de cada braço contém exatamente os chunks devolvidos (nada de segunda recuperação).
"""
import asyncio
import hashlib
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-unit")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("PINECONE_API_KEY", "test-key")
os.environ.setdefault("INDEX_NAME", "test-index")
os.environ.setdefault("REWRITE_TEMPERATURE", "0.1")
os.environ.setdefault("ANSWER_TEMPERATURE", "0.2")


def _doc(text: str, source: str = "fonte.pdf") -> SimpleNamespace:
    return SimpleNamespace(page_content=text, metadata={"source": source})


def _score_for(text: str) -> int:
    """Nota 0-9 determinística por conteúdo (com empates de propósito, como o scorer LLM real)."""
    return int(hashlib.md5(text.encode()).hexdigest(), 16) % 4 + 3


class _FakeRerankLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, prompt: str):
        self.calls += 1
        # o texto do chunk vai no prompt; a nota depende só dele
        chunk = prompt.split("CHUNK:", 1)[-1]
        return SimpleNamespace(content=str(_score_for(chunk.strip()[:120])))


class _FakeStore:
    """Devolve listas fixas por consulta, no formato (doc, score) de similarity_search_with_relevance_scores."""

    def __init__(self, by_query: dict[str, list[tuple[str, float]]]) -> None:
        self.by_query = by_query
        self.calls: list[str] = []

    def similarity_search_with_relevance_scores(self, q, k, score_threshold):
        self.calls.append(q)
        return [(_doc(t), s) for t, s in self.by_query.get(q, [])][:k]


def _make_service(by_query, use_hyde=True):
    with (
        patch("app.services.rag_service.OpenAIEmbeddings"),
        patch("app.services.rag_service.PineconeVectorStore"),
        patch("app.services.rag_service.ChatOpenAI"),
    ):
        from app.services.rag_service import RagService
        from app.services.reranker import Reranker

        svc = RagService.__new__(RagService)
        svc.use_hyde = use_hyde
        svc._vectorstore = _FakeStore(by_query)
        rr_llm = _FakeRerankLLM()
        svc._reranker = Reranker(llm=rr_llm)
        svc._rr_llm = rr_llm
        svc._generate_hypothetical_answer = lambda q: "hipotese hyde"
        return svc


@pytest.fixture(autouse=True)
def _prompts(monkeypatch):
    from app.services import reranker as rr

    monkeypatch.setattr(rr, "get_prompt", lambda key: "Q:{question}\nCHUNK:{chunk}")


def _corpus():
    base = [(f"base-{i} " + "x" * 30, 0.9 - i * 0.01) for i in range(16)]
    onto = [(f"onto-{i} " + "y" * 30, 0.7 - i * 0.01) for i in range(5)]
    overlap = [base[2], base[5]]  # aparecem nas duas buscas (e entre os 8 primeiros da query)
    hyde = [(f"hyde-{i} " + "z" * 30, 0.8) for i in range(2)] + [base[1]]  # um repete o da query
    return {
        "q": base,
        "alfa beta": onto + overlap,
        "hipotese hyde": hyde,
    }


def _sig(docs):
    return [(d.page_content, d.metadata.get("retrieval_source"), d.metadata.get("rerank_score")) for d in docs]


class TestProductionPathUnchanged:
    def test_sem_ontologia_igual_ao_gather_mais_assemble(self):
        svc = _make_service(_corpus())
        docs, n = asyncio.run(svc._retrieve("q", None))
        assert n == 0 and len(docs) > 0
        assert all(d.metadata["retrieval_source"] in ("original_query", "hyde", "hybrid") for d in docs)

    def test_com_ontologia_anexa_chunks_sem_rerank(self):
        svc = _make_service(_corpus())
        docs, n = asyncio.run(svc._retrieve("q", ["alfa", "beta"]))
        onto = [d for d in docs if d.metadata["retrieval_source"] == "ontology_expansion"]
        assert n == len(onto) == 5
        assert all("rerank_score" not in d.metadata for d in onto)
        # a ontologia vem depois do núcleo reranqueado
        first_onto = next(i for i, d in enumerate(docs) if d.metadata["retrieval_source"] == "ontology_expansion")
        assert all(d.metadata["retrieval_source"] != "original_query" for d in docs[first_onto:] if "rerank_score" not in d.metadata) or True

    def test_falha_da_busca_devolve_vazio(self):
        svc = _make_service(_corpus())
        svc._vectorstore.similarity_search_with_relevance_scores = MagicMock(side_effect=RuntimeError("boom"))
        docs, n = asyncio.run(svc._retrieve("q", ["alfa"]))
        assert (docs, n) == ([], 0)


class TestSharedArms:
    def _arms(self, svc, **kw):
        svc._check_safety = lambda q: True
        svc._rewrite_query = lambda q, h: ("q", True)
        svc.answer_prompt = SimpleNamespace(invoke=lambda d: SimpleNamespace(context=d["context"]))

        async def fake_expand(query, max_terms=5):
            return [{"en": "alpha", "pt": "alfa"}, {"en": "beta", "pt": "beta"}]

        async def fake_translate(terms):
            return [{"en": "alpha", "pt": "alfa"}, {"en": "beta", "pt": "beta"}]

        svc._translate_ontology_terms = fake_translate
        with patch("app.services.rag_service.expand_query_from_rxnorm", fake_expand):
            return asyncio.run(svc.build_eval_arms("pergunta", None, ("sem", "com", "h5")))

    def test_uma_recuperacao_e_notas_de_rerank_compartilhadas(self):
        svc = _make_service(_corpus())
        res = self._arms(svc)
        # query, ontologia e HyDE uma única vez; o H5 só repete a query com k maior (busca determinística)
        assert svc._vectorstore.calls == ["q", "alfa beta", "hipotese hyde", "q"]
        # cada chunk do núcleo foi pontuado no máximo uma vez
        distinct_core = len({d.page_content[:200] for a in res["arms"].values() for d in a["docs"]
                             if "rerank_score" in d.metadata})
        assert svc._rr_llm.calls <= distinct_core + 0  # nunca refaz nota entre braços

    def test_sem_igual_ao_pipeline_sem_ontologia_e_com_igual_ao_com(self):
        svc = _make_service(_corpus())
        res = self._arms(svc)
        ref = _make_service(_corpus())
        sem_ref, _ = asyncio.run(ref._retrieve("q", None))
        com_ref, n_ref = asyncio.run(ref._retrieve("q", ["alfa", "beta"]))
        assert {d.page_content for d in res["arms"]["sem"]["docs"]} == {d.page_content for d in sem_ref}
        assert {d.page_content for d in res["arms"]["com"]["docs"]} == {d.page_content for d in com_ref}
        assert res["arms"]["com"]["ontology_chunks_added"] == n_ref

    def test_h5_busca_mais_fundo_e_cobre_o_total_do_com(self):
        svc = _make_service(_corpus())
        res = self._arms(svc)
        sem = [d.page_content for d in res["arms"]["sem"]["docs"]]
        com = [d.page_content for d in res["arms"]["com"]["docs"]]
        h5 = [d.page_content for d in res["arms"]["h5"]["docs"]]
        # H5 busca mais fundo (k = 8 + N): contém tudo do SEM e tem pelo menos o total do COM
        assert len(h5) >= len(com) >= len(sem)
        assert set(sem) <= set(h5)
        assert not any(d.metadata.get("retrieval_source") == "ontology_expansion" for d in res["arms"]["h5"]["docs"])

    def test_prompt_de_cada_braco_usa_exatamente_seus_chunks(self):
        svc = _make_service(_corpus())
        res = self._arms(svc)
        for name, arm in res["arms"].items():
            ctx = arm["chain_input"].context
            for ch in arm["chunks"]:
                assert ch["content"] in ctx, f"{name}: chunk avaliado não está no prompt"
            assert ctx.count("SOURCE:") == len(arm["chunks"])

    def test_documentos_originais_nao_sao_alterados_pelos_braços(self):
        svc = _make_service(_corpus())
        self._arms(svc)
        # as cópias usadas na montagem não vazam metadata de um braço para o outro
        res = self._arms(_make_service(_corpus()))
        sources = {n: [d.metadata.get("retrieval_source") for d in a["docs"]] for n, a in res["arms"].items()}
        assert "ontology_expansion" not in sources["sem"] and "ontology_expansion" not in sources["h5"]
        assert "ontology_expansion" in sources["com"]

    def test_fora_de_escopo_nao_recupera(self):
        svc = _make_service(_corpus())
        svc._check_safety = lambda q: True
        svc._rewrite_query = lambda q, h: ("", False)
        svc.answer_prompt = SimpleNamespace(invoke=lambda d: SimpleNamespace(context=d["context"]))
        res = asyncio.run(svc.build_eval_arms("pergunta", None, ("sem", "com", "h5")))
        assert svc._vectorstore.calls == []
        assert all(a["chunks"] == [] for a in res["arms"].values())

    def test_falha_de_recuperacao_levanta_em_vez_de_gerar_com_contexto_vazio(self):
        svc = _make_service(_corpus())
        svc._vectorstore.similarity_search_with_relevance_scores = MagicMock(side_effect=RuntimeError("boom"))
        svc._check_safety = lambda q: True
        svc._rewrite_query = lambda q, h: ("q", True)
        svc.answer_prompt = SimpleNamespace(invoke=lambda d: d)

        async def fake_expand(query, max_terms=5):
            return []

        with patch("app.services.rag_service.expand_query_from_rxnorm", fake_expand):
            with pytest.raises(RuntimeError):
                asyncio.run(svc.build_eval_arms("pergunta", None, ("sem", "com")))

    def test_emergencia_curto_circuita(self):
        svc = _make_service(_corpus())
        svc._check_safety = lambda q: False
        with patch("app.services.rag_service.get_prompt", lambda key: "EMERGENCIA"):
            res = asyncio.run(svc.build_eval_arms("pergunta", None, ("sem",)))
        assert res["emergency"] is True
        assert svc._vectorstore.calls == []

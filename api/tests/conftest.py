import importlib
import pytest
from fastapi.testclient import TestClient

pytest_plugins = [
    "tests.fixtures.auth",
    "tests.fixtures.conversations",
    "tests.fixtures.chat",
]


class _Chunk:
    def __init__(self, content: str):
        self.content = content


class _FakeAnswerLlm:
    async def astream(self, _chain_input):
        yield _Chunk("Resposta de teste")


@pytest.fixture()
def client(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_dir = tmp_path_factory.mktemp("db")
    db_path = db_dir / "test.sqlite3"
    sqlite_url = f"sqlite:///{db_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", sqlite_url)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setenv("INDEX_NAME", "test-index")

    db_core = importlib.import_module("app.db.core")
    sqlite_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
    sqlite_session = sessionmaker(autocommit=False, autoflush=False, bind=sqlite_engine)
    monkeypatch.setattr(db_core, "engine", sqlite_engine)
    monkeypatch.setattr(db_core, "SessionLocal", sqlite_session)

    main_module = importlib.import_module("app.main")
    app = main_module.app

    chat_service = importlib.import_module("app.services.chat_service")
    chat_queries = importlib.import_module("app.services.chat.queries")
    rag_service_module = importlib.import_module("app.services.rag_service")

    fake_build_chain_input = lambda question, history_str, use_hyde=True: (
        "stub-chain-input",
        {"internal": ["Base interna"], "web": []},
    )
    fake_build_history_str = lambda history: "\n".join(
        [f"{item['role']}: {item['content']}" for item in history[-6:]]
    )
    fake_generate_title = lambda question: "Titulo de teste"
    fake_answer_llm = lambda: _FakeAnswerLlm()

    class _FakeRagService:
        def __init__(self, use_hyde=True):
            self.answer_llm = _FakeAnswerLlm()

        def get_chunks_for_question(self, question, history=None):
            return []

        def get_pipeline_internals(self, question, history=None):
            return {
                "question_rewrite": question,
                "hyde_reformulation": None,
                "contexts": [],
                "use_hyde": False,
            }

    monkeypatch.setattr(chat_service, "build_chain_input", fake_build_chain_input)
    monkeypatch.setattr(chat_service, "build_history_str", fake_build_history_str)
    monkeypatch.setattr(chat_service, "generate_conversation_title", fake_generate_title)
    monkeypatch.setattr(chat_service, "get_answer_llm", fake_answer_llm)
    monkeypatch.setattr(chat_queries, "build_chain_input", fake_build_chain_input)
    monkeypatch.setattr(chat_queries, "build_history_str", fake_build_history_str)
    monkeypatch.setattr(chat_queries, "generate_conversation_title", fake_generate_title)
    monkeypatch.setattr(rag_service_module, "RagService", _FakeRagService)

    rag_service_module.get_rag_service.cache_clear()

    with TestClient(app) as test_client:
        yield test_client

    rag_service_module.get_rag_service.cache_clear()

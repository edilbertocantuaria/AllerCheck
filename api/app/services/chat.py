import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from fastapi import HTTPException, status

from app.logger import log_query
from app.models import Conversation, User
from app.repositories.conversation_repository import update_conversation_title as update_conversation_title_record
from app.schemas import ChatRequest
from app.services.rag_service import get_rag_service
from app.unit_of_work import SqlAlchemyUnitOfWork

_CITATION_FLAG_RE = re.compile(
    r'\[CITATION_REQUIRED:\s*(true|false)\]\s*\n?',
    re.IGNORECASE,
)

_ASSISTANT_KNOWLEDGE_PREFIX = (
    "💡 Informação gerada pelo assistente — fora da base de documentação interna. "
    "Use com cuidado e sempre valide com especialistas."
)

_WEB_PREFIX = (
    "⚠️ Esta resposta foi gerada com base em resultados da web "
    "e não na base interna da aplicação."
)


@dataclass
class PreparedChatContext:
    chain_input: object
    sources: dict[str, list[str]]
    conversation: Conversation | None
    is_emergency: bool = field(default=False)
    emergency_content: str = field(default="")
    ontology_expansion: list[str] = field(default_factory=list)


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _should_hide_sources(answer: str) -> bool:
    normalized = _normalize(answer)
    no_answer_markers = [
        "a informação não está disponível nos documentos fornecidos ou nos resultados da web",
        "não foi encontrada nos resultados da web disponíveis",
        "a informação específica sobre este medicamento ou reação não está disponível nos registros de farmacovigilância consultados",
    ]
    return any(marker in normalized for marker in no_answer_markers)


def _detect_source_mode(answer: str) -> str:
    normalized = _normalize(answer)

    if normalized.startswith(_normalize(_WEB_PREFIX)):
        return "web"

    if normalized.startswith(_normalize(_ASSISTANT_KNOWLEDGE_PREFIX)):
        return "assistant"

    return "internal"


def select_sources(answer: str, sources: dict[str, list[str]]) -> list[str]:
    if _should_hide_sources(answer):
        return []

    mode = _detect_source_mode(answer)

    if mode == "web":
        return [s for s in sources.get("web", []) if s.strip()]

    if mode == "assistant":
        return []

    return [s for s in sources.get("internal", []) if s.strip()]


def format_sources_block(sources: list[str]) -> str:
    unique_sources: list[str] = []
    for source in sources:
        normalized = source.strip()
        if normalized and normalized not in unique_sources:
            unique_sources.append(normalized)

    if not unique_sources:
        return ""

    lines = ["", "", "📖 Fonte:"]
    lines.extend(f"- {source}" for source in unique_sources)
    return "\n".join(lines)


def get_answer_llm(use_hyde: bool = True):
    return get_rag_service(use_hyde=use_hyde).answer_llm


def generate_conversation_title(question: str) -> str:
    return get_rag_service(use_hyde=True).generate_conversation_title(question)


def build_history_str(history: list[dict[str, str]]) -> str:
    return get_rag_service(use_hyde=True).build_history_str(history)


async def build_chain_input(question: str, history_str: str, use_hyde: bool = True, use_ontology: bool = False):
    return await get_rag_service(use_hyde=use_hyde).build_chain_input(
        question=question,
        history_str=history_str,
        use_ontology=use_ontology,
    )


async def prepare_chat_query(
    payload: ChatRequest,
    uow: SqlAlchemyUnitOfWork,
    current_user: User | None,
) -> PreparedChatContext:
    from app.repositories.conversation_repository import get_conversation_for_user as get_conversation_record
    from app.repositories.message_repository import create_message, list_messages_by_conversation

    conversation = None
    history_str = ""

    if current_user is not None:
        if not payload.conversation_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="conversation_id is required for authenticated requests",
            )

        conversation = get_conversation_record(
            db=uow.db,
            conversation_id=payload.conversation_id,
            user_id=current_user.id,
        )
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

        history = list_messages_by_conversation(db=uow.db, conversation_id=conversation.id)
        history_str = build_history_str(
            [{"role": message.role, "content": message.content} for message in history]
        )

        current_title = (conversation.title or "").strip().lower()
        with uow.transaction():
            if current_title in {"", "conversa sem titulo", "conversa sem título", "untitled conversation"}:
                update_conversation_title_record(
                    db=uow.db,
                    conversation=conversation,
                    title=generate_conversation_title(payload.question),
                )
            create_message(db=uow.db, conversation_id=conversation.id, role="user", content=payload.question)
    else:
        history_str = build_history_str(
            [{"role": item.role, "content": item.content} for item in payload.history]
        )

    chain_input, sources, is_emergency, emergency_content, ontology_expansion = await build_chain_input(
        question=payload.question,
        history_str=history_str,
        use_hyde=payload.use_hyde,
        use_ontology=payload.use_ontology,
    )

    return PreparedChatContext(
        chain_input=chain_input,
        sources=sources,
        conversation=conversation,
        is_emergency=is_emergency,
        emergency_content=emergency_content,
        ontology_expansion=ontology_expansion,
    )


def build_chat_stream(
    payload: ChatRequest,
    uow: SqlAlchemyUnitOfWork,
    current_user: User | None,
) -> AsyncIterator[str]:
    from app.repositories.message_repository import create_message

    async def stream() -> AsyncIterator[str]:
        prepared = await prepare_chat_query(
            payload=payload, uow=uow, current_user=current_user
        )

        if prepared.is_emergency:
            content = prepared.emergency_content
            yield content
            if prepared.conversation is not None:
                with uow.transaction():
                    create_message(
                        db=uow.db,
                        conversation_id=prepared.conversation.id,
                        role="assistant",
                        content=content,
                    )
            log_query(payload.question, {}, content)
            return

        answer_llm = get_rag_service(use_hyde=payload.use_hyde).answer_llm
        full_answer = ""
        buffer = ""
        flag_stripped = False

        async for chunk in answer_llm.astream(prepared.chain_input):
            if not chunk.content:
                continue

            if not flag_stripped:
                buffer += chunk.content
                if "\n" not in buffer:
                    continue
                buffer = _CITATION_FLAG_RE.sub("", buffer)
                flag_stripped = True
                buffer = buffer.lstrip("\n")
                if buffer:
                    full_answer += buffer
                    yield buffer
                buffer = ""
                continue

            full_answer += chunk.content
            yield chunk.content

        if not flag_stripped and buffer:
            buffer = _CITATION_FLAG_RE.sub("", buffer).strip()
            if buffer:
                full_answer += buffer
                yield buffer

        full_answer = _CITATION_FLAG_RE.sub("", full_answer).strip()

        selected_sources = select_sources(full_answer, prepared.sources)
        sources_block = format_sources_block(selected_sources)
        if sources_block:
            full_answer += sources_block
            yield sources_block

        if prepared.conversation is not None:
            with uow.transaction():
                create_message(
                    db=uow.db,
                    conversation_id=prepared.conversation.id,
                    role="assistant",
                    content=full_answer,
                )

        log_query(payload.question, selected_sources, full_answer)

    return stream()

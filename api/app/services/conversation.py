from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Conversation, Message, User
from app.repositories.conversation_repository import (
    create_conversation as create_conversation_record,
    delete_conversation as delete_conversation_record,
    get_conversation_for_user as get_conversation_for_user_record,
    list_conversations_for_user,
    update_conversation_title as update_conversation_title_record,
)
from app.repositories.message_repository import (
    create_message,
    list_messages_by_conversation,
)
from app.schemas import ConversationResponse, MessageResponse
from app.unit_of_work import SqlAlchemyUnitOfWork


def create(db: Session, user_id: str, title: str | None = None) -> Conversation:
    return create_conversation_record(db=db, user_id=user_id, title=title)


def list_conversations(db: Session, user_id: str) -> list[Conversation]:
    return list_conversations_for_user(db=db, user_id=user_id)


def get_for_user(db: Session, conversation_id: str, user_id: str) -> Conversation | None:
    return get_conversation_for_user_record(
        db=db,
        conversation_id=conversation_id,
        user_id=user_id,
    )


def delete(db: Session, conversation: Conversation) -> None:
    delete_conversation_record(db=db, conversation=conversation)


def update_title(db: Session, conversation: Conversation, title: str) -> Conversation:
    return update_conversation_title_record(db=db, conversation=conversation, title=title)


def list_messages(db: Session, conversation_id: str) -> list[Message]:
    return list_messages_by_conversation(db=db, conversation_id=conversation_id)


def save_message(db: Session, conversation_id: str, role: str, content: str) -> Message:
    return create_message(db=db, conversation_id=conversation_id, role=role, content=content)


def create_conversation_command(
    uow: SqlAlchemyUnitOfWork,
    current_user: User,
    title: str | None,
) -> ConversationResponse:
    with uow.transaction():
        conversation = create(db=uow.db, user_id=current_user.id, title=title)

    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
    )


def delete_conversation_command(
    conversation_id: str,
    uow: SqlAlchemyUnitOfWork,
    current_user: User,
) -> None:
    conversation = get_for_user(
        db=uow.db,
        conversation_id=conversation_id,
        user_id=current_user.id,
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    with uow.transaction():
        delete(db=uow.db, conversation=conversation)


def list_conversations_query(
    uow: SqlAlchemyUnitOfWork,
    current_user: User,
) -> list[ConversationResponse]:
    conversations = list_conversations(db=uow.db, user_id=current_user.id)
    return [
        ConversationResponse(id=item.id, title=item.title, created_at=item.created_at)
        for item in conversations
    ]


def get_conversation_messages_query(
    conversation_id: str,
    uow: SqlAlchemyUnitOfWork,
    current_user: User,
) -> list[MessageResponse]:
    conversation = get_for_user(
        db=uow.db,
        conversation_id=conversation_id,
        user_id=current_user.id,
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    messages = list_messages(db=uow.db, conversation_id=conversation.id)
    return [
        MessageResponse(
            id=message.id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
        )
        for message in messages
    ]

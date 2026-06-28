from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conversation


def create_conversation(db: Session, user_id: str, title: str | None = None) -> Conversation:
    conversation = Conversation(user_id=user_id, title=title)
    db.add(conversation)
    db.flush()
    db.refresh(conversation)
    return conversation


def list_conversations_for_user(db: Session, user_id: str) -> list[Conversation]:
    statement = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.created_at.desc())
    )
    return list(db.execute(statement).scalars().all())


def get_conversation_for_user(db: Session, conversation_id: str, user_id: str) -> Conversation | None:
    statement = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == user_id,
    )
    return db.execute(statement).scalars().first()


def update_conversation_title(db: Session, conversation: Conversation, title: str) -> Conversation:
    conversation.title = title
    db.add(conversation)
    db.flush()
    db.refresh(conversation)
    return conversation


def delete_conversation(db: Session, conversation: Conversation) -> None:
    db.delete(conversation)

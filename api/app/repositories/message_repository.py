from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Message


def list_messages_by_conversation(db: Session, conversation_id: str) -> list[Message]:
    statement = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    return list(db.execute(statement).scalars().all())


def create_message(db: Session, conversation_id: str, role: str, content: str) -> Message:
    message = Message(conversation_id=conversation_id, role=role, content=content)
    db.add(message)
    db.flush()
    db.refresh(message)
    return message

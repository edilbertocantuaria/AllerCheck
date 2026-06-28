from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


def get_user_by_id(db: Session, user_id: str) -> User | None:
    statement = select(User).where(User.id == user_id)
    return db.execute(statement).scalars().first()


def get_user_by_email(db: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    return db.execute(statement).scalars().first()


def create_user(db: Session, email: str, password_hash: str) -> User:
    user = User(email=email, password_hash=password_hash)
    db.add(user)
    db.flush()
    db.refresh(user)
    return user

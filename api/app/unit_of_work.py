from contextlib import contextmanager
from typing import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db import get_db


class SqlAlchemyUnitOfWork:
    def __init__(self, db: Session):
        self.db = db

    @contextmanager
    def transaction(self) -> Iterator[None]:
        try:
            yield
        except Exception:
            self.db.rollback()
            raise
        else:
            self.db.commit()


def get_uow(db: Session = Depends(get_db)) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db)

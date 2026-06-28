import logging
import secrets

import requests
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from app.config import GOOGLE_CLIENT_ID
from app.core.security import create_access_token, hash_password, verify_password
from app.repositories.user_repository import create_user, get_user_by_email
from app.schemas import TokenResponse
from app.unit_of_work import SqlAlchemyUnitOfWork

logger = logging.getLogger(__name__)


def _verify_google_id_token(id_token: str) -> str:
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google authentication is not configured",
        )

    try:
        response = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": id_token},
            timeout=10,
        )
    except requests.RequestException as exc:
        logger.exception("Google token verification request failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google authentication service is temporarily unavailable",
        ) from exc

    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token")

    token_data = response.json()
    if token_data.get("aud") != GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token audience")

    if token_data.get("email_verified") not in {"true", True}:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google email is not verified")

    email = token_data.get("email")
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google token has no email")

    return str(email).lower()


def register(
    email: str,
    password: str,
    uow: SqlAlchemyUnitOfWork,
) -> dict[str, object]:
    try:
        existing_user = get_user_by_email(db=uow.db, email=email)
        if existing_user is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

        try:
            password_hash = hash_password(password)
        except Exception as exc:
            logger.exception("Password hashing failed during register")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service is temporarily unavailable",
            ) from exc

        with uow.transaction():
            user = create_user(db=uow.db, email=email, password_hash=password_hash)

        return {"id": user.id, "email": user.email, "created_at": user.created_at}

    except HTTPException:
        raise
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered") from exc
    except OperationalError as exc:
        logger.exception("Database unavailable during register")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable. Verify DATABASE_URL and PostgreSQL status.",
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("Database error during register")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while creating user",
        ) from exc


def login_with_password(
    email: str,
    password: str,
    uow: SqlAlchemyUnitOfWork,
) -> TokenResponse:
    try:
        user = get_user_by_email(db=uow.db, email=email)
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

        try:
            token = create_access_token(subject=user.id, email=user.email)
        except Exception as exc:
            logger.exception("Token generation failed during login")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service is temporarily unavailable",
            ) from exc

        return TokenResponse(access_token=token)

    except HTTPException:
        raise
    except OperationalError as exc:
        logger.exception("Database unavailable during login")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable. Verify DATABASE_URL and PostgreSQL status.",
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("Database error during login")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while performing login",
        ) from exc


def login_with_google(id_token: str, uow: SqlAlchemyUnitOfWork) -> TokenResponse:
    try:
        email = _verify_google_id_token(id_token)

        user = get_user_by_email(db=uow.db, email=email)
        if user is None:
            with uow.transaction():
                user = create_user(
                    db=uow.db,
                    email=email,
                    password_hash=hash_password(secrets.token_urlsafe(32)),
                )

        token = create_access_token(subject=user.id, email=user.email)
        return TokenResponse(access_token=token)

    except HTTPException:
        raise
    except OperationalError as exc:
        logger.exception("Database unavailable during Google login")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable. Verify DATABASE_URL and PostgreSQL status.",
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("Database error during Google login")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while performing Google login",
        ) from exc

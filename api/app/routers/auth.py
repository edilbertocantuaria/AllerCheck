from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.schemas import AuthLoginRequest, AuthRegisterRequest, GoogleAuthRequest, TokenResponse
from app.services.auth import login_with_google, login_with_password, register
from app.unit_of_work import SqlAlchemyUnitOfWork, get_uow

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_endpoint(payload: AuthRegisterRequest, uow: SqlAlchemyUnitOfWork = Depends(get_uow)):
    return register(email=str(payload.email), password=payload.password, uow=uow)


@router.post("/login", response_model=TokenResponse)
def login(payload: AuthLoginRequest, uow: SqlAlchemyUnitOfWork = Depends(get_uow)) -> TokenResponse:
    return login_with_password(email=str(payload.email), password=payload.password, uow=uow)


@router.post("/token", response_model=TokenResponse)
def login_oauth2_form(
    form_data: OAuth2PasswordRequestForm = Depends(),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> TokenResponse:
    return login_with_password(email=form_data.username, password=form_data.password, uow=uow)


@router.post("/google", response_model=TokenResponse)
def login_google(payload: GoogleAuthRequest, uow: SqlAlchemyUnitOfWork = Depends(get_uow)) -> TokenResponse:
    return login_with_google(id_token=payload.id_token, uow=uow)

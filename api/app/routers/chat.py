from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.dependencies import get_optional_current_user
from app.models import User
from app.schemas import ChatRequest
from app.services.chat import build_chat_stream
from app.unit_of_work import SqlAlchemyUnitOfWork, get_uow

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    current_user: User | None = Depends(get_optional_current_user),
):
    stream = build_chat_stream(payload=payload, uow=uow, current_user=current_user)
    return StreamingResponse(stream, media_type="text/plain")

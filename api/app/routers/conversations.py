from fastapi import APIRouter, Depends, Response, status

from app.dependencies import get_current_user
from app.models import User
from app.schemas import ConversationCreateRequest, ConversationResponse, MessageResponse
from app.services.conversation import (
    create_conversation_command,
    delete_conversation_command,
    get_conversation_messages_query,
    list_conversations_query,
)
from app.unit_of_work import SqlAlchemyUnitOfWork, get_uow

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation_endpoint(
    payload: ConversationCreateRequest,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    current_user: User = Depends(get_current_user),
) -> ConversationResponse:
    return create_conversation_command(
        uow=uow,
        current_user=current_user,
        title=payload.title,
    )


@router.get("", response_model=list[ConversationResponse])
def list_conversations_endpoint(
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    current_user: User = Depends(get_current_user),
) -> list[ConversationResponse]:
    return list_conversations_query(uow=uow, current_user=current_user)


@router.get("/{conversation_id}", response_model=list[MessageResponse])
def get_conversation_messages_endpoint(
    conversation_id: str,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    current_user: User = Depends(get_current_user),
) -> list[MessageResponse]:
    return get_conversation_messages_query(
        conversation_id=conversation_id,
        uow=uow,
        current_user=current_user,
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation_endpoint(
    conversation_id: str,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    current_user: User = Depends(get_current_user),
) -> Response:
    delete_conversation_command(
        conversation_id=conversation_id,
        uow=uow,
        current_user=current_user,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

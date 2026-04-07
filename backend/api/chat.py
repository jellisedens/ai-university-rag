from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.dependencies import get_db
from backend.models.user import User
from backend.services.auth import get_current_user
from backend.services.chat import (
    ask_question,
    create_chat_session,
    get_chat_session,
    get_user_sessions,
    get_session_messages,
    delete_chat_session,
)

router = APIRouter(prefix="/chat", tags=["Chat"])


# --- Schemas ---

class CreateSessionResponse(BaseModel):
    session_id: UUID


class QuestionRequest(BaseModel):
    question: str


class SourceResponse(BaseModel):
    document_title: str
    file_name: str
    page_number: int
    distance: float


class StructuredDataResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, str]]
    total: int
    titles: list[str] = []


class AnswerResponse(BaseModel):
    answer: str
    sources: list[SourceResponse]
    structured_data: StructuredDataResponse | None = None


class SessionPreview(BaseModel):
    id: str
    preview: str
    message_count: int
    created_at: str


class MessageResponse(BaseModel):
    role: str
    content: str
    created_at: str


# --- Endpoints ---

@router.post("/sessions", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new chat session."""
    session = await create_chat_session(db, user.id)
    return CreateSessionResponse(session_id=session.id)


@router.get("/sessions", response_model=list[SessionPreview])
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all chat sessions for the current user."""
    sessions = await get_user_sessions(db, user.id)
    return [SessionPreview(**s) for s in sessions]


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get all messages for a chat session."""
    messages = await get_session_messages(db, session_id, user.id)
    if not messages and not await get_chat_session(db, session_id, user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    return [MessageResponse(**m) for m in messages]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a chat session and all its messages."""
    deleted = await delete_chat_session(db, session_id, user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")


@router.post("/sessions/{session_id}/ask", response_model=AnswerResponse)
async def ask(
    session_id: UUID,
    body: QuestionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Ask a question within a chat session."""
    session = await get_chat_session(db, session_id, user.id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")

    result = await ask_question(db, user.id, session_id, body.question)

    # Build response with optional structured data
    structured = None
    if result.get("structured_data"):
        sd = result["structured_data"]
        structured = StructuredDataResponse(
            columns=sd["columns"],
            rows=sd["rows"],
            total=sd["total"],
            titles=sd.get("titles", []),
        )

    return AnswerResponse(
        answer=result["answer"],
        sources=[SourceResponse(**s) for s in result["sources"]],
        structured_data=structured,
    )
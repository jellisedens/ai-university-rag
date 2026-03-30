from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.dependencies import get_db
from backend.models.user import User
from backend.services.auth import get_current_user
from backend.services.chat import ask_question, create_chat_session, get_chat_session

router = APIRouter(prefix="/chat", tags=["Chat"])


# --- Request/Response schemas ---

class CreateSessionResponse(BaseModel):
    session_id: UUID


class QuestionRequest(BaseModel):
    question: str


class SourceResponse(BaseModel):
    document_title: str
    file_name: str
    page_number: int
    distance: float


class AnswerResponse(BaseModel):
    answer: str
    sources: list[SourceResponse]


# --- Endpoints ---

@router.post("/sessions", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new chat session."""
    session = await create_chat_session(db, user.id)
    return CreateSessionResponse(session_id=session.id)


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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )

    result = await ask_question(db, user.id, session_id, body.question)

    return AnswerResponse(
        answer=result["answer"],
        sources=[SourceResponse(**s) for s in result["sources"]],
    )
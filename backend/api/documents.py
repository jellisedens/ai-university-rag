from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.dependencies import get_db
from backend.models.user import User
from backend.services.auth import get_current_user
from backend.services.document import (
    create_document,
    get_document_by_id,
    get_user_documents,
    save_upload,
)

router = APIRouter(prefix="/documents", tags=["Documents"])


# --- Response schemas ---

class DocumentResponse(BaseModel):
    id: UUID
    title: str
    file_name: str
    status: str
    uploaded_at: str

    class Config:
        from_attributes = True


# --- Endpoints ---

@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload a PDF document."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepted",
        )

    content = await file.read()
    file_path = await save_upload(file.filename, content)

    title = file.filename.rsplit(".", 1)[0]
    document = await create_document(db, user.id, title, file.filename, file_path)

    return DocumentResponse(
        id=document.id,
        title=document.title,
        file_name=document.file_name,
        status=document.status,
        uploaded_at=document.uploaded_at.isoformat(),
    )


@router.get("/", response_model=list[DocumentResponse])
async def list_documents(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all documents for the current user."""
    documents = await get_user_documents(db, user.id)
    return [
        DocumentResponse(
            id=doc.id,
            title=doc.title,
            file_name=doc.file_name,
            status=doc.status,
            uploaded_at=doc.uploaded_at.isoformat(),
        )
        for doc in documents
    ]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a specific document."""
    document = await get_document_by_id(db, document_id, user.id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return DocumentResponse(
        id=document.id,
        title=document.title,
        file_name=document.file_name,
        status=document.status,
        uploaded_at=document.uploaded_at.isoformat(),
    )
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.dependencies import get_db
from backend.models.user import User
from backend.services.auth import get_current_user
from backend.services.document import (
    create_document,
    delete_document,
    get_document_by_id,
    get_user_documents,
    save_upload,
)
from backend.rag.pipeline import process_document

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
    """Upload a document for processing."""
    allowed_extensions = {".pdf", ".txt", ".md", ".docx", ".doc", ".xlsx", ".xls", ".csv"}
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided",
        )
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Accepted: {', '.join(sorted(allowed_extensions))}",
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


@router.post("/{document_id}/process", response_model=DocumentResponse)
async def process_uploaded_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Process an uploaded document through the ingestion pipeline."""
    document = await get_document_by_id(db, document_id, user.id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if document.status != "uploaded":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document cannot be processed (current status: {document.status})",
        )

    await process_document(db, document)

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
    """List all documents in the system."""
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

@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a document and all its chunks."""
    deleted = await delete_document(db, document_id, user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
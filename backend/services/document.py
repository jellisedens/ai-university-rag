import os
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models.document import Document


async def save_upload(file_name: str, file_content: bytes) -> str:
    """Save an uploaded file to disk and return the file path."""
    os.makedirs(settings.upload_dir, exist_ok=True)

    # Generate a unique filename to prevent collisions
    ext = Path(file_name).suffix
    unique_name = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(settings.upload_dir, unique_name)

    with open(file_path, "wb") as f:
        f.write(file_content)

    return file_path


async def create_document(
    db: AsyncSession,
    user_id: uuid.UUID,
    title: str,
    file_name: str,
    file_path: str,
) -> Document:
    """Create a document record in the database."""
    document = Document(
        user_id=user_id,
        title=title,
        file_name=file_name,
        file_path=file_path,
        status="uploaded",
    )
    db.add(document)
    await db.flush()
    return document


async def get_user_documents(
    db: AsyncSession, user_id: uuid.UUID
) -> list[Document]:
    """Get all documents belonging to a user."""
    result = await db.execute(
        select(Document)
        .order_by(Document.uploaded_at.desc())
    )
    return list(result.scalars().all())


async def get_document_by_id(
    db: AsyncSession, document_id: uuid.UUID, user_id: uuid.UUID
) -> Document | None:
    """Get a specific document, only if it belongs to the user."""
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()

async def delete_document(
    db: AsyncSession, document_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Delete a document and all its chunks. Returns True if deleted."""
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()
    if not document:
        return False
    await db.delete(document)
    await db.flush()
    return True
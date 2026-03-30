import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.document import Document, DocumentChunk
from backend.rag.text_extraction import extract_text
from backend.rag.chunking import chunk_text
from backend.rag.embeddings import generate_embeddings


async def process_document(db: AsyncSession, document: Document) -> None:
    """
    Run the full ingestion pipeline on a document.
    
    Steps:
    1. Update status to 'processing'
    2. Extract text from the PDF
    3. Chunk the text
    4. Generate embeddings for all chunks
    5. Store chunks with embeddings in the database
    6. Update status to 'completed' (or 'failed' on error)
    """
    try:
        # Step 1: Mark as processing
        document.status = "processing"
        await db.flush()

        # Step 2: Extract text
        pages = extract_text(document.file_path)
        if not pages:
            document.status = "failed"
            await db.flush()
            return

        # Step 3: Chunk the text
        chunks = chunk_text(pages)
        if not chunks:
            document.status = "failed"
            await db.flush()
            return

        # Step 4: Generate embeddings in batches
        batch_size = 50
        all_embeddings = []
        for i in range(0, len(chunks), batch_size):
            batch_texts = [c["content"] for c in chunks[i:i + batch_size]]
            batch_embeddings = await generate_embeddings(batch_texts)
            all_embeddings.extend(batch_embeddings)

        # Step 5: Store chunks with embeddings
        for chunk, embedding in zip(chunks, all_embeddings):
            db_chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=chunk["chunk_index"],
                content=chunk["content"],
                page_number=chunk["page_number"],
                embedding=embedding,
            )
            db.add(db_chunk)

        # Step 6: Mark as completed
        document.status = "completed"
        await db.flush()

    except Exception as e:
        document.status = "failed"
        await db.flush()
        raise e
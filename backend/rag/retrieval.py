import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.rag.embeddings import generate_single_embedding


async def retrieve_relevant_chunks(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    top_k: int | None = None,
) -> list[dict]:
    """
    Find the most relevant document chunks for a user's question.

    Steps:
    1. Convert the question to an embedding vector
    2. Search PostgreSQL for the most similar chunk vectors
    3. Return the top results with content and metadata
    """
    top_k = top_k or settings.top_k_results

    # Step 1: Convert question to a vector
    query_embedding = await generate_single_embedding(query)

    # Step 2: Vector similarity search in PostgreSQL
    # This uses pgvector's cosine distance operator (<=>)
    # We join with documents to filter by user_id (user isolation)
    sql = text("""
        SELECT
            dc.content,
            dc.page_number,
            dc.chunk_index,
            d.title AS document_title,
            d.file_name,
            d.id AS document_id,
            dc.embedding <=> :embedding AS distance
        FROM document_chunks dc
        JOIN documents d ON dc.document_id = d.id
        WHERE d.status = 'completed'
            AND dc.embedding IS NOT NULL
        ORDER BY dc.embedding <=> :embedding
        LIMIT :top_k
    """)

    result = await db.execute(
        sql,
        {
            "embedding": str(query_embedding),
            "top_k": top_k,
        },
    )

    rows = result.fetchall()

    # Step 3: Format results
    return [
        {
            "content": row.content,
            "page_number": row.page_number,
            "chunk_index": row.chunk_index,
            "document_title": row.document_title,
            "file_name": row.file_name,
            "document_id": str(row.document_id),
            "distance": float(row.distance),
        }
        for row in rows
    ]
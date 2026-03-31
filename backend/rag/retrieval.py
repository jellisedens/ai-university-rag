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
    """
    top_k = top_k or settings.top_k_results

    query_embedding = await generate_single_embedding(query)

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

    chunks = [
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

    if chunks:
        top_doc_id = chunks[0]["document_id"]

        # Fetch summary chunks from the top document
        extra_sql = text("""
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
            WHERE d.id = CAST(:doc_id AS UUID)
                AND dc.embedding IS NOT NULL
                AND dc.content LIKE :prefix
            ORDER BY dc.chunk_index
        """)

        extra_result = await db.execute(
            extra_sql,
            {
                "embedding": str(query_embedding),
                "doc_id": top_doc_id,
                "prefix": "Total records%",
            },
        )

        extra_rows = extra_result.fetchall()
        existing_indices = {(c["document_id"], c["chunk_index"]) for c in chunks}

        for row in extra_rows:
            key = (str(row.document_id), row.chunk_index)
            if key not in existing_indices:
                chunks.append({
                    "content": row.content,
                    "page_number": row.page_number,
                    "chunk_index": row.chunk_index,
                    "document_title": row.document_title,
                    "file_name": row.file_name,
                    "document_id": str(row.document_id),
                    "distance": float(row.distance),
                })

    return chunks
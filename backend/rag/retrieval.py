import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.rag.embeddings import generate_single_embedding
from backend.rag.query_filter import extract_filters


async def retrieve_relevant_chunks(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    top_k: int | None = None,
) -> list[dict]:
    """
    Find the most relevant document chunks for a user's question.
    Uses keyword filtering as a boost alongside vector similarity.
    """
    top_k = top_k or settings.top_k_results

    # Step 1: Extract keywords from the question
    filters = await extract_filters(query)
    keywords = filters.get("keywords", [])

    # Step 2: Convert question to a vector
    query_embedding = await generate_single_embedding(query)

    chunks = []
    seen_indices = set()

    # Step 3: If we have keywords, first get keyword-matched chunks
    if keywords:
        keyword_conditions = " OR ".join(
            [f"LOWER(dc.content) LIKE :kw{i}" for i in range(len(keywords))]
        )

        filtered_sql = text(f"""
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
                AND ({keyword_conditions})
            ORDER BY dc.embedding <=> :embedding
            LIMIT :top_k
        """)

        params = {
            "embedding": str(query_embedding),
            "top_k": top_k,
        }
        for i, kw in enumerate(keywords):
            params[f"kw{i}"] = f"%{kw.lower()}%"

        result = await db.execute(filtered_sql, params)
        for row in result.fetchall():
            key = (str(row.document_id), row.chunk_index)
            if key not in seen_indices:
                seen_indices.add(key)
                chunks.append({
                    "content": row.content,
                    "page_number": row.page_number,
                    "chunk_index": row.chunk_index,
                    "document_title": row.document_title,
                    "file_name": row.file_name,
                    "document_id": str(row.document_id),
                    "distance": float(row.distance),
                })

    # Step 4: Always also do a standard vector search (catches summaries and general matches)
    standard_sql = text("""
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
        standard_sql,
        {
            "embedding": str(query_embedding),
            "top_k": top_k,
        },
    )

    for row in result.fetchall():
        key = (str(row.document_id), row.chunk_index)
        if key not in seen_indices:
            seen_indices.add(key)
            chunks.append({
                "content": row.content,
                "page_number": row.page_number,
                "chunk_index": row.chunk_index,
                "document_title": row.document_title,
                "file_name": row.file_name,
                "document_id": str(row.document_id),
                "distance": float(row.distance),
            })

    # Step 5: Fetch all summary chunks from the top document
    if chunks:
        top_doc_id = chunks[0]["document_id"]

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

        for row in extra_result.fetchall():
            key = (str(row.document_id), row.chunk_index)
            if key not in seen_indices:
                seen_indices.add(key)
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
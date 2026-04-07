"""
Query Router — Dispatches Queries to the Correct Retrieval Strategy

Routes:
  - list + programs    → ai_assisted_retrieval()  — always extracts Title, Colleges, Program Levels
  - lookup + tuition   → hybrid_retrieval()       — SQL + vector
  - lookup + fees      → hybrid_retrieval()
  - everything else    → existing retrieve_relevant_chunks()

The chat answer is always a clean list of program names.
Full details (all columns) are fetched separately via /explorer/expand
when the user clicks "View full dataset."

File location: backend/rag/query_router.py
"""

import json
import logging
import re
import uuid

from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.rag.query_classifier import classify_query
from backend.rag.embeddings import generate_single_embedding

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=settings.openai_api_key)


def trim_chunks_to_token_budget(chunks: list[dict], max_tokens: int = 80000) -> list[dict]:
    """Trim chunks to fit within a token budget."""
    trimmed = []
    total_tokens = 0
    for chunk in chunks:
        content = chunk.get("content", "")
        chunk_tokens = int(len(content.split()) * 1.3)
        if total_tokens + chunk_tokens > max_tokens:
            break
        trimmed.append(chunk)
        total_tokens += chunk_tokens
    if len(trimmed) < len(chunks):
        logger.info(f"Trimmed chunks from {len(chunks)} to {len(trimmed)}")
    return trimmed


# =============================================================================
# Main Router
# =============================================================================

async def route_query(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    retrieve_fn,
    top_k: int | None = None,
) -> dict:
    """
    Main entry point. Classifies the query, then dispatches.

    Returns dict with:
        - chunks: list of chunk dicts
        - strategy: which path was used
        - classification: the full classification
        - structured_data: (optional) summary rows + matched titles for expand
    """
    top_k = top_k or settings.top_k_results

    classification = await classify_query(query)
    intent = classification["intent"]
    entity = classification["entity"]
    filters = classification.get("filters", {})

    print(f"[ROUTER] intent={intent}, entity={entity}, filters={filters}")

    structured_data = None

    if intent == "list" and entity == "programs":
        chunks, structured_data = await ai_assisted_retrieval(
            db=db, query=query, filters=filters,
        )
        strategy = "ai_assisted"

    elif intent == "lookup" and entity in ("tuition", "fees"):
        chunks = await hybrid_retrieval(
            db=db, user_id=user_id, query=query,
            filters=filters, retrieve_fn=retrieve_fn, top_k=top_k,
        )
        strategy = "hybrid"

    else:
        chunks = await retrieve_fn(db, user_id, query, top_k)
        strategy = "rag"

    print(f"[ROUTER] strategy={strategy}, chunks={len(chunks)}, has_dashboard={'yes' if structured_data else 'no'}")

    result = {
        "chunks": chunks,
        "strategy": strategy,
        "classification": classification,
    }
    if structured_data:
        result["structured_data"] = structured_data

    return result


# =============================================================================
# Schema Discovery
# =============================================================================

async def _discover_data_schema(db: AsyncSession) -> str:
    """Discover the schema at runtime for the SQL generation prompt."""
    sample_sql = text("""
        SELECT LEFT(dc.content, 1000) AS sample, d.file_name
        FROM document_chunks dc
        JOIN documents d ON dc.document_id = d.id
        WHERE dc.content LIKE 'Total records%'
        LIMIT 3
    """)
    sample_result = await db.execute(sample_sql)
    samples = sample_result.fetchall()

    lines = []
    lines.append("DATABASE INFO:")
    lines.append("Table: document_chunks (aliased as dc), joined with documents (aliased as d)")
    lines.append("The 'content' column contains pipe-separated metadata fields.")
    lines.append("Fields are extracted using: TRIM(substring(dc.content from 'FieldName: ([^|]+)'))")
    lines.append("")

    if samples:
        lines.append("AVAILABLE DATA SOURCES:")
        for s in samples:
            lines.append(f"  File: {s.file_name}")
            content = s.sample
            if "All columns:" in content:
                cols_part = content.split("All columns:")[1].strip()
                lines.append(f"  Fields: {cols_part[:500]}")
        lines.append("")

    return "\n".join(lines)


# =============================================================================
# SQL Generation — Always extracts only 3 core columns
# =============================================================================

async def _generate_extraction_sql(
    schema: str,
    query: str,
    filters: dict,
) -> str | None:
    """
    Ask the LLM to generate a SQL query that extracts ONLY:
    - Title
    - Colleges
    - Program Levels

    The LLM's job is just to build the right WHERE clause based on
    the user's question. The SELECT is always the same three fields.
    """
    system_prompt = f"""You are a SQL query generator for a university program database.

{schema}

CRITICAL RULES:
1. ALWAYS select exactly these 3 fields, no more, no less:
   SELECT DISTINCT
       TRIM(substring(dc.content from 'Title: ([^|]+)')) AS title,
       TRIM(substring(dc.content from 'Colleges: ([^|]+)')) AS colleges,
       TRIM(substring(dc.content from 'Program Levels: ([^|]+)')) AS program_levels
   FROM document_chunks dc
   JOIN documents d ON dc.document_id = d.id

2. Always include: WHERE d.status = 'completed' AND dc.content LIKE '%Title:%'

3. FIELD-SPECIFIC FILTERING — filter on EXTRACTED fields, never on raw content:
   CORRECT: WHERE LOWER(TRIM(substring(dc.content from 'Colleges: ([^|]+)'))) LIKE '%business%'
   WRONG:   WHERE LOWER(dc.content) LIKE '%business%'

4. Degree level mapping (filter on extracted Program Levels field):
   - "undergraduate" → LIKE '%bachelor%'
   - "graduate" → LIKE '%graduate%' OR LIKE '%master%'
   - "doctoral" → LIKE '%doctorate%' OR LIKE '%ph.d%'
   - "certificate" → LIKE '%certificate%'

5. College filtering (filter on extracted Colleges field):
   - "College of Business" → LIKE '%business%'
   - "College of Arts and Sciences" → LIKE '%arts and sciences%'

6. ORDER BY program_levels, title
7. Do NOT use LIMIT.
8. Return ONLY the SQL query. No explanation, no markdown, no backticks.
"""

    user_msg = f"User question: {query}\n"
    if filters:
        user_msg += f"Extracted filters: {json.dumps(filters)}\n"
    user_msg += "\nGenerate the SQL query:"

    try:
        response = await _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0,
            max_tokens=500,
        )

        sql = response.choices[0].message.content.strip()
        sql = sql.replace("```sql", "").replace("```", "").strip()

        if not sql.upper().startswith("SELECT"):
            return None

        dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE"]
        sql_upper = sql.upper()
        for keyword in dangerous:
            if re.search(rf'\b{keyword}\b', sql_upper):
                return None

        print(f"[ROUTER] LLM generated SQL: {sql}")
        return sql

    except Exception as e:
        logger.error(f"SQL generation failed: {e}")
        return None


# =============================================================================
# AI-Assisted Retrieval
# =============================================================================

async def ai_assisted_retrieval(
    db: AsyncSession,
    query: str,
    filters: dict,
) -> tuple[list[dict], dict | None]:
    """
    Returns:
        - chunks: one virtual chunk with compact text for the LLM
        - structured_data: dict with summary rows + titles for the expand endpoint
    """
    schema = await _discover_data_schema(db)
    generated_sql = await _generate_extraction_sql(schema, query, filters)

    if not generated_sql:
        chunks = await _fallback_structured_retrieval(db, query, filters)
        return chunks, None

    try:
        result = await db.execute(text(generated_sql))
        rows = result.fetchall()
        columns = list(result.keys()) if hasattr(result, 'keys') else []
    except Exception as e:
        logger.error(f"Generated SQL execution failed: {e}")
        chunks = await _fallback_structured_retrieval(db, query, filters)
        return chunks, None

    if not rows:
        return [], None

    col_names = columns if columns else ["title", "colleges", "program_levels"]

    print(f"[ROUTER] SQL returned {len(rows)} raw rows, columns: {col_names}")

    # Deduplicate by title (first column)
    structured_rows = []
    seen_titles = set()
    titles_list = []  # For the expand endpoint

    # Group by level for display
    groups: dict[str, list[dict]] = {}

    for row in rows:
        row_dict = dict(zip(col_names, row))
        cleaned = {k: str(v).strip() if v else "" for k, v in row_dict.items()}

        title = cleaned.get("title", "")
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)

        structured_rows.append(cleaned)
        titles_list.append(title)

        level = cleaned.get("program_levels", "Other")
        if level not in groups:
            groups[level] = []
        groups[level].append(cleaned)

    # Build compact text for the LLM
    lines = []
    lines.append(f"PROGRAM LIST ({len(structured_rows)} programs found)")
    lines.append(f"Query: {query}")
    lines.append("")

    for level in sorted(groups.keys()):
        group = groups[level]
        lines.append(f"--- {level} ({len(group)} programs) ---")
        for i, row in enumerate(sorted(group, key=lambda r: r.get("title", "")), 1):
            college = row.get("colleges", "")
            title = row.get("title", "")
            lines.append(f"  {i}. {title} — {college}")
        lines.append("")

    compact_content = "\n".join(lines)

    print(f"[ROUTER] AI-assisted: {len(structured_rows)} unique programs, ~{int(len(compact_content.split()) * 1.3)} tokens")

    chunks = [{
        "content": compact_content,
        "page_number": 1,
        "chunk_index": 0,
        "document_title": "Program Database Query",
        "file_name": "structured-query-result",
        "document_id": "ai-assisted-extraction",
        "distance": 0.0,
    }]

    # structured_data includes the summary rows for inline display
    # AND the titles list so the expand endpoint knows what to fetch
    structured_data = {
        "columns": ["Title", "Colleges", "Program Levels"],
        "rows": [
            {"Title": r.get("title", ""), "Colleges": r.get("colleges", ""), "Program Levels": r.get("program_levels", "")}
            for r in structured_rows
        ],
        "total": len(structured_rows),
        "titles": titles_list,  # Used by /explorer/expand
    }

    return chunks, structured_data


# =============================================================================
# Fallback
# =============================================================================

async def _fallback_structured_retrieval(db, query, filters):
    """Fallback if AI-assisted SQL generation fails."""
    filter_conditions = []
    params = {}

    college = filters.get("college", "")
    if college:
        filter_conditions.append("LOWER(dc.content) LIKE :college_filter")
        params["college_filter"] = f"%{college.lower()}%"

    if not filter_conditions:
        stop_words = {"list", "all", "show", "me", "the", "what", "are", "is",
                      "in", "of", "for", "a", "an", "and", "or", "do", "does",
                      "programs", "program", "offer", "offered", "available",
                      "can", "you", "tell", "about", "give", "every", "how",
                      "many", "count", "by", "title", "name"}
        for i, word in enumerate([w.lower() for w in query.split() if w.lower() not in stop_words and len(w) > 2]):
            filter_conditions.append(f"LOWER(dc.content) LIKE :qw{i}")
            params[f"qw{i}"] = f"%{word}%"

    if not filter_conditions:
        return []

    where_clause = " AND ".join(filter_conditions)

    sql = text(f"""
        SELECT DISTINCT
            TRIM(substring(dc.content from 'Title: ([^|]+)')) AS title,
            TRIM(substring(dc.content from 'Colleges: ([^|]+)')) AS colleges,
            TRIM(substring(dc.content from 'Program Levels: ([^|]+)')) AS program_levels
        FROM document_chunks dc
        JOIN documents d ON dc.document_id = d.id
        WHERE d.status = 'completed' AND dc.content LIKE '%Title:%' AND ({where_clause})
        ORDER BY program_levels, title
    """)

    result = await db.execute(sql, params)
    rows = result.fetchall()
    if not rows:
        return []

    seen = set()
    lines = [f"PROGRAM DATA ({len(rows)} results)", ""]
    for row in rows:
        title = (row.title or "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        lines.append(f"- {title} | {(row.colleges or '').strip()} | {(row.program_levels or '').strip()}")

    return [{"content": "\n".join(lines), "page_number": 1, "chunk_index": 0,
             "document_title": "Program Database", "file_name": "structured-query-result",
             "document_id": "fallback-extraction", "distance": 0.0}]


# =============================================================================
# Hybrid Retrieval (unchanged)
# =============================================================================

async def hybrid_retrieval(db, user_id, query, filters, retrieve_fn, top_k):
    """Hybrid retrieval for relational queries."""
    all_chunks = []
    seen_indices = set()

    rag_chunks = await retrieve_fn(db, user_id, query, top_k)
    for chunk in rag_chunks:
        key = (chunk.get("document_id", ""), chunk.get("chunk_index", 0))
        if key not in seen_indices:
            seen_indices.add(key)
            all_chunks.append(chunk)

    program = filters.get("program", "")
    if not program:
        query_lower = query.lower()
        for remove in ["what", "is", "the", "tuition", "fee", "fees", "cost", "for",
                       "how", "much", "does", "it", "program", "of", "a", "an", "in", "to"]:
            query_lower = query_lower.replace(remove, "")
        remaining = query_lower.strip()
        if remaining and len(remaining) > 2:
            program = remaining.strip()

    if program:
        query_embedding = await generate_single_embedding(query)
        targeted_sql = text("""
            SELECT dc.content, dc.page_number, dc.chunk_index,
                   d.title AS document_title, d.file_name, d.id AS document_id,
                   dc.embedding <=> :embedding AS distance
            FROM document_chunks dc JOIN documents d ON dc.document_id = d.id
            WHERE d.status = 'completed' AND dc.embedding IS NOT NULL
                AND LOWER(dc.content) LIKE :program
                AND (LOWER(dc.content) LIKE '%tuition%' OR LOWER(dc.content) LIKE '%cost%'
                     OR LOWER(dc.content) LIKE '%fee%' OR LOWER(dc.content) LIKE '%per credit%'
                     OR LOWER(dc.content) LIKE '%per semester%' OR LOWER(dc.content) LIKE '%rate%')
            ORDER BY dc.embedding <=> :embedding LIMIT :top_k
        """)
        result = await db.execute(targeted_sql, {
            "embedding": str(query_embedding), "program": f"%{program.lower()}%", "top_k": top_k,
        })
        for row in result.fetchall():
            key = (str(row.document_id), row.chunk_index)
            if key not in seen_indices:
                seen_indices.add(key)
                all_chunks.append({"content": row.content, "page_number": row.page_number,
                    "chunk_index": row.chunk_index, "document_title": row.document_title,
                    "file_name": row.file_name, "document_id": str(row.document_id),
                    "distance": float(row.distance)})

    return trim_chunks_to_token_budget(all_chunks)
"""
Data Explorer API — Expand endpoint

Fetches full details for a list of program titles.
Simple approach: fetch the raw chunk content for matching titles,
then parse the pipe-separated fields in Python.

No regex extraction in SQL, no column discovery, no alias sanitization.

File location: backend/api/explorer.py
"""

import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.dependencies import get_db
from backend.models.user import User
from backend.services.auth import get_current_user

router = APIRouter(prefix="/explorer", tags=["Data Explorer"])

# Fields to exclude from display (WordPress/CMS junk)
EXCLUDED_FIELDS = {
    "ID", "Post Type", "Permalink", "Image URL", "Image Title",
    "Image Caption", "Image Description", "Image Alt Text",
    "Image Featured", "Attachment URL", "Content", "Excerpt", "Date",
    "web-program-id", "Slug", "Parent", "Parent Slug", "Order",
    "Comment Status", "Ping Status", "Post Modified Date",
    "Author ID", "Author Username", "Author Email",
    "Author First Name", "Author Last Name", "Status",
}

# Fields to show first (in this order)
PRIORITY_FIELDS = [
    "Title", "Colleges", "Departments", "Program Levels",
    "Areas of Study", "Locations", "credit-hours", "degree-duration",
    "program-director", "class-location-format",
    "tuition-hr", "total-tuition-cost", "total-tuition-cost-per-semester",
    "total-tuition-cost-per-year", "fee-breakdown",
]


class ExpandRequest(BaseModel):
    titles: list[str]


class ExpandRow(BaseModel):
    values: dict[str, str]


class ExpandResponse(BaseModel):
    columns: list[str]
    rows: list[ExpandRow]
    total: int


def _parse_chunk_fields(content: str) -> dict[str, str]:
    """
    Parse pipe-separated fields from a chunk's content.

    Content format: "field1: value1 | field2: value2 | field3: value3"

    Returns a dict of {field_name: value}, excluding junk fields.
    """
    fields = {}

    # Split on pipe separator
    parts = content.split("|")

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Split on first colon to get field name and value
        colon_idx = part.find(":")
        if colon_idx == -1:
            continue

        field_name = part[:colon_idx].strip()
        value = part[colon_idx + 1:].strip()

        # Skip excluded fields
        if field_name in EXCLUDED_FIELDS:
            continue

        # Skip fields that start with underscore (internal WordPress meta)
        if field_name.startswith("_"):
            continue

        # Skip empty values
        if not value or value in ("0", "FALSE", "default"):
            continue

        # Skip very long values (likely HTML or serialized data)
        if len(value) > 500:
            continue

        fields[field_name] = value

    return fields


@router.post("/expand", response_model=ExpandResponse)
async def expand_dataset(
    body: ExpandRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Fetch full details for a list of program titles.

    Simple approach:
    1. Query document_chunks WHERE the extracted Title matches any of the given titles
    2. Parse the pipe-separated fields from each chunk's raw content in Python
    3. Deduplicate by title and return all useful fields
    """
    if not body.titles:
        raise HTTPException(status_code=400, detail="No titles provided")

    titles = body.titles[:200]

    # Build parameterized query to match titles
    title_conditions = []
    params = {}
    for i, title in enumerate(titles):
        param_name = f"t{i}"
        title_conditions.append(
            f"TRIM(substring(dc.content from 'Title: ([^|]+)')) = :{param_name}"
        )
        params[param_name] = title

    title_where = " OR ".join(title_conditions)

    # Fetch the raw content for matching chunks
    sql = text(f"""
        SELECT dc.content
        FROM document_chunks dc
        JOIN documents d ON dc.document_id = d.id
        WHERE d.status = 'completed'
            AND dc.content LIKE '%Title:%'
            AND dc.content NOT LIKE 'Total records%'
            AND ({title_where})
    """)

    try:
        result = await db.execute(sql, params)
        rows = result.fetchall()
    except Exception as e:
        print(f"[EXPLORER] Expand query failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to expand dataset")

    # Parse fields from each chunk
    all_fields = set()
    parsed_rows = []
    seen_titles = set()

    for row in rows:
        fields = _parse_chunk_fields(row.content)

        title = fields.get("Title", "")
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)

        parsed_rows.append(fields)
        all_fields.update(fields.keys())

    # Order columns: priority fields first, then the rest alphabetically
    ordered_columns = []
    remaining_fields = sorted(all_fields)

    for pref in PRIORITY_FIELDS:
        if pref in remaining_fields:
            ordered_columns.append(pref)
            remaining_fields.remove(pref)

    ordered_columns.extend(remaining_fields)

    # Build response
    data_rows = []
    for fields in sorted(parsed_rows, key=lambda f: f.get("Title", "")):
        data_rows.append(ExpandRow(values=fields))

    print(f"[EXPLORER] Expanded {len(data_rows)} programs with {len(ordered_columns)} columns")

    return ExpandResponse(
        columns=ordered_columns,
        rows=data_rows,
        total=len(data_rows),
    )
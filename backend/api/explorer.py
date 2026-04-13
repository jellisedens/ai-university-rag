"""
Data Explorer API — Expand endpoint

Fetches full details for a list of program titles.
Fetches raw chunk content, parses pipe-separated fields in Python.

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

# Fields to exclude from display
EXCLUDED_FIELDS = {
    "ID", "Post Type", "Permalink", "Image URL", "Image Title",
    "Image Caption", "Image Description", "Image Alt Text",
    "Image Featured", "Attachment URL", "Content", "Excerpt", "Date",
    "web-program-id", "Slug", "Parent", "Parent Slug", "Order",
    "Comment Status", "Ping Status", "Post Modified Date",
    "Author ID", "Author Username", "Author Email",
    "Author First Name", "Author Last Name", "Status",
    "Sheet", "Columns", "Records",
}

# Fields to show first
PRIORITY_FIELDS = [
    "Title", "Colleges", "Departments", "Program Levels",
    "Areas of Study", "Locations", "credit-hours", "degree-duration",
    "program-director", "class-location-format",
]


class ExpandRequest(BaseModel):
    titles: list[str]


class ExpandRow(BaseModel):
    values: dict[str, str]


class ExpandResponse(BaseModel):
    columns: list[str]
    rows: list[ExpandRow]
    total: int


def _extract_field(content: str, field_name: str) -> str:
    """
    Extract a specific field value from chunk content using regex.
    Handles the case where fields are pipe-separated:
      field_name: value | next_field: ...
    OR where the field is followed by a space and another field name with colon.
    """
    # Pattern: field_name: (everything up to the next pipe or end of string)
    pattern = re.escape(field_name) + r':\s*([^|]+)'
    match = re.search(pattern, content)
    if match:
        return match.group(1).strip()
    return ""


def _parse_all_fields(content: str) -> dict[str, str]:
    """
    Parse ALL pipe-separated fields from chunk content.
    
    The content may contain fields in any order, and Title may not be
    at the start. We find all patterns of 'FieldName: value' separated
    by pipes.
    """
    fields = {}
    
    # Split on pipe
    parts = content.split("|")
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        # Find the LAST colon that's preceded by what looks like a field name
        # Some values contain colons (e.g., "start-dates: Fall: August")
        # Strategy: find first colon, check if left side is a reasonable field name
        colon_idx = part.find(":")
        if colon_idx == -1:
            continue
        
        field_name = part[:colon_idx].strip()
        value = part[colon_idx + 1:].strip()
        
        # Skip if field name is too long (likely not a real field name)
        if len(field_name) > 60:
            continue
        
        # Skip if field name contains digits only (like "17 Title")
        # This happens when two fields get concatenated without a pipe
        # Try to recover: look for a known field name pattern
        if " " in field_name and any(c.isdigit() for c in field_name.split()[0]):
            # Try to find the actual field name after the number
            # e.g., "17 Title" -> skip the "17" part
            words = field_name.split()
            for i, word in enumerate(words):
                if not any(c.isdigit() for c in word) and len(word) > 1:
                    # Found a non-numeric word — this might be the real field name
                    potential_field = " ".join(words[i:])
                    if potential_field:
                        field_name = potential_field
                        break
        
        # Skip excluded fields
        if field_name in EXCLUDED_FIELDS:
            continue
        if field_name.startswith("_"):
            continue
        
        # Skip empty/default values
        if not value or value in ("0", "FALSE", "default"):
            continue
        
        # Skip very long values (HTML, serialized data)
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
    """
    print(f"[EXPLORER] Received {len(body.titles)} titles")
    if body.titles:
        print(f"[EXPLORER] First 3: {body.titles[:3]}")

    if not body.titles:
        raise HTTPException(status_code=400, detail="No titles provided")

    titles = body.titles[:200]

    # Fetch ALL chunks that contain any of the title strings
    # Use simple LIKE matching on raw content
    title_conditions = []
    params = {}
    for i, title in enumerate(titles):
        param_name = f"t{i}"
        title_conditions.append(f"LOWER(dc.content) LIKE :{param_name}")
        params[param_name] = f"%{title.strip().lower()}%"

    title_where = " OR ".join(title_conditions)

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
        print(f"[EXPLORER] Executing query with {len(params)} params")
        result = await db.execute(sql, params)
        rows = result.fetchall()
        print(f"[EXPLORER] Query returned {len(rows)} raw rows")
    except Exception as e:
        print(f"[EXPLORER] Expand query failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to expand dataset")

    # Parse fields from each chunk, grouping by title
    # A single program may span multiple chunks — merge their fields
    programs: dict[str, dict[str, str]] = {}
    titles_lower = {t.strip().lower() for t in titles}

    for row in rows:
        fields = _parse_all_fields(row.content)
        
        # Also try regex extraction for Title specifically
        # since it might be concatenated with a previous field
        title = fields.get("Title", "")
        if not title:
            title = _extract_field(row.content, "Title")
            if title:
                fields["Title"] = title
        
        if not title:
            continue
        
        # Verify this title is one we asked for
        title_lower = title.strip().lower()
        if not any(t in title_lower or title_lower in t for t in titles_lower):
            continue
        
        # Merge fields into existing program data (later chunks add fields)
        if title not in programs:
            programs[title] = {}
        
        for k, v in fields.items():
            if k not in programs[title] or not programs[title][k]:
                programs[title][k] = v

    print(f"[EXPLORER] Parsed {len(programs)} unique programs")

    # Collect all field names across all programs
    all_fields = set()
    for prog_fields in programs.values():
        all_fields.update(prog_fields.keys())

    # Order columns: priority first, then rest alphabetically
    ordered_columns = []
    remaining = sorted(all_fields)

    for pref in PRIORITY_FIELDS:
        if pref in remaining:
            ordered_columns.append(pref)
            remaining.remove(pref)

    ordered_columns.extend(remaining)

    # Build response rows
    data_rows = []
    for title in sorted(programs.keys()):
        data_rows.append(ExpandRow(values=programs[title]))

    print(f"[EXPLORER] Expanded {len(data_rows)} programs with {len(ordered_columns)} columns")

    return ExpandResponse(
        columns=ordered_columns,
        rows=data_rows,
        total=len(data_rows),
    )
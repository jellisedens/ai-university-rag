"""
Query Classification for Intent-Based Retrieval Routing

Classifies user queries into intent + entity pairs to determine
which retrieval strategy to use:

  - list + programs    → SQL structured retrieval (completeness)
  - lookup + tuition   → hybrid retrieval (SQL + vector)
  - lookup + fees      → hybrid retrieval (SQL + vector)
  - explain + general  → standard RAG pipeline (relevance)

Uses OpenAI function calling for reliable structured output
instead of regex/keyword matching, which is brittle.
"""

import json
import logging
from openai import AsyncOpenAI

from backend.config import settings

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = AsyncOpenAI(api_key=settings.openai_api_key)

# Classification schema for OpenAI function calling
CLASSIFICATION_FUNCTION = {
    "name": "classify_query",
    "description": "Classify a user query by intent and entity type for retrieval routing.",
    "parameters": {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": ["list", "lookup", "explain"],
                "description": (
                    "list = user wants a complete enumeration (all programs, all majors, etc.). "
                    "lookup = user wants specific facts about a known entity (tuition for nursing, "
                    "requirements for a program, fees for something specific). "
                    "explain = user wants a general explanation, description, or open-ended answer."
                ),
            },
            "entity": {
                "type": "string",
                "enum": ["programs", "tuition", "fees", "general"],
                "description": (
                    "programs = query is about academic programs, majors, degrees, colleges, departments. "
                    "tuition = query is about tuition costs, tuition rates. "
                    "fees = query is about fees, charges, costs (non-tuition). "
                    "general = query is about policies, admissions, financial aid, or anything else."
                ),
            },
            "filters": {
                "type": "object",
                "description": "Extracted filter values from the query.",
                "properties": {
                    "college": {
                        "type": "string",
                        "description": (
                            "The college name if mentioned (e.g., 'College of Business', "
                            "'College of Engineering'). Return the full college name."
                        ),
                    },
                    "program": {
                        "type": "string",
                        "description": (
                            "The specific program or major name if mentioned "
                            "(e.g., 'nursing', 'computer science', 'MBA')."
                        ),
                    },
                    "degree_level": {
                        "type": "string",
                        "description": (
                            "The degree level if mentioned "
                            "(e.g., 'undergraduate', 'graduate', 'doctoral', 'certificate')."
                        ),
                    },
                },
            },
        },
        "required": ["intent", "entity"],
    },
}

CLASSIFICATION_SYSTEM_PROMPT = """You are a query classifier for a university knowledge system.

Given a user question, determine:
1. The INTENT: what kind of answer the user expects
   - "list" = they want ALL items that match (e.g., "List all programs in College of Business")
   - "lookup" = they want specific info about a known thing (e.g., "What is tuition for nursing?")
   - "explain" = they want a general explanation (e.g., "How does financial aid work?")

2. The ENTITY type the query is about
   - "programs" = academic programs, majors, degrees, colleges, departments
   - "tuition" = tuition costs and rates
   - "fees" = fees and charges
   - "general" = everything else (policies, admissions, financial aid descriptions, etc.)

3. Any FILTERS mentioned in the query (college name, program name, degree level)

Examples:
- "List all College of Business programs" → list, programs, college="College of Business"
- "What programs does the College of Engineering offer?" → list, programs, college="College of Engineering"
- "What is tuition for the nursing program?" → lookup, tuition, program="nursing"
- "How much does it cost to attend?" → lookup, tuition
- "Explain the financial aid process" → explain, general
- "What are the admission requirements for MBA?" → lookup, general, program="MBA"
- "Show me all graduate programs" → list, programs, degree_level="graduate"
"""


async def classify_query(query: str) -> dict:
    """
    Classify a user query into intent + entity + filters.

    Uses OpenAI function calling for structured classification.
    Falls back to simple keyword matching if the API call fails.

    Args:
        query: The user's natural language question

    Returns:
        dict with keys:
            - intent: "list" | "lookup" | "explain"
            - entity: "programs" | "tuition" | "fees" | "general"
            - filters: dict with optional keys: college, program, degree_level
    """
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",  # Fast + cheap, good enough for classification
            messages=[
                {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            functions=[CLASSIFICATION_FUNCTION],
            function_call={"name": "classify_query"},
            temperature=0,  # Deterministic classification
        )

        # Extract the function call arguments
        function_args = response.choices[0].message.function_call.arguments
        classification = json.loads(function_args)

        # Ensure filters key exists
        if "filters" not in classification:
            classification["filters"] = {}

        logger.info(
            f"Query classified: intent={classification['intent']}, "
            f"entity={classification['entity']}, "
            f"filters={classification.get('filters', {})}"
        )

        return classification

    except Exception as e:
        logger.warning(f"LLM classification failed, using fallback: {e}")
        return _fallback_classify(query)


def _fallback_classify(query: str) -> dict:
    """
    Simple keyword-based fallback classifier.

    Used when the LLM classification fails (API error, timeout, etc.).
    Less accurate but ensures the system stays functional.
    """
    query_lower = query.lower()

    # Determine intent
    list_keywords = ["list", "show all", "all programs", "what programs", "how many programs"]
    lookup_keywords = ["how much", "what is the", "tuition for", "cost of", "fee for", "requirements for"]

    intent = "explain"  # default
    if any(kw in query_lower for kw in list_keywords):
        intent = "list"
    elif any(kw in query_lower for kw in lookup_keywords):
        intent = "lookup"

    # Determine entity
    entity = "general"  # default
    if any(word in query_lower for word in ["program", "major", "degree", "college of"]):
        entity = "programs"
    elif "tuition" in query_lower:
        entity = "tuition"
    elif "fee" in query_lower:
        entity = "fees"

    # Extract basic filters
    filters = {}
    # Try to find college name pattern: "College of X"
    import re
    college_match = re.search(r"college of \w+(?:\s+\w+)?", query_lower)
    if college_match:
        # Title-case the match
        filters["college"] = college_match.group(0).title()

    return {
        "intent": intent,
        "entity": entity,
        "filters": filters,
    }
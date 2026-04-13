"""
Query Filter + Expansion

Extracts search keywords from the user's question AND expands them
with related terms, acronyms, and synonyms.

Example:
  Question: "What fees are associated with nursing?"
  Keywords: nursing
  Expanded: nursing, BSN, ABSN, TBSN, RN to BSN, College of Health Professions

This ensures vector search and keyword filtering find chunks that use
abbreviations or related terminology instead of the exact word the
user typed.

File location: backend/rag/query_filter.py
"""

from openai import AsyncOpenAI
from backend.config import settings

client = AsyncOpenAI(api_key=settings.openai_api_key)


async def extract_filters(question: str) -> dict:
    """
    Extract search keywords from the user's question and expand them
    with related terms, acronyms, and synonyms.

    Returns a dict with:
        - keywords: list of all search terms (original + expanded)
    """
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """You are a university search assistant. Given a student's question, extract search keywords AND expand them with related terms.

TASK: Return a comma-separated list of search terms. Include:
1. Specific terms from the question (program names, colleges, degree types)
2. Common abbreviations and acronyms for those terms
3. Related program names or department names
4. Full names for any abbreviations mentioned

UNIVERSITY CONTEXT — common abbreviations:
- Nursing programs: BSN, ABSN, TBSN, RN to BSN, Bachelor of Science in Nursing
- Business programs: BBA, BSB, MBA, MOL
- Engineering: BS, BSME, BSEE, BSCE
- Education: MAT, MEd, EdS, EdD
- Christian Studies: MDiv, MMin, MA Ministry, ThM
- Arts & Sciences: BA, BS
- Health Professions: includes Nursing, Exercise Science, Athletic Training
- College of Health Professions: covers nursing, health science programs
- Online/Hybrid: distance learning, remote, virtual

RULES:
- Always include the original terms from the question
- Add 3-6 related abbreviations or terms that might appear in university documents
- For program names, include both the full name and common abbreviations
- For colleges, include the programs that belong to that college
- If the question is general with no specific terms, return: NONE
- Return ONLY the comma-separated list, nothing else

EXAMPLES:
Question: "What fees are associated with nursing?"
Keywords: nursing, BSN, ABSN, TBSN, RN to BSN, College of Health Professions, Bachelor of Science in Nursing

Question: "Tell me about MBA programs"
Keywords: MBA, Master of Business Administration, College of Business, BBA, graduate business

Question: "What scholarships are available for education majors?"
Keywords: education, MAT, MEd, EdS, College of Education, teaching, teacher certification

Question: "How much does the computer engineering program cost?"
Keywords: computer engineering, BSCE, College of Engineering, engineering tuition, Bachelor of Science

Question: "What are the admission requirements?"
Keywords: admission, requirements, GPA, SAT, ACT, transcripts, application

Question: "Hello, what can you help me with?"
Keywords: NONE"""
            },
            {"role": "user", "content": question}
        ],
        temperature=0,
        max_tokens=150,
    )

    result = response.choices[0].message.content.strip()

    if result == "NONE" or not result:
        return {"keywords": []}

    keywords = [k.strip() for k in result.split(",") if k.strip()]

    print(f"[FILTER] Question: {question}")
    print(f"[FILTER] Expanded keywords: {keywords}")

    return {"keywords": keywords}
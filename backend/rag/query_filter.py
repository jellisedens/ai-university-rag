from openai import AsyncOpenAI
from backend.config import settings

client = AsyncOpenAI(api_key=settings.openai_api_key)


async def extract_filters(question: str) -> dict:
    """
    Use the LLM to extract filterable metadata from a question.
    Returns a dict with optional keys: keywords, document_type
    """
    response = await client.chat.completions.create(
        model=settings.chat_model,
        messages=[
            {
                "role": "system",
                "content": """Extract search filters from the user's question. Return ONLY a comma-separated list of specific keywords that should appear in the relevant documents. Focus on:
- Specific program names (e.g., Biology, Chemistry, MBA)
- College or department names (e.g., College of Business, College of Arts)
- Degree types (e.g., Bachelor, Master, Certificate, PhD)
- Specific data points mentioned (e.g., credit hours, tuition, director)

If the question is general with no specific filters, return: NONE

Examples:
Question: "What are the admission requirements for the BS in Biology?"
Keywords: Biology, Bachelor of Science

Question: "List all College of Business programs"
Keywords: College of Business

Question: "Compare the biology and chemistry programs"
Keywords: Biology, Chemistry

Question: "What graduate programs are available?"
Keywords: Graduate

Question: "Hello, what can you help me with?"
Keywords: NONE"""
            },
            {"role": "user", "content": question}
        ],
        temperature=0,
        max_tokens=100,
    )

    result = response.choices[0].message.content.strip()

    if result == "NONE" or not result:
        return {"keywords": []}

    keywords = [k.strip() for k in result.split(",") if k.strip()]
    return {"keywords": keywords}
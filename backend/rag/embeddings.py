from openai import AsyncOpenAI

from backend.config import settings

client = AsyncOpenAI(api_key=settings.openai_api_key)


async def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for a list of texts using OpenAI's API.
    Returns a list of embedding vectors (each is 1536 floats).
    """
    if not texts:
        return []

    response = await client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
    )

    return [item.embedding for item in response.data]


async def generate_single_embedding(text: str) -> list[float]:
    """Generate an embedding for a single text string."""
    results = await generate_embeddings([text])
    return results[0]
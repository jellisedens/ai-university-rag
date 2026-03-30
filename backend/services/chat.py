import uuid

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models.chat import ChatSession, Message
from backend.rag.retrieval import retrieve_relevant_chunks
from backend.rag.prompt import build_rag_prompt

client = AsyncOpenAI(api_key=settings.openai_api_key)


async def create_chat_session(db: AsyncSession, user_id: uuid.UUID) -> ChatSession:
    """Create a new chat session for a user."""
    session = ChatSession(user_id=user_id)
    db.add(session)
    await db.flush()
    return session


async def get_chat_session(
    db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID
) -> ChatSession | None:
    """Get a chat session, only if it belongs to the user."""
    from sqlalchemy import select
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def save_message(
    db: AsyncSession, session_id: uuid.UUID, role: str, content: str
) -> Message:
    """Save a message to a chat session."""
    message = Message(
        session_id=session_id,
        role=role,
        content=content,
    )
    db.add(message)
    await db.flush()
    return message


async def ask_question(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    question: str,
) -> dict:
    """
    Full RAG pipeline for answering a question.

    1. Retrieve relevant chunks
    2. Build prompt with context
    3. Call LLM
    4. Save messages
    5. Return answer with sources
    """
    # Step 1: Retrieve relevant chunks
    chunks = await retrieve_relevant_chunks(db, user_id, question)

    # Step 2: Build the prompt
    prompt = build_rag_prompt(question, chunks)

    # Step 3: Call the LLM
    response = await client.chat.completions.create(
        model=settings.chat_model,
        messages=[
            {"role": "system", "content": "You are a helpful university knowledge assistant."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )

    answer = response.choices[0].message.content

    # Step 4: Save the conversation
    await save_message(db, session_id, "user", question)
    await save_message(db, session_id, "assistant", answer)

    # Step 5: Return answer with sources
    sources = [
        {
            "document_title": chunk["document_title"],
            "file_name": chunk["file_name"],
            "page_number": chunk["page_number"],
            "distance": chunk["distance"],
        }
        for chunk in chunks
    ]

    return {
        "answer": answer,
        "sources": sources,
    }
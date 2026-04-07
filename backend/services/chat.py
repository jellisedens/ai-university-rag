import logging
import uuid

from openai import AsyncOpenAI
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models.chat import ChatSession, Message
from backend.rag.retrieval import retrieve_relevant_chunks
from backend.rag.prompt import build_rag_prompt
from backend.rag.query_router import route_query

logger = logging.getLogger(__name__)

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
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_user_sessions(
    db: AsyncSession, user_id: uuid.UUID
) -> list[dict]:
    """Get all chat sessions for a user, ordered by most recent first."""
    sessions_result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.created_at.desc())
    )
    sessions = sessions_result.scalars().all()

    session_list = []
    for session in sessions:
        first_msg_result = await db.execute(
            select(Message.content)
            .where(Message.session_id == session.id, Message.role == "user")
            .order_by(Message.created_at.asc())
            .limit(1)
        )
        first_msg = first_msg_result.scalar_one_or_none()

        count_result = await db.execute(
            select(func.count(Message.id)).where(Message.session_id == session.id)
        )
        message_count = count_result.scalar_one()

        if message_count > 0:
            session_list.append({
                "id": str(session.id),
                "preview": (first_msg[:80] + "...") if first_msg and len(first_msg) > 80 else (first_msg or "New conversation"),
                "message_count": message_count,
                "created_at": session.created_at.isoformat(),
            })

    return session_list


async def get_session_messages(
    db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID
) -> list[dict]:
    """Get all messages for a session, in chronological order."""
    session = await get_chat_session(db, session_id, user_id)
    if not session:
        return []

    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    )
    messages = result.scalars().all()

    return [
        {"role": msg.role, "content": msg.content, "created_at": msg.created_at.isoformat()}
        for msg in messages
    ]


async def delete_chat_session(
    db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Delete a chat session and all its messages."""
    session = await get_chat_session(db, session_id, user_id)
    if not session:
        return False

    await db.execute(delete(Message).where(Message.session_id == session_id))
    await db.execute(delete(ChatSession).where(ChatSession.id == session_id))
    await db.flush()
    return True


async def save_message(
    db: AsyncSession, session_id: uuid.UUID, role: str, content: str
) -> Message:
    """Save a message to a chat session."""
    message = Message(session_id=session_id, role=role, content=content)
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
    Returns answer, sources, and optionally structured_data for dashboard display.
    """
    # Step 1: Get recent conversation history
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc())
        .limit(10)
    )
    recent_messages = list(reversed(result.scalars().all()))

    # Step 2: Retrieve relevant chunks (with routing)
    route_result = await route_query(
        db=db,
        user_id=user_id,
        query=question,
        retrieve_fn=retrieve_relevant_chunks,
    )
    chunks = route_result["chunks"]
    structured_data = route_result.get("structured_data")

    # Step 3: Build the prompt
    prompt = build_rag_prompt(question, chunks)

    # Step 4: Build message history for the LLM
    llm_messages = [
        {"role": "system", "content": "You are a helpful university knowledge assistant."},
    ]
    for msg in recent_messages:
        llm_messages.append({"role": msg.role, "content": msg.content})
    llm_messages.append({"role": "user", "content": prompt})

    # Step 5: Call the LLM
    response = await client.chat.completions.create(
        model=settings.chat_model,
        messages=llm_messages,
        temperature=0.3,
        max_tokens=4096,
    )
    answer = response.choices[0].message.content

    # Step 6: Save the conversation
    await save_message(db, session_id, "user", question)
    await save_message(db, session_id, "assistant", answer)

    # Step 7: Return answer with sources and optional dashboard data
    sources = [
        {
            "document_title": chunk["document_title"],
            "file_name": chunk["file_name"],
            "page_number": chunk["page_number"],
            "distance": chunk["distance"],
        }
        for chunk in chunks
    ]

    result = {
        "answer": answer,
        "sources": sources,
    }

    # Include structured data if the AI-assisted route produced it
    if structured_data:
        result["structured_data"] = structured_data

    return result
from fastapi import FastAPI

from backend.database.session import engine

app = FastAPI(
    title="AI University Knowledge Repository",
    description="RAG-powered Q&A system for university documents",
    version="0.1.0",
)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/health/db")
async def db_health_check():
    """Verify the database connection is working."""
    try:
        async with engine.connect() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": str(e)}
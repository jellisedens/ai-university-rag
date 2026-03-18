from fastapi import FastAPI

app = FastAPI(
    title="AI University Knowledge Repository",
    description="RAG-powered Q&A system for university documents",
    version="0.1.0",
)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
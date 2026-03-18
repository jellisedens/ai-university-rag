# AI University Knowledge Repository

A Retrieval-Augmented Generation (RAG) system that allows users to upload university documents and ask natural language questions about them.

## Overview

Users upload PDF documents (academic catalogs, admissions guides, financial aid info) and the system:

1. Extracts and chunks the text
2. Generates vector embeddings for each chunk
3. Stores embeddings in PostgreSQL with pgvector
4. Retrieves relevant chunks when a user asks a question
5. Sends retrieved context to an LLM to generate a grounded answer with citations

## Project Structure
```
ai-university-rag/
├── backend/
│   ├── api/            # FastAPI route handlers
│   ├── models/         # SQLAlchemy ORM models
│   ├── services/       # Business logic services
│   ├── rag/            # RAG pipeline (chunking, retrieval, prompts)
│   ├── database/       # Database connection and session config
│   └── main.py         # FastAPI application entry point
├── docker/             # Dockerfiles for backend and database
├── docs/               # Architecture and design documents
├── docker-compose.yml  # Local development orchestration
└── README.md
```

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Python 3.11+

### Run with Docker
```bash
docker-compose up --build
```

This starts:
- PostgreSQL with pgvector on port **5432**
- FastAPI backend on port **8000**

### API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

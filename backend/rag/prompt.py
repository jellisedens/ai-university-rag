def build_rag_prompt(query: str, chunks: list[dict]) -> str:
    """
    Build a prompt that includes retrieved document context.
    
    The prompt instructs the LLM to:
    - Only answer based on the provided context
    - Cite specific documents and page numbers
    - Admit when the context doesn't contain the answer
    """
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        source = f"[Source {i}: {chunk['document_title']}, Page {chunk['page_number']}]"
        context_parts.append(f"{source}\n{chunk['content']}")

    context = "\n\n---\n\n".join(context_parts)

    prompt = f"""You are a helpful university knowledge assistant. Answer the user's question based ONLY on the provided document context below. 

Rules:
- Only use information from the provided context to answer
- Cite your sources by referencing the document title and page number
- If the context does not contain enough information to answer the question, say so clearly
- Be concise and direct in your answers

DOCUMENT CONTEXT:
{context}

USER QUESTION:
{query}

ANSWER:"""

    return prompt
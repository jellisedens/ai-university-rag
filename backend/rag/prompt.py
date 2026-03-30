def build_rag_prompt(query: str, chunks: list[dict]) -> str:
    """
    Build a prompt that includes retrieved document context.
    """
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        source = f"[Source {i}: {chunk['document_title']}, Page {chunk['page_number']}]"
        context_parts.append(f"{source}\n{chunk['content']}")

    context = "\n\n---\n\n".join(context_parts)

    # Build a list of all unique documents for summary-type questions
    unique_docs = list({chunk['document_title'] for chunk in chunks})
    doc_list = ", ".join(unique_docs)

    prompt = f"""You are a helpful university knowledge assistant. Answer the user's question based ONLY on the provided document context below.

Rules:
- Only use information from the provided context to answer
- Cite your sources by referencing the document title and page number
- If the context does not contain enough information to fully answer the question, answer what you can and clearly state what information is missing
- If the question has multiple parts, address each part separately
- When asked to list or count items, always provide the COMPLETE list - never truncate or summarize with "and more"
- Be concise and direct in your answers

Available documents in the system: {doc_list}

DOCUMENT CONTEXT:
{context}

USER QUESTION:
{query}

ANSWER:"""

    return prompt
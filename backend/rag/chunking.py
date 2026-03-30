from backend.config import settings


def chunk_text(pages: list[dict]) -> list[dict]:
    """
    Split page text into overlapping chunks.
    
    Takes the page list from text_extraction and returns chunks
    with content, page_number, and chunk_index.
    """
    chunk_size = settings.chunk_size
    overlap = settings.chunk_overlap
    chunks = []
    chunk_index = 0

    for page in pages:
        text = page["text"]
        page_number = page["page_number"]
        words = text.split()

        start = 0
        while start < len(words):
            end = start + chunk_size
            chunk_words = words[start:end]
            content = " ".join(chunk_words)

            if content.strip():
                chunks.append({
                    "content": content,
                    "page_number": page_number,
                    "chunk_index": chunk_index,
                })
                chunk_index += 1

            start += chunk_size - overlap

    return chunks
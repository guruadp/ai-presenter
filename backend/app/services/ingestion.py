import hashlib
import io

from openai import OpenAI

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
EMBEDDING_MODEL = "text-embedding-3-small"


def extract_text(content: bytes, filename: str, content_type: str) -> str:
    name_lower = filename.lower()
    if name_lower.endswith((".txt", ".md")) or content_type in ("text/plain", "text/markdown"):
        return content.decode("utf-8", errors="replace")
    if name_lower.endswith(".pdf") or "pdf" in content_type:
        return _extract_pdf(content)
    if name_lower.endswith(".docx") or "wordprocessingml" in content_type:
        return _extract_docx(content)
    raise ValueError(f"Unsupported file type: {filename!r}")


def _extract_pdf(content: bytes) -> str:
    try:
        import pypdf
    except ImportError as e:
        raise ImportError("pypdf required: pip install pypdf") from e
    reader = pypdf.PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx(content: bytes) -> str:
    try:
        import docx
    except ImportError as e:
        raise ImportError("python-docx required: pip install python-docx") from e
    doc = docx.Document(io.BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunk = text[start : start + chunk_size]
        if chunk.strip():
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def embed_chunks(chunks: list[str], client: OpenAI | None = None) -> list[list[float]]:
    if client is None:
        from app.config import get_settings
        client = OpenAI(api_key=get_settings().OPENAI_API_KEY)
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=chunks)
    return [item.embedding for item in resp.data]


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()[:16]

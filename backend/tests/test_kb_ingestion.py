from unittest.mock import MagicMock, patch

import pytest

from app.services.ingestion import chunk_text, content_hash, extract_text


# ── Unit tests for ingestion helpers ──────────────────────────────────────────

def test_extract_text_txt():
    assert extract_text(b"hello world", "doc.txt", "text/plain") == "hello world"


def test_extract_text_md():
    assert extract_text(b"# Title\nBody", "README.md", "text/markdown") == "# Title\nBody"


def test_extract_text_unsupported():
    with pytest.raises(ValueError, match="Unsupported"):
        extract_text(b"data", "file.xyz", "application/octet-stream")


def test_chunk_text_splits_correctly():
    # 2500 chars, step=800 → starts at 0, 800, 1600, 2400 → 4 chunks
    text = "a" * 2500
    chunks = chunk_text(text, chunk_size=1000, overlap=200)
    assert len(chunks) == 4
    assert all(len(c) <= 1000 for c in chunks)


def test_chunk_text_skips_empty():
    chunks = chunk_text("   \n   ", chunk_size=1000, overlap=200)
    assert chunks == []


def test_content_hash_is_deterministic():
    data = b"some content"
    assert content_hash(data) == content_hash(data)
    assert len(content_hash(data)) == 16


# ── Integration test: ingest endpoint (mocked embeddings + chroma) ────────────

def _make_openai_mock(embedding: list[float]):
    mock = MagicMock()
    mock.embeddings.create.return_value = MagicMock(
        data=[MagicMock(embedding=embedding)]
    )
    return mock


def test_ingest_text_document(client):
    kb = client.post("/kbs", json={"name": "KB", "owner": "alice"}).json()

    mock_col = MagicMock()
    mock_chroma = MagicMock()
    mock_chroma.get_or_create_collection.return_value = mock_col

    fake_embedding = [0.1] * 1536

    with (
        patch("app.services.ingestion.OpenAI", return_value=_make_openai_mock(fake_embedding)),
        patch("app.routers.knowledge_bases.retrieval_svc.get_chroma_client", return_value=mock_chroma),
    ):
        resp = client.post(
            f"/kbs/{kb['id']}/documents",
            files={"file": ("product.txt", b"Our product costs $99 per month.", "text/plain")},
            data={"tags": "product,pricing"},
        )

    assert resp.status_code == 201
    doc = resp.json()
    assert doc["filename"] == "product.txt"
    assert set(doc["tags"]) == {"product", "pricing"}
    assert doc["chunk_count"] >= 1

    # version bumped after ingestion
    kb_after = client.get(f"/kbs/{kb['id']}").json()
    assert kb_after["version"] == 2

    # Chroma upsert was called
    mock_col.upsert.assert_called_once()


def test_ingest_bumps_version_and_lists_document(client):
    kb = client.post("/kbs", json={"name": "KB", "owner": "alice"}).json()

    mock_col = MagicMock()
    mock_chroma = MagicMock()
    mock_chroma.get_or_create_collection.return_value = mock_col

    with (
        patch("app.services.ingestion.OpenAI", return_value=_make_openai_mock([0.0] * 1536)),
        patch("app.routers.knowledge_bases.retrieval_svc.get_chroma_client", return_value=mock_chroma),
    ):
        client.post(
            f"/kbs/{kb['id']}/documents",
            files={"file": ("a.txt", b"content", "text/plain")},
        )

    docs = client.get(f"/kbs/{kb['id']}/documents").json()
    assert len(docs) == 1
    assert docs[0]["filename"] == "a.txt"

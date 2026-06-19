from unittest.mock import MagicMock, patch


def _chroma_result(kb_id: str, text: str = "chunk text", doc_id: str = "doc1"):
    return {
        "ids": [[f"{doc_id}:0"]],
        "documents": [[text]],
        "metadatas": [[{"source": "file.txt", "kb_id": kb_id, "doc_id": doc_id, "tags": "product"}]],
        "distances": [[0.1]],
    }


def _make_openai_mock():
    mock = MagicMock()
    mock.embeddings.create.return_value = MagicMock(
        data=[MagicMock(embedding=[0.1] * 1536)]
    )
    return mock


def test_retrieve_returns_chunks_for_kb(client):
    kb = client.post("/kbs", json={"name": "KB", "owner": "alice"}).json()

    mock_col = MagicMock()
    mock_col.query.return_value = _chroma_result(kb["id"])
    mock_chroma = MagicMock()
    mock_chroma.get_collection.return_value = mock_col

    with (
        patch("app.services.retrieval.OpenAI", return_value=_make_openai_mock()),
        patch("app.services.retrieval.get_chroma_client", return_value=mock_chroma),
    ):
        resp = client.post(
            "/retrieve",
            json={"text": "product pricing", "kb_ids": [kb["id"]], "top_k": 3},
        )

    assert resp.status_code == 200
    chunks = resp.json()["chunks"]
    assert len(chunks) == 1
    assert chunks[0]["kb_id"] == kb["id"]
    assert chunks[0]["chunk_text"] == "chunk text"
    assert chunks[0]["score"] == 0.9
    assert "product" in chunks[0]["tags"]


def test_retrieve_scoped_to_requested_kbs_only(client):
    kb1 = client.post("/kbs", json={"name": "KB1", "owner": "alice"}).json()
    kb2 = client.post("/kbs", json={"name": "KB2", "owner": "alice"}).json()

    mock_col = MagicMock()
    mock_col.query.return_value = _chroma_result(kb1["id"])
    mock_chroma = MagicMock()
    mock_chroma.get_collection.return_value = mock_col

    with (
        patch("app.services.retrieval.OpenAI", return_value=_make_openai_mock()),
        patch("app.services.retrieval.get_chroma_client", return_value=mock_chroma),
    ):
        resp = client.post(
            "/retrieve",
            json={"text": "query", "kb_ids": [kb1["id"]], "top_k": 5},
        )

    chunks = resp.json()["chunks"]
    assert all(c["kb_id"] == kb1["id"] for c in chunks)
    # get_collection called once (only for kb1)
    assert mock_chroma.get_collection.call_count == 1


def test_retrieve_empty_kb_ids_returns_empty(client):
    resp = client.post("/retrieve", json={"text": "anything", "kb_ids": []})
    assert resp.status_code == 200
    assert resp.json()["chunks"] == []


def test_retrieve_missing_collection_skipped(client):
    kb = client.post("/kbs", json={"name": "KB", "owner": "alice"}).json()

    mock_chroma = MagicMock()
    mock_chroma.get_collection.side_effect = Exception("Collection not found")

    with (
        patch("app.services.retrieval.OpenAI", return_value=_make_openai_mock()),
        patch("app.services.retrieval.get_chroma_client", return_value=mock_chroma),
    ):
        resp = client.post(
            "/retrieve",
            json={"text": "query", "kb_ids": [kb["id"]]},
        )

    assert resp.status_code == 200
    assert resp.json()["chunks"] == []

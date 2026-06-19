from typing import Optional

from openai import OpenAI

from app.services.ingestion import EMBEDDING_MODEL


def get_chroma_client():
    import chromadb
    from app.config import get_settings
    return chromadb.PersistentClient(path=get_settings().CHROMA_DIR)


def collection_name(kb_id: str) -> str:
    return f"kb_{kb_id}"


def retrieve(
    text: str,
    kb_ids: list[str],
    filters: Optional[dict] = None,
    top_k: int = 5,
    openai_client=None,
    chroma_client=None,
) -> list[dict]:
    if not kb_ids:
        return []

    if openai_client is None:
        from app.config import get_settings
        openai_client = OpenAI(api_key=get_settings().OPENAI_API_KEY)
    if chroma_client is None:
        chroma_client = get_chroma_client()

    resp = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=[text])
    query_embedding = resp.data[0].embedding

    results: list[dict] = []
    for kb_id in kb_ids:
        try:
            col = chroma_client.get_collection(collection_name(kb_id))
        except Exception:
            continue  # no documents ingested yet for this KB

        query_kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if filters:
            query_kwargs["where"] = filters

        res = col.query(**query_kwargs)
        if not res["ids"] or not res["ids"][0]:
            continue

        for i, chunk_id in enumerate(res["ids"][0]):
            meta = res["metadatas"][0][i] if res["metadatas"] else {}
            dist = res["distances"][0][i] if res["distances"] else 1.0
            tags_str = meta.get("tags", "")
            results.append({
                "chunk_text": res["documents"][0][i],
                "source": meta.get("source", ""),
                "score": round(1.0 - dist, 4),
                "kb_id": kb_id,
                "doc_id": meta.get("doc_id", ""),
                "tags": [t for t in tags_str.split(",") if t],
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]

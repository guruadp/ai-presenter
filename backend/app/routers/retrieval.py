from fastapi import APIRouter

from app.schemas.knowledge_base import RetrieveRequest, RetrieveResponse
from app.services import retrieval as retrieval_svc

router = APIRouter(prefix="/retrieve", tags=["retrieval"])


@router.post("", response_model=RetrieveResponse)
def retrieve_chunks(body: RetrieveRequest) -> dict:
    chunks = retrieval_svc.retrieve(
        text=body.text,
        kb_ids=body.kb_ids,
        filters=body.filters,
        top_k=body.top_k,
    )
    return {"chunks": chunks}

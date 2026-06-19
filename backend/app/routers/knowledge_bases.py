import hashlib
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.knowledge_base import KBDocument, KBFact, KBLimitation, KnowledgeBase
from app.schemas.knowledge_base import (
    KBCreate,
    KBDocumentOut,
    KBFactCreate,
    KBFactOut,
    KBLimitationCreate,
    KBLimitationOut,
    KBOut,
    KBUpdate,
)
from app.services import ingestion, retrieval as retrieval_svc

log = logging.getLogger(__name__)
router = APIRouter(prefix="/kbs", tags=["knowledge-bases"])

DbDep = Annotated[Session, Depends(get_db)]


def _get_kb_or_404(kb_id: str, db: Session) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(404, "Knowledge base not found")
    return kb


def _bump_version(kb: KnowledgeBase, db: Session) -> None:
    kb.version += 1
    kb.content_hash = hashlib.sha256(f"{kb.id}:{kb.version}".encode()).hexdigest()[:16]
    db.add(kb)
    db.commit()
    log.info("kb_changed event: id=%s version=%s", kb.id, kb.version)


# ── KB CRUD ───────────────────────────────────────────────────────────────────

@router.post("", response_model=KBOut, status_code=201)
def create_kb(body: KBCreate, db: DbDep) -> KnowledgeBase:
    # Generate ID at the Python level so content_hash can reference it before flush.
    kb_id = str(uuid.uuid4())
    kb = KnowledgeBase(id=kb_id, name=body.name, owner=body.owner)
    kb.content_hash = hashlib.sha256(kb_id.encode()).hexdigest()[:16]
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb


@router.get("", response_model=list[KBOut])
def list_kbs(db: DbDep) -> list[KnowledgeBase]:
    return db.query(KnowledgeBase).all()


@router.get("/{kb_id}", response_model=KBOut)
def get_kb(kb_id: str, db: DbDep) -> KnowledgeBase:
    return _get_kb_or_404(kb_id, db)


@router.patch("/{kb_id}", response_model=KBOut)
def update_kb(kb_id: str, body: KBUpdate, db: DbDep) -> KnowledgeBase:
    kb = _get_kb_or_404(kb_id, db)
    if body.name is not None:
        kb.name = body.name
    _bump_version(kb, db)
    db.refresh(kb)
    return kb


@router.delete("/{kb_id}", status_code=204)
def delete_kb(kb_id: str, db: DbDep) -> None:
    kb = _get_kb_or_404(kb_id, db)
    try:
        client = retrieval_svc.get_chroma_client()
        client.delete_collection(retrieval_svc.collection_name(kb_id))
    except Exception:
        pass
    db.delete(kb)
    db.commit()


# ── Documents ─────────────────────────────────────────────────────────────────

@router.get("/{kb_id}/documents", response_model=list[KBDocumentOut])
def list_documents(kb_id: str, db: DbDep) -> list[KBDocument]:
    _get_kb_or_404(kb_id, db)
    return db.query(KBDocument).filter(KBDocument.kb_id == kb_id).all()


@router.post("/{kb_id}/documents", response_model=KBDocumentOut, status_code=201)
async def ingest_document(
    kb_id: str,
    db: DbDep,
    file: UploadFile = File(...),
    tags: str = Form(default=""),
) -> KBDocument:
    kb = _get_kb_or_404(kb_id, db)
    content = await file.read()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    filename = file.filename or "unknown"
    content_type = file.content_type or "text/plain"

    text = ingestion.extract_text(content, filename, content_type)
    chunks = ingestion.chunk_text(text)
    embeddings = ingestion.embed_chunks(chunks)

    chroma = retrieval_svc.get_chroma_client()
    col = chroma.get_or_create_collection(retrieval_svc.collection_name(kb_id))

    doc_id = str(uuid.uuid4())
    col.upsert(
        ids=[f"{doc_id}:{i}" for i in range(len(chunks))],
        embeddings=embeddings,
        documents=chunks,
        metadatas=[
            {"source": filename, "kb_id": kb_id, "doc_id": doc_id, "tags": ",".join(tag_list)}
            for _ in chunks
        ],
    )

    doc = KBDocument(
        id=doc_id,
        kb_id=kb_id,
        filename=filename,
        content_type=content_type,
        content_hash=ingestion.content_hash(content),
        chunk_count=len(chunks),
        tags=tag_list,
    )
    db.add(doc)
    _bump_version(kb, db)
    db.refresh(doc)
    return doc


# ── Structured Facts ──────────────────────────────────────────────────────────

@router.get("/{kb_id}/facts", response_model=list[KBFactOut])
def list_facts(kb_id: str, db: DbDep) -> list[KBFact]:
    _get_kb_or_404(kb_id, db)
    return db.query(KBFact).filter(KBFact.kb_id == kb_id).all()


@router.post("/{kb_id}/facts", response_model=KBFactOut, status_code=201)
def add_fact(kb_id: str, body: KBFactCreate, db: DbDep) -> KBFact:
    kb = _get_kb_or_404(kb_id, db)
    fact = KBFact(kb_id=kb_id, key=body.key, value=body.value, source=body.source)
    db.add(fact)
    _bump_version(kb, db)
    db.refresh(fact)
    return fact


@router.delete("/{kb_id}/facts/{fact_id}", status_code=204)
def delete_fact(kb_id: str, fact_id: str, db: DbDep) -> None:
    kb = _get_kb_or_404(kb_id, db)
    fact = db.get(KBFact, fact_id)
    if not fact or fact.kb_id != kb_id:
        raise HTTPException(404, "Fact not found")
    db.delete(fact)
    _bump_version(kb, db)


# ── Limitations / Negative-Space Doc ─────────────────────────────────────────

@router.get("/{kb_id}/limitations", response_model=list[KBLimitationOut])
def list_limitations(kb_id: str, db: DbDep) -> list[KBLimitation]:
    _get_kb_or_404(kb_id, db)
    return db.query(KBLimitation).filter(KBLimitation.kb_id == kb_id).all()


@router.post("/{kb_id}/limitations", response_model=KBLimitationOut, status_code=201)
def add_limitation(kb_id: str, body: KBLimitationCreate, db: DbDep) -> KBLimitation:
    kb = _get_kb_or_404(kb_id, db)
    lim = KBLimitation(kb_id=kb_id, description=body.description)
    db.add(lim)
    _bump_version(kb, db)
    db.refresh(lim)
    return lim


@router.delete("/{kb_id}/limitations/{lim_id}", status_code=204)
def delete_limitation(kb_id: str, lim_id: str, db: DbDep) -> None:
    kb = _get_kb_or_404(kb_id, db)
    lim = db.get(KBLimitation, lim_id)
    if not lim or lim.kb_id != kb_id:
        raise HTTPException(404, "Limitation not found")
    db.delete(lim)
    _bump_version(kb, db)

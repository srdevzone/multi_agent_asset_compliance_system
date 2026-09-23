"""
POST /api/v1/ingest — Document ingestion pipeline.

Handles three lifecycle events for asset documents:
  - create: first-time ingest of all documents for a new asset (idempotent)
  - update: replace one document's vectors (surgical delete + re-embed)
  - add:    append new document(s) to an existing asset namespace

Workflow per document:
  1. For image documents (installation_image): describe via LLM vision → single vector
  2. For all other documents: download from S3 → parse PDF → chunk → embed → upsert

All document types are processed sequentially within a single Lambda invocation.
"""

import asyncio
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

import structlog
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from pinecone import Index

from app.config import Settings
from app.dependencies import EmbeddingsDep, ImageLLMDep, PineconeDep, S3Dep, SettingsDep
from app.schemas.ingest import IngestRequest, IngestResponse, S3Document
from app.services import document_loader, pinecone_service, s3_service
from app.services.embedding_service import embed_texts

router = APIRouter(prefix="/ingest", tags=["ingestion"])
logger = structlog.get_logger(__name__)


async def _describe_image(
    image_llm: BaseChatModel,
    s3_client: Any,
    settings: Settings,
    document: S3Document,
    asset_id: str,
) -> str:
    """
    Use LLM vision to generate a text description of an image document.

    The description is stored as the vector's text in Pinecone, allowing
    image documents to participate in semantic retrieval.
    """
    image_b64 = await s3_service.download_as_base64(s3_client, settings.s3_bucket_name, document.s3_key)
    media_type = s3_service.infer_media_type(document.filename)
    image_url = f"data:{media_type};base64,{image_b64}"

    prompt_text = (
        f"This is an installation or reference image for asset ID '{asset_id}'. "
        "Describe all visible components, labels, connections, measurements, "
        "and any text you can read. Be thorough — this description is used "
        "for compliance retrieval."
    )

    messages = [
        HumanMessage(
            content=[
                {"type": "text", "text": prompt_text},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]
        )
    ]

    response = await image_llm.ainvoke(messages)
    description: str = str(response.content)
    logger.debug(
        "image_document_described",
        doc_id=document.doc_id,
        asset_id=asset_id,
        description_length=len(description),
    )
    return description


async def _ingest_document(
    document: S3Document,
    asset_id: str,
    index: Index,
    s3_client: Any,
    embeddings: Embeddings,
    image_llm: BaseChatModel,
    settings: Settings,
) -> int:
    """
    Ingest a single document: download → chunk → embed → upsert.

    Returns the number of vectors upserted.
    Callers are responsible for any pre-deletion logic (update events).
    """
    if document.doc_type == "installation_image":
        description = await _describe_image(image_llm, s3_client, settings, document, asset_id)
        chunks = document_loader.load_image_document(document, asset_id, description)
    else:
        raw = await s3_service.download_bytes(s3_client, settings.s3_bucket_name, document.s3_key)
        chunks = document_loader.load_pdf(raw, document, asset_id)

    if not chunks:
        logger.warning(
            "no_chunks_produced",
            doc_id=document.doc_id,
            asset_id=asset_id,
            doc_type=document.doc_type,
        )
        return 0

    texts = [c["text"] for c in chunks]
    embeddings_vectors = await embed_texts(embeddings, texts)

    vectors = [
        {
            "id": f"{asset_id}_{chunk['chunk_id']}",
            "values": emb,
            "metadata": chunk["metadata"],
        }
        for chunk, emb in zip(chunks, embeddings_vectors, strict=True)
    ]

    upserted = pinecone_service.upsert_vectors(index, asset_id, vectors)

    logger.info(
        "document_ingested",
        doc_id=document.doc_id,
        asset_id=asset_id,
        vectors_upserted=upserted,
    )
    return upserted


@router.post(
    "",
    response_model=IngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest asset documents into Pinecone",
    description=(
        "Download documents from S3, chunk, embed, and upsert into the asset's "
        "Pinecone namespace. Supports create, update, and add lifecycle events."
    ),
)
async def ingest_documents(
    request: IngestRequest,
    index: PineconeDep,
    embeddings: EmbeddingsDep,
    image_llm: ImageLLMDep,
    s3_client: S3Dep,
    settings: SettingsDep,
) -> IngestResponse:
    """Handle document ingestion for all three lifecycle events."""
    log = logger.bind(asset_id=request.asset_id, event=request.event)

    total_upserted = 0
    total_deleted = 0

    if request.event == "create":
        # Idempotency guard: if namespace already has vectors, skip processing
        if pinecone_service.namespace_has_docs(index, request.asset_id):
            log.info("ingest_skipped_namespace_exists")
            return IngestResponse(
                asset_id=request.asset_id,
                event=request.event,
                documents_processed=0,
                vectors_upserted=0,
                vectors_deleted=0,
                completed_at=datetime.now(UTC),
                namespace=f"asset_{request.asset_id}",
            )

    elif request.event == "update":
        # update requires exactly one document for surgical replacement
        if len(request.documents) != 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="'update' event requires exactly one document in the documents list.",
            )
        deleted = pinecone_service.delete_by_doc_id(
            index, request.asset_id, request.documents[0].doc_id
        )
        total_deleted += deleted
        log.info("stale_vectors_deleted", doc_id=request.documents[0].doc_id, deleted=deleted)

    # Process all documents (for create/add, or the single doc for update)
    for document in request.documents:
        upserted = await _ingest_document(
            document,
            request.asset_id,
            index,
            s3_client,
            embeddings,
            image_llm,
            settings,
        )
        total_upserted += upserted

    log.info(
        "ingest_complete",
        documents_processed=len(request.documents),
        vectors_upserted=total_upserted,
        vectors_deleted=total_deleted,
        business_metric="IngestionVolume",
    )

    return IngestResponse(
        asset_id=request.asset_id,
        event=request.event,
        documents_processed=len(request.documents),
        vectors_upserted=total_upserted,
        vectors_deleted=total_deleted,
        completed_at=datetime.now(UTC),
        namespace=f"asset_{request.asset_id}",
    )


@router.post(
    "/upload",
    response_model=IngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload and ingest documents into Pinecone",
    description="Accepts multiple files via form upload, writes them to S3, and embeds/upserts them into Pinecone.",
)
async def upload_and_ingest_documents(
    asset_id: Annotated[str, Form(min_length=1)],
    event: Annotated[str, Form(pattern="^(create|add)$")],
    files: Annotated[list[UploadFile], File()],
    index: PineconeDep,
    embeddings: EmbeddingsDep,
    image_llm: ImageLLMDep,
    s3_client: S3Dep,
    settings: SettingsDep,
) -> IngestResponse:
    """Upload files to S3 and trigger Pinecone vector ingestion."""
    log = logger.bind(asset_id=asset_id, event=event)

    total_upserted = 0
    total_deleted = 0

    if event == "create":
        # Idempotency guard: if namespace already has vectors, skip processing
        if pinecone_service.namespace_has_docs(index, asset_id):
            log.info("upload_skipped_namespace_exists")
            return IngestResponse(
                asset_id=asset_id,
                event=event,
                documents_processed=0,
                vectors_upserted=0,
                vectors_deleted=0,
                completed_at=datetime.now(UTC),
                namespace=f"asset_{asset_id}",
            )

    documents = []
    # Process each uploaded file: save to S3 first
    for upload_file in files:
        filename = upload_file.filename or "unnamed_file"
        # Generate a safe doc_id and key from filename
        safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in filename)
        doc_id = f"doc_{safe_name.rsplit('.', 1)[0]}"
        s3_key = f"{asset_id}/{safe_name}"

        # Determine doc_type from filename extension
        ext = safe_name.lower().rsplit(".", 1)[-1] if "." in safe_name else ""
        doc_type: Literal[
            "user_manual",
            "safety_sheet",
            "compliance_spec",
            "installation_image",
            "other",
        ]
        if ext in ("jpg", "jpeg", "png", "webp", "gif"):
            doc_type = "installation_image"
        elif ext == "pdf":
            doc_type = "compliance_spec"
            if "manual" in safe_name.lower() or "user" in safe_name.lower():
                doc_type = "user_manual"
            elif "safety" in safe_name.lower() or "msds" in safe_name.lower():
                doc_type = "safety_sheet"
        else:
            doc_type = "other"

        # Read file bytes
        raw_bytes = await upload_file.read()
        
        # Save to S3
        await asyncio.to_thread(
            s3_client.put_object,
            Bucket=settings.s3_bucket_name,
            Key=s3_key,
            Body=raw_bytes,
        )

        document = S3Document(
            s3_key=s3_key,
            doc_id=doc_id,
            doc_type=doc_type,
            filename=filename,
        )
        documents.append(document)

    # Process all uploaded documents
    for document in documents:
        upserted = await _ingest_document(
            document,
            asset_id,
            index,
            s3_client,
            embeddings,
            image_llm,
            settings,
        )
        total_upserted += upserted

    log.info(
        "upload_ingest_complete",
        documents_processed=len(files),
        vectors_upserted=total_upserted,
        business_metric="IngestionVolume",
    )

    return IngestResponse(
        asset_id=asset_id,
        event=event,
        documents_processed=len(files),
        vectors_upserted=total_upserted,
        vectors_deleted=total_deleted,
        completed_at=datetime.now(UTC),
        namespace=f"asset_{asset_id}",
    )

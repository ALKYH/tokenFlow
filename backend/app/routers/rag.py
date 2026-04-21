from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_optional_user
from ..schemas.rag import (
    RagDocumentIngestRequest,
    RagDocumentIngestResponse,
    RagMetricsResponse,
    RagRetrieveRequest,
    RagRetrieveResponse,
)
from ..services.rag_service import RagServiceError, get_retrieval_metrics, ingest_document, retrieve_chunks

router = APIRouter(prefix='/api/rag', tags=['rag'])


def _resolve_workspace_id(request_workspace_id: str, user: object | None) -> str:
    workspace_id = (request_workspace_id or '').strip()
    if workspace_id:
        return workspace_id
    if not user:
        return 'default'
    email = getattr(user, 'email', '')
    if email:
        return f'user:{email}'
    user_id = getattr(user, 'id', '')
    return f'user:{user_id}' if user_id else 'default'


@router.post(
    '/documents/ingest',
    response_model=RagDocumentIngestResponse,
    summary='Ingest text into pgvector RAG store',
)
async def rag_ingest_document(payload: RagDocumentIngestRequest, user=Depends(get_optional_user)):
    try:
        normalized = payload.model_copy(update={'workspace_id': _resolve_workspace_id(payload.workspace_id, user)})
        return await ingest_document(normalized)
    except RagServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f'RAG ingest failed: {exc}') from exc


@router.post(
    '/retrieve',
    response_model=RagRetrieveResponse,
    summary='Retrieve top-k chunks and injected context',
)
async def rag_retrieve(payload: RagRetrieveRequest, user=Depends(get_optional_user)):
    try:
        normalized = payload.model_copy(update={'workspace_id': _resolve_workspace_id(payload.workspace_id, user)})
        return await retrieve_chunks(normalized)
    except RagServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f'RAG retrieval failed: {exc}') from exc


@router.get(
    '/metrics',
    response_model=RagMetricsResponse,
    summary='RAG retrieval metrics summary',
)
async def rag_metrics(workspace_id: str = 'default', window_hours: int = 24, user=Depends(get_optional_user)):
    resolved_workspace = _resolve_workspace_id(workspace_id, user)
    return await get_retrieval_metrics(workspace_id=resolved_workspace, window_hours=window_hours)


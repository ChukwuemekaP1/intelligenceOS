"""API endpoints for knowledge source ingestion and status tracking.

Enforces workspace isolation, authentication, and authorization.
Provides file upload (PDF, CSV, Image), URL submission with SSRF checks,
status polling, chunk inspection, and retry capabilities.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Path, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_workspace_membership,
    require_workspace_role,
)
from app.core.exceptions import NotFoundError
from app.database.session import get_db
from app.models.membership import Membership, WorkspaceRole
from app.models.user import User
from app.schemas.source import (
    ChunkResponse,
    DocumentResponse,
    SourceResponse,
    UrlSourceCreate,
)
from app.services.ingestion_service import IngestionService

router = APIRouter(prefix="/workspaces/{workspace_id}/sources", tags=["Sources & Ingestion"])


@router.post(
    "/upload",
    response_model=SourceResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a file for asynchronous knowledge ingestion",
)
async def upload_file_source(
    workspace_id: Annotated[uuid.UUID, Path(..., description="Target workspace ID")],
    file: UploadFile = File(
        ..., description="Binary file to ingest (PDF, CSV, PNG, JPG, WEBP, TIFF)"
    ),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(
        require_workspace_role(WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER)
    ),
    session: AsyncSession = Depends(get_db),
) -> SourceResponse:
    """Accepts an uploaded file, saves it to object storage, and initiates background ingestion."""
    content = await file.read()
    filename = file.filename or "uploaded_file"

    source = await IngestionService.create_file_source(
        session=session,
        workspace_id=workspace_id,
        filename=filename,
        content=content,
        content_type=file.content_type,
    )
    return SourceResponse.model_validate(source)


@router.post(
    "/url",
    response_model=SourceResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a website URL for asynchronous knowledge ingestion",
)
async def submit_url_source(
    request: UrlSourceCreate,
    workspace_id: Annotated[uuid.UUID, Path(..., description="Target workspace ID")],
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(
        require_workspace_role(WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER)
    ),
    session: AsyncSession = Depends(get_db),
) -> SourceResponse:
    """Validates a public URL against SSRF rules, saves source record, and enqueues ingestion."""
    source = await IngestionService.create_url_source(
        session=session,
        workspace_id=workspace_id,
        url=str(request.url),
        name=request.name,
    )
    return SourceResponse.model_validate(source)


@router.get(
    "",
    response_model=list[SourceResponse],
    status_code=status.HTTP_200_OK,
    summary="List all knowledge sources in a workspace",
)
async def list_workspace_sources(
    workspace_id: Annotated[uuid.UUID, Path(...)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    membership: Membership = Depends(get_workspace_membership),
    session: AsyncSession = Depends(get_db),
) -> list[SourceResponse]:
    """Returns paginated list of sources within the authorized workspace."""
    sources = await IngestionService.list_sources(session, workspace_id, skip=skip, limit=limit)
    return [SourceResponse.model_validate(s) for s in sources]


@router.get(
    "/{source_id}",
    response_model=SourceResponse,
    status_code=status.HTTP_200_OK,
    summary="Get source details and current ingestion status",
)
async def get_source_details(
    workspace_id: Annotated[uuid.UUID, Path(...)],
    source_id: Annotated[uuid.UUID, Path(...)],
    membership: Membership = Depends(get_workspace_membership),
    session: AsyncSession = Depends(get_db),
) -> SourceResponse:
    """Returns source metadata and processing state (PENDING, PROCESSING, COMPLETED, FAILED)."""
    source = await IngestionService.get_source(session, source_id, workspace_id)
    if not source:
        raise NotFoundError("Source not found in workspace.")
    return SourceResponse.model_validate(source)


@router.get(
    "/{source_id}/documents",
    response_model=list[DocumentResponse],
    status_code=status.HTTP_200_OK,
    summary="List documents and versions for a source",
)
async def get_source_documents(
    workspace_id: Annotated[uuid.UUID, Path(...)],
    source_id: Annotated[uuid.UUID, Path(...)],
    membership: Membership = Depends(get_workspace_membership),
    session: AsyncSession = Depends(get_db),
) -> list[DocumentResponse]:
    """Inspects logical documents and versions created for a source."""
    source = await IngestionService.get_source(session, source_id, workspace_id)
    if not source:
        raise NotFoundError("Source not found in workspace.")

    docs = await IngestionService.get_source_documents(session, source_id, workspace_id)
    return [DocumentResponse.model_validate(d) for d in docs]


@router.get(
    "/{source_id}/chunks",
    response_model=list[ChunkResponse],
    status_code=status.HTTP_200_OK,
    summary="Inspect indexed chunks and traceability metadata",
)
async def get_source_chunks(
    workspace_id: Annotated[uuid.UUID, Path(...)],
    source_id: Annotated[uuid.UUID, Path(...)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    membership: Membership = Depends(get_workspace_membership),
    session: AsyncSession = Depends(get_db),
) -> list[ChunkResponse]:
    """Retrieves chunks generated from the source for auditing and verification."""
    source = await IngestionService.get_source(session, source_id, workspace_id)
    if not source:
        raise NotFoundError("Source not found in workspace.")

    chunks = await IngestionService.get_source_chunks(
        session, source_id, workspace_id, skip=skip, limit=limit
    )
    return [ChunkResponse.model_validate(c) for c in chunks]


@router.post(
    "/{source_id}/retry",
    response_model=SourceResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry a failed or pending ingestion pipeline",
)
async def retry_source_ingestion(
    workspace_id: Annotated[uuid.UUID, Path(...)],
    source_id: Annotated[uuid.UUID, Path(...)],
    membership: Membership = Depends(
        require_workspace_role(WorkspaceRole.OWNER, WorkspaceRole.ADMIN)
    ),
    session: AsyncSession = Depends(get_db),
) -> SourceResponse:
    """Re-enqueues a source for background ingestion (restricted to OWNER and ADMIN)."""
    source = await IngestionService.retry_ingestion(session, source_id, workspace_id)
    return SourceResponse.model_validate(source)

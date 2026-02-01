"""
MITRE API routes per assignment.md (Task 2).

API list:
- GET /api/mitre/version  → latest x_mitre_version (Subtask 1 & 4)
- GET /api/mitre/         → retrieve MITRE content as JSON (Subtask 2 & 5)
- PUT /api/mitre/{x_mitre_version}  → replace MITRE for given version (Subtask 3)
- PUT /api/mitre/         → create new MITRE entry (body: version + content) (Subtask 6)
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.db import (
    DuplicateVersionError,
    MitreDBError,
    get_mitre_content,
    get_mitre_version,
    insert_mitre_document,
    put_mitre_document,
)
from app.schemas.mitre import (
    MitreBundle,
    MitreContentResponse,
    MitreMetadata,
    MitrePutResponse,
    MitreVersionResponse,
)

router = APIRouter()


def _make_metadata(x_mitre_version: str, content: MitreBundle) -> MitreMetadata:
    """Build metadata for stored MITRE content."""
    raw = content.model_dump_json()
    size = len(raw.encode("utf-8"))
    return MitreMetadata(
        x_mitre_version=x_mitre_version,
        last_modified=datetime.now(timezone.utc).isoformat(),
        size=size,
        type="application/json",
    )


def _handle_db_error(exc: Exception) -> None:
    """Map DB errors to HTTP 503 (service unavailable) or 500."""
    if isinstance(exc, MitreDBError):
        raise HTTPException(
            status_code=503,
            detail=f"Database unavailable: {exc}",
        ) from exc
    if isinstance(exc, RuntimeError) and "not initialized" in str(exc).lower():
        raise HTTPException(
            status_code=503,
            detail="Database not initialized",
        ) from exc
    raise HTTPException(
        status_code=500,
        detail="An unexpected error occurred",
    ) from exc


@router.get("/version", response_model=MitreVersionResponse)
async def get_mitre_version_endpoint() -> MitreVersionResponse:
    """
    **Subtask 1 & 4:** Return latest x_mitre_version stored in backend.
    """
    try:
        version = await get_mitre_version()
    except (MitreDBError, RuntimeError) as e:
        _handle_db_error(e)
    if version is None:
        raise HTTPException(status_code=404, detail="No MITRE data loaded yet")
    return MitreVersionResponse(x_mitre_version=version)


@router.get("/", response_model=MitreContentResponse)
async def get_mitre_content_endpoint() -> MitreContentResponse:
    """
    **Subtask 2 & 5:** Download/retrieve MITRE entity content as JSON.
    Returns 404 if MITRE data is missing.
    """
    try:
        result = await get_mitre_content()
    except (MitreDBError, RuntimeError) as e:
        _handle_db_error(e)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="MITRE data not found. Load data first via PUT /api/mitre/ or PUT /api/mitre/{x_mitre_version}.",
        )
    content, metadata = result
    return MitreContentResponse(
        x_mitre_version=metadata.x_mitre_version,
        content=content,
        metadata=metadata,
    )


@router.put("/{x_mitre_version}", response_model=MitrePutResponse)
async def put_mitre_by_version(x_mitre_version: str, body: MitreBundle) -> MitrePutResponse:
    """
    **Subtask 3:** Update/replace existing MITRE with new version.
    User provides new MITRE file or content; validated and stored.
    """
    metadata = _make_metadata(x_mitre_version, body)
    try:
        await put_mitre_document(x_mitre_version, body, metadata)
    except (MitreDBError, RuntimeError) as e:
        _handle_db_error(e)
    return MitrePutResponse(
        status="updated",
        x_mitre_version=x_mitre_version,
        message=None,
    )


@router.put("/", response_model=MitrePutResponse, status_code=201)
async def put_mitre(body: MitreBundle) -> MitrePutResponse:
    """
    **Subtask 6:** Create a new MITRE entry (POST-like).
    Accepts MITRE bundle as JSON; x_mitre_version is taken from the bundle's spec_version.
    Returns 409 if that version already exists.
    """
    x_mitre_version = body.spec_version
    metadata = _make_metadata(x_mitre_version, body)
    try:
        await insert_mitre_document(x_mitre_version, body, metadata)
    except DuplicateVersionError as e:
        raise HTTPException(
            status_code=409,
            detail=f"Version already exists: {e}",
        ) from e
    except (MitreDBError, RuntimeError) as e:
        _handle_db_error(e)
    return MitrePutResponse(
        status="created",
        x_mitre_version=x_mitre_version,
        message="MITRE entry created successfully.",
    )

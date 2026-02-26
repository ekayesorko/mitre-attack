from datetime import datetime, timezone
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.db.mongo import DuplicateVersionError, MongoDBRepo, MitreDBError
from app.schemas.db import MitreVersionEntry
from app.dependencies import get_mitre_db, get_mitre_write_service
from app.schemas.mitre import (
    MitreBundle,
    MitreMetadata,
    MitrePutResponse,
    MitreVersionInfo,
    MitreVersionResponse,
    MitreVersionsResponse,
)
from app.services.protocols import MitreWriteService

router = APIRouter()


def _bundle_to_json_source_shape(content: MitreBundle) -> str:
    """Serialize bundle to JSON matching source document shape: no null keys, recursive exclude_none."""
    data = content.model_dump(mode="json", exclude_none=True)
    data["objects"] = [
        o.model_dump(mode="json", exclude_none=True) for o in content.objects
    ]
    return json.dumps(data, indent=2)


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

## extra endpoint
@router.get("/list", response_model=MitreVersionsResponse)
async def list_mitre_versions_endpoint(
    mitre_db: MongoDBRepo = Depends(get_mitre_db),
) -> MitreVersionsResponse:
    """
    List all available MITRE data versions stored in the backend.
    Returns version id and metadata for each; newest first by last_modified.
    """
    try:
        raw: list[MitreVersionEntry] = await mitre_db.list_mitre_versions()
    except (MitreDBError, RuntimeError) as e:
        _handle_db_error(e)
    items = [
        MitreVersionInfo(
            x_mitre_version=v.x_mitre_version,
            metadata=v.metadata,
        )
        for v in raw
    ]
    return MitreVersionsResponse(versions=items)

#subtask 2.1, 2.4
@router.get("/version", response_model=MitreVersionResponse)
async def get_mitre_version_endpoint(
    mitre_db: MongoDBRepo = Depends(get_mitre_db),
) -> MitreVersionResponse:
    """
    return the latest x_mitre_version stored in the backend.
    """
    try:
        version = await mitre_db.get_mitre_version()
    except (MitreDBError, RuntimeError) as e:
        _handle_db_error(e)
    if version is None:
        raise HTTPException(status_code=404, detail="No MITRE data loaded yet")
    return MitreVersionResponse(x_mitre_version=version)


##2.2 2.5
@router.get("/{x_mitre_version}")
async def download_mitre_version_endpoint(
    x_mitre_version: str,
    mitre_db: MongoDBRepo = Depends(get_mitre_db),
) -> Response:
    """
    Return MITRE bundle for the given version as a downloadable JSON file.
    """
    try:
        result = await mitre_db.get_mitre_content_by_version(x_mitre_version)
    except (MitreDBError, RuntimeError) as e:
        _handle_db_error(e)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"MITRE version '{x_mitre_version}' not found.",
        )
    content, _ = result
    body = _bundle_to_json_source_shape(content)
    filename = f"mitre-{x_mitre_version}.json"
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )

##subtask 2.3
@router.put("/{x_mitre_version}", response_model=MitrePutResponse)
async def put_mitre_by_version(
    x_mitre_version: str,
    body: MitreBundle,
    mitre_write_service: MitreWriteService = Depends(get_mitre_write_service),
) -> MitrePutResponse:
    """
    User provides new MITRE file or content; validated and stored.
    """
    metadata = _make_metadata(x_mitre_version, body)
    try:
        await mitre_write_service.put_document(x_mitre_version, body, metadata)
    except (MitreDBError, RuntimeError) as e:
        _handle_db_error(e)
    return MitrePutResponse(
        status="updated",
        x_mitre_version=x_mitre_version,
        message=None,
    )




## subtask 2.6
@router.put("/", response_model=MitrePutResponse, status_code=201)
async def put_mitre(
    body: MitreBundle,
    mitre_write_service: MitreWriteService = Depends(get_mitre_write_service),
) -> MitrePutResponse:
    """
    Accepts MITRE bundle as JSON; x_mitre_version is taken from the bundle's spec_version.
    Returns 409 if that version already exists.
    """
    x_mitre_version = body.objects[0].x_mitre_version
    if x_mitre_version is None:
        raise HTTPException(
            status_code=400,
            detail="MITRE version not found in bundle.",
        )
    metadata = _make_metadata(x_mitre_version, body)
    try:
        await mitre_write_service.insert_document(x_mitre_version, body, metadata)
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



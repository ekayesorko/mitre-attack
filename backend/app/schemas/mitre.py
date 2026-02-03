"""MITRE API request/response schemas. Fixed types only (no Any/dict)."""
from typing import Literal

from pydantic import BaseModel, Field


class MitreVersionResponse(BaseModel):
    """Latest x_mitre_version stored in backend (GET /api/mitre/version)."""
    x_mitre_version: str = Field(..., description="Latest MITRE version identifier")


class MitreMetadata(BaseModel):
    """Stored MITRE document metadata."""
    x_mitre_version: str = Field(..., description="MITRE version identifier")
    last_modified: str = Field(..., description="ISO 8601 last modified")
    size: int = Field(..., description="Content size in bytes")
    type: str = Field(default="application/json", description="MIME type")


class MitreVersionInfo(BaseModel):
    """Single version entry for GET /api/mitre/versions."""
    x_mitre_version: str = Field(..., description="MITRE version identifier")
    metadata: MitreMetadata = Field(..., description="Stored metadata for this version")


class MitreVersionsResponse(BaseModel):
    """List of available MITRE versions (GET /api/mitre/versions)."""
    versions: list[MitreVersionInfo] = Field(
        default_factory=list,
        description="Available versions, newest first",
    )


class MitreExternalReference(BaseModel):
    """External reference for a MITRE/STIX object."""
    source_name: str = Field(..., description="Source identifier")
    url: str | None = Field(default=None, description="Reference URL")
    external_id: str | None = Field(default=None, description="External ID")
    description: str | None = Field(default=None, description="Optional description")


class MitreKillChainPhase(BaseModel):
    """Kill chain phase reference."""
    phase_name: str = Field(..., description="Phase name")
    kill_chain_name: str = Field(..., description="Kill chain name")


class MitreObject(BaseModel):
    """Single MITRE/STIX object in a bundle (attack-pattern, course-of-action, etc.)."""
    type: str = Field(..., description="Object type (e.g. attack-pattern, bundle)")
    id: str = Field(..., description="STIX ID")
    spec_version: str | None = Field(default=None, description="STIX spec version")
    name: str | None = Field(default=None, description="Name")
    description: str | None = Field(default=None, description="Description")
    created: str | None = Field(default=None, description="Creation timestamp")
    modified: str | None = Field(default=None, description="Modification timestamp")
    created_by_ref: str | None = Field(default=None, description="Creator reference")
    revoked: bool | None = Field(default=None, description="Revocation flag")
    external_references: list[MitreExternalReference] | None = Field(default=None)
    x_mitre_version: str | None = Field(default=None, description="MITRE version")
    x_mitre_modified_by_ref: str | None = Field(default=None)
    x_mitre_deprecated: bool | None = Field(default=None)
    x_mitre_domains: list[str] | None = Field(default=None)
    x_mitre_platforms: list[str] | None = Field(default=None)
    x_mitre_contributors: list[str] | None = Field(default=None)
    x_mitre_attack_spec_version: str | None = Field(default=None)
    x_mitre_shortname: str | None = Field(default=None)
    kill_chain_phases: list[MitreKillChainPhase] | None = Field(default=None)
    aliases: list[str] | None = Field(default=None)
    object_marking_refs: list[str] | None = Field(default=None)
    relationship_type: str | None = Field(default=None)
    source_ref: str | None = Field(default=None)
    target_ref: str | None = Field(default=None)
    start_time: str | None = Field(default=None)
    stop_time: str | None = Field(default=None)


class MitreBundle(BaseModel):
    """MITRE ATT&CK STIX bundle (root content)."""
    type: Literal["bundle"] = Field(default="bundle", description="Bundle type")
    id: str | None = Field(default=None, description="Bundle ID")
    spec_version: str = Field(..., description="STIX spec version (e.g. 2.1)")
    objects: list[MitreObject] = Field(default_factory=list, description="STIX objects")


class MitreContentResponse(BaseModel):
    """MITRE entity content (GET /api/mitre/)."""
    x_mitre_version: str = Field(..., description="Version of returned content")
    content: MitreBundle = Field(..., description="MITRE bundle (typed)")
    metadata: MitreMetadata | None = Field(default=None, description="Size, type, last modified")


class MitrePutResponse(BaseModel):
    """Response for PUT /api/mitre/ (create) and PUT /api/mitre/{x_mitre_version} (update)."""
    status: Literal["created", "updated"] = Field(..., description="created for new entry, updated for replace")
    x_mitre_version: str = Field(..., description="Version that was created or updated")
    message: str | None = Field(default=None, description="Optional message")

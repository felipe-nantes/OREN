"""Modelos Pydantic da API do webapp (REF-03 seam 1, extraídos de server.py).

Movidos byte-idênticos; `webapp.server` re-exporta todos (façade), então
`server.ApprovalPayload` etc. continuam válidos para rotas, testes e tools.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ReviewChecklistPayload(BaseModel):
    inspected_3d_contour: bool = False
    compared_2d_reference: bool = False
    reviewed_candidate_against_mr: bool = False
    acknowledged_research_only: bool = False


class ClippingStatePayload(BaseModel):
    enabled: bool = False
    axis: Literal["x", "y", "z"] = "z"
    position_percent: float = 50.0
    inverted: bool = False


class ViewerSavedViewPayload(BaseModel):
    bookmark_id: str = Field(max_length=24, pattern=r"^view-[0-9]{3}$")
    label: str = Field(min_length=1, max_length=96)
    active_view: Literal[
        "padrao", "anterior", "superior", "direita", "focus", "anatomical", "saved"
    ] = "saved"
    active_preset: Literal[
        "custom", "default", "surface", "realistic", "anatomy", "triage", "segments"
    ] = "custom"
    active_anatomical_view: Literal[
        "none", "liver", "segments", "vascular", "candidate"
    ] = "none"
    material_profile: Literal["default", "anatomy", "triage", "segments"] = "default"
    rendering_profile: Literal[
        "scientific_current_v1", "anatomic_realistic_v1"
    ] = "scientific_current_v1"
    selected_role: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9_]+$")
    selection_isolated: bool = False
    camera_position_mm: list[float] = Field(min_length=3, max_length=3)
    camera_target_mm: list[float] = Field(min_length=3, max_length=3)
    reference_sync_enabled: bool = True
    reference_view: Literal["axial", "coronal", "sagittal"] = "axial"
    reference_frame_index: int = Field(default=0, ge=0)
    clipping: ClippingStatePayload = Field(default_factory=ClippingStatePayload)
    visible_roles: list[str] = Field(default_factory=list, max_length=64)
    opacity_by_role: dict[str, float] = Field(default_factory=dict)


class StructureDimensions3DPayload(BaseModel):
    role: str = Field(max_length=64, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=96)
    left_right_mm: float = Field(gt=0, le=5000)
    anterior_posterior_mm: float = Field(gt=0, le=5000)
    superior_inferior_mm: float = Field(gt=0, le=5000)
    method: Literal["axis_aligned_lps_bounding_box"] = "axis_aligned_lps_bounding_box"
    coordinate_system: Literal["LPS"] = "LPS"
    source: Literal["selected_segmentation_mesh"] = "selected_segmentation_mesh"
    approximate: Literal[True] = True


class ViewerStatePayload(BaseModel):
    active_view: Literal[
        "padrao", "anterior", "superior", "direita", "focus", "anatomical", "saved"
    ] = "padrao"
    active_preset: Literal[
        "custom", "default", "surface", "realistic", "anatomy", "triage", "segments"
    ] = "custom"
    active_anatomical_view: Literal[
        "none", "liver", "segments", "vascular", "candidate"
    ] = "none"
    rendering_profile: Literal[
        "scientific_current_v1", "anatomic_realistic_v1"
    ] = "scientific_current_v1"
    rendering_quality_tier: Literal["quality", "stability"] = "quality"
    material_pack_id: Literal["oren-liver-realistic-v1"] | None = None
    material_pack_variant: Literal["desktop_1k", "quest512"] | None = None
    rendering_fallback_reason: Literal[
        "asset_load_error", "performance_budget_exceeded"
    ] | None = None
    wireframe_enabled: bool = False
    reference_sync_enabled: bool = True
    reference_view: Literal["axial", "coronal", "sagittal"] = "axial"
    reference_frame_index: int = Field(default=0, ge=0)
    selected_role: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9_]+$")
    selection_isolated: bool = False
    saved_views: list[ViewerSavedViewPayload] = Field(default_factory=list, max_length=8)
    compared_saved_view_ids: list[str] = Field(default_factory=list, max_length=2)
    clipping: ClippingStatePayload | None = None
    measurements_mm: list[float] = Field(default_factory=list)
    structure_dimensions_3d: list[StructureDimensions3DPayload] = Field(
        default_factory=list, max_length=16
    )
    visible_roles: list[str] = Field(default_factory=list)


class ApprovalPayload(BaseModel):
    status: Literal["approved", "revision_requested"]
    checklist: ReviewChecklistPayload | None = None
    viewer_state: ViewerStatePayload | None = None
    candidate_review_decision: Literal[
        "accepted_as_region_of_interest", "rejected", "needs_correction"
    ] | None = None


class XRSessionRequest(BaseModel):
    role: Literal["patient", "clinician"] = "clinician"
    ttl_minutes: int = Field(default=30, ge=5, le=120)


class XRClientEventPayload(BaseModel):
    event: Literal[
        "viewer_ready", "entry_click", "session_requested", "session_started", "session_failed"
    ]
    mode: Literal["immersive-ar", "immersive-vr", "unknown"] = "unknown"
    error_name: str | None = Field(default=None, max_length=80)
    message: str | None = Field(default=None, max_length=300)

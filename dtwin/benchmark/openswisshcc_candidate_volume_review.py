"""Signed human technical review records for OpenSwissHCC v16 candidate stacks."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from dtwin.benchmark.openswisshcc_candidate_volume_score import (
    REVIEW_SCHEMA,
    validate_candidate_volume_bundle,
)
from dtwin.benchmark.openswisshcc_highdimensional_inference import (
    _atomic_json,
    _canonical_hash,
)
from dtwin.core import PipelineError

REQUIRED_CONFIRMATIONS = (
    "roi_contains_liver",
    "adjacent_slice_continuity",
    "dynamic_t1_alignment",
    "morphology_sequence_correspondence",
    "contrast_adequate",
    "no_visible_phi_or_overlay",
    "fallback_is_usable",
)


def record_candidate_volume_review(
    *,
    bundle_root: Path,
    out_path: Path,
    reviewer: str,
    confirmations: dict[str, bool],
    approved: bool,
    notes: str = "",
    reviewed_at_utc: str | None = None,
) -> dict:
    """Persist an explicit, bundle-bound review; never infer approval from defaults."""

    reviewer = str(reviewer).strip()
    notes = str(notes).strip()
    if not reviewer or len(reviewer) > 120:
        raise PipelineError("Identificacao do revisor v16 ausente ou longa demais.")
    if set(confirmations) != set(REQUIRED_CONFIRMATIONS) or any(type(value) is not bool for value in confirmations.values()):
        raise PipelineError("Confirmacoes da revisao v16 estao incompletas ou invalidas.")
    if approved and not all(confirmations.values()):
        raise PipelineError("Aprovacao v16 exige todas as confirmacoes tecnicas explicitas.")
    if not approved and not notes:
        raise PipelineError("Rejeicao v16 exige observacao objetiva.")
    bundle = validate_candidate_volume_bundle(bundle_root)
    timestamp = reviewed_at_utc or datetime.now(timezone.utc).isoformat()
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise PipelineError("Data UTC da revisao v16 invalida.")
    value = {
        "schema": REVIEW_SCHEMA,
        "status": "approved_for_blind_4b_scoring" if approved else "rejected_technical_review",
        "reviewer": reviewer,
        "reviewed_at_utc": timestamp,
        "confirmations": {key: confirmations[key] for key in REQUIRED_CONFIRMATIONS},
        "notes": notes,
        "cohort_sha256": bundle["cohort_sha256"],
        "gallery_signature": bundle["cohort"]["gallery_signature"],
        "case_count": bundle["case_count"],
        "candidate_stack_count": bundle["candidate_stack_count"],
        "ground_truth_read": False,
        "dataset_lesion_mask_used": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    value["review_signature"] = _canonical_hash(value)
    out_path = Path(out_path)
    if out_path.exists():
        raise PipelineError("Registro de revisao v16 ja existe; sobrescrita recusada.")
    _atomic_json(out_path, value)
    return value


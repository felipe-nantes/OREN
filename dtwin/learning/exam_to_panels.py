"""Generic 'one exam -> liver-enriched multiphase panels' orchestrator.

The Etapa C classifier was trained on liver-enriched ``multiphase_rgb_fusion``
panels (arterial/venous/delayed, 3 panels/case, 9 axial slices each). To run it
on a NEW exam, that exam must be rendered into the SAME panels with the SAME
panel config, otherwise inference is off-distribution.

The low-level renderer already exists and is generic:
``generate_liver_enriched_panel_set_multiphase``
(`dtwin/medgemma_panel_liver_enriched.py`). The per-cohort pilots
(`dtwin/benchmark/lld_mmri_v23_liver_enriched_pilot.py`, etc.) wire it up with
dataset-specific plumbing. This module is the missing generic wrapper: given a
case's phase volumes (already identified) + the coarse liver mask that the
webapp segmentation already produces (`mask_organ.nii.gz`), it builds the case
manifest and calls the renderer with the frozen liver-enriched panel config.

Automatic identification of which DICOM series is arterial/venous/delayed is a
separate, unsolved problem and is explicitly out of scope: the phases are an
input contract here (see docs/123).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dtwin.core import PipelineError
from dtwin.medgemma_client import load_screening_config, model_trace
from dtwin.medgemma_panel_liver_enriched import (
    LIVER_ENRICHED_POLICY,
    generate_liver_enriched_panel_set_multiphase,
)

# The exact liver-enriched panel config used to render the training panels. Using
# any other panel config would shift the input distribution away from what the
# production bundle was trained on.
DEFAULT_LIVER_ENRICHED_PANEL_CONFIG = "configs/medgemma_local_4b_lld_v23_liver_enriched_pilot.yaml"
DEFAULT_MONOPHASE_MEDSIGLIP_PANEL_CONFIG = (
    "configs/medsiglip_monophase_liver_enriched_v1.yaml"
)
# ``LIVER_ENRICHED_POLICY`` is imported from the renderer rather than restated
# here: the value written into the manifest ("coarse_liver_localized_full_fov_
# interleaved_2or3x9_v1") is NOT the config's ``spatial_focus``
# ("liver_enriched_full_fov"), and duplicating it silently broke the contract
# check against correctly rendered panels.

# The renderer keys phases by the SHORT names its channel map uses (art/pv/del),
# while the ingestion pipeline speaks the canonical DICOM-ish role names. The
# training pipelines translate with this exact table
# (`dtwin/benchmark/lld_mmri_v23_full_fov_pilot.ROLE_TO_PHASE`), so it is
# reproduced here to keep inference byte-compatible with how the panels the
# model was trained on were rendered.
CANONICAL_ROLE_TO_PANEL_PHASE = {
    "t1_arterial": "art",
    "t1_venous": "pv",
    "t1_delayed": "del",
}


def anonymous_manifest_case_id(case_id: str) -> str:
    """Anonymous ``anon-*`` id for the panel case manifest.

    The renderer refuses any identifier that is not anonymized
    (`dtwin/medgemma_panel.py`), and the ingestion-side id may be a cohort
    identifier (e.g. a blind benchmark id) that should not be written into panel
    metadata. Already-anonymous ids pass through unchanged; anything else is
    hashed. The derivation is deterministic — unlike stage 1's random UUID — so
    re-running the same case reproduces the same manifest.
    """
    token = str(case_id).strip()
    if token.startswith("anon-"):
        return token
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
    return f"anon-{digest}"


def _to_panel_phase_keys(
    phase_paths: Mapping[str, Path], required_phases: set[str]
) -> dict[str, Path]:
    """Translate canonical role names onto the keys the panel config expects.

    Only renames what the config actually asks for, and leaves keys already in
    the renderer's vocabulary untouched, so a config using either naming works.
    """
    translated: dict[str, Path] = {}
    for name, path in phase_paths.items():
        key = str(name)
        if key not in required_phases and key in CANONICAL_ROLE_TO_PANEL_PHASE:
            key = CANONICAL_ROLE_TO_PANEL_PHASE[key]
        translated[key] = Path(path)
    missing = sorted(required_phases - set(translated))
    if missing:
        raise PipelineError(
            f"Fases exigidas pela config de painel ausentes após tradução: {missing}. "
            f"Recebidas: {sorted(phase_paths)}."
        )
    return translated


@dataclass(frozen=True)
class ExamPanelResult:
    case_id: str
    panel_paths: list[Path]
    panel_count: int
    manifest_path: Path


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build_exam_panels(
    *,
    case_id: str,
    phase_paths: Mapping[str, Path],
    coarse_liver_mask_path: Path,
    output_dir: Path,
    panel_config_path: Path | str = DEFAULT_LIVER_ENRICHED_PANEL_CONFIG,
    visible_phi_confirmed: bool = False,
    renderer_model_trace: Mapping[str, Any] | None = None,
) -> ExamPanelResult:
    """Render one exam's liver-enriched multiphase panels.

    ``phase_paths`` maps phase name -> NIfTI volume (already identified, e.g.
    {'t1_arterial': ..., 't1_venous': ..., 't1_delayed': ...}); the required
    phases come from the panel config's channel map. ``coarse_liver_mask_path``
    is the webapp's ``mask_organ.nii.gz``. Enforces the same technical contract
    the pilots enforce (no lesion mask, no ground truth, mask used only for
    localization, no contour), failing closed otherwise.
    """
    case_id = str(case_id).strip()
    if not case_id:
        raise PipelineError("build_exam_panels exige case_id.")
    manifest_case_id = anonymous_manifest_case_id(case_id)
    config = load_screening_config(Path(panel_config_path))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    case_manifest = output_dir / "case_manifest.json"
    _atomic_write_json(
        case_manifest,
        {
            "case_id": manifest_case_id,
            "policy": "anonymize",
            "regulatory_state": "PESQUISA",
            "modality": "MRI",
        },
    )
    from dtwin.medgemma_panel_multiphase import _resolve_channel_map

    required_phases = set(_resolve_channel_map(config.get("panel", {})).values())
    result = generate_liver_enriched_panel_set_multiphase(
        phase_paths=_to_panel_phase_keys(phase_paths, required_phases),
        coarse_liver_mask_path=Path(coarse_liver_mask_path),
        case_manifest_path=case_manifest,
        screening_config=config,
        output_dir=output_dir,
        model_trace=(
            dict(renderer_model_trace)
            if renderer_model_trace is not None
            else model_trace(config)
        ),
        visible_phi_confirmed=visible_phi_confirmed,
    )
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    if (
        manifest.get("spatial_policy") != LIVER_ENRICHED_POLICY
        or manifest.get("organ_mask_rendered") is not False
        or manifest.get("lesion_mask_used") is not False
        or manifest.get("ground_truth_used") is not False
        or manifest.get("crop_to_liver") is not False
        or manifest.get("contour_rendered") is not False
        or result.panel_count not in {2, 3}
    ):
        raise PipelineError("Painel liver-enriched do exame violou o contrato técnico.")
    return ExamPanelResult(
        case_id=case_id,
        panel_paths=[Path(p) for p in result.panel_paths],
        panel_count=int(result.panel_count),
        manifest_path=Path(result.manifest_path),
    )


def build_monophase_exam_panels(
    *,
    case_id: str,
    volume_path: Path,
    coarse_liver_mask_path: Path,
    output_dir: Path,
    panel_config_path: Path | str = DEFAULT_MONOPHASE_MEDSIGLIP_PANEL_CONFIG,
    visible_phi_confirmed: bool = False,
) -> ExamPanelResult:
    """Render one real series as grayscale RGB for the frozen MedSigLIP encoder.

    The same source voxels populate R/G/B; this is an encoder compatibility
    operation, not phase synthesis.  The manifest must explicitly prove that no
    dynamic enhancement information or lesion/ground-truth signal was added.
    """

    result = build_exam_panels(
        case_id=case_id,
        phase_paths={"mono": Path(volume_path)},
        coarse_liver_mask_path=coarse_liver_mask_path,
        output_dir=output_dir,
        panel_config_path=panel_config_path,
        visible_phi_confirmed=visible_phi_confirmed,
        renderer_model_trace={
            "model_family": "MedSigLIP",
            "model_version": "google/medsiglip-448",
            "execution_role": "frozen_image_encoder_input_representation",
        },
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    channel_map = manifest.get("fusion_channel_map")
    if (
        manifest.get("input_type")
        != "mri_single_phase_replicated_grayscale_full_fov_liver_enriched"
        or manifest.get("single_phase_replicated_across_rgb") is not True
        or manifest.get("dynamic_enhancement_information_present") is not False
        or not isinstance(channel_map, dict)
        or set(channel_map.values()) != {"mono"}
        or manifest.get("lesion_mask_used") is not False
        or manifest.get("ground_truth_used") is not False
    ):
        raise PipelineError("Painel monofásico MedSigLIP violou o contrato técnico.")
    return result


__all__ = [
    "DEFAULT_LIVER_ENRICHED_PANEL_CONFIG",
    "DEFAULT_MONOPHASE_MEDSIGLIP_PANEL_CONFIG",
    "ExamPanelResult",
    "anonymous_manifest_case_id",
    "build_exam_panels",
    "build_monophase_exam_panels",
]

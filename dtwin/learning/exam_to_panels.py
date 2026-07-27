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

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from dtwin.core import PipelineError
from dtwin.medgemma_client import load_screening_config, model_trace
from dtwin.medgemma_panel_liver_enriched import generate_liver_enriched_panel_set_multiphase

# The exact liver-enriched panel config used to render the training panels. Using
# any other panel config would shift the input distribution away from what the
# production bundle was trained on.
DEFAULT_LIVER_ENRICHED_PANEL_CONFIG = "configs/medgemma_local_4b_lld_v23_liver_enriched_pilot.yaml"
LIVER_ENRICHED_POLICY = "liver_enriched_full_fov"


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
    config = load_screening_config(Path(panel_config_path))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    case_manifest = output_dir / "case_manifest.json"
    _atomic_write_json(
        case_manifest,
        {
            "case_id": case_id,
            "policy": "anonymize",
            "regulatory_state": "PESQUISA",
            "modality": "MRI",
        },
    )
    result = generate_liver_enriched_panel_set_multiphase(
        phase_paths={str(name): Path(path) for name, path in phase_paths.items()},
        coarse_liver_mask_path=Path(coarse_liver_mask_path),
        case_manifest_path=case_manifest,
        screening_config=config,
        output_dir=output_dir,
        model_trace=model_trace(config),
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

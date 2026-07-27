"""Atomic cohort builder for reviewed OpenSwissHCC volumetric candidates."""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Callable

from dtwin.benchmark.openswisshcc_alignment import _publish_directory
from dtwin.benchmark.openswisshcc_review import ready_case_ids, verify_panel_review
from dtwin.benchmark.openswisshcc_volumetric import render_volumetric_candidate
from dtwin.core import PipelineError


COHORT_SCHEMA = "argos-openswisshcc-volumetric-candidate-cohort-v1"


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_volumetric_candidate_cohort(
    *, input_root: Path, alignment_root: Path, source_panel_root: Path,
    source_review_path: Path, output_root: Path, multiphase_config: Path,
    fallback_config: Path, high_contrast_fallback_config: Path,
    source_high_contrast_config: Path, profile_path: Path,
    expected_case_count: int = 88,
    renderer: Callable[..., dict[str, Any]] = render_volumetric_candidate,
) -> dict[str, Any]:
    """Build all cases in staging and publish only a complete validated cohort."""
    source_panel_root = Path(source_panel_root).resolve()
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Destino volumetrico ja existe; nao sera sobrescrito.")
    case_ids = ready_case_ids(source_panel_root)
    if len(case_ids) != int(expected_case_count):
        raise PipelineError(
            f"Coorte fonte possui {len(case_ids)} casos; esperado {expected_case_count}."
        )
    review = verify_panel_review(
        review_path=source_review_path,
        panel_root=source_panel_root,
        required_case_ids=case_ids,
    )
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._volset_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        cases: list[dict[str, Any]] = []
        for case_id in case_ids:
            result = renderer(
                case_id=case_id,
                input_root=input_root,
                alignment_root=alignment_root,
                source_panel_root=source_panel_root,
                output_root=staging,
                multiphase_config=multiphase_config,
                fallback_config=fallback_config,
                high_contrast_fallback_config=high_contrast_fallback_config,
                source_high_contrast_config=source_high_contrast_config,
                profile_path=profile_path,
            )
            coverage = result.get("coverage")
            if (
                result.get("case_id") != case_id
                or result.get("panel_strategy") != "volumetric_blocks"
                or not isinstance(coverage, dict)
                or coverage.get("gate_passed") is not True
                or coverage.get("covered_liver_voxels") != coverage.get("total_liver_voxels")
                or not isinstance(result.get("panel_image_count"), int)
                or result["panel_image_count"] < 1
            ):
                raise PipelineError(f"Candidato volumetrico invalido no caso {case_id}.")
            cases.append(
                {
                    "case_id": case_id,
                    "candidate_kind": result.get("candidate_kind"),
                    "candidate_signature": result.get("candidate_signature"),
                    "panel_image_count": result["panel_image_count"],
                    "panel_set_sha256": result.get("panel_set_sha256"),
                    "total_liver_voxels": coverage.get("total_liver_voxels"),
                    "covered_liver_voxels": coverage.get("covered_liver_voxels"),
                }
            )
        if len([item for item in staging.iterdir() if item.is_dir()]) != expected_case_count:
            raise PipelineError("Staging volumetrico nao contem exatamente a coorte esperada.")
        manifest = {
            "schema": COHORT_SCHEMA,
            "case_count": len(cases),
            "panel_image_count": sum(item["panel_image_count"] for item in cases),
            "max_panels_per_case": max(item["panel_image_count"] for item in cases),
            "candidate_kind_counts": {
                kind: sum(item["candidate_kind"] == kind for item in cases)
                for kind in sorted({str(item["candidate_kind"]) for item in cases})
            },
            "source_review_signature": review["review_signature"],
            "cases": cases,
            "cohort_signature": _canonical_sha256(cases),
            "research_only": True,
            "clinical_use_allowed": False,
            "ground_truth_read": False,
            "inference_executed": False,
            "requires_new_human_review": True,
        }
        (staging / "cohort_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _publish_directory(staging, output_root)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


"""Atomic chunk execution support for the blind OpenSwissHCC v10 localizer run."""
from __future__ import annotations

import json
import os
import shutil
import statistics
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_lesion_localizer import CASE_SCHEMA, RUN_SCHEMA, TASK
from dtwin.benchmark.openswisshcc_multisequence_chunks import verify_chunk_plan
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

MERGED_RUN_SCHEMA = "argos-openswisshcc-lesion-localizer-merged-run-v1"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON do localizador v10 invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("JSON do localizador v10 deve ser objeto.")
    return value


def load_verified_selection_plan(plan_path: Path, expected_case_count: int = 87) -> dict[str, Any]:
    """Verify the signed blind plan without consulting any ground-truth labels."""
    raw = _load_json(plan_path)
    return verify_chunk_plan(
        plan_path=plan_path,
        experiment_signature=str(raw.get("experiment_signature", "")),
        review_signature=str(raw.get("review_signature", "")),
        expected_case_count=expected_case_count,
    )


def planned_chunk(plan: dict[str, Any], chunk_number: int) -> list[str]:
    chunks = plan.get("chunks")
    if not isinstance(chunks, list) or not 1 <= int(chunk_number) <= len(chunks):
        raise PipelineError("Numero de bloco do localizador v10 invalido.")
    spec = chunks[int(chunk_number) - 1]
    if spec.get("chunk_number") != int(chunk_number):
        raise PipelineError("Ordem dos blocos do localizador v10 invalida.")
    case_ids = spec.get("case_ids")
    if not isinstance(case_ids, list) or not case_ids:
        raise PipelineError("Bloco do localizador v10 vazio ou invalido.")
    return [str(case_id) for case_id in case_ids]


def _copy_tree_with_hardlinks(source: Path, destination: Path) -> None:
    """Copy a validated case tree, preferring hardlinks to avoid duplicate masks."""
    if source.is_symlink() or not source.is_dir():
        raise PipelineError("Diretorio de caso do localizador v10 invalido.")
    destination.mkdir()
    for item in source.iterdir():
        target = destination / item.name
        if item.is_symlink():
            raise PipelineError("Links simbolicos nao sao permitidos nos blocos v10.")
        if item.is_dir():
            _copy_tree_with_hardlinks(item, target)
        elif item.is_file():
            try:
                os.link(item, target)
            except OSError:
                shutil.copy2(item, target)
        else:
            raise PipelineError("Entrada especial nao permitida no bloco v10.")


def _validate_case(case_dir: Path, case_id: str, summary: dict[str, Any]) -> dict[str, Any]:
    manifest = _load_json(case_dir / "localizer_manifest.json")
    raw_mask = case_dir / "raw_model_output" / "liver_lesions.nii.gz"
    filtered_mask = case_dir / "liver_lesion_candidates_in_liver.nii.gz"
    features = manifest.get("features")
    if (
        manifest.get("schema") != CASE_SCHEMA
        or manifest.get("case_id") != case_id
        or manifest.get("status") != "candidate_scores_only_no_decision"
        or manifest.get("task") != TASK
        or manifest.get("task") != summary.get("task")
        or manifest.get("model_version") != summary.get("model_version")
        or manifest.get("within_90_seconds") is not True
        or manifest.get("ground_truth_lesion_mask_used") is not False
        or manifest.get("ground_truth_read") is not False
        or manifest.get("metrics_calculated") is not False
        or manifest.get("final_decision") is not None
        or manifest.get("research_only") is not True
        or manifest.get("clinical_use_allowed") is not False
        or manifest.get("requires_human_review") is not True
        or not isinstance(features, dict)
    ):
        raise PipelineError(f"Manifesto de caso do localizador v10 invalido: {case_id}.")
    if not raw_mask.is_file() or manifest.get("raw_candidate_mask_sha256") != _sha256(raw_mask):
        raise PipelineError(f"Mascara bruta ausente ou adulterada no caso {case_id}.")
    if not filtered_mask.is_file() or manifest.get("filtered_candidate_mask_sha256") != _sha256(filtered_mask):
        raise PipelineError(f"Mascara filtrada ausente ou adulterada no caso {case_id}.")
    if not isinstance(features.get("total_candidate_volume_mm3"), (int, float)):
        raise PipelineError(f"Volume candidato ausente no caso {case_id}.")
    return manifest


def merge_localizer_chunks(
    *,
    chunks_root: Path,
    selection_plan_path: Path,
    output_root: Path,
    expected_case_count: int = 87,
) -> dict[str, Any]:
    """Validate every planned chunk and atomically publish one authoritative run."""
    chunks_root = Path(chunks_root).resolve()
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Run consolidado do localizador v10 ja existe.")
    plan = load_verified_selection_plan(selection_plan_path, expected_case_count)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._v10localizer_merge_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    manifests: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_wall_seconds = 0.0
    common: dict[str, Any] | None = None
    try:
        for chunk in plan["chunks"]:
            chunk_number = int(chunk["chunk_number"])
            planned = planned_chunk(plan, chunk_number)
            root = chunks_root / f"chunk_{chunk_number:03d}"
            summary = _load_json(root / "summary.json")
            if (
                summary.get("schema") != RUN_SCHEMA
                or summary.get("status") != "complete_scores_only_no_decision"
                or summary.get("case_count") != len(planned)
                or summary.get("case_ids") != planned
                or summary.get("selection_signature") != plan["plan_signature"]
                or summary.get("ground_truth_lesion_mask_used") is not False
                or summary.get("ground_truth_read") is not False
                or summary.get("metrics_calculated") is not False
                or summary.get("final_decision") is not None
                or summary.get("all_cases_within_90_seconds") is not True
                or summary.get("research_only") is not True
                or summary.get("clinical_use_allowed") is not False
            ):
                raise PipelineError(f"Resumo do bloco {chunk_number:03d} invalido.")
            visible = sorted(path.name for path in root.iterdir() if path.is_dir() and not path.name.startswith("."))
            if visible != sorted(planned):
                raise PipelineError(f"Bloco {chunk_number:03d} nao contem exatamente os casos planejados.")
            signature = {
                "task": summary.get("task"),
                "model_version": summary.get("model_version"),
                "input_manifest_sha256": summary.get("input_manifest_sha256"),
            }
            if common is None:
                common = signature
            elif signature != common:
                raise PipelineError("Versao do modelo ou manifesto divergiu entre blocos v10.")
            for case_id in planned:
                if case_id in seen:
                    raise PipelineError(f"Caso duplicado entre blocos v10: {case_id}.")
                case_dir = root / case_id
                manifest = _validate_case(case_dir, case_id, summary)
                _copy_tree_with_hardlinks(case_dir, staging / case_id)
                manifests.append(manifest)
                seen.add(case_id)
            total_wall_seconds += float(summary.get("total_wall_seconds", 0.0))

        expected = [case_id for chunk in plan["chunks"] for case_id in chunk["case_ids"]]
        if list(seen) == [] or seen != set(expected) or len(manifests) != expected_case_count:
            raise PipelineError("Consolidacao dos blocos v10 esta incompleta.")
        elapsed = [float(manifest["elapsed_seconds"]) for manifest in manifests]
        assert common is not None
        summary = {
            "schema": MERGED_RUN_SCHEMA,
            "source_run_schema": RUN_SCHEMA,
            "status": "complete_scores_only_no_decision",
            "case_count": len(manifests),
            "candidate_positive_count": sum(bool(m["features"]["candidate_present"]) for m in manifests),
            "candidate_negative_count": sum(not bool(m["features"]["candidate_present"]) for m in manifests),
            "case_ids": expected,
            "chunk_count": len(plan["chunks"]),
            "task": common["task"],
            "model_version": common["model_version"],
            "input_manifest_sha256": common["input_manifest_sha256"],
            "selection_signature": plan["plan_signature"],
            "selection_plan_sha256": _sha256(Path(selection_plan_path).resolve()),
            "mean_case_seconds": statistics.fmean(elapsed),
            "max_case_seconds": max(elapsed),
            "all_cases_within_90_seconds": all(m["within_90_seconds"] for m in manifests),
            "sum_chunk_wall_seconds": total_wall_seconds,
            "ground_truth_lesion_mask_used": False,
            "ground_truth_read": False,
            "metrics_calculated": False,
            "final_decision": None,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        _write_json_atomic(staging / "summary.json", summary)
        _publish_directory(staging, output_root)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

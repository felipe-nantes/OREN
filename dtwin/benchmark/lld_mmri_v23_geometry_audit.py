"""Label-blind readability and geometry audit for the frozen LLD-MMRI v23 cohort."""
from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.lld_mmri_v23_download import (
    PHASE_SUFFIXES,
    validate_lld_mmri_v23_download,
)
from dtwin.benchmark.lld_mmri_v23_preparation import (
    _geometry,
    _read_valid_nifti,
    _same_geometry,
)
from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic


CASE_SCHEMA = "argos-lld-mmri-v23-geometry-audit-case-v1"
AUDIT_SCHEMA = "argos-lld-mmri-v23-geometry-audit-v1"
DYNAMIC_T1_ROLES = ("t1_native", "t1_arterial", "t1_venous", "t1_delayed")


def audit_lld_mmri_v23_geometry(
    *, protocol_root: Path, download_root: Path, output_root: Path
) -> dict[str, Any]:
    """Read all selected images and freeze the pre-segmentation geometry gate."""

    download_root = Path(download_root).resolve()
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Auditoria geometrica LLD-MMRI existente; sobrescrita recusada.")
    manifest = validate_lld_mmri_v23_download(
        protocol_root=protocol_root, destination=download_root
    )
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._lldv23audit_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    try:
        for case in manifest["cases"]:
            case_id = str(case["case_id"])
            case_started = time.perf_counter()
            images = {}
            image_records = []
            error = None
            try:
                for role in PHASE_SUFFIXES:
                    item = case["images"][role]
                    path = (download_root / str(item["relative_path"])).resolve()
                    image = _read_valid_nifti(path, role=role)
                    images[role] = image
                    image_records.append(
                        {
                            "role": role,
                            "bytes": path.stat().st_size,
                            "sha256": _sha256(path),
                            "pixel_id": image.GetPixelIDTypeAsString(),
                            "geometry": _geometry(image),
                        }
                    )
                reference = images["t1_venous"]
                mismatch_roles = [
                    role
                    for role in DYNAMIC_T1_ROLES
                    if not _same_geometry(reference, images[role])
                ]
                dynamic_gate = not mismatch_roles
                if not dynamic_gate:
                    error = "dynamic_t1_geometry_mismatch"
            except PipelineError as exc:
                mismatch_roles = []
                dynamic_gate = False
                error = "unreadable_or_invalid_nifti"
                failures.append({"case_id": case_id, "reason": str(exc)})
            if error == "dynamic_t1_geometry_mismatch":
                failures.append({"case_id": case_id, "reason": error})
            base = {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "status": "passed" if error is None else "failed",
                "image_count": len(image_records),
                "images": image_records,
                "dynamic_t1_reference": "t1_venous",
                "dynamic_t1_same_physical_grid": dynamic_gate,
                "dynamic_t1_mismatch_roles": mismatch_roles,
                "failure_code": error,
                "elapsed_seconds": time.perf_counter() - case_started,
                "ground_truth_read": False,
                "lesion_masks_read": 0,
                "research_only": True,
                "clinical_use_allowed": False,
            }
            row = dict(base)
            row["case_audit_signature"] = _canonical_sha(base)
            rows.append(row)

        cases_path = staging / "cases.jsonl"
        cases_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        passed = not failures and all(
            row["image_count"] == len(PHASE_SUFFIXES) for row in rows
        )
        base = {
            "schema": AUDIT_SCHEMA,
            "status": "passed_ready_for_segmentation" if passed else "failed_do_not_segment",
            "technical_gate_passed": passed,
            "case_count": len(rows),
            "image_count": sum(row["image_count"] for row in rows),
            "case_ids": [row["case_id"] for row in rows],
            "failed_case_count": len(failures),
            "failed_cases": failures,
            "cases_sha256": _sha256(cases_path),
            "protocol_signature": manifest["protocol_signature"],
            "download_manifest_signature": manifest["manifest_signature"],
            "dynamic_t1_geometry_gate": "exact_same_physical_grid_or_abort",
            "elapsed_seconds": time.perf_counter() - started,
            "ground_truth_read": False,
            "labels_read": False,
            "lesion_masks_read": 0,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        summary = dict(base)
        summary["audit_signature"] = _canonical_sha(base)
        _write_json_atomic(staging / "summary.json", summary)
        _publish_directory(staging, output_root)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_lld_mmri_v23_geometry_audit(
    *, protocol_root: Path, download_root: Path, audit_root: Path
) -> dict[str, Any]:
    """Fail closed unless the signed all-case audit still matches the download."""

    manifest = validate_lld_mmri_v23_download(
        protocol_root=protocol_root, destination=download_root
    )
    audit_root = Path(audit_root).resolve()
    cases_path = audit_root / "cases.jsonl"
    try:
        summary = json.loads((audit_root / "summary.json").read_text(encoding="utf-8"))
        rows = [
            json.loads(line)
            for line in cases_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Auditoria geometrica LLD-MMRI ausente ou invalida.") from exc
    unsigned = dict(summary) if isinstance(summary, dict) else {}
    signature = unsigned.pop("audit_signature", None)
    if (
        summary.get("schema") != AUDIT_SCHEMA
        or summary.get("status") != "passed_ready_for_segmentation"
        or summary.get("technical_gate_passed") is not True
        or signature != _canonical_sha(unsigned)
        or summary.get("cases_sha256") != _sha256(cases_path)
        or summary.get("protocol_signature") != manifest["protocol_signature"]
        or summary.get("download_manifest_signature") != manifest["manifest_signature"]
        or summary.get("case_count") != manifest["case_count"]
        or summary.get("image_count") != manifest["image_count"]
        or summary.get("case_ids") != [case["case_id"] for case in manifest["cases"]]
        or summary.get("failed_case_count") != 0
        or summary.get("ground_truth_read") is not False
        or summary.get("labels_read") is not False
        or summary.get("lesion_masks_read") != 0
        or len(rows) != manifest["case_count"]
    ):
        raise PipelineError("Gate geometrico LLD-MMRI ausente, falho ou adulterado.")
    for expected, row in zip(manifest["cases"], rows, strict=True):
        unsigned_row = dict(row) if isinstance(row, dict) else {}
        row_signature = unsigned_row.pop("case_audit_signature", None)
        audited_hashes = {
            str(item.get("role")): item.get("sha256") for item in row.get("images", [])
        }
        expected_hashes = {
            role: item["sha256"] for role, item in expected["images"].items()
        }
        if (
            row.get("schema") != CASE_SCHEMA
            or row.get("case_id") != expected["case_id"]
            or row.get("status") != "passed"
            or row_signature != _canonical_sha(unsigned_row)
            or row.get("image_count") != len(PHASE_SUFFIXES)
            or row.get("dynamic_t1_same_physical_grid") is not True
            or row.get("dynamic_t1_mismatch_roles") != []
            or row.get("failure_code") is not None
            or audited_hashes != expected_hashes
            or row.get("ground_truth_read") is not False
            or row.get("lesion_masks_read") != 0
        ):
            raise PipelineError("Registro da auditoria geometrica LLD-MMRI divergiu.")
    return summary


__all__ = [
    "AUDIT_SCHEMA",
    "CASE_SCHEMA",
    "audit_lld_mmri_v23_geometry",
    "verify_lld_mmri_v23_geometry_audit",
]

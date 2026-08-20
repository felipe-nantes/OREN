"""Reusable blind geometry scan for native OpenSwissHCC ADC/DWI/T2 volumes."""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_multisequence_audit import (
    TRACE_RE,
    _coverage,
    _image_record,
    _physical_mask_points,
    _rows,
)
from dtwin.core import PipelineError


def _geometry_matches(left: sitk.Image, right: sitk.Image) -> bool:
    return bool(
        left.GetSize() == right.GetSize()
        and np.allclose(left.GetSpacing(), right.GetSpacing(), rtol=0.0, atol=1e-6)
        and np.allclose(left.GetOrigin(), right.GetOrigin(), rtol=0.0, atol=1e-5)
        and np.allclose(left.GetDirection(), right.GetDirection(), rtol=0.0, atol=1e-6)
    )


def scan_multisequence_geometry(
    *, input_root: Path, manifest_path: Path, output_path: Path,
    expected_case_count: int = 88,
) -> dict[str, Any]:
    input_root = Path(input_root).resolve()
    rows = _rows(Path(manifest_path).resolve())
    if len(rows) != expected_case_count:
        raise PipelineError("Quantidade inesperada de casos multissequencia.")
    cases = []
    for row in sorted(rows, key=lambda value: str(value.get("case_id", ""))):
        case_id = str(row.get("case_id", ""))
        if (
            not case_id.startswith("anon-")
            or row.get("schema") != "argos-public-liver-mri-input-v1"
            or row.get("research_only") is not True
            or row.get("clinical_use_allowed") is not False
        ):
            raise PipelineError("Manifesto multissequencia invalido ou nao anonimizado.")
        files = {str(item["role"]): item for item in row.get("files", [])}
        required = {"dwi_adc", "t1_venous", "liver_mask_venous"}
        if not required.issubset(files):
            raise PipelineError(f"Sequencias essenciais ausentes: {case_id}.")
        trace_roles = sorted(
            (role for role in files if TRACE_RE.fullmatch(role)),
            key=lambda role: int(TRACE_RE.fullmatch(role).group(1)),
        )
        if len(trace_roles) < 3:
            raise PipelineError(f"Menos de tres TRACE em {case_id}.")
        t2_role = "t2_blade" if "t2_blade" in files else "t2_haste" if "t2_haste" in files else None
        if not t2_role:
            raise PipelineError(f"T2 ausente em {case_id}.")

        def resolve(role: str, *, files=files, case_id=case_id) -> Path:
            item = files[role]
            path = input_root / str(item["relative_path"])
            if (
                not path.is_file()
                or path.stat().st_size != int(item["bytes"])
                or _sha256(path) != str(item["sha256"])
            ):
                raise PipelineError(f"Hash/bytes divergentes: {case_id}/{role}.")
            return path

        venous = sitk.ReadImage(str(resolve("t1_venous")))
        mask = sitk.ReadImage(str(resolve("liver_mask_venous")))
        if not _geometry_matches(venous, mask):
            raise PipelineError(f"Mascara venosa realmente diverge do T1 em {case_id}.")
        points = _physical_mask_points(mask)
        selected_roles = ["dwi_adc", *trace_roles, t2_role]
        sequences = {}
        trace_medians = []
        for role in selected_roles:
            record = _image_record(resolve(role), venous.GetDirection())
            image = record.pop("image")
            record["liver_physical_fov"] = _coverage(points, image)
            sequences[role] = record
            match = TRACE_RE.fullmatch(role)
            if match:
                trace_medians.append((int(match.group(1)), record["nonzero_median"]))
        nonincreasing = [
            float(right[1]) <= float(left[1])
            for left, right in zip(trace_medians, trace_medians[1:])
        ]
        cases.append({
            "case_id": case_id,
            "trace_roles": trace_roles,
            "trace_first_role": trace_roles[0],
            "trace_middle_role": trace_roles[len(trace_roles) // 2],
            "trace_last_role": trace_roles[-1],
            "trace_role_semantics": "ordered_only_b_values_not_explicit_in_public_sidecar",
            "t2_role": t2_role,
            "trace_adjacent_nonincreasing_fraction": (
                sum(nonincreasing) / len(nonincreasing) if nonincreasing else 1.0
            ),
            "sequences": sequences,
            "ground_truth_read": False,
        })
    if len({case["case_id"] for case in cases}) != expected_case_count:
        raise PipelineError("Casos duplicados no scan multissequencia.")
    summary_roles = {
        "adc": lambda case: "dwi_adc",
        "trace_first": lambda case: case["trace_first_role"],
        "trace_middle": lambda case: case["trace_middle_role"],
        "trace_last": lambda case: case["trace_last_role"],
        "t2": lambda case: case["t2_role"],
    }
    coverage = {}
    orientation = {}
    for name, resolver in summary_roles.items():
        cover_values = []
        cosine_values = []
        for case in cases:
            record = case["sequences"][resolver(case)]
            cover_values.append(float(record["liver_physical_fov"]["inside_fraction"]))
            cosine_values.append(float(record["same_axis_min_abs_cosine"]))
        coverage[name] = {
            "minimum": min(cover_values),
            "p05": float(np.percentile(cover_values, 5)),
            "median": statistics.median(cover_values),
            "cases_below_0_95": sum(value < 0.95 for value in cover_values),
        }
        orientation[name] = {
            "minimum": min(cosine_values),
            "median": statistics.median(cosine_values),
            "cases_below_0_99": sum(value < 0.99 for value in cosine_values),
        }
    result = {
        "schema": "argos-openswisshcc-multisequence-geometry-v1",
        "status": "scan_complete_no_inference",
        "case_count": len(cases),
        "availability": {
            "adc": len(cases),
            "trace_at_least_3": sum(len(case["trace_roles"]) >= 3 for case in cases),
            "trace_10_runs": sum(len(case["trace_roles"]) == 10 for case in cases),
            "t2_blade": sum(case["t2_role"] == "t2_blade" for case in cases),
            "t2_haste_fallback": sum(case["t2_role"] == "t2_haste" for case in cases),
        },
        "physical_liver_fov": coverage,
        "orientation": orientation,
        "trace_order": {
            "fully_nonincreasing_cases": sum(
                case["trace_adjacent_nonincreasing_fraction"] == 1.0 for case in cases
            ),
            "median_nonincreasing_fraction": statistics.median(
                case["trace_adjacent_nonincreasing_fraction"] for case in cases
            ),
            "b_values_explicitly_known": False,
        },
        "cases": cases,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result

"""Blind geometry/content audit for OpenSwissHCC ADC, ordered DWI TRACE and T2."""
from __future__ import annotations

import json
import math
import re
import statistics
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.core import PipelineError


TRACE_RE = re.compile(r"^dwi_trace_run_(\d+)$")


def _rows(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Manifesto de inputs invalido: {exc}") from exc


def _physical_mask_points(mask: sitk.Image, limit: int = 10_000) -> np.ndarray:
    zyx = np.argwhere(sitk.GetArrayViewFromImage(mask) > 0)
    if not len(zyx):
        raise PipelineError("Mascara venosa vazia na auditoria multissequencia.")
    step = max(1, math.ceil(len(zyx) / limit))
    xyz = zyx[::step, ::-1].astype(np.float64)
    direction = np.asarray(mask.GetDirection(), dtype=np.float64).reshape(3, 3)
    spacing = np.asarray(mask.GetSpacing(), dtype=np.float64)
    origin = np.asarray(mask.GetOrigin(), dtype=np.float64)
    return origin + (direction @ (xyz * spacing).T).T


def _coverage(points: np.ndarray, image: sitk.Image) -> dict[str, Any]:
    direction = np.asarray(image.GetDirection(), dtype=np.float64).reshape(3, 3)
    spacing = np.asarray(image.GetSpacing(), dtype=np.float64)
    origin = np.asarray(image.GetOrigin(), dtype=np.float64)
    continuous = ((direction.T @ (points - origin).T).T) / spacing
    size = np.asarray(image.GetSize(), dtype=np.float64)
    inside = np.all((continuous >= -0.5) & (continuous <= size - 0.5), axis=1)
    return {
        "sampled_liver_points": int(len(points)),
        "inside_point_count": int(inside.sum()),
        "inside_fraction": float(inside.mean()),
        "mapped_index_min_xyz": continuous.min(axis=0).tolist(),
        "mapped_index_max_xyz": continuous.max(axis=0).tolist(),
    }


def _image_record(path: Path, reference_direction: tuple[float, ...]) -> dict[str, Any]:
    image = sitk.ReadImage(str(path))
    array = sitk.GetArrayViewFromImage(image)
    finite = np.asarray(array[np.isfinite(array)], dtype=np.float32)
    nonzero = finite[finite != 0]
    values = nonzero if len(nonzero) else finite
    if not len(values):
        raise PipelineError(f"Volume sem intensidades finitas: {path.name}.")
    ref = np.asarray(reference_direction, dtype=np.float64).reshape(3, 3)
    current = np.asarray(image.GetDirection(), dtype=np.float64).reshape(3, 3)
    axis_cosines = [abs(float(np.dot(ref[:, index], current[:, index]))) for index in range(3)]
    return {
        "size_xyz": list(image.GetSize()),
        "spacing_xyz": list(image.GetSpacing()),
        "origin_xyz": list(image.GetOrigin()),
        "direction": list(image.GetDirection()),
        "same_axis_min_abs_cosine": min(axis_cosines),
        "nonzero_voxels": int(len(nonzero)),
        "nonzero_mean": float(np.mean(values)),
        "nonzero_median": float(np.median(values)),
        "nonzero_p95": float(np.percentile(values, 95)),
        "image": image,
    }


def audit_multisequence_inputs(
    *, input_root: Path, manifest_path: Path, output_path: Path,
    expected_case_count: int = 88,
) -> dict[str, Any]:
    input_root = Path(input_root).resolve()
    rows = _rows(Path(manifest_path).resolve())
    if len(rows) != expected_case_count:
        raise PipelineError("Quantidade inesperada de casos na auditoria multissequencia.")
    case_ids = [str(row.get("case_id", "")) for row in rows]
    if len(case_ids) != len(set(case_ids)) or any(not value.startswith("anon-") for value in case_ids):
        raise PipelineError("Case IDs invalidos na auditoria multissequencia.")
    cases = []
    for row in sorted(rows, key=lambda value: str(value["case_id"])):
        case_id = str(row["case_id"])
        if row.get("schema") != "argos-public-liver-mri-input-v1" or row.get("research_only") is not True:
            raise PipelineError("Manifesto de input nao esta em modo pesquisa.")
        files = {str(item["role"]): item for item in row.get("files", [])}
        required = {"dwi_adc", "dwi_trace_run_01", "dwi_trace_run_02", "dwi_trace_run_03",
                    "t1_venous", "liver_mask_venous"}
        if not required.issubset(files):
            raise PipelineError(f"Sequencias obrigatorias ausentes: {case_id}.")
        t2_role = "t2_blade" if "t2_blade" in files else "t2_haste" if "t2_haste" in files else None
        if t2_role is None:
            raise PipelineError(f"Caso sem T2 utilizavel: {case_id}.")
        trace_roles = sorted(
            (role for role in files if TRACE_RE.fullmatch(role)),
            key=lambda role: int(TRACE_RE.fullmatch(role).group(1)),
        )
        last_trace_role = trace_roles[-1]

        def resolve(role: str) -> Path:
            item = files[role]
            path = input_root / str(item["relative_path"])
            if not path.is_file() or path.stat().st_size != int(item["bytes"]) or _sha256(path) != item["sha256"]:
                raise PipelineError(f"Hash/bytes divergentes em {case_id}/{role}.")
            return path

        venous = sitk.ReadImage(str(resolve("t1_venous")))
        mask = sitk.ReadImage(str(resolve("liver_mask_venous")))
        if (
        venous.GetSize() != mask.GetSize()
        or not np.allclose(venous.GetSpacing(), mask.GetSpacing(), rtol=0.0, atol=1e-6)
        or not np.allclose(venous.GetOrigin(), mask.GetOrigin(), rtol=0.0, atol=1e-5)
        or not np.allclose(venous.GetDirection(), mask.GetDirection(), rtol=0.0, atol=1e-6)
    ):
            raise PipelineError(f"Mascara venosa nao corresponde ao T1 em {case_id}.")
        points = _physical_mask_points(mask)
        sequence_records = {}
        trace_medians = []
        for role in ["dwi_adc", *trace_roles, t2_role]:
            record = _image_record(resolve(role), venous.GetDirection())
            image = record.pop("image")
            record["liver_physical_fov"] = _coverage(points, image)
            sequence_records[role] = record
            match = TRACE_RE.fullmatch(role)
            if match:
                trace_medians.append((int(match.group(1)), float(record["nonzero_median"])))
        monotonic_pairs = [
            right[1] <= left[1]
            for left, right in zip(trace_medians, trace_medians[1:])
        ]
        cases.append({
            "case_id": case_id,
            "trace_roles": trace_roles,
            "last_ordered_trace_role": last_trace_role,
            "last_ordered_trace_selection_basis": "highest_numeric_run; explicit b-values unavailable",
            "t2_role": t2_role,
            "trace_adjacent_nonincreasing_fraction": (
                sum(monotonic_pairs) / len(monotonic_pairs) if monotonic_pairs else 1.0
            ),
            "sequences": sequence_records,
            "ground_truth_read": False,
        })
    key_roles = ["dwi_adc", "last_ordered_trace", "t2"]
    fractions = {role: [] for role in key_roles}
    cosines = {role: [] for role in key_roles}
    for case in cases:
        mapping = {
            "dwi_adc": "dwi_adc",
            "last_ordered_trace": case["last_ordered_trace_role"],
            "t2": case["t2_role"],
        }
        for key, role in mapping.items():
            record = case["sequences"][role]
            fractions[key].append(float(record["liver_physical_fov"]["inside_fraction"]))
            cosines[key].append(float(record["same_axis_min_abs_cosine"]))
    summary = {
        "schema": "argos-openswisshcc-multisequence-audit-v1",
        "status": "audit_complete_no_inference",
        "case_count": len(cases),
        "availability": {
            "adc": len(cases),
            "dwi_at_least_3_runs": sum(len(case["trace_roles"]) >= 3 for case in cases),
            "t2_blade": sum(case["t2_role"] == "t2_blade" for case in cases),
            "t2_haste_fallback": sum(case["t2_role"] == "t2_haste" for case in cases),
        },
        "physical_fov_inside_fraction": {
            role: {"minimum": min(values), "median": statistics.median(values)}
            for role, values in fractions.items()
        },
        "orientation_same_axis_abs_cosine": {
            role: {"minimum": min(values), "median": statistics.median(values)}
            for role, values in cosines.items()
        },
        "trace_order_support": {
            "median_adjacent_nonincreasing_fraction": statistics.median(
                case["trace_adjacent_nonincreasing_fraction"] for case in cases
            ),
            "cases_fully_nonincreasing": sum(
                case["trace_adjacent_nonincreasing_fraction"] == 1.0 for case in cases
            ),
            "caution": "The final ordered TRACE run is not claimed as high-b because public JSON sidecars do not expose explicit b-values.",
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
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary



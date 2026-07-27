"""Independently verify the published ARGOS blind benchmark.

This verifier never runs inference. It checks the public DICOM copies, private
answer key, source immutability, hashes, de-identification and compatibility
with the same MR-series selector used by the webapp.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pydicom

from dtwin.benchmark.dataset_audit import select_best_mr_series


FORBIDDEN_PUBLIC_TOKENS = {
    "positive",
    "negative",
    "normal",
    "healthy",
    "hcc",
    "tumor",
    "lesion",
    "metastasis",
    "hemangioma",
    "cyst",
    "ground_truth",
    "diagnosis",
    "label",
    "openswisshcc",
    "lld-mmri",
    "liverhccseg",
    "chaos",
}
PUBLIC_CASE_KEYS = {
    "blind_case_id",
    "relative_input_path",
    "file_count",
    "input_format",
    "input_hash",
    "technical_status",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return value


def verify(dataset_root: Path) -> dict[str, Any]:
    dataset_root = dataset_root.resolve()
    webapp_root = dataset_root / "webapp_input"
    private_root = dataset_root / "private_reference"
    manifest_root = dataset_root / "manifests"
    failures: list[str] = []

    with (private_root / "selected_cases_private.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        private_rows = list(csv.DictReader(stream))
    public_manifest = _json(manifest_root / "public_manifest.json")
    hash_manifest = _json(manifest_root / "file_hashes.json")
    conversion_records = json.loads(
        (private_root / "conversion_audit.json").read_text(encoding="utf-8")
    )

    expected_ids = [
        f"ARGOS-BLIND-{index:04d}" for index in range(1, 121)
    ]
    public_dirs = sorted(
        path for path in webapp_root.iterdir() if path.is_dir()
    )
    public_records = public_manifest.get("cases", [])
    private_by_id = {row["blind_case_id"]: row for row in private_rows}
    public_by_id = {row["blind_case_id"]: row for row in public_records}
    expected_hashes = {
        row["relative_path"]: row["sha256"]
        for row in hash_manifest.get("files", [])
    }

    checks: dict[str, bool] = {}
    checks["case_count_120"] = (
        len(public_dirs) == len(private_rows) == len(public_records) == 120
    )
    checks["blind_ids_exact"] = (
        [path.name for path in public_dirs] == expected_ids
        and sorted(private_by_id) == expected_ids
        and sorted(public_by_id) == expected_ids
    )
    labels = Counter(row["binary_label"] for row in private_rows)
    checks["label_distribution_70_50"] = (
        labels == Counter({"POSITIVE": 70, "NEGATIVE": 50})
    )
    checks["patients_unique_120"] = (
        len({row["patient_group_id"] for row in private_rows}) == 120
    )
    checks["public_manifest_schema_safe"] = all(
        set(row) == PUBLIC_CASE_KEYS for row in public_records
    )

    ordered = sorted(private_rows, key=lambda row: row["blind_case_id"])
    label_transitions = sum(
        left["binary_label"] != right["binary_label"]
        for left, right in zip(ordered, ordered[1:])
    )
    dataset_transitions = sum(
        left["dataset_id"] != right["dataset_id"]
        for left, right in zip(ordered, ordered[1:])
    )
    checks["blind_order_is_mixed"] = (
        label_transitions >= 30 and dataset_transitions >= 40
    )

    public_files = sorted(path for path in webapp_root.rglob("*") if path.is_file())
    checks["public_contains_dicom_only"] = bool(public_files) and all(
        path.suffix.lower() == ".dcm" for path in public_files
    )
    checks["file_manifest_complete"] = (
        len(public_files) == hash_manifest.get("file_count") == len(expected_hashes)
        and {
            path.relative_to(dataset_root).as_posix() for path in public_files
        }
        == set(expected_hashes)
    )

    public_hashes_ok = True
    public_terms_ok = True
    dicom_deidentified = True
    webapp_compatible = True
    public_original_ids_absent = True
    original_ids = {
        row["original_case_id"].lower()
        for row in private_rows
        if row.get("original_case_id")
    }
    for case_dir in public_dirs:
        relative_strings = [
            path.relative_to(webapp_root).as_posix().lower()
            for path in case_dir.rglob("*")
        ]
        if any(
            token in value
            for value in relative_strings
            for token in FORBIDDEN_PUBLIC_TOKENS
        ):
            public_terms_ok = False
        if any(
            original_id in value
            for value in relative_strings
            for original_id in original_ids
        ):
            public_original_ids_absent = False
        for path in sorted(case_dir.rglob("*.dcm")):
            relative = path.relative_to(dataset_root).as_posix()
            if _sha256(path) != expected_hashes.get(relative):
                public_hashes_ok = False
            dataset = pydicom.dcmread(
                str(path), stop_before_pixels=True, force=True
            )
            if (
                str(getattr(dataset, "PatientID", "")) != case_dir.name
                or str(getattr(dataset, "PatientName", "")) != "ARGOS^BLIND"
                or str(getattr(dataset, "Modality", "")) != "MR"
            ):
                dicom_deidentified = False
            for element in dataset.iterall():
                if element.VR not in {
                    "AE",
                    "CS",
                    "LO",
                    "LT",
                    "PN",
                    "SH",
                    "ST",
                    "UC",
                    "UT",
                }:
                    continue
                value = str(element.value).lower()
                if any(token in value for token in FORBIDDEN_PUBLIC_TOKENS):
                    public_terms_ok = False
                if any(original_id in value for original_id in original_ids):
                    public_original_ids_absent = False
        files, frames, metadata = select_best_mr_series(
            case_dir, min_slices=16
        )
        if not files or frames < 16 or metadata is None:
            webapp_compatible = False
        record = public_by_id.get(case_dir.name)
        if record is None:
            webapp_compatible = False
        elif len(list(case_dir.rglob("*.dcm"))) != int(record["file_count"]):
            webapp_compatible = False

    checks["all_public_hashes_match"] = public_hashes_ok
    checks["public_forbidden_terms_absent"] = public_terms_ok
    checks["original_case_ids_absent_public"] = public_original_ids_absent
    checks["dicom_deidentified"] = dicom_deidentified
    checks["webapp_selector_accepts_all_120"] = webapp_compatible

    source_hashes_ok = True
    source_files_present = True
    output_hashes_match_audit = True
    for row in conversion_records:
        source = Path(row["source_path_private"])
        if not source.is_file():
            source_files_present = False
            continue
        if _sha256(source) != row["source_sha256"]:
            source_hashes_ok = False
        relative = (
            f"webapp_input/{row['blind_case_id']}/"
            f"series_{int(row['series_number']):03d}/volume.dcm"
        )
        if expected_hashes.get(relative) != row["output_sha256"]:
            output_hashes_match_audit = False
    checks["all_source_files_still_present"] = source_files_present
    checks["original_source_hashes_unchanged"] = source_hashes_ok
    checks["conversion_audit_matches_output_hashes"] = output_hashes_match_audit
    checks["no_lesion_masks_or_reports_public"] = (
        checks["public_contains_dicom_only"]
        and checks["public_forbidden_terms_absent"]
    )

    for name, passed in checks.items():
        if not passed:
            failures.append(name)
    return {
        "schema": "argos-internal-blind-independent-verification-v1",
        "dataset_root": str(dataset_root),
        "status": "passed" if not failures else "failed",
        "case_count": len(public_dirs),
        "positive_count": labels["POSITIVE"],
        "negative_count": labels["NEGATIVE"],
        "patient_count": len(
            {row["patient_group_id"] for row in private_rows}
        ),
        "dicom_file_count": len(public_files),
        "source_file_count": len(conversion_records),
        "label_transitions": label_transitions,
        "dataset_transitions": dataset_transitions,
        "checks": checks,
        "failure_count": len(failures),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "dataset_root",
        nargs="?",
        type=Path,
        default=Path.cwd() / "ARGOS_INTERNAL_BLIND_BENCHMARK_120_V1",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON destination; defaults inside manifests/.",
    )
    args = parser.parse_args()
    result = verify(args.dataset_root)
    output = (
        args.output
        or args.dataset_root
        / "manifests"
        / "independent_verification.json"
    )
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

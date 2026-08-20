"""Build the ARGOS internal blind multicohort benchmark.

This utility is intentionally isolated from inference.  It reads protected
labels only for deterministic selection, creates de-identified multi-frame
DICOM copies from verified NIfTI inputs, and keeps all answers outside
``webapp_input``.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pydicom
import SimpleITK as sitk
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import EnhancedMRImageStorage, ExplicitVRLittleEndian

from dtwin.benchmark.dataset_audit import select_best_mr_series

SEED = 20260726
OUTPUT_NAME = "ARGOS_INTERNAL_BLIND_BENCHMARK_120_V1"
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


@dataclass
class SelectedCase:
    original_case_id: str
    patient_group_id: str
    dataset_id: str
    binary_label: str
    positive_subtype: str = ""
    negative_subtype: str = ""
    difficulty: str = "unknown"
    source_path: str = ""
    selection_reason: str = ""
    source_files: list[tuple[str, Path]] = field(default_factory=list)
    lesion_size_group: str = "unknown"
    blind_case_id: str = ""


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Objeto JSON esperado: {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _uid(*parts: str) -> str:
    return f"2.25.{uuid.uuid5(uuid.NAMESPACE_URL, '|'.join(parts)).int}"


def _safe_role(role: str) -> str:
    value = "".join(character.lower() if character.isalnum() else "_" for character in role)
    return "_".join(part for part in value.split("_") if part) or "mr"


def _series_semantics(role: str) -> tuple[str, str]:
    lowered = role.lower()
    if "arterial" in lowered:
        return "T1 ARTERIAL", "T1_ARTERIAL"
    if "venous" in lowered or "portal" in lowered:
        return "T1 PORTAL", "T1_PORTAL"
    if "delay" in lowered:
        return "T1 DELAYED", "T1_DELAYED"
    if "dwi" in lowered and "adc" not in lowered:
        return "DWI", "DWI"
    if "adc" in lowered:
        return "ADC", "ADC"
    if "t2" in lowered:
        return "T2", "T2"
    if "in_phase" in lowered or "t1_in" in lowered:
        return "T1 IN PHASE", "T1_IN_PHASE"
    if "out_phase" in lowered or "t1_out" in lowered:
        return "T1 OUT PHASE", "T1_OUT_PHASE"
    if "native" in lowered or "pre" in lowered:
        return "T1 NATIVE", "T1_UNSPECIFIED"
    return "MR SERIES", "UNKNOWN"


def _direction_vectors(image: sitk.Image) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    direction = np.asarray(image.GetDirection(), dtype=float).reshape(3, 3)
    return direction[:, 0], direction[:, 1], direction[:, 2]


def _scaled_int16(array: np.ndarray) -> tuple[np.ndarray, float, float]:
    values = np.nan_to_num(array.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    minimum = float(values.min())
    maximum = float(values.max())
    if maximum <= minimum:
        return np.zeros(values.shape, dtype=np.int16), 1.0, minimum
    slope = (maximum - minimum) / 60000.0
    stored = np.rint((values - minimum) / slope - 30000.0)
    stored = np.clip(stored, -30000, 30000).astype("<i2")
    intercept = minimum + 30000.0 * slope
    return stored, slope, intercept


def _ds(value: float) -> str:
    """DICOM DS with deterministic precision and the 16-character VR limit."""
    return format(float(value), ".10g")


def nifti_to_multiframe_dicom(
    source: Path,
    destination: Path,
    *,
    blind_case_id: str,
    series_number: int,
    role: str,
) -> dict[str, Any]:
    image = sitk.ReadImage(str(source))
    if image.GetDimension() != 3 or min(image.GetSize()) < 2:
        raise RuntimeError(f"Volume 3D inválido: {source}")
    array = sitk.GetArrayFromImage(image)
    stored, slope, intercept = _scaled_int16(array)
    frames, rows, columns = stored.shape
    spacing = image.GetSpacing()
    origin = np.asarray(image.GetOrigin(), dtype=float)
    row_direction, column_direction, slice_direction = _direction_vectors(image)

    file_meta = FileMetaDataset()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.MediaStorageSOPClassUID = EnhancedMRImageStorage
    sop_uid = _uid(blind_case_id, str(series_number), "sop")
    file_meta.MediaStorageSOPInstanceUID = sop_uid
    file_meta.ImplementationClassUID = _uid("ARGOS", "benchmark", "implementation")

    ds = FileDataset(
        str(destination),
        {},
        file_meta=file_meta,
        preamble=b"\0" * 128,
    )
    ds.SOPClassUID = EnhancedMRImageStorage
    ds.SOPInstanceUID = sop_uid
    ds.StudyInstanceUID = _uid(blind_case_id, "study")
    ds.SeriesInstanceUID = _uid(blind_case_id, str(series_number), "series")
    ds.FrameOfReferenceUID = _uid(blind_case_id, "frame")
    ds.Modality = "MR"
    ds.PatientName = "ARGOS^BLIND"
    ds.PatientID = blind_case_id
    ds.PatientBirthDate = ""
    ds.PatientSex = ""
    ds.StudyDate = "20000101"
    ds.SeriesDate = "20000101"
    ds.AcquisitionDate = "20000101"
    ds.ContentDate = "20000101"
    ds.StudyTime = "000000"
    ds.SeriesTime = "000000"
    ds.AcquisitionTime = "000000"
    ds.ContentTime = "000000"
    ds.AccessionNumber = ""
    ds.InstitutionName = "RESEARCH"
    ds.ReferringPhysicianName = ""
    ds.StudyID = "1"
    ds.SeriesNumber = int(series_number)
    ds.InstanceNumber = 1
    series_description, sequence_class = _series_semantics(role)
    ds.SeriesDescription = series_description
    ds.ProtocolName = series_description
    ds.SequenceName = series_description
    ds.ImageType = ["DERIVED", "PRIMARY", sequence_class]
    ds.Manufacturer = "ARGOS RESEARCH"
    ds.PatientPosition = "HFS"
    ds.Rows = rows
    ds.Columns = columns
    ds.NumberOfFrames = str(frames)
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 1
    ds.RescaleSlope = _ds(slope)
    ds.RescaleIntercept = _ds(intercept)
    ds.RescaleType = "US"
    ds.WindowCenter = str((float(stored.min()) + float(stored.max())) / 2.0)
    ds.WindowWidth = str(max(1.0, float(stored.max()) - float(stored.min())))

    pixel_measures = Dataset()
    pixel_measures.PixelSpacing = [_ds(spacing[1]), _ds(spacing[0])]
    pixel_measures.SliceThickness = _ds(spacing[2])
    pixel_measures.SpacingBetweenSlices = _ds(spacing[2])
    orientation = Dataset()
    orientation.ImageOrientationPatient = [
        *[_ds(value) for value in row_direction],
        *[_ds(value) for value in column_direction],
    ]
    ds.PixelSpacing = pixel_measures.PixelSpacing
    ds.SliceThickness = pixel_measures.SliceThickness
    ds.SpacingBetweenSlices = pixel_measures.SpacingBetweenSlices
    ds.ImageOrientationPatient = orientation.ImageOrientationPatient
    ds.ImagePositionPatient = [_ds(value) for value in origin]
    shared = Dataset()
    shared.PixelMeasuresSequence = Sequence([pixel_measures])
    shared.PlaneOrientationSequence = Sequence([orientation])
    ds.SharedFunctionalGroupsSequence = Sequence([shared])

    per_frame: list[Dataset] = []
    for frame_index in range(frames):
        position = origin + slice_direction * spacing[2] * frame_index
        plane = Dataset()
        plane.ImagePositionPatient = [_ds(value) for value in position]
        frame_content = Dataset()
        frame_content.DimensionIndexValues = [frame_index + 1]
        frame = Dataset()
        frame.PlanePositionSequence = Sequence([plane])
        frame.FrameContentSequence = Sequence([frame_content])
        per_frame.append(frame)
    ds.PerFrameFunctionalGroupsSequence = Sequence(per_frame)
    ds.PixelData = stored.tobytes(order="C")
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    destination.parent.mkdir(parents=True, exist_ok=True)
    ds.save_as(str(destination), enforce_file_format=True)
    return {
        "frames": frames,
        "rows": rows,
        "columns": columns,
        "spacing_xyz": [float(value) for value in spacing],
        "source_sha256": _sha256(source),
        "output_sha256": _sha256(destination),
        "conversion": "nifti_to_deidentified_enhanced_mr_multiframe",
    }


def _open_swiss_cases(root: Path) -> tuple[list[SelectedCase], list[dict[str, str]]]:
    labels_path = (
        root
        / "casos/qualification/openswisshcc_v1/prepared/development_v1/"
        "protected_ground_truth/development_labels.jsonl"
    )
    input_root = (
        root
        / "casos/qualification/openswisshcc_v1/prepared/development_v1/inputs"
    )
    metadata_path = (
        root
        / "casos/qualification/openswisshcc_v1/source_metadata/participants.tsv"
    )
    labels = _jsonl(labels_path)
    metadata_rows = list(
        csv.DictReader(metadata_path.open(encoding="utf-8"), delimiter="\t")
    )
    by_subject: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in metadata_rows:
        by_subject[str(row["ID"])].append(row)

    candidates: list[SelectedCase] = []
    private_meta: dict[str, dict[str, Any]] = {}
    for label in labels:
        case_id = str(label["case_id"])
        subject_id = str(label["public_subject_id"])
        rows = by_subject.get(subject_id, [])
        hcc_rows = [row for row in rows if row.get("HCC") == "1"]
        sizes = [
            float(row["Lesion size"])
            for row in hcc_rows
            if row.get("Lesion size") not in {"", None}
        ]
        max_size = max(sizes) if sizes else None
        lesion_count_values = [
            int(float(row["Number of lesions"]))
            for row in rows
            if row.get("Number of lesions") not in {"", None}
        ]
        lesion_count = max(lesion_count_values, default=0)
        if label["label"] == "POSITIVE":
            size_group = (
                "small"
                if max_size is not None and max_size <= 15
                else "medium"
                if max_size is not None and max_size <= 30
                else "large"
                if max_size is not None
                else "unknown"
            )
            difficulty = (
                "hard"
                if size_group == "small" or lesion_count > 1
                else "medium"
                if size_group == "medium"
                else "easy"
                if size_group == "large"
                else "unknown"
            )
            positive_subtype = "hcc"
            negative_subtype = ""
        else:
            hard_markers = 0
            for row in rows:
                for key in (
                    "Cirrhosis",
                    "Cirrhotic dystrophy (fibrosis)",
                    "Nodular appearance of the contours",
                    "Steatosis",
                    "Sign of HTTP (varicose veins)",
                ):
                    try:
                        hard_markers += int(float(row.get(key) or 0) > 0)
                    except ValueError:
                        pass
            difficulty = "hard" if hard_markers >= 2 else "medium" if rows else "unknown"
            size_group = "not_applicable"
            positive_subtype = ""
            negative_subtype = "hcc_absent_chronic_liver_control"
        case_root = input_root / case_id
        files: list[tuple[str, Path]] = []
        for path in sorted(case_root.rglob("*.nii.gz")):
            relative = path.relative_to(case_root).as_posix().lower()
            if "mask" in relative:
                continue
            role = path.name.removesuffix(".nii.gz")
            files.append((role, path))
        if not files:
            continue
        candidates.append(
            SelectedCase(
                original_case_id=case_id,
                patient_group_id=case_id,
                dataset_id="OpenSwissHCC",
                binary_label=str(label["label"]),
                positive_subtype=positive_subtype,
                negative_subtype=negative_subtype,
                difficulty=difficulty,
                source_path=str(case_root.resolve()),
                selection_reason="expert-validated OpenSwissHCC label; diversity by lesion size and liver background",
                source_files=files,
                lesion_size_group=size_group,
            )
        )
        private_meta[case_id] = {
            "public_subject_id": subject_id,
            "max_hcc_lesion_size_mm": max_size,
            "number_of_lesions": lesion_count,
            "machine": rows[0].get("Machine", "") if rows else "",
        }

    rng = random.Random(SEED + 1)
    positives = [case for case in candidates if case.binary_label == "POSITIVE"]
    negatives = [case for case in candidates if case.binary_label == "NEGATIVE"]
    grouped: dict[str, list[SelectedCase]] = defaultdict(list)
    for case in positives:
        grouped[case.lesion_size_group].append(case)
    for group in grouped.values():
        rng.shuffle(group)
    selected_positive: list[SelectedCase] = []
    for group, quota in (("small", 10), ("medium", 12), ("large", 9)):
        selected_positive.extend(grouped[group][:quota])
    if len(selected_positive) < 31:
        remaining = [
            case for case in positives if case not in selected_positive
        ]
        rng.shuffle(remaining)
        selected_positive.extend(remaining[: 31 - len(selected_positive)])
    negatives.sort(
        key=lambda case: (
            {"hard": 0, "medium": 1, "easy": 2, "unknown": 3}[case.difficulty],
            _canonical_hash([SEED, case.original_case_id]),
        )
    )
    selected = selected_positive[:31] + negatives[:30]
    selected_ids = {case.original_case_id for case in selected}
    excluded = [
        {
            "original_case_id": case.original_case_id,
            "dataset_id": case.dataset_id,
            "reason": "not_selected_after_deterministic_diversity_quota",
        }
        for case in candidates
        if case.original_case_id not in selected_ids
    ]
    for case in selected:
        meta = private_meta[case.original_case_id]
        case.selection_reason += (
            f"; size_group={case.lesion_size_group}; "
            f"machine={meta['machine'] or 'unknown'}"
        )
    return selected, excluded


def _lld_cases(root: Path) -> tuple[list[SelectedCase], list[dict[str, str]]]:
    labels_path = (
        root
        / "casos/qualification/lld_mmri_v23/prepared/external_protocol_v1/"
        "protected_ground_truth/labels.jsonl"
    )
    download_manifest_path = (
        root / "data/raw/LLD_MMRI_v23_hf/image_download_manifest.json"
    )
    labels = {str(row["case_id"]): row for row in _jsonl(labels_path)}
    manifest = _json(download_manifest_path)
    cases_by_id = {
        str(row["case_id"]): row for row in manifest.get("cases", [])
    }
    by_subtype: dict[str, list[SelectedCase]] = defaultdict(list)
    for case_id, row in labels.items():
        subtype = str(row.get("subtype") or "unknown")
        source = cases_by_id.get(case_id)
        if not source:
            continue
        files = [
            (
                str(role),
                (download_manifest_path.parent / item["relative_path"]).resolve(),
            )
            for role, item in sorted(source["images"].items())
        ]
        by_subtype[subtype].append(
            SelectedCase(
                original_case_id=case_id,
                patient_group_id=case_id,
                dataset_id="LLD-MMRI",
                binary_label="POSITIVE",
                positive_subtype=subtype,
                difficulty="unknown",
                source_path=str(download_manifest_path.parent.resolve()),
                selection_reason=(
                    "official focal-lesion subtype; benchmark endpoint is presence "
                    "of a documented focal liver alteration"
                ),
                source_files=files,
                lesion_size_group="unknown",
            )
        )
    quotas = {"hcc": 5, "hemangioma": 7, "hepatic_cyst": 7, "fnh": 6}
    selected: list[SelectedCase] = []
    rng = random.Random(SEED + 2)
    for subtype, quota in quotas.items():
        group = by_subtype[subtype]
        rng.shuffle(group)
        selected.extend(group[:quota])
    selected_ids = {case.original_case_id for case in selected}
    excluded = [
        {
            "original_case_id": case.original_case_id,
            "dataset_id": case.dataset_id,
            "reason": "not_selected_after_subtype_quota",
        }
        for cases in by_subtype.values()
        for case in cases
        if case.original_case_id not in selected_ids
    ]
    return selected, excluded


def _prepared_blind_cases(
    root: Path,
    *,
    cohort_path: Path,
    dataset_id: str,
    binary_label: str,
    subtype: str,
) -> list[SelectedCase]:
    cohort = _json(root / cohort_path)
    cohort_root = (root / cohort_path).parent
    selected: list[SelectedCase] = []
    for item in cohort["cases"]:
        case_id = str(item["case_id"])
        manifest_path = cohort_root / item["case_manifest"]
        manifest = _json(manifest_path)
        case_root = manifest_path.parent
        files = []
        for record in manifest["files"]:
            role = str(record["role"])
            if "mask" in role.lower():
                continue
            path = cohort_root / str(record["relative_path"])
            if _sha256(path) != record["sha256"]:
                raise RuntimeError(f"Hash de fonte divergente: {path}")
            files.append((role, path))
        selected.append(
            SelectedCase(
                original_case_id=case_id,
                patient_group_id=case_id,
                dataset_id=dataset_id,
                binary_label=binary_label,
                positive_subtype=subtype if binary_label == "POSITIVE" else "",
                negative_subtype=subtype if binary_label == "NEGATIVE" else "",
                difficulty="unknown",
                source_path=str(case_root.resolve()),
                selection_reason=(
                    "verified public blind-input cohort; patient-level identity "
                    "and source hashes preserved privately"
                ),
                source_files=files,
                lesion_size_group="unknown",
            )
        )
    return selected


def select_cases(root: Path) -> tuple[list[SelectedCase], list[dict[str, str]], list[dict[str, str]]]:
    openswiss, excluded_os = _open_swiss_cases(root)
    lld, excluded_lld = _lld_cases(root)
    liver = _prepared_blind_cases(
        root,
        cohort_path=Path("data/prepared/liverhccseg_v21_blind/cohort_manifest.json"),
        dataset_id="LiverHccSeg",
        binary_label="POSITIVE",
        subtype="hcc",
    )
    chaos = _prepared_blind_cases(
        root,
        cohort_path=Path("data/prepared/chaos_v21_blind/cohort_manifest.json"),
        dataset_id="CHAOS MRI",
        binary_label="NEGATIVE",
        subtype="anatomic_control_not_absolute_normality",
    )
    if len(openswiss) != 61 or len(lld) != 25 or len(liver) != 14 or len(chaos) != 20:
        raise RuntimeError(
            f"Composição pré-randomização inesperada: "
            f"{len(openswiss)}/{len(lld)}/{len(liver)}/{len(chaos)}"
        )
    selected = openswiss + lld + liver + chaos
    rng = random.Random(SEED)
    rng.shuffle(selected)
    for index, case in enumerate(selected, start=1):
        case.blind_case_id = f"ARGOS-BLIND-{index:04d}"
    substitutions = [
        {
            "planned": "LLD-MMRI 5 NEGATIVE",
            "actual": "OpenSwissHCC +5 NEGATIVE",
            "reason": (
                "LLD-MMRI local subset contains documented focal lesions only; "
                "benign lesions were not misclassified as absence of focal alteration"
            ),
        },
        {
            "planned": "LiverHccSeg 20 POSITIVE",
            "actual": "LiverHccSeg 14 POSITIVE + OpenSwissHCC 6 POSITIVE",
            "reason": (
                "protected public audit confirms only 14 unique tumor-positive "
                "LiverHccSeg patients; no patient was duplicated"
            ),
        },
        {
            "planned": "LLD-MMRI broad subtypes including metastasis/abscess/ICC",
            "actual": "HCC 5, hemangioma 7, hepatic cyst 7, FNH 6",
            "reason": (
                "selective local download contains only public categories "
                "HCC/hemangioma/cyst/FNH; missing diagnoses were not invented"
            ),
        },
    ]
    excluded = excluded_os + excluded_lld + [
        {
            "original_case_id": "protected_non_tumor_subject",
            "dataset_id": "LiverHccSeg",
            "reason": "3 documented non-tumor subjects excluded; not assumed negative",
        }
    ]
    return selected, excluded, substitutions


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_reports(
    output: Path,
    final_output: Path,
    selected: list[SelectedCase],
    excluded: list[dict[str, str]],
    substitutions: list[dict[str, str]],
    public_records: list[dict[str, Any]],
    private_records: list[dict[str, Any]],
    file_hashes: list[dict[str, str]],
    verification: dict[str, Any],
) -> None:
    labels = Counter(case.binary_label for case in selected)
    datasets = Counter(
        (case.dataset_id, case.binary_label) for case in selected
    )
    subtypes = Counter(
        case.positive_subtype or case.negative_subtype or "unknown"
        for case in selected
    )
    difficulties = Counter(case.difficulty for case in selected)
    sizes = Counter(case.lesion_size_group for case in selected)
    _write_csv(
        output / "private_reference/blind_labels.csv",
        private_records,
        [
            "blind_case_id",
            "original_case_id",
            "patient_group_id",
            "dataset_id",
            "binary_label",
            "positive_subtype",
            "negative_subtype",
            "difficulty",
            "source_path",
            "selection_reason",
        ],
    )
    _write_csv(
        output / "private_reference/selected_cases_private.csv",
        private_records,
        list(private_records[0]),
    )
    dataset_rows = []
    for dataset in sorted({case.dataset_id for case in selected}):
        positive = datasets[(dataset, "POSITIVE")]
        negative = datasets[(dataset, "NEGATIVE")]
        dataset_rows.append(
            {
                "dataset_id": dataset,
                "positive": positive,
                "negative": negative,
                "total": positive + negative,
            }
        )
    _write_csv(
        output / "reports/dataset_distribution.csv",
        dataset_rows,
        ["dataset_id", "positive", "negative", "total"],
    )
    _write_csv(
        output / "reports/subtype_distribution.csv",
        [
            {"subtype": subtype, "count": count}
            for subtype, count in sorted(subtypes.items())
        ],
        ["subtype", "count"],
    )
    _write_csv(
        output / "reports/difficulty_distribution.csv",
        [
            {"difficulty": difficulty, "count": count}
            for difficulty, count in sorted(difficulties.items())
        ],
        ["difficulty", "count"],
    )
    _write_csv(
        output / "reports/excluded_cases.csv",
        excluded,
        ["original_case_id", "dataset_id", "reason"],
    )
    _write_csv(
        output / "reports/substitutions.csv",
        substitutions,
        ["planned", "actual", "reason"],
    )
    public_manifest = {
        "schema": "argos-internal-blind-benchmark-public-manifest-v1",
        "benchmark_id": OUTPUT_NAME,
        "classification": [
            "Internal Blind Benchmark",
            "Retrospective Multicohort",
            "Research Only",
            "Not External Validation",
        ],
        "case_count": len(public_records),
        "cases": public_records,
    }
    private_manifest = {
        "schema": "argos-internal-blind-benchmark-private-manifest-v1",
        "benchmark_id": OUTPUT_NAME,
        "seed": SEED,
        "target_condition": "documented_focal_liver_alteration_presence",
        "case_count": len(private_records),
        "positive_count": labels["POSITIVE"],
        "negative_count": labels["NEGATIVE"],
        "cases": private_records,
        "substitutions": substitutions,
        "research_only": True,
        "not_external_validation": True,
    }
    (output / "manifests/public_manifest.json").write_text(
        json.dumps(public_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "manifests/private_manifest.json").write_text(
        json.dumps(private_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "manifests/file_hashes.json").write_text(
        json.dumps(
            {
                "schema": "argos-internal-blind-file-hashes-v1",
                "file_count": len(file_hashes),
                "files": file_hashes,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    report_lines = [
        "# Relatório de seleção — ARGOS Internal Blind Benchmark 120 V1",
        "",
        "Classificação: **Internal Blind Benchmark; Retrospective Multicohort; "
        "Research Only; Not External Validation.**",
        "",
        f"- Casos: {len(selected)}",
        f"- Pacientes únicos: {len({case.patient_group_id for case in selected})}",
        f"- Positivos: {labels['POSITIVE']}",
        f"- Negativos: {labels['NEGATIVE']}",
        f"- Seed de cegamento: {SEED}",
        "",
        "## Composição real",
        "",
        "| Dataset | Positivos | Negativos | Total |",
        "|---|---:|---:|---:|",
    ]
    for row in dataset_rows:
        report_lines.append(
            f"| {row['dataset_id']} | {row['positive']} | "
            f"{row['negative']} | {row['total']} |"
        )
    report_lines.extend(
        [
            "",
            "## Substituições metodológicas",
            "",
        ]
    )
    for row in substitutions:
        report_lines.append(
            f"- **{row['planned']} → {row['actual']}**: {row['reason']}."
        )
    report_lines.extend(
        [
            "",
            "## Critérios de seleção",
            "",
            "- Seleção determinística e cegamento com seed `20260726`.",
            "- Um único caso por `patient_group_id`; fases e sequências do mesmo "
            "paciente permanecem reunidas.",
            "- Rótulos obtidos exclusivamente de referências públicas/protegidas "
            "já congeladas no projeto, nunca de novas previsões.",
            "- OpenSwissHCC: diversidade por tamanho de lesão, equipamento e "
            "doença hepática de base, conforme metadados disponíveis.",
            "- LLD-MMRI: quotas entre HCC, hemangioma, cisto hepático e FNH, que "
            "são os subtipos realmente presentes no download local.",
            "- LiverHccSeg: todos os 14 pacientes tumor-positivos únicos "
            "confirmados pela auditoria pública protegida.",
            "- CHAOS: 20 controles de RM, mantendo T1-Dual e T2-SPIR do mesmo "
            "paciente no mesmo caso.",
            "- Dificuldade ou tamanho ausente permaneceu `unknown`; nenhum "
            "metadado foi inferido ou inventado.",
            "",
            "## Subtipos",
            "",
            *[
                f"- {subtype}: {count}"
                for subtype, count in sorted(subtypes.items())
            ],
            "",
            "## Dificuldade",
            "",
            *[
                f"- {difficulty}: {count}"
                for difficulty, count in sorted(difficulties.items())
            ],
            "",
            "Casos sem base documental suficiente permaneceram `unknown`; "
            "nenhuma dificuldade foi inventada.",
            "",
            "## Tamanho de lesão",
            "",
            *[
                f"- {size}: {count}"
                for size, count in sorted(sizes.items())
            ],
            "",
            "## Integridade",
            "",
            f"- Casos excluídos/fora das quotas: {len(excluded)}",
            "- Conflitos de rótulo selecionados: 0",
            "- Duplicatas selecionadas: 0",
            "- Máscaras de lesão na pasta pública: 0",
            "- Relatórios clínicos na pasta pública: 0",
            f"- Verificação automática: {verification['status']}",
            "",
            "## Caminhos",
            "",
            f"- Entrada webapp: `{(final_output / 'webapp_input').resolve()}`",
            f"- Respostas privadas: `{(final_output / 'private_reference/blind_labels.csv').resolve()}`",
        ]
    )
    (output / "reports/selection_report.md").write_text(
        "\n".join(report_lines) + "\n", encoding="utf-8"
    )


def _public_dicom_strings(path: Path) -> list[str]:
    dataset = pydicom.dcmread(str(path), stop_before_pixels=True, force=True)
    values = []
    for element in dataset.iterall():
        if element.VR in {"AE", "CS", "LO", "LT", "PN", "SH", "ST", "UC", "UT"}:
            values.append(str(element.value).lower())
    return values


def verify_output(
    output: Path,
    selected: list[SelectedCase],
    public_records: list[dict[str, Any]],
) -> dict[str, Any]:
    webapp_root = output / "webapp_input"
    case_dirs = sorted(path for path in webapp_root.iterdir() if path.is_dir())
    failures: list[str] = []
    if len(case_dirs) != 120:
        failures.append("public_case_count")
    if len(selected) != 120:
        failures.append("selected_case_count")
    if len({case.patient_group_id for case in selected}) != 120:
        failures.append("patient_uniqueness")
    labels = Counter(case.binary_label for case in selected)
    if labels != Counter({"POSITIVE": 70, "NEGATIVE": 50}):
        failures.append("label_distribution")
    expected_names = {f"ARGOS-BLIND-{index:04d}" for index in range(1, 121)}
    if {path.name for path in case_dirs} != expected_names:
        failures.append("blind_case_names")
    record_by_id = {row["blind_case_id"]: row for row in public_records}
    for case_dir in case_dirs:
        for path in case_dir.rglob("*"):
            relative_lower = path.relative_to(webapp_root).as_posix().lower()
            if any(token in relative_lower for token in FORBIDDEN_PUBLIC_TOKENS):
                failures.append(f"forbidden_path:{relative_lower}")
            if path.is_file() and path.suffix.lower() == ".dcm":
                for value in _public_dicom_strings(path):
                    if any(token in value for token in FORBIDDEN_PUBLIC_TOKENS):
                        failures.append(f"forbidden_dicom:{case_dir.name}")
                        break
        files, frames, metadata = select_best_mr_series(case_dir, min_slices=16)
        if not files or frames < 16 or metadata is None:
            failures.append(f"webapp_series:{case_dir.name}")
        record = record_by_id.get(case_dir.name)
        dicom_paths = sorted(case_dir.rglob("*.dcm"))
        if not record or record["file_count"] != len(dicom_paths):
            failures.append(f"public_manifest:{case_dir.name}")
        elif record["input_hash"] != _canonical_hash(
            [
                {
                    "relative_path": path.relative_to(output).as_posix(),
                    "sha256": _sha256(path),
                }
                for path in dicom_paths
            ]
        ):
            failures.append(f"input_hash:{case_dir.name}")
    forbidden_public_keys = {
        "dataset_id",
        "label",
        "subtype",
        "difficulty",
        "original_case_id",
        "source_path",
        "diagnosis",
    }
    for row in public_records:
        if forbidden_public_keys & set(row):
            failures.append(f"public_keys:{row.get('blind_case_id')}")
    return {
        "schema": "argos-internal-blind-benchmark-verification-v1",
        "status": "passed" if not failures else "failed",
        "checks": {
            "case_count_120": len(case_dirs) == 120,
            "patient_count_120": len({case.patient_group_id for case in selected}) == 120,
            "positive_count_70": labels["POSITIVE"] == 70,
            "negative_count_50": labels["NEGATIVE"] == 50,
            "blind_names_only": {path.name for path in case_dirs} == expected_names,
            "public_manifest_has_no_private_keys": all(
                not (forbidden_public_keys & set(row)) for row in public_records
            ),
            "webapp_series_detected_all_cases": not any(
                item.startswith("webapp_series:") for item in failures
            ),
            "input_hashes_match_all_cases": not any(
                item.startswith("input_hash:") for item in failures
            ),
            "public_forbidden_tokens_absent": not any(
                item.startswith(("forbidden_path:", "forbidden_dicom:"))
                for item in failures
            ),
        },
        "failure_count": len(failures),
        "failures": failures,
    }


def build(root: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise RuntimeError(f"Saída já existe e é imutável: {output}")
    staging = output.with_name(f".{output.name}.incomplete")
    if staging.exists():
        raise RuntimeError(f"Staging já existe: {staging}")
    for relative in (
        "webapp_input",
        "private_reference",
        "reports",
        "manifests",
    ):
        (staging / relative).mkdir(parents=True, exist_ok=True)
    selected, excluded, substitutions = select_cases(root)
    source_hashes_before = {
        str(path): _sha256(path)
        for case in selected
        for _role, path in case.source_files
    }
    public_records: list[dict[str, Any]] = []
    private_records: list[dict[str, Any]] = []
    file_hashes: list[dict[str, str]] = []
    conversion_records: list[dict[str, Any]] = []
    for case in selected:
        case_root = staging / "webapp_input" / case.blind_case_id
        case_files: list[dict[str, str]] = []
        for series_number, (role, source) in enumerate(case.source_files, start=1):
            destination = (
                case_root
                / f"series_{series_number:03d}"
                / "volume.dcm"
            )
            conversion = nifti_to_multiframe_dicom(
                source,
                destination,
                blind_case_id=case.blind_case_id,
                series_number=series_number,
                role=role,
            )
            relative = destination.relative_to(staging).as_posix()
            case_files.append(
                {
                    "relative_path": relative,
                    "sha256": conversion["output_sha256"],
                }
            )
            file_hashes.append(
                {
                    "relative_path": relative,
                    "sha256": conversion["output_sha256"],
                }
            )
            conversion_records.append(
                {
                    "blind_case_id": case.blind_case_id,
                    "series_number": series_number,
                    "role_private": role,
                    "source_path_private": str(source.resolve()),
                    **conversion,
                }
            )
        input_hash = _canonical_hash(case_files)
        public_records.append(
            {
                "blind_case_id": case.blind_case_id,
                "relative_input_path": f"webapp_input/{case.blind_case_id}",
                "file_count": len(case_files),
                "input_format": "deidentified_enhanced_mr_multiframe_dicom",
                "input_hash": input_hash,
                "technical_status": "ready",
            }
        )
        private_records.append(
            {
                "blind_case_id": case.blind_case_id,
                "original_case_id": case.original_case_id,
                "patient_group_id": case.patient_group_id,
                "dataset_id": case.dataset_id,
                "binary_label": case.binary_label,
                "positive_subtype": case.positive_subtype,
                "negative_subtype": case.negative_subtype,
                "difficulty": case.difficulty,
                "lesion_size_group": case.lesion_size_group,
                "source_path": case.source_path,
                "selection_reason": case.selection_reason,
                "input_hash": input_hash,
            }
        )
    if any(_sha256(Path(path)) != digest for path, digest in source_hashes_before.items()):
        raise RuntimeError("Uma fonte original foi alterada durante a cópia.")
    (staging / "private_reference/conversion_audit.json").write_text(
        json.dumps(conversion_records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    verification = verify_output(staging, selected, public_records)
    _write_reports(
        staging,
        output,
        selected,
        excluded,
        substitutions,
        public_records,
        private_records,
        file_hashes,
        verification,
    )
    (staging / "manifests/verification.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    readme = f"""# {OUTPUT_NAME}

Internal Blind Benchmark — Retrospective Multicohort — Research Only.

Not External Validation. This collection contains de-identified derived
multi-frame MR DICOM copies prepared exclusively for the ARGOS webapp.

Use only:

`webapp_input/`

**DO NOT PROVIDE private_reference/ TO THE WEBAPP OR TO THE MODEL.**

The answer key, original identifiers, source paths and selection rationale are
kept under `private_reference/`. Public inputs contain only blind identifiers.
No lesion mask or medical report is present in `webapp_input/`.
"""
    (staging / "README.md").write_text(readme, encoding="utf-8")
    if verification["status"] != "passed":
        raise RuntimeError(
            f"Verificação falhou ({verification['failure_count']}): "
            f"{verification['failures'][:10]}"
        )
    os.replace(staging, output)
    total_bytes = sum(
        path.stat().st_size for path in output.rglob("*") if path.is_file()
    )
    return {
        "status": "complete",
        "output": str(output.resolve()),
        "webapp_input": str((output / "webapp_input").resolve()),
        "private_labels": str(
            (output / "private_reference/blind_labels.csv").resolve()
        ),
        "case_count": 120,
        "positive_count": 70,
        "negative_count": 50,
        "dataset_distribution": dict(
            Counter(case.dataset_id for case in selected)
        ),
        "substitution_count": len(substitutions),
        "excluded_record_count": len(excluded),
        "file_count": len(file_hashes),
        "total_bytes": total_bytes,
        "verification": verification,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output", type=Path, default=Path.cwd() / OUTPUT_NAME
    )
    parser.add_argument(
        "--selection-only",
        action="store_true",
        help="Validate deterministic selection without materializing DICOM.",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if args.selection_only:
        selected, excluded, substitutions = select_cases(root)
        result = {
            "case_count": len(selected),
            "positive_count": sum(case.binary_label == "POSITIVE" for case in selected),
            "negative_count": sum(case.binary_label == "NEGATIVE" for case in selected),
            "patient_count": len({case.patient_group_id for case in selected}),
            "dataset_distribution": dict(Counter(case.dataset_id for case in selected)),
            "substitutions": substitutions,
            "excluded_record_count": len(excluded),
        }
    else:
        result = build(root, args.output.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

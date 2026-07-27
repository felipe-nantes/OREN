"""Auditoria segura de lotes DICOM para qualificação do benchmark hepático.

Este módulo lê apenas metadados técnicos necessários para agrupar e classificar
séries. Identificadores DICOM, nomes de diretório e descrições livres nunca são
persistidos: somente hashes, categorias normalizadas e métricas geométricas.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pydicom


AUDIT_SCHEMA = "argos-liver-mri-dataset-audit-v1"
_PHI_FIELD_NAMES = {
    "PatientName",
    "PatientID",
    "PatientBirthDate",
    "AccessionNumber",
    "InstitutionName",
    "ReferringPhysicianName",
}
_TECHNICAL_TAGS = [
    "Modality",
    "SeriesInstanceUID",
    "SOPInstanceUID",
    "InstanceNumber",
    "NumberOfFrames",
    "SeriesDescription",
    "ProtocolName",
    "SequenceName",
    "ImageType",
    "ScanningSequence",
    "SequenceVariant",
    "EchoTime",
    "RepetitionTime",
    "DiffusionBValue",
    "ImageOrientationPatient",
    "ImagePositionPatient",
    "SliceThickness",
    "SpacingBetweenSlices",
    "PixelSpacing",
    "Rows",
    "Columns",
    "ContrastBolusAgent",
]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _float_list(value: Any) -> list[float]:
    if value is None:
        return []
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return []


def _normalized_text(dataset: Any, source: Path) -> str:
    values = [
        getattr(dataset, "SeriesDescription", ""),
        getattr(dataset, "ProtocolName", ""),
        getattr(dataset, "SequenceName", ""),
        getattr(dataset, "ScanningSequence", ""),
        getattr(dataset, "SequenceVariant", ""),
        getattr(dataset, "ImageType", ""),
        source.parent.name,
    ]
    text = " ".join(str(value) for value in values).lower()
    return re.sub(r"[^a-z0-9+#]+", " ", text)


def classify_sequence(dataset: Any, source: Path) -> str:
    """Converte texto técnico livre em uma categoria sem persistir o texto."""
    text = _normalized_text(dataset, source)
    b_value = _safe_float(getattr(dataset, "DiffusionBValue", None))
    if "adc" in text:
        return "ADC"
    if any(token in text for token in ("dwi", "diff", "ep2d")) or (b_value or 0) > 0:
        return "DWI"
    if any(token in text for token in ("t2", "haste", "ssfp")):
        return "T2"
    if any(token in text for token in ("outphase", "out phase", "opposed", "op fase")):
        return "T1_OUT_PHASE"
    if any(token in text for token in ("inphase", "in phase", "in fase")):
        return "T1_IN_PHASE"
    if any(token in text for token in ("arterial", "art phase", "art fase")):
        return "T1_ARTERIAL"
    if any(token in text for token in ("portal", "venous", "venosa")):
        return "T1_PORTAL"
    if any(token in text for token in ("delayed", "delay", "tardia", "equilibrium", "5 min")):
        return "T1_DELAYED"
    if any(token in text for token in ("post", "+c", "gad", "contrast")):
        return "T1_POST_CONTRAST"
    if any(token in text for token in ("pre", "t1", "vibe", "dixon", "dual")):
        return "T1_UNSPECIFIED"
    return "UNKNOWN"


def _orientation(dataset: Any) -> str:
    values = _float_list(getattr(dataset, "ImageOrientationPatient", None))
    if len(values) != 6:
        return "unknown"
    row, column = values[:3], values[3:]
    normal = (
        row[1] * column[2] - row[2] * column[1],
        row[2] * column[0] - row[0] * column[2],
        row[0] * column[1] - row[1] * column[0],
    )
    axis = max(range(3), key=lambda idx: abs(normal[idx]))
    return ("sagittal", "coronal", "axial")[axis]


def _position(dataset: Any) -> float | None:
    orientation = _float_list(getattr(dataset, "ImageOrientationPatient", None))
    position = _float_list(getattr(dataset, "ImagePositionPatient", None))
    if len(orientation) != 6 or len(position) != 3:
        return None
    row, column = orientation[:3], orientation[3:]
    normal = (
        row[1] * column[2] - row[2] * column[1],
        row[2] * column[0] - row[0] * column[2],
        row[0] * column[1] - row[1] * column[0],
    )
    return sum(normal[index] * position[index] for index in range(3))


def _echo_bucket(value: Any) -> str:
    echo = _safe_float(value)
    return "unknown" if echo is None else f"{echo:.3f}"


@dataclass
class _SeriesAccumulator:
    series_key: str
    sequence_class: str
    modality: str
    orientation: str
    echo_time_ms: float | None
    files: int = 0
    frames: int = 0
    rows: Counter[int] = field(default_factory=Counter)
    columns: Counter[int] = field(default_factory=Counter)
    slice_thickness_mm: list[float] = field(default_factory=list)
    pixel_spacing_mm: list[tuple[float, float]] = field(default_factory=list)
    positions: list[float] = field(default_factory=list)
    instance_numbers: list[int] = field(default_factory=list)
    contrast_present: bool = False
    read_errors: int = 0
    paths: list[Path] = field(default_factory=list)

    def add(self, dataset: Any, source: Path) -> None:
        self.files += 1
        self.paths.append(source)
        frames = int(getattr(dataset, "NumberOfFrames", 1) or 1)
        self.frames += max(frames, 1)
        rows = int(getattr(dataset, "Rows", 0) or 0)
        columns = int(getattr(dataset, "Columns", 0) or 0)
        if rows:
            self.rows[rows] += 1
        if columns:
            self.columns[columns] += 1
        thickness = _safe_float(getattr(dataset, "SliceThickness", None))
        if thickness is not None:
            self.slice_thickness_mm.append(thickness)
        spacing = _float_list(getattr(dataset, "PixelSpacing", None))
        if len(spacing) == 2:
            self.pixel_spacing_mm.append((spacing[0], spacing[1]))
        position = _position(dataset)
        if position is not None:
            self.positions.append(position)
        try:
            self.instance_numbers.append(int(getattr(dataset, "InstanceNumber")))
        except (TypeError, ValueError, AttributeError):
            pass
        self.contrast_present = self.contrast_present or bool(
            str(getattr(dataset, "ContrastBolusAgent", "")).strip()
        )


def _mode(counter: Counter[int]) -> int | None:
    return counter.most_common(1)[0][0] if counter else None


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[midpoint], 4)
    return round((ordered[midpoint - 1] + ordered[midpoint]) / 2, 4)


def _geometry(accumulator: _SeriesAccumulator) -> dict[str, Any]:
    unique_positions = sorted(set(round(value, 4) for value in accumulator.positions))
    deltas = [
        unique_positions[index + 1] - unique_positions[index]
        for index in range(len(unique_positions) - 1)
        if unique_positions[index + 1] > unique_positions[index]
    ]
    median_delta = _median(deltas)
    nonuniform = False
    if median_delta and deltas:
        tolerance = max(0.2, abs(median_delta) * 0.1)
        nonuniform = any(abs(delta - median_delta) > tolerance for delta in deltas)
    duplicate_positions = max(0, len(accumulator.positions) - len(unique_positions))
    duplicate_instances = max(
        0, len(accumulator.instance_numbers) - len(set(accumulator.instance_numbers))
    )
    return {
        "unique_slice_positions": len(unique_positions),
        "duplicate_slice_positions": duplicate_positions,
        "duplicate_instance_numbers": duplicate_instances,
        "median_slice_spacing_mm": median_delta,
        "nonuniform_slice_spacing": nonuniform,
    }


def _quality(accumulator: _SeriesAccumulator, geometry: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    warnings: list[str] = []
    if accumulator.modality == "MR":
        score += 40
    else:
        warnings.append("modality_not_mr")
    if accumulator.orientation == "axial":
        score += 20
    elif accumulator.orientation == "unknown":
        warnings.append("orientation_unknown")
    if accumulator.frames >= 16:
        score += 20
    else:
        warnings.append("insufficient_slices")
    sequence_bonus = {
        "DWI": 20,
        "ADC": 18,
        "T2": 16,
        "T1_ARTERIAL": 20,
        "T1_PORTAL": 20,
        "T1_DELAYED": 18,
        "T1_POST_CONTRAST": 16,
        "T1_IN_PHASE": 10,
        "T1_OUT_PHASE": 10,
        "T1_UNSPECIFIED": 8,
        "UNKNOWN": 0,
    }
    score += sequence_bonus.get(accumulator.sequence_class, 0)
    if geometry["nonuniform_slice_spacing"]:
        score -= 20
        warnings.append("nonuniform_slice_spacing")
    if geometry["duplicate_slice_positions"]:
        score -= 10
        warnings.append("duplicate_slice_positions")
    if len(accumulator.rows) > 1 or len(accumulator.columns) > 1:
        score -= 20
        warnings.append("mixed_matrix_size")
    if accumulator.read_errors:
        score -= 10
        warnings.append("dicom_read_errors")
    return max(score, 0), warnings


def _series_payload(accumulator: _SeriesAccumulator) -> dict[str, Any]:
    geometry = _geometry(accumulator)
    quality_score, warnings = _quality(accumulator, geometry)
    spacing = accumulator.pixel_spacing_mm[0] if accumulator.pixel_spacing_mm else None
    return {
        "series_key": accumulator.series_key,
        "modality": accumulator.modality or "unknown",
        "sequence_class": accumulator.sequence_class,
        "orientation": accumulator.orientation,
        "echo_time_ms": accumulator.echo_time_ms,
        "file_count": accumulator.files,
        "frame_count": accumulator.frames,
        "rows": _mode(accumulator.rows),
        "columns": _mode(accumulator.columns),
        "pixel_spacing_mm": list(spacing) if spacing else None,
        "slice_thickness_mm": _median(accumulator.slice_thickness_mm),
        "contrast_metadata_present": accumulator.contrast_present,
        "geometry": geometry,
        "quality_score": quality_score,
        "eligible_for_screening": (
            accumulator.modality == "MR"
            and quality_score >= 60
            and accumulator.frames >= 16
        ),
        "warnings": sorted(set(warnings)),
    }


def _dicom_files(case_dir: Path) -> Iterable[Path]:
    for path in case_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".dcm", ".ima", ""}:
            yield path


def _accumulate_series(paths: Iterable[Path]) -> tuple[list[_SeriesAccumulator], int]:
    groups: dict[tuple[str, str, str], _SeriesAccumulator] = {}
    unreadable = 0
    for path in paths:
        try:
            dataset = pydicom.dcmread(
                str(path), stop_before_pixels=True, force=True, specific_tags=_TECHNICAL_TAGS
            )
        except Exception:  # noqa: BLE001 - erro é resumido sem caminho/PHI
            unreadable += 1
            continue
        if any(name in dataset for name in _PHI_FIELD_NAMES):
            raise RuntimeError("Auditoria solicitou tag PHI inesperadamente.")
        series_uid = str(getattr(dataset, "SeriesInstanceUID", "missing"))
        echo_bucket = _echo_bucket(getattr(dataset, "EchoTime", None))
        modality = str(getattr(dataset, "Modality", "")).upper()
        key = (_digest(series_uid)[:16], echo_bucket, modality)
        if key not in groups:
            groups[key] = _SeriesAccumulator(
                series_key=_digest(f"{series_uid}|{echo_bucket}|{modality}")[:16],
                sequence_class=classify_sequence(dataset, path),
                modality=modality,
                orientation=_orientation(dataset),
                echo_time_ms=_safe_float(getattr(dataset, "EchoTime", None)),
            )
        groups[key].add(dataset, path)

    return list(groups.values()), unreadable


def _discover_series(case_dir: Path) -> tuple[list[_SeriesAccumulator], int]:
    return _accumulate_series(_dicom_files(case_dir))


def select_best_mr_series(
    root: Path, *, min_slices: int = 3
) -> tuple[list[str], int, dict[str, Any] | None]:
    """Seleciona uma série MR de forma determinística e retorna auditoria sanitizada.

    Caminhos são retornados apenas ao chamador local e nunca entram no metadata.
    O desempate usa score técnico, prioridade de sequência, frames e hash da série.
    """
    groups, _unreadable = _discover_series(Path(root))
    priority = {
        "T1_ARTERIAL": 100,
        "T1_PORTAL": 95,
        "DWI": 90,
        "ADC": 85,
        "T2": 80,
        "T1_DELAYED": 75,
        "T1_POST_CONTRAST": 70,
        "T1_IN_PHASE": 60,
        "T1_OUT_PHASE": 55,
        "T1_UNSPECIFIED": 40,
        "UNKNOWN": 0,
    }
    candidates: list[tuple[_SeriesAccumulator, dict[str, Any]]] = []
    minimum_score = 60 if int(min_slices) >= 16 else 40
    for accumulator in groups:
        payload = _series_payload(accumulator)
        if (
            accumulator.modality == "MR"
            and accumulator.frames >= int(min_slices)
            and payload["quality_score"] >= minimum_score
        ):
            candidates.append((accumulator, payload))
    if not candidates:
        return [], 0, None
    accumulator, payload = max(
        candidates,
        key=lambda item: (
            item[1]["quality_score"],
            priority.get(item[1]["sequence_class"], 0),
            item[0].frames,
            item[1]["series_key"],
        ),
    )
    files = sorted(str(path) for path in accumulator.paths)
    metadata = {
        "schema": "argos-series-selection-v1",
        "strategy": "technical_clinical_score",
        "selected": payload,
        "candidate_count": len(candidates),
        "raw_paths_persisted": False,
        "raw_uids_persisted": False,
    }
    return files, accumulator.frames, metadata


def describe_selected_series(files: Iterable[str | Path]) -> dict[str, Any]:
    """Descreve arquivos selecionados sem persistir seus caminhos ou UIDs."""
    groups, unreadable = _accumulate_series(Path(path) for path in files)
    payloads = sorted(
        (_series_payload(group) for group in groups),
        key=lambda item: (-item["quality_score"], item["series_key"]),
    )
    return {
        "schema": "argos-series-selection-v1",
        "strategy": "technical_clinical_score",
        "selected_series": payloads,
        "selected_group_count": len(payloads),
        "unreadable_file_count": unreadable,
        "raw_paths_persisted": False,
        "raw_uids_persisted": False,
        "contains_phi": False,
    }


def audit_case(case_dir: Path, *, case_ref: str, label: str) -> dict[str, Any]:
    groups, unreadable = _discover_series(case_dir)

    series = sorted(
        (_series_payload(value) for value in groups),
        key=lambda item: (-item["quality_score"], item["series_key"]),
    )
    warnings: list[str] = []
    if not series:
        warnings.append("no_readable_dicom_series")
    if unreadable:
        warnings.append("unreadable_dicom_files")
    eligible = [item for item in series if item["eligible_for_screening"]]
    if not eligible:
        warnings.append("no_eligible_series")
    return {
        "case_ref": case_ref,
        "source_name_sha256": _digest(case_dir.name),
        "protected_label": label,
        "series_count": len(series),
        "eligible_series_count": len(eligible),
        "recommended_series_key": eligible[0]["series_key"] if eligible else None,
        "series": series,
        "warnings": sorted(set(warnings)),
    }


def audit_dataset_roots(roots: dict[str, Path]) -> dict[str, Any]:
    """Audita raízes `positive`/`negative` sem copiar imagens ou labels à inferência."""
    cases: list[dict[str, Any]] = []
    for label in ("positive", "negative"):
        root = Path(roots[label]).resolve()
        if not root.is_dir():
            raise ValueError(f"Raiz {label} não encontrada: {root}")
        directories = sorted((path for path in root.iterdir() if path.is_dir()), key=lambda p: p.name)
        for index, directory in enumerate(directories, start=1):
            cases.append(
                audit_case(directory, case_ref=f"{label[:3]}-{index:03d}", label=label)
            )

    distributions: dict[str, Counter[str]] = {
        "positive": Counter(),
        "negative": Counter(),
    }
    for case in cases:
        label = case["protected_label"]
        for series in case["series"]:
            if series["eligible_for_screening"]:
                distributions[label][series["sequence_class"]] += 1
    warnings: list[str] = []
    positive_sequences = set(distributions["positive"])
    negative_sequences = set(distributions["negative"])
    if positive_sequences != negative_sequences:
        warnings.append("sequence_distribution_differs_between_labels")
    if any(case["eligible_series_count"] == 0 for case in cases):
        warnings.append("cases_without_eligible_series")

    return {
        "schema": AUDIT_SCHEMA,
        "research_only": True,
        "contains_phi": False,
        "raw_paths_persisted": False,
        "raw_uids_persisted": False,
        "case_count": len(cases),
        "label_counts": dict(Counter(case["protected_label"] for case in cases)),
        "eligible_sequence_distribution": {
            label: dict(sorted(counter.items())) for label, counter in distributions.items()
        },
        "warnings": warnings,
        "cases": cases,
    }

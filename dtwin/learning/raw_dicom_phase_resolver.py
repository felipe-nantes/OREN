"""Fail-closed resolver for raw multiphase liver MRI DICOM studies.

The production classifier needs arterial, portal-venous and delayed T1 phases.
Folder names remain the most authoritative input, but a raw scanner export can
be resolved when the DICOM series themselves provide sufficient evidence.

No free-text DICOM value or UID is persisted.  The audit manifest contains only
normalized technical categories, counts and salted-independent SHA-256 hashes.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pydicom

from dtwin.core import PipelineError

ARTERIAL = "t1_arterial"
VENOUS = "t1_venous"
DELAYED = "t1_delayed"
REQUIRED_PHASES = (ARTERIAL, VENOUS, DELAYED)


class RawPhaseResolutionError(PipelineError):
    """A raw study could not be mapped safely onto three dynamic phases.

    The machine-readable ``code`` distinguishes a genuinely insufficient
    phase set (eligible for the explicitly limited single-phase workflow) from
    ambiguity, which must continue to fail closed.
    """

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = str(code)

_ARTERIAL = ("arterial", "art phase", "fase art", "t1 art")
_VENOUS = ("portal venous", "portal", "venous", "venosa", "venoso", "t1 pv")
_DELAYED = ("delayed", "delay", "late phase", "tardia", "tardio", "equilibrium", "equilibrio")
_DYNAMIC_T1 = ("t1", "vibe", "lava", "thrive", "dce", "dynamic", "dyn ", "fl3d")
_POST_CONTRAST = ("post", "+ c", "+c", "contrast", "gad", "ce ")
_EXCLUDED = (
    "t2", "haste", "dwi", "diff", "adc", "localizer", "scout", "survey",
    "in phase", "in ph", "out phase", "out ph", "opp phase", "opp ph", "opposed",
    # Derived reconstructions frequently copy the protocol and acquisition time
    # of their source phase. They are useful for review, but must never compete
    # with the original dynamic acquisition during temporal phase resolution.
    "sub_", "subtraction", " mpr ", " mip ",
)


def _hash(value: str, *, length: int = 24) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:length]


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _time_seconds(value: Any) -> float | None:
    text = re.sub(r"[^0-9.]", "", str(value or ""))
    if len(text.split(".", 1)[0]) < 6:
        return None
    try:
        base, _, fraction = text.partition(".")
        hour, minute, second = int(base[:2]), int(base[2:4]), int(base[4:6])
        result = hour * 3600 + minute * 60 + second
        if fraction:
            result += float(f"0.{fraction}")
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _normalized_text(ds: Any, source: Path) -> str:
    values = (
        getattr(ds, "SeriesDescription", ""),
        getattr(ds, "ProtocolName", ""),
        getattr(ds, "SequenceName", ""),
        getattr(ds, "ImageType", ""),
        source.parent.name,
    )
    text = " ".join(str(value) for value in values).lower()
    text = (text.replace("á", "a").replace("ã", "a").replace("â", "a")
            .replace("é", "e").replace("ê", "e").replace("í", "i")
            .replace("ó", "o").replace("ô", "o").replace("õ", "o")
            .replace("ú", "u").replace("ç", "c"))
    return re.sub(r"[^a-z0-9+._ -]+", " ", text)


def _orientation(ds: Any) -> str:
    try:
        values = [float(item) for item in getattr(ds, "ImageOrientationPatient", [])]
    except (TypeError, ValueError):
        return "unknown"
    if len(values) != 6:
        return "unknown"
    row, column = values[:3], values[3:]
    normal = (
        row[1] * column[2] - row[2] * column[1],
        row[2] * column[0] - row[0] * column[2],
        row[0] * column[1] - row[1] * column[0],
    )
    return ("sagittal", "coronal", "axial")[max(range(3), key=lambda index: abs(normal[index]))]


def _explicit_role(text: str) -> str | None:
    matches: list[str] = []
    if any(token in text for token in _ARTERIAL):
        matches.append(ARTERIAL)
    if any(token in text for token in _VENOUS):
        matches.append(VENOUS)
    if any(token in text for token in _DELAYED):
        matches.append(DELAYED)
    return matches[0] if len(matches) == 1 else None


@dataclass
class RawSeries:
    study_hash: str
    series_hash: str
    files: list[Path] = field(default_factory=list)
    frames: int = 0
    series_number: int | None = None
    acquisition_seconds: float | None = None
    orientation: str = "unknown"
    rows: int | None = None
    columns: int | None = None
    contrast_present: bool = False
    text: str = ""
    explicit_role: str | None = None

    @property
    def order_key(self) -> tuple[float, int, str]:
        timestamp = self.acquisition_seconds
        return (
            timestamp if timestamp is not None else float("inf"),
            self.series_number if self.series_number is not None else 10**9,
            self.series_hash,
        )

    @property
    def dynamic_t1(self) -> bool:
        return (
            not any(token in self.text for token in _EXCLUDED)
            and any(token in self.text for token in _DYNAMIC_T1)
        )

    @property
    def post_contrast(self) -> bool:
        return self.contrast_present or any(token in self.text for token in _POST_CONTRAST)


@dataclass(frozen=True)
class RawPhaseResolution:
    phase_dirs: dict[str, Path]
    method: str
    confidence: float
    manifest_path: Path


def _read_series(root: Path) -> list[RawSeries]:
    grouped: dict[tuple[str, str], RawSeries] = {}
    for source in sorted(Path(root).rglob("*")):
        if not source.is_file():
            continue
        try:
            ds = pydicom.dcmread(str(source), stop_before_pixels=True, force=True)
        except Exception:
            continue
        if str(getattr(ds, "Modality", "") or "").upper() != "MR":
            continue
        study_uid = str(getattr(ds, "StudyInstanceUID", "") or f"path:{root.resolve()}")
        series_uid = str(getattr(ds, "SeriesInstanceUID", "") or f"path:{source.parent.resolve()}")
        key = (study_uid, series_uid)
        if key not in grouped:
            text = _normalized_text(ds, source)
            acquisition_seconds = _time_seconds(getattr(ds, "AcquisitionTime", None))
            if acquisition_seconds is None:
                acquisition_seconds = _time_seconds(getattr(ds, "SeriesTime", None))
            grouped[key] = RawSeries(
                study_hash=_hash(study_uid),
                series_hash=_hash(series_uid),
                series_number=_safe_int(getattr(ds, "SeriesNumber", None)),
                acquisition_seconds=acquisition_seconds,
                orientation=_orientation(ds),
                rows=_safe_int(getattr(ds, "Rows", None)),
                columns=_safe_int(getattr(ds, "Columns", None)),
                contrast_present=bool(str(getattr(ds, "ContrastBolusAgent", "") or "").strip()),
                text=text,
                explicit_role=_explicit_role(text),
            )
        item = grouped[key]
        item.files.append(source)
        item.frames += max(_safe_int(getattr(ds, "NumberOfFrames", 1)) or 1, 1)
    return sorted(grouped.values(), key=lambda series: (series.study_hash, series.order_key))


def _geometry_compatible(items: list[RawSeries]) -> bool:
    rows = {item.rows for item in items if item.rows}
    columns = {item.columns for item in items if item.columns}
    orientations = {item.orientation for item in items if item.orientation != "unknown"}
    return len(rows) <= 1 and len(columns) <= 1 and orientations <= {"axial"}


def _select(series: list[RawSeries]) -> tuple[dict[str, RawSeries], str, float]:
    studies: dict[str, list[RawSeries]] = defaultdict(list)
    for item in series:
        studies[item.study_hash].append(item)

    geometry_rejected_a_complete_candidate = False

    explicit_candidates: list[dict[str, RawSeries]] = []
    for items in studies.values():
        by_role: dict[str, list[RawSeries]] = defaultdict(list)
        for item in items:
            if (
                item.explicit_role
                and item.frames >= 3
                and item.dynamic_t1
                and item.orientation in {"axial", "unknown"}
            ):
                by_role[item.explicit_role].append(item)
        if set(by_role) == set(REQUIRED_PHASES) and all(len(by_role[role]) == 1 for role in REQUIRED_PHASES):
            chosen = {role: by_role[role][0] for role in REQUIRED_PHASES}
            if _geometry_compatible(list(chosen.values())):
                explicit_candidates.append(chosen)
            else:
                geometry_rejected_a_complete_candidate = True
    if len(explicit_candidates) == 1:
        return explicit_candidates[0], "explicit_dicom_phase_semantics", 1.0
    if len(explicit_candidates) > 1:
        raise RawPhaseResolutionError(
            "Mais de um estudo contém um conjunto multifásico explicitamente rotulado.",
            code="ambiguous_explicit_multiphase_studies",
        )

    ordered_candidates: list[dict[str, RawSeries]] = []
    for items in studies.values():
        dynamic = [
            item for item in items
            if item.frames >= 3 and item.dynamic_t1 and item.post_contrast
            and item.orientation in {"axial", "unknown"}
        ]
        # When the scanner populated ContrastBolusAgent on at least three
        # acquisitions, that explicit technical signal outranks generic labels
        # such as "PRE-POST", which may also be present on pre-contrast series.
        contrast_tagged = [item for item in dynamic if item.contrast_present]
        if len(contrast_tagged) >= 3:
            dynamic = contrast_tagged
        if len(dynamic) < 3:
            continue
        if not _geometry_compatible(dynamic):
            geometry_rejected_a_complete_candidate = True
            continue
        # Temporal order must be grounded in Acquisition/Series time or, as a
        # fallback, in distinct SeriesNumber values. Ties are rejected.
        temporal = [item.acquisition_seconds for item in dynamic]
        if all(value is not None for value in temporal):
            dynamic.sort(key=lambda item: float(item.acquisition_seconds))
            keys = [float(item.acquisition_seconds) for item in dynamic]
        else:
            numbers = [item.series_number for item in dynamic]
            if any(value is None for value in numbers):
                continue
            dynamic.sort(key=lambda item: int(item.series_number))
            keys = [float(item.series_number) for item in dynamic]
        if len(keys) != len(set(keys)):
            continue
        ordered_candidates.append({
            ARTERIAL: dynamic[0],
            VENOUS: dynamic[1],
            DELAYED: dynamic[-1],
        })
    if len(ordered_candidates) == 1:
        return ordered_candidates[0], "ordered_axial_t1_postcontrast_series", 0.8
    if len(ordered_candidates) > 1:
        raise RawPhaseResolutionError(
            "Mais de um estudo possui séries T1 pós-contraste temporalmente elegíveis.",
            code="ambiguous_ordered_multiphase_studies",
        )
    if geometry_rejected_a_complete_candidate:
        raise RawPhaseResolutionError(
            "Um conjunto de fases com papéis/contagem suficientes foi encontrado, mas foi "
            "rejeitado por geometria incompatível entre as séries (linhas, colunas ou "
            "orientação divergentes). Confira se todas as séries do exame pertencem à mesma "
            "aquisição e grade.",
            code="geometry_incompatible_series",
        )
    raise RawPhaseResolutionError(
        "Não foi possível identificar arterial, venosa e tardia com segurança nos metadados DICOM. "
        "O exame precisa conter um único estudo com fases explicitamente rotuladas ou pelo menos "
        "três séries T1 axiais pós-contraste ordenáveis.",
        code="insufficient_dynamic_phases",
    )


def _materialize(selected: dict[str, RawSeries], destination: Path) -> dict[str, Path]:
    destination.mkdir(parents=True, exist_ok=True)
    phase_dirs: dict[str, Path] = {}
    for role in REQUIRED_PHASES:
        phase_dir = destination / role
        phase_dir.mkdir(parents=True, exist_ok=True)
        for index, source in enumerate(selected[role].files):
            target = phase_dir / f"{index:06d}.dcm"
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)
        phase_dirs[role] = phase_dir
    return phase_dirs


def resolve_raw_dicom_phases(root: Path, destination: Path) -> RawPhaseResolution:
    """Resolve and materialize a raw DICOM study into three internal folders."""
    root, destination = Path(root), Path(destination)
    series = _read_series(root)
    if not series:
        raise PipelineError("Nenhuma série DICOM de RM válida foi encontrada no envio bruto.")
    selected, method, confidence = _select(series)
    if destination.exists():
        shutil.rmtree(destination)
    phase_dirs = _materialize(selected, destination)
    manifest = {
        "schema": "argos-raw-dicom-phase-resolution-v1",
        "method": method,
        "confidence": confidence,
        "research_only": True,
        "clinical_use_allowed": False,
        "phi_persisted": False,
        "series_discovered": len(series),
        "selected": {
            role: {
                "study_hash": selected[role].study_hash,
                "series_hash": selected[role].series_hash,
                "files": len(selected[role].files),
                "frames": selected[role].frames,
                "series_number": selected[role].series_number,
                "orientation": selected[role].orientation,
            }
            for role in REQUIRED_PHASES
        },
    }
    manifest_path = destination / "phase_resolution_manifest.json"
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(manifest_path)
    return RawPhaseResolution(
        phase_dirs=phase_dirs,
        method=method,
        confidence=confidence,
        manifest_path=manifest_path,
    )


__all__ = [
    "RawPhaseResolution",
    "RawPhaseResolutionError",
    "resolve_raw_dicom_phases",
]

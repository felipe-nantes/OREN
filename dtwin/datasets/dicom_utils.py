"""Utilitários DICOM seguros para o registry de datasets."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pydicom

from dtwin.core import PipelineError


@dataclass(frozen=True)
class DicomSeries:
    series_uid_hash: str
    modality: str
    files: tuple[Path, ...]
    series_dir: Path
    series_description: str | None = None


def stable_hash(value: str, *, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def iter_candidate_dicom_files(root: Path) -> Iterable[Path]:
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            yield path


def read_dicom_header(path: Path):
    try:
        return pydicom.dcmread(str(path), stop_before_pixels=True, force=True)
    except Exception as exc:
        raise PipelineError(f"Falha ao ler cabeçalho DICOM: {path}") from exc


def discover_dicom_series(root: Path, *, modality: str = "MR") -> list[DicomSeries]:
    root = Path(root)
    grouped: dict[tuple[str, str], list[Path]] = {}
    metadata: dict[tuple[str, str], dict[str, str | None]] = {}
    ignored_non_matching = 0
    malformed = 0
    for path in iter_candidate_dicom_files(root):
        try:
            ds = read_dicom_header(path)
        except PipelineError:
            malformed += 1
            continue
        current_modality = str(getattr(ds, "Modality", "") or "").upper()
        if current_modality != modality:
            ignored_non_matching += 1
            continue
        series_uid = str(getattr(ds, "SeriesInstanceUID", "") or "").strip()
        if not series_uid:
            series_uid = f"path:{path.parent.resolve()}"
        try:
            parent_token = path.parent.resolve().relative_to(root.resolve()).as_posix()
        except ValueError as exc:
            raise PipelineError("Arquivo DICOM fora da raiz autorizada.") from exc
        key = (series_uid, parent_token)
        grouped.setdefault(key, []).append(path)
        metadata.setdefault(
            key,
            {
                "modality": current_modality,
                "series_description": str(getattr(ds, "SeriesDescription", "") or "").strip() or None,
            },
        )

    if malformed and not grouped:
        raise PipelineError(f"Nenhuma série DICOM válida encontrada em {root}.")
    series: list[DicomSeries] = []
    uid_directory_count: dict[str, int] = {}
    for series_uid, _parent_token in grouped:
        uid_directory_count[series_uid] = uid_directory_count.get(series_uid, 0) + 1
    for key, files in sorted(
        grouped.items(), key=lambda item: stable_hash("\0".join(item[0]))
    ):
        series_uid, parent_token = key
        common = Path(files[0]).parent
        identity = (
            series_uid
            if uid_directory_count[series_uid] == 1
            else f"{series_uid}\0directory:{parent_token}"
        )
        series.append(
            DicomSeries(
                series_uid_hash=stable_hash(identity, length=24),
                modality=str(metadata[key]["modality"] or modality),
                files=tuple(sorted(files)),
                series_dir=common,
                series_description=metadata[key]["series_description"],
            )
        )
    if not series:
        detail = " Arquivos de outra modalidade foram ignorados." if ignored_non_matching else ""
        raise PipelineError(f"Nenhuma série DICOM MR encontrada em {root}.{detail}")
    return series

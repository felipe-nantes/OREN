"""Authorized phase resolver for ``ARGOS_INTERNAL_BLIND_BENCHMARK_120_V1``.

The public benchmark intentionally stores series under opaque names such as
``series_001``.  Their clinical role is kept in a server-side conversion audit
and must never be uploaded to the browser, MedSigLIP, or a generated panel.

This module uses that audit only as a deterministic index.  It fails closed
unless the selected DICOM file has the exact SHA-256 and basic DICOM identity
declared for the blind case.  Returned provenance is deliberately safe: source
paths, original identifiers, labels, and non-selected audit rows are omitted.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pydicom

from dtwin.core import PipelineError

from .multiphase_ingest import ARTERIAL, DELAYED, REQUIRED_PHASES, VENOUS

BLIND_CASE_PATTERN = re.compile(r"^ARGOS-BLIND-\d{4}$")
AUDIT_FILENAME = "conversion_audit.json"
SERIES_FILENAME = "volume.dcm"
ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    ARTERIAL: ("t1_arterial", "t1_arterial_ttc_1"),
    VENOUS: ("t1_venous",),
    DELAYED: ("t1_delayed",),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_audit(path: Path) -> list[dict[str, Any]]:
    path = Path(path)
    if path.name != AUDIT_FILENAME or not path.is_file():
        raise PipelineError("Índice privado de fases autorizado não encontrado.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Índice privado de fases autorizado é inválido.") from exc
    if not isinstance(value, list) or not value:
        raise PipelineError("Índice privado de fases deve conter uma lista não vazia.")
    if not all(isinstance(row, dict) for row in value):
        raise PipelineError("Índice privado de fases contém registros inválidos.")
    return value


def _series_number(row: dict[str, Any]) -> int:
    raw = row.get("series_number")
    if isinstance(raw, bool):
        raise PipelineError("Índice privado contém número de série inválido.")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise PipelineError("Índice privado contém número de série inválido.") from exc
    if value < 1 or value > 999:
        raise PipelineError("Índice privado contém número de série fora do limite.")
    return value


def _expected_hash(row: dict[str, Any]) -> str:
    value = str(row.get("output_sha256") or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise PipelineError("Índice privado contém SHA-256 inválido.")
    return value


def _find_series_directory(case_dir: Path, series_number: int) -> Path:
    name = f"series_{series_number:03d}"
    candidates = sorted(
        path.resolve()
        for path in case_dir.rglob(name)
        if path.is_dir()
    )
    if len(candidates) != 1:
        state = "ausente" if not candidates else "ambígua"
        raise PipelineError(f"Série multifásica autorizada {state}: {name}.")
    try:
        candidates[0].relative_to(case_dir.resolve())
    except ValueError as exc:
        raise PipelineError("Série multifásica saiu do diretório autorizado do caso.") from exc
    return candidates[0]


def _validate_dicom_identity(
    dicom_path: Path,
    *,
    case_id: str,
    series_number: int,
) -> None:
    try:
        dataset = pydicom.dcmread(
            str(dicom_path),
            stop_before_pixels=True,
            force=False,
        )
    except Exception as exc:
        raise PipelineError("Arquivo da série multifásica não é um DICOM válido.") from exc
    if str(getattr(dataset, "PatientID", "")) != case_id:
        raise PipelineError("Identificador DICOM não corresponde ao caso cego.")
    if str(getattr(dataset, "Modality", "")).upper() != "MR":
        raise PipelineError("Série multifásica autorizada não possui modalidade MR.")
    try:
        observed_series = int(getattr(dataset, "SeriesNumber", -1))
    except (TypeError, ValueError) as exc:
        raise PipelineError("DICOM não possui SeriesNumber válido.") from exc
    if observed_series != series_number:
        raise PipelineError("SeriesNumber do DICOM diverge do índice autorizado.")


def summarize_authorized_blind_phase_eligibility(
    audit_path: Path,
) -> dict[str, Any]:
    """Return a label-free cohort preflight from the authorized phase index."""

    audit_path = Path(audit_path)
    rows = _load_audit(audit_path)
    by_case: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        case_id = str(row.get("blind_case_id") or "")
        if BLIND_CASE_PATTERN.fullmatch(case_id):
            by_case.setdefault(case_id, []).append(row)

    eligible: list[str] = []
    ineligible: list[dict[str, Any]] = []
    for case_id in sorted(by_case):
        case_rows = by_case[case_id]
        missing: list[str] = []
        ambiguous: list[str] = []
        selected_numbers: list[int] = []
        for phase in REQUIRED_PHASES:
            matches = [
                row
                for row in case_rows
                if str(row.get("role_private") or "") in ROLE_ALIASES[phase]
            ]
            if not matches:
                missing.append(phase)
                continue
            if len(matches) != 1:
                ambiguous.append(phase)
                continue
            selected_numbers.append(_series_number(matches[0]))
            _expected_hash(matches[0])
        reused = len(selected_numbers) != len(set(selected_numbers))
        if not missing and not ambiguous and not reused:
            eligible.append(case_id)
        else:
            ineligible.append(
                {
                    "case_id": case_id,
                    "missing_phases": missing,
                    "ambiguous_phases": ambiguous,
                    "series_reused": reused,
                }
            )
    return {
        "schema": "argos-authorized-blind-phase-eligibility-v1",
        "audit_sha256": _sha256(audit_path),
        "case_count": len(by_case),
        "eligible_count": len(eligible),
        "ineligible_count": len(ineligible),
        "eligible_case_ids": eligible,
        "ineligible_cases": ineligible,
        "labels_read": False,
        "lesion_masks_read": 0,
        "private_paths_persisted": False,
        "research_only": True,
    }


@dataclass(frozen=True)
class AuthorizedPhaseResolution:
    """Phase directories plus provenance safe to persist with inference."""

    case_id: str
    phase_dirs: dict[str, Path]
    audit_sha256: str
    selected_series: dict[str, dict[str, Any]]

    def safe_manifest(self) -> dict[str, Any]:
        return {
            "schema": "argos-authorized-blind-phase-resolution-v1",
            "resolution_mode": "server_side_private_audit_with_dicom_hash_gate",
            "case_id": self.case_id,
            "audit_sha256": self.audit_sha256,
            "selected_series": self.selected_series,
            "private_paths_persisted": False,
            "original_identifiers_persisted": False,
            "labels_read": False,
            "lesion_masks_read": 0,
            "research_only": True,
            "clinical_use_allowed": False,
        }


def resolve_authorized_blind_phase_folders(
    *,
    case_id: str,
    case_dir: Path,
    audit_path: Path,
) -> AuthorizedPhaseResolution:
    """Resolve opaque ``series_###`` folders for one authorized blind case.

    The function never trusts paths supplied by the audit.  It derives each
    directory from the numeric series identifier, constrains it to ``case_dir``,
    verifies the DICOM hash, and checks the de-identified DICOM identity.
    """

    case_id = str(case_id)
    if not BLIND_CASE_PATTERN.fullmatch(case_id):
        raise PipelineError("Identificador não pertence ao benchmark cego autorizado.")
    case_dir = Path(case_dir)
    if not case_dir.is_dir():
        raise PipelineError("Diretório do caso cego autorizado não encontrado.")

    audit_path = Path(audit_path)
    rows = [
        row
        for row in _load_audit(audit_path)
        if str(row.get("blind_case_id") or "") == case_id
    ]
    if not rows:
        raise PipelineError("Caso não consta no índice privado de fases autorizado.")

    phase_dirs: dict[str, Path] = {}
    selected_series: dict[str, dict[str, Any]] = {}
    for phase in REQUIRED_PHASES:
        accepted_roles = ROLE_ALIASES[phase]
        matches = [row for row in rows if str(row.get("role_private") or "") in accepted_roles]
        if len(matches) != 1:
            if not matches:
                raise PipelineError(f"Caso cego sem fase obrigatória autorizada: {phase}.")
            raise PipelineError(f"Caso cego possui fase autorizada ambígua: {phase}.")
        row = matches[0]
        series_number = _series_number(row)
        expected_hash = _expected_hash(row)
        series_dir = _find_series_directory(case_dir, series_number)
        dicom_path = series_dir / SERIES_FILENAME
        if not dicom_path.is_file():
            raise PipelineError("Série multifásica autorizada não contém volume.dcm.")
        dicom_files = sorted(
            path.resolve()
            for path in series_dir.rglob("*")
            if path.is_file() and path.suffix.lower() == ".dcm"
        )
        if dicom_files != [dicom_path.resolve()]:
            raise PipelineError(
                "Série multifásica autorizada contém DICOM adicional não autenticado."
            )
        observed_hash = _sha256(dicom_path)
        if observed_hash != expected_hash:
            raise PipelineError("Hash da série multifásica diverge do índice autorizado.")
        _validate_dicom_identity(
            dicom_path,
            case_id=case_id,
            series_number=series_number,
        )
        phase_dirs[phase] = series_dir
        selected_series[phase] = {
            "series_number": series_number,
            "dicom_sha256": observed_hash,
            "role": phase,
        }

    if len({path.resolve() for path in phase_dirs.values()}) != len(REQUIRED_PHASES):
        raise PipelineError("Índice privado reutiliza uma série em mais de uma fase.")

    return AuthorizedPhaseResolution(
        case_id=case_id,
        phase_dirs=phase_dirs,
        audit_sha256=_sha256(audit_path),
        selected_series=selected_series,
    )


__all__ = [
    "AUDIT_FILENAME",
    "AuthorizedPhaseResolution",
    "BLIND_CASE_PATTERN",
    "resolve_authorized_blind_phase_folders",
    "summarize_authorized_blind_phase_eligibility",
]

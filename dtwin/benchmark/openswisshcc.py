"""Preparação segura do conjunto de desenvolvimento OpenSwissHCC.

O módulo não conhece nem aceita caminhos de máscaras manuais de lesão. As
imagens são publicadas sob identificadores anônimos e o ground truth fica em uma
árvore protegida, separada dos inputs de inferência.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterable
from zipfile import ZipFile, ZipInfo

from dtwin.core import PipelineError


DATASET_ID = "openswisshcc-v1"
INPUT_DATASET_ALIAS = "public_liver_mri_v1"
DEVELOPMENT_ARCHIVES = {
    "sub-001-sub-044.zip": {
        "md5": "4daf23886b23639514a689082aa5578c",
        "subjects": frozenset(f"sub-{number:03d}" for number in range(1, 45)),
    },
    "sub-088-sub-132.zip": {
        "md5": "df0280231b3b7cf3a4628fa53d06a611",
        "subjects": frozenset(f"sub-{number:03d}" for number in range(89, 133)),
    },
}
DEVELOPMENT_SUBJECTS = frozenset().union(
    *(record["subjects"] for record in DEVELOPMENT_ARCHIVES.values())
)
HOLDOUT_SUBJECTS = frozenset(f"sub-{number:03d}" for number in range(45, 89))
HOLDOUT_ARCHIVE = {
    "name": "sub-044-sub-088.zip",
    "md5": "201ea2266c1874cc95105f5f0a9fcf7c",
    "subjects": HOLDOUT_SUBJECTS,
}
FORBIDDEN_INPUT_TERMS = ("lesion", "manual", "ground_truth", "label", "truth")
_SUBJECT_RE = re.compile(r"^sub-(\d{3})$")
_PHASE_RE = re.compile(r"_phase-(.+?)_T1w\.nii\.gz$")
_T2_RE = re.compile(r"_acq-([A-Za-z0-9-]+)_T2w\.nii\.gz$")
_TRACE_RE = re.compile(r"_run-([A-Za-z0-9-]+)_desc-TRACE_dwi\.nii\.gz$")


@dataclass(frozen=True)
class SubjectLabel:
    subject_id: str
    label: str


@dataclass(frozen=True)
class SelectedMember:
    archive: Path
    info: ZipInfo
    subject_id: str
    role: str
    relative_destination: Path


def md5_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with Path(path).open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def anonymized_case_id(subject_id: str) -> str:
    if not _SUBJECT_RE.fullmatch(subject_id):
        raise PipelineError(f"ID OpenSwissHCC inválido: {subject_id!r}.")
    digest = hashlib.sha256(f"{DATASET_ID}:{subject_id}".encode("utf-8")).hexdigest()
    return f"anon-openswiss-{digest[:16]}"


def load_subject_labels(participants_path: Path) -> dict[str, SubjectLabel]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    try:
        with Path(participants_path).open(encoding="utf-8", newline="") as source:
            for row in csv.DictReader(source, delimiter="\t"):
                grouped[str(row.get("ID", ""))].append(row)
    except OSError as exc:
        raise PipelineError(f"Não foi possível ler participants.tsv: {exc}") from exc
    if set(grouped) != DEVELOPMENT_SUBJECTS | HOLDOUT_SUBJECTS:
        missing = sorted((DEVELOPMENT_SUBJECTS | HOLDOUT_SUBJECTS) - set(grouped))
        extra = sorted(set(grouped) - (DEVELOPMENT_SUBJECTS | HOLDOUT_SUBJECTS))
        raise PipelineError(f"Subjects inesperados em participants.tsv; missing={missing}, extra={extra}.")
    labels = {
        subject: SubjectLabel(
            subject_id=subject,
            label="POSITIVE" if any(row.get("HCC") == "1" for row in rows) else "NEGATIVE",
        )
        for subject, rows in grouped.items()
    }
    positive = sum(item.label == "POSITIVE" for item in labels.values())
    negative = sum(item.label == "NEGATIVE" for item in labels.values())
    if (positive, negative) != (63, 69):
        raise PipelineError(
            f"Distribuição OpenSwissHCC incompatível: positive={positive}, negative={negative}."
        )
    return labels


def validate_splits() -> None:
    if DEVELOPMENT_SUBJECTS & HOLDOUT_SUBJECTS:
        raise PipelineError("Split OpenSwissHCC contém sujeitos sobrepostos.")
    if DEVELOPMENT_SUBJECTS | HOLDOUT_SUBJECTS != {
        f"sub-{number:03d}" for number in range(1, 133)
    }:
        raise PipelineError("Split OpenSwissHCC não cobre exatamente os 132 sujeitos.")


def _safe_member_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise PipelineError(f"Membro ZIP inseguro: {name!r}.")
    return path


def _subject_from_member(path: PurePosixPath) -> str | None:
    if not path.parts:
        return None
    return path.parts[0] if _SUBJECT_RE.fullmatch(path.parts[0]) else None


def _canonical_image_role(path: PurePosixPath) -> tuple[str, Path] | None:
    if len(path.parts) != 3 or not path.name.endswith(".nii.gz"):
        return None
    subject, group, name = path.parts
    if group == "dyn" and "_acq-water_" in name:
        match = _PHASE_RE.search(name)
        if not match:
            return None
        phase = re.sub(r"[^a-z0-9]+", "_", match.group(1).lower()).strip("_")
        role = f"t1_{phase}"
        return role, Path("dyn") / f"{role}.nii.gz"
    if group == "anat":
        match = _T2_RE.search(name)
        if not match:
            return None
        acquisition = re.sub(r"[^a-z0-9]+", "_", match.group(1).lower()).strip("_")
        role = f"t2_{acquisition}"
        return role, Path("anat") / f"{role}.nii.gz"
    if group == "dwi" and "_desc-ADC_dwi.nii.gz" in name:
        return "dwi_adc", Path("dwi") / "dwi_adc.nii.gz"
    if group == "dwi":
        match = _TRACE_RE.search(name)
        if not match:
            return None
        run = re.sub(r"[^a-z0-9]+", "_", match.group(1).lower()).strip("_")
        role = f"dwi_trace_run_{run}"
        return role, Path("dwi") / f"{role}.nii.gz"
    return None


def _canonical_mask_role(path: Path) -> tuple[str, Path] | None:
    name = path.name
    if not name.endswith("-liver_seg.nii.gz") or "_acq-water_" not in name:
        return None
    match = re.search(r"_phase-(.+?)_T1w-liver_seg\.nii\.gz$", name)
    if not match:
        return None
    phase = re.sub(r"[^a-z0-9]+", "_", match.group(1).lower()).strip("_")
    role = f"liver_mask_{phase}"
    return role, Path("masks") / f"{role}.nii.gz"


def inspect_development_archive(archive: Path) -> tuple[set[str], list[SelectedMember]]:
    archive = Path(archive)
    expected = DEVELOPMENT_ARCHIVES.get(archive.name)
    if expected is None:
        raise PipelineError(f"Arquivo não autorizado para desenvolvimento: {archive.name!r}.")
    if not archive.is_file():
        raise PipelineError(f"Arquivo OpenSwissHCC ausente: {archive}.")
    actual_md5 = md5_file(archive)
    if actual_md5 != expected["md5"]:
        raise PipelineError(
            f"MD5 incompatível para {archive.name}: {actual_md5} != {expected['md5']}."
        )
    subjects: set[str] = set()
    selected: list[SelectedMember] = []
    destinations: set[tuple[str, str]] = set()
    with ZipFile(archive) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            member_path = _safe_member_path(info.filename)
            subject = _subject_from_member(member_path)
            if subject is None:
                continue
            subjects.add(subject)
            if subject in HOLDOUT_SUBJECTS:
                raise PipelineError(
                    f"Arquivo de desenvolvimento contém sujeito do holdout: {subject}."
                )
            canonical = _canonical_image_role(member_path)
            if canonical is None:
                continue
            role, destination = canonical
            key = (subject, destination.as_posix())
            if key in destinations:
                raise PipelineError(f"Colisão de destino para {subject}: {destination}.")
            destinations.add(key)
            selected.append(
                SelectedMember(
                    archive=archive,
                    info=info,
                    subject_id=subject,
                    role=role,
                    relative_destination=destination,
                )
            )
    if subjects != expected["subjects"]:
        raise PipelineError(
            f"Fronteiras inesperadas em {archive.name}: "
            f"missing={sorted(expected['subjects'] - subjects)}, "
            f"extra={sorted(subjects - expected['subjects'])}."
        )
    return subjects, selected


def _copy_stream_atomic(source: BinaryIO, destination: Path) -> tuple[int, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".tmp-{uuid.uuid4().hex}")
    digest = hashlib.sha256()
    size = 0
    try:
        with temporary.open("wb") as output:
            while chunk := source.read(8 * 1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return size, digest.hexdigest()


def _write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_jsonl_atomic(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            for row in rows:
                output.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_subject_roles(subject: str, roles: set[str]) -> None:
    required = {"t1_native", "t1_venous", "t1_delayed"}
    missing = required - roles
    if missing:
        raise PipelineError(f"{subject} sem fases obrigatórias: {sorted(missing)}.")
    if not any(role.startswith("t1_arterial") for role in roles):
        raise PipelineError(f"{subject} sem fase arterial acq-water.")
    t1_phases = {role.removeprefix("t1_") for role in roles if role.startswith("t1_")}
    mask_phases = {
        role.removeprefix("liver_mask_")
        for role in roles
        if role.startswith("liver_mask_")
    }
    missing_masks = t1_phases - mask_phases
    if missing_masks:
        raise PipelineError(
            f"{subject} sem máscara hepática automática para as fases: {sorted(missing_masks)}."
        )


def prepare_development_dataset(
    *,
    participants_path: Path,
    archives: Iterable[Path],
    allowed_derivatives_dir: Path,
    output_dir: Path,
) -> dict[str, object]:
    """Prepare 88 development cases without exposing labels to ``inputs/``."""
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError(f"Destino já existe; preparação não sobrescreve dados: {output_dir}.")
    validate_splits()
    labels = load_subject_labels(participants_path)
    archive_paths = tuple(sorted((Path(path) for path in archives), key=lambda p: p.name))
    if {path.name for path in archive_paths} != set(DEVELOPMENT_ARCHIVES):
        raise PipelineError("Devem ser fornecidos exatamente os dois arquivos de desenvolvimento.")
    staging = output_dir.with_name(f".{output_dir.name}.staging.{uuid.uuid4().hex}")
    staging.mkdir(parents=True)
    input_records: dict[str, dict[str, object]] = {}
    protected_records: dict[str, dict[str, object]] = {}
    source_records: list[dict[str, object]] = []
    try:
        for subject in sorted(DEVELOPMENT_SUBJECTS):
            case_id = anonymized_case_id(subject)
            input_records[subject] = {
                "schema": "argos-public-liver-mri-input-v1",
                "case_id": case_id,
                "dataset_id": INPUT_DATASET_ALIAS,
                "split": "development",
                "research_only": True,
                "clinical_use_allowed": False,
                "files": [],
            }
            protected_records[subject] = {
                "schema": "argos-openswisshcc-ground-truth-v1",
                "case_id": case_id,
                "public_subject_id": subject,
                "label": labels[subject].label,
                "target_condition": "hcc_presence",
                "label_basis": "openswisshcc_participants_tsv",
                "review_status": "dataset_expert_validated",
            }

        for archive in archive_paths:
            _, members = inspect_development_archive(archive)
            with ZipFile(archive) as zf:
                for member in members:
                    case_id = anonymized_case_id(member.subject_id)
                    destination = staging / "inputs" / case_id / member.relative_destination
                    with zf.open(member.info) as source:
                        size, digest = _copy_stream_atomic(source, destination)
                    input_records[member.subject_id]["files"].append(
                        {
                            "role": member.role,
                            "relative_path": destination.relative_to(staging / "inputs").as_posix(),
                            "bytes": size,
                            "sha256": digest,
                        }
                    )
                    source_records.append(
                        {
                            "case_id": case_id,
                            "public_subject_id": member.subject_id,
                            "source_archive": archive.name,
                            "source_member": member.info.filename,
                            "role": member.role,
                        }
                    )

        allowed_derivatives_dir = Path(allowed_derivatives_dir).resolve()
        for subject in sorted(DEVELOPMENT_SUBJECTS):
            subject_masks = allowed_derivatives_dir / subject / "dyn"
            if not subject_masks.is_dir():
                raise PipelineError(f"Máscaras hepáticas automáticas ausentes para {subject}.")
            seen_mask_roles: set[str] = set()
            for source_mask in sorted(subject_masks.glob("*.nii.gz")):
                lowered = source_mask.name.lower()
                if any(term in lowered for term in FORBIDDEN_INPUT_TERMS):
                    raise PipelineError(f"Derivado proibido na origem permitida: {source_mask.name}.")
                canonical = _canonical_mask_role(source_mask)
                if canonical is None:
                    continue
                role, relative = canonical
                if role in seen_mask_roles:
                    raise PipelineError(f"Máscara duplicada para {subject}: {role}.")
                seen_mask_roles.add(role)
                case_id = anonymized_case_id(subject)
                destination = staging / "inputs" / case_id / relative
                with source_mask.open("rb") as source:
                    size, digest = _copy_stream_atomic(source, destination)
                input_records[subject]["files"].append(
                    {
                        "role": role,
                        "relative_path": destination.relative_to(staging / "inputs").as_posix(),
                        "bytes": size,
                        "sha256": digest,
                    }
                )
                source_records.append(
                    {
                        "case_id": case_id,
                        "public_subject_id": subject,
                        "source_archive": "derivatives.zip",
                        "source_member": source_mask.relative_to(allowed_derivatives_dir).as_posix(),
                        "role": role,
                    }
                )

        for subject, record in input_records.items():
            files = record["files"]
            roles = {str(item["role"]) for item in files}
            _validate_subject_roles(subject, roles)
            if not any(role.startswith("liver_mask_") for role in roles):
                raise PipelineError(f"{subject} sem máscara hepática automática.")
            serialized = json.dumps(record, ensure_ascii=False).lower()
            if any(term in serialized for term in FORBIDDEN_INPUT_TERMS):
                raise PipelineError(f"Manifesto de input contém termo protegido para {subject}.")
            if "sub-" in serialized:
                raise PipelineError(f"Manifesto de input expõe ID público para {subject}.")

        sorted_inputs = [input_records[key] for key in sorted(input_records)]
        sorted_ground_truth = [protected_records[key] for key in sorted(protected_records)]
        _write_jsonl_atomic(staging / "manifests" / "development_inputs.jsonl", sorted_inputs)
        _write_jsonl_atomic(
            staging / "protected_ground_truth" / "development_labels.jsonl",
            sorted_ground_truth,
        )
        _write_jsonl_atomic(
            staging / "protected_ground_truth" / "source_map.jsonl",
            sorted(source_records, key=lambda row: (str(row["case_id"]), str(row["role"]))),
        )
        positive = sum(labels[subject].label == "POSITIVE" for subject in DEVELOPMENT_SUBJECTS)
        negative = len(DEVELOPMENT_SUBJECTS) - positive
        protocol = {
            "schema": "argos-openswisshcc-preparation-v1",
            "dataset_id": DATASET_ID,
            "split": "development",
            "case_count": len(sorted_inputs),
            "protected_label_counts": {"positive": positive, "negative": negative},
            "holdout_case_count": len(HOLDOUT_SUBJECTS),
            "holdout_archive_downloaded": False,
            "manual_lesion_masks_copied": 0,
            "input_root": "inputs",
            "input_manifest": "manifests/development_inputs.jsonl",
            "protected_ground_truth": "protected_ground_truth/development_labels.jsonl",
            "requires_human_review": True,
            "research_only": True,
            "clinical_use_allowed": False,
            "development_archives": [
                {"name": path.name, "md5": DEVELOPMENT_ARCHIVES[path.name]["md5"]}
                for path in archive_paths
            ],
        }
        _write_json_atomic(staging / "protocol.json", protocol)
        os.replace(staging, output_dir)
        return protocol
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise







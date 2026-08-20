"""Preparação estritamente label-blind do holdout OpenSwissHCC 045–088.

Este módulo deliberadamente não recebe ``participants.tsv`` e não cria ground
truth. Ele publica apenas volumes de RM e máscaras hepáticas automáticas já
isoladas, mantendo a proveniência pública fora da árvore usada na inferência.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from zipfile import ZipFile

from dtwin.benchmark.openswisshcc import (
    DATASET_ID,
    FORBIDDEN_INPUT_TERMS,
    HOLDOUT_ARCHIVE,
    HOLDOUT_SUBJECTS,
    INPUT_DATASET_ALIAS,
    SelectedMember,
    _canonical_image_role,
    _canonical_mask_role,
    _copy_stream_atomic,
    _safe_member_path,
    _subject_from_member,
    _validate_subject_roles,
    _write_json_atomic,
    _write_jsonl_atomic,
    anonymized_case_id,
    md5_file,
)
from dtwin.core import PipelineError

HOLDOUT_PREPARATION_SCHEMA = "argos-openswisshcc-holdout-label-blind-preparation-v1"
HOLDOUT_INPUT_SCHEMA = "argos-public-liver-mri-holdout-input-v1"
HOLDOUT_AUDIT_SCHEMA = "argos-openswisshcc-holdout-label-blind-audit-v1"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_holdout_archive(archive: Path) -> tuple[set[str], list[SelectedMember]]:
    """Validate the one authorized archive and select image volumes only."""

    archive = Path(archive)
    if archive.name != HOLDOUT_ARCHIVE["name"]:
        raise PipelineError(f"Arquivo não autorizado para holdout: {archive.name!r}.")
    if not archive.is_file():
        raise PipelineError(f"Arquivo OpenSwissHCC ausente: {archive}.")
    actual_md5 = md5_file(archive)
    if actual_md5 != HOLDOUT_ARCHIVE["md5"]:
        raise PipelineError(
            f"MD5 incompatível para {archive.name}: "
            f"{actual_md5} != {HOLDOUT_ARCHIVE['md5']}."
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
            if subject not in HOLDOUT_SUBJECTS:
                raise PipelineError(
                    f"Arquivo de holdout contém sujeito fora de 045–088: {subject}."
                )
            canonical = _canonical_image_role(member_path)
            if canonical is None:
                continue
            role, destination = canonical
            lowered = f"{role}/{destination.as_posix()}/{info.filename}".lower()
            if any(term in lowered for term in FORBIDDEN_INPUT_TERMS):
                raise PipelineError(f"Membro protegido selecionado no holdout: {info.filename}.")
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

    expected_subjects = set(HOLDOUT_ARCHIVE["subjects"])
    if subjects != expected_subjects:
        raise PipelineError(
            f"Fronteiras inesperadas em {archive.name}: "
            f"missing={sorted(expected_subjects - subjects)}, "
            f"extra={sorted(subjects - expected_subjects)}."
        )
    return subjects, selected


def prepare_holdout_dataset_label_blind(
    *,
    archive: Path,
    allowed_derivatives_dir: Path,
    output_dir: Path,
) -> dict[str, object]:
    """Prepare 44 holdout cases without accepting or reading labels."""

    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError(f"Destino já existe; preparação não sobrescreve dados: {output_dir}.")
    archive = Path(archive).resolve()
    allowed_derivatives_dir = Path(allowed_derivatives_dir).resolve()
    staging = output_dir.with_name(f".{output_dir.name}.staging.{uuid.uuid4().hex}")
    staging.mkdir(parents=True)
    input_records: dict[str, dict[str, object]] = {}
    source_records: list[dict[str, object]] = []
    try:
        _, members = inspect_holdout_archive(archive)
        for subject in sorted(HOLDOUT_SUBJECTS):
            case_id = anonymized_case_id(subject)
            input_records[subject] = {
                "schema": HOLDOUT_INPUT_SCHEMA,
                "case_id": case_id,
                "dataset_id": INPUT_DATASET_ALIAS,
                "split": "holdout_blind",
                "research_only": True,
                "clinical_use_allowed": False,
                "files": [],
            }

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

        for subject in sorted(HOLDOUT_SUBJECTS):
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
                        "source_archive": "automated_liver_annotations_only",
                        "source_member": source_mask.relative_to(allowed_derivatives_dir).as_posix(),
                        "role": role,
                    }
                )

        for subject, record in input_records.items():
            roles = {str(item["role"]) for item in record["files"]}
            _validate_subject_roles(subject, roles)
            serialized = json.dumps(record, ensure_ascii=False).lower()
            if any(term in serialized for term in FORBIDDEN_INPUT_TERMS):
                raise PipelineError(f"Manifesto de input contém termo protegido para {subject}.")
            if "sub-" in serialized or "hcc" in serialized:
                raise PipelineError(f"Manifesto de input expõe informação protegida para {subject}.")

        sorted_inputs = [input_records[subject] for subject in sorted(HOLDOUT_SUBJECTS)]
        _write_jsonl_atomic(staging / "manifests" / "holdout_inputs.jsonl", sorted_inputs)
        _write_jsonl_atomic(
            staging / "protected_provenance" / "source_map.jsonl",
            sorted(source_records, key=lambda row: (str(row["case_id"]), str(row["role"]))),
        )
        protocol = {
            "schema": HOLDOUT_PREPARATION_SCHEMA,
            "dataset_id": DATASET_ID,
            "split": "holdout_blind",
            "case_count": len(sorted_inputs),
            "subject_range": "045-088",
            "labels_read": False,
            "participants_tsv_read": False,
            "ground_truth_created": False,
            "lesion_masks_read": 0,
            "manual_lesion_masks_copied": 0,
            "input_root": "inputs",
            "input_manifest": "manifests/holdout_inputs.jsonl",
            "protected_provenance": "protected_provenance/source_map.jsonl",
            "archive": {"name": archive.name, "md5": HOLDOUT_ARCHIVE["md5"]},
            "allowed_derivatives": "automated_liver_annotations_only",
            "requires_human_review": True,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        _write_json_atomic(staging / "protocol.json", protocol)
        os.replace(staging, output_dir)
        return protocol
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def audit_prepared_holdout_label_blind(prepared_dir: Path) -> dict[str, object]:
    """Verify completeness, hashes and absence of protected content in inputs."""

    prepared_dir = Path(prepared_dir).resolve()
    protocol_path = prepared_dir / "protocol.json"
    manifest_path = prepared_dir / "manifests" / "holdout_inputs.jsonl"
    provenance_path = prepared_dir / "protected_provenance" / "source_map.jsonl"
    try:
        protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
        rows = [
            json.loads(line)
            for line in manifest_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        provenance = [
            json.loads(line)
            for line in provenance_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Holdout preparado possui manifesto inválido ou ausente.") from exc

    if protocol.get("schema") != HOLDOUT_PREPARATION_SCHEMA:
        raise PipelineError("Schema de preparação do holdout inválido.")
    required_false = ("labels_read", "participants_tsv_read", "ground_truth_created")
    if any(protocol.get(field) is not False for field in required_false):
        raise PipelineError("Protocolo não comprova preparação label-blind.")
    if protocol.get("lesion_masks_read") != 0 or protocol.get("manual_lesion_masks_copied") != 0:
        raise PipelineError("Protocolo indica acesso a máscara de lesão.")
    if (prepared_dir / "protected_ground_truth").exists():
        raise PipelineError("Árvore de ground truth não é permitida no holdout preparado.")
    if len(rows) != len(HOLDOUT_SUBJECTS) or protocol.get("case_count") != len(rows):
        raise PipelineError("Quantidade de casos do holdout preparado é inválida.")

    case_ids: set[str] = set()
    manifested: dict[str, dict[str, object]] = {}
    image_count = 0
    liver_mask_count = 0
    total_bytes = 0
    tree_digest = hashlib.sha256()
    inputs_root = (prepared_dir / "inputs").resolve()
    for row in rows:
        serialized = json.dumps(row, ensure_ascii=False, sort_keys=True).lower()
        if any(term in serialized for term in FORBIDDEN_INPUT_TERMS):
            raise PipelineError("Manifesto de input do holdout contém termo protegido.")
        if "sub-" in serialized or "hcc" in serialized:
            raise PipelineError("Manifesto de input do holdout expõe sujeito ou diagnóstico.")
        if row.get("schema") != HOLDOUT_INPUT_SCHEMA or row.get("split") != "holdout_blind":
            raise PipelineError("Registro de input do holdout possui schema ou split inválido.")
        case_id = str(row.get("case_id", ""))
        if not case_id or case_id in case_ids:
            raise PipelineError("Case ID ausente ou duplicado no holdout.")
        case_ids.add(case_id)
        roles: set[str] = set()
        for item in row.get("files", []):
            relative = Path(str(item.get("relative_path", "")))
            path = (inputs_root / relative).resolve()
            try:
                path.relative_to(inputs_root)
            except ValueError as exc:
                raise PipelineError("Caminho de input escapa da raiz do holdout.") from exc
            relative_key = path.relative_to(inputs_root).as_posix()
            if relative_key in manifested:
                raise PipelineError("Arquivo duplicado no manifesto do holdout.")
            if not path.is_file() or not path.name.endswith(".nii.gz"):
                raise PipelineError(f"Arquivo de input ausente ou inválido: {relative_key}.")
            actual_bytes = path.stat().st_size
            actual_sha256 = _sha256_file(path)
            if actual_bytes != item.get("bytes") or actual_sha256 != item.get("sha256"):
                raise PipelineError(f"Hash ou tamanho incompatível: {relative_key}.")
            role = str(item.get("role", ""))
            roles.add(role)
            image_count += not role.startswith("liver_mask_")
            liver_mask_count += role.startswith("liver_mask_")
            total_bytes += actual_bytes
            manifested[relative_key] = item
            tree_digest.update(relative_key.encode("utf-8"))
            tree_digest.update(b"\0")
            tree_digest.update(actual_sha256.encode("ascii"))
            tree_digest.update(b"\n")
        public_subject = next(
            (
                str(item.get("public_subject_id"))
                for item in provenance
                if item.get("case_id") == case_id
            ),
            "",
        )
        _validate_subject_roles(public_subject, roles)

    actual_files = {
        path.resolve().relative_to(inputs_root).as_posix()
        for path in inputs_root.rglob("*")
        if path.is_file()
    }
    if actual_files != set(manifested):
        raise PipelineError(
            "Árvore de inputs diverge do manifesto: "
            f"missing={sorted(set(manifested) - actual_files)}, "
            f"extra={sorted(actual_files - set(manifested))}."
        )

    provenance_text = json.dumps(provenance, ensure_ascii=False).lower()
    if any(term in provenance_text for term in ("label", "truth", "lesion", "diagnosis", "hcc")):
        raise PipelineError("Proveniência protegida contém ground truth ou diagnóstico.")
    provenance_subjects = {str(item.get("public_subject_id", "")) for item in provenance}
    if provenance_subjects != set(HOLDOUT_SUBJECTS):
        raise PipelineError("Proveniência não cobre exatamente os sujeitos 045–088.")

    return {
        "schema": HOLDOUT_AUDIT_SCHEMA,
        "status": "label_blind_holdout_preparation_verified",
        "case_count": len(rows),
        "input_file_count": len(actual_files),
        "image_volume_count": int(image_count),
        "automatic_liver_mask_count": int(liver_mask_count),
        "total_input_bytes": total_bytes,
        "input_tree_sha256": tree_digest.hexdigest(),
        "input_manifest_sha256": _sha256_file(manifest_path),
        "protocol_sha256": _sha256_file(protocol_path),
        "labels_read": False,
        "participants_tsv_read": False,
        "ground_truth_created": False,
        "lesion_masks_read": 0,
        "manual_lesion_masks_copied": 0,
        "public_subject_ids_in_inference_inputs": False,
        "holdout_subject_range": "045-088",
        "requires_human_review": True,
        "research_only": True,
        "clinical_use_allowed": False,
    }

"""Extração segura dos transforms T1 permitidos do OpenSwissHCC.

Somente parâmetros de registro necessários para alinhar fases T1 à grade
venosa são materializados. Máscaras manuais e anotações de lesão não fazem
parte da API deste módulo.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, ZipInfo

from dtwin.benchmark.openswisshcc import (
    DEVELOPMENT_SUBJECTS,
    HOLDOUT_SUBJECTS,
    anonymized_case_id,
    md5_file,
)
from dtwin.core import PipelineError

DERIVATIVES_MD5 = "e7df6554b20aeb941d697710e4201c18"
TRANSFORM_PREFIX = PurePosixPath("derivatives/T1_registration_transforms")
FORBIDDEN_TERMS = ("lesion", "manual", "ground_truth", "label", "truth")


def _safe_member(info: ZipInfo) -> PurePosixPath:
    name = info.filename
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise PipelineError(f"Membro ZIP inseguro: {name!r}.")
    return path


def _selected_source_names(names: set[str]) -> dict[str, str]:
    triple_suffix = "arterial_TTC_3_to_venous.txt"
    simple_suffix = "arterial_to_venous.txt"
    if any(name.endswith(triple_suffix) for name in names):
        arterial_suffix = triple_suffix
        arterial_source_phase = "arterial_ttc_3"
    elif any(name.endswith(simple_suffix) for name in names):
        arterial_suffix = simple_suffix
        arterial_source_phase = "arterial"
    else:
        raise PipelineError("Transform arterial direto para venosa ausente.")
    selected = {
        "arterial_to_venous_stage_0": f"pairwise_registration_transform_parameters_0_{arterial_suffix}",
        "arterial_to_venous_stage_1": f"pairwise_registration_transform_parameters_1_{arterial_suffix}",
        "delayed_to_venous_stage_0": "pairwise_registration_transform_parameters_0_delayed_to_venous.txt",
        "delayed_to_venous_stage_1": "pairwise_registration_transform_parameters_1_delayed_to_venous.txt",
        "groupwise": "groupwise_registration_transform_parameters_0.txt",
    }
    missing = set(selected.values()) - names
    if missing:
        raise PipelineError(f"Transform(s) obrigatório(s) ausente(s): {sorted(missing)}.")
    selected["arterial_source_phase"] = arterial_source_phase
    return selected


def _copy_atomic(source, destination: Path) -> tuple[int, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".tmp-{uuid.uuid4().hex}")
    digest = hashlib.sha256()
    size = 0
    try:
        with temporary.open("wb") as output:
            while chunk := source.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return size, digest.hexdigest()


def _write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".tmp-{uuid.uuid4().hex}")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def extract_development_registration_transforms(
    derivatives_zip: Path,
    output_dir: Path,
) -> dict[str, object]:
    """Extraia transforms T1 whitelistados dos 88 casos de desenvolvimento."""
    derivatives_zip = Path(derivatives_zip).resolve()
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError(f"Destino já existe; extração não sobrescreve dados: {output_dir}.")
    if not derivatives_zip.is_file():
        raise PipelineError(f"derivatives.zip ausente: {derivatives_zip}.")
    actual_md5 = md5_file(derivatives_zip)
    if actual_md5 != DERIVATIVES_MD5:
        raise PipelineError(f"MD5 inválido para derivatives.zip: {actual_md5}.")

    staging = output_dir.with_name(f".{output_dir.name}.staging.{uuid.uuid4().hex}")
    staging.mkdir(parents=True)
    try:
        by_subject: dict[str, dict[str, ZipInfo]] = {
            subject: {} for subject in DEVELOPMENT_SUBJECTS
        }
        with ZipFile(derivatives_zip) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                path = _safe_member(info)
                if len(path.parts) != 5 or PurePosixPath(*path.parts[:2]) != TRANSFORM_PREFIX:
                    continue
                subject, group, name = path.parts[2], path.parts[3], path.parts[4]
                if group != "dyn" or not name.endswith(".txt"):
                    continue
                lowered = path.as_posix().lower()
                if any(term in lowered for term in FORBIDDEN_TERMS):
                    raise PipelineError(f"Transform proibido encontrado: {path.as_posix()}.")
                if subject in HOLDOUT_SUBJECTS:
                    continue
                if subject in DEVELOPMENT_SUBJECTS:
                    by_subject[subject][name] = info

            records: list[dict[str, object]] = []
            for subject in sorted(DEVELOPMENT_SUBJECTS):
                source_by_name = by_subject[subject]
                selected = _selected_source_names(set(source_by_name))
                arterial_source_phase = selected.pop("arterial_source_phase")
                case_id = anonymized_case_id(subject)
                files: list[dict[str, object]] = []
                for role, source_name in sorted(selected.items()):
                    destination = staging / "transforms" / case_id / f"{role}.txt"
                    with archive.open(source_by_name[source_name]) as source:
                        size, digest = _copy_atomic(source, destination)
                    files.append(
                        {
                            "role": role,
                            "relative_path": destination.relative_to(staging).as_posix(),
                            "bytes": size,
                            "sha256": digest,
                        }
                    )
                records.append(
                    {
                        "schema": "argos-public-liver-mri-registration-v1",
                        "case_id": case_id,
                        "reference_phase": "venous",
                        "arterial_source_phase": arterial_source_phase,
                        "files": files,
                        "research_only": True,
                        "clinical_use_allowed": False,
                    }
                )

        if len(records) != len(DEVELOPMENT_SUBJECTS):
            raise PipelineError("Quantidade inesperada de casos com transforms selecionados.")
        manifest = {
            "schema": "argos-public-liver-mri-registration-set-v1",
            "case_count": len(records),
            "files_per_case": 5,
            "source_derivatives_md5": actual_md5,
            "holdout_subjects_extracted": 0,
            "manual_or_lesion_files_extracted": 0,
            "records": records,
        }
        serialized = json.dumps(records, ensure_ascii=False).lower()
        if "sub-" in serialized or any(term in serialized for term in FORBIDDEN_TERMS):
            raise PipelineError("Manifesto de transforms expõe identificador ou termo protegido.")
        _write_json_atomic(staging / "registration_manifest.json", manifest)
        os.replace(staging, output_dir)
        return manifest
    except Exception:
        import shutil

        shutil.rmtree(staging, ignore_errors=True)
        raise


def extract_holdout_registration_transforms_label_blind(
    derivatives_zip: Path,
    output_dir: Path,
) -> dict[str, object]:
    """Extract only T1 registration parameters for subjects 045–088."""

    derivatives_zip = Path(derivatives_zip).resolve()
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError(f"Destino já existe; extração não sobrescreve dados: {output_dir}.")
    if not derivatives_zip.is_file():
        raise PipelineError(f"derivatives.zip ausente: {derivatives_zip}.")
    actual_md5 = md5_file(derivatives_zip)
    if actual_md5 != DERIVATIVES_MD5:
        raise PipelineError(f"MD5 inválido para derivatives.zip: {actual_md5}.")

    staging = output_dir.with_name(f".{output_dir.name}.staging.{uuid.uuid4().hex}")
    staging.mkdir(parents=True)
    try:
        by_subject: dict[str, dict[str, ZipInfo]] = {
            subject: {} for subject in HOLDOUT_SUBJECTS
        }
        with ZipFile(derivatives_zip) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                path = _safe_member(info)
                if len(path.parts) != 5 or PurePosixPath(*path.parts[:2]) != TRANSFORM_PREFIX:
                    continue
                subject, group, name = path.parts[2], path.parts[3], path.parts[4]
                if group != "dyn" or not name.endswith(".txt"):
                    continue
                lowered = path.as_posix().lower()
                if any(term in lowered for term in FORBIDDEN_TERMS):
                    raise PipelineError(f"Transform proibido encontrado: {path.as_posix()}.")
                if subject not in HOLDOUT_SUBJECTS:
                    continue
                by_subject[subject][name] = info

            records: list[dict[str, object]] = []
            for subject in sorted(HOLDOUT_SUBJECTS):
                source_by_name = by_subject[subject]
                selected = _selected_source_names(set(source_by_name))
                arterial_source_phase = selected.pop("arterial_source_phase")
                case_id = anonymized_case_id(subject)
                files: list[dict[str, object]] = []
                for role, source_name in sorted(selected.items()):
                    destination = staging / "transforms" / case_id / f"{role}.txt"
                    with archive.open(source_by_name[source_name]) as source:
                        size, digest = _copy_atomic(source, destination)
                    files.append(
                        {
                            "role": role,
                            "relative_path": destination.relative_to(staging).as_posix(),
                            "bytes": size,
                            "sha256": digest,
                        }
                    )
                records.append(
                    {
                        "schema": "argos-public-liver-mri-registration-v1",
                        "case_id": case_id,
                        "split": "holdout_blind",
                        "reference_phase": "venous",
                        "arterial_source_phase": arterial_source_phase,
                        "files": files,
                        "research_only": True,
                        "clinical_use_allowed": False,
                    }
                )

        if len(records) != len(HOLDOUT_SUBJECTS):
            raise PipelineError("Quantidade inesperada de casos holdout com transforms.")
        manifest = {
            "schema": "argos-public-liver-mri-registration-set-v1",
            "split": "holdout_blind",
            "case_count": len(records),
            "files_per_case": 5,
            "source_derivatives_md5": actual_md5,
            "holdout_subjects_extracted": len(records),
            "development_subjects_extracted": 0,
            "manual_or_lesion_files_extracted": 0,
            "ground_truth_read": False,
            "records": records,
        }
        serialized = json.dumps(records, ensure_ascii=False).lower()
        if "sub-" in serialized or any(term in serialized for term in FORBIDDEN_TERMS):
            raise PipelineError("Manifesto holdout de transforms expõe conteúdo protegido.")
        _write_json_atomic(staging / "registration_manifest.json", manifest)
        os.replace(staging, output_dir)
        return manifest
    except Exception:
        import shutil

        shutil.rmtree(staging, ignore_errors=True)
        raise


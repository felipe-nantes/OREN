"""Label-blind acquisition gate for the public Gd-EOB-DTPA HBP cohort.

The Zenodo archive co-locates images, anatomical annotations, tumour masks and
clinicopathological spreadsheets.  This module is deliberately fail-closed:
only ``PHLF/CenterN/Image/*.nii.gz`` members may be extracted into the
inference-visible directory.  Protected material is inventoried by name but
its payload is never opened by this workflow.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable

import nibabel as nib
import numpy as np

from dtwin.benchmark.openswisshcc_alignment import _publish_directory
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.benchmark.openswisshcc_v23_baseline import verify_v23_baseline_lock
from dtwin.core import PipelineError


DATASET_ID = "gd_eob_dtpa_phlf_2026"
ZENODO_RECORD_ID = 18622298
ZENODO_RECORD_URL = "https://zenodo.org/records/18622298"
ZENODO_API_URL = "https://zenodo.org/api/records/18622298"
ZENODO_ARCHIVE_URL = (
    "https://zenodo.org/api/records/18622298/files/PHLF.zip/content"
)
ARCHIVE_NAME = "PHLF.zip"
ARCHIVE_BYTES = 1_345_046_539
ARCHIVE_MD5 = "0bd127e0e144b3ed3d75432d70963865"
DATASET_LICENSE = "CC-BY-4.0"
ARTICLE_DOI = "10.1038/s41597-026-07483-x"
DATASET_DOI = "10.5281/zenodo.18622298"

EXPECTED_CENTER_COUNTS = {"center-1": 88, "center-2": 94, "center-3": 38}
EXPECTED_CASE_COUNT = sum(EXPECTED_CENTER_COUNTS.values())
EXPECTED_HCC_COUNT = 164
EXPECTED_NON_HCC_COUNT = 56

CONTRACT_SCHEMA = "argos-v23-external-hcc-hbp-contract-v1"
ARCHIVE_INVENTORY_SCHEMA = "argos-gd-eob-hcc-archive-inventory-v1"
IMAGE_CASE_SCHEMA = "argos-gd-eob-hcc-image-case-v1"
IMAGE_COLLECTION_SCHEMA = "argos-gd-eob-hcc-image-collection-v1"
READINESS_SCHEMA = "argos-gd-eob-hcc-label-blind-readiness-v1"

IMAGE_MEMBER = re.compile(
    r"^PHLF/Center(?P<center>[123])/Image/(?P<source_id>[1-9][0-9]*)\.nii\.gz$"
)
PROTECTED_PATH_TERMS = (
    "annotation",
    "clinicopathological",
    "tumor",
    "tumour",
    "label",
    "mask",
    "ground_truth",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise PipelineError(f"Artefato ausente: {path}.") from exc
    return digest.hexdigest()


def _md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    try:
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise PipelineError(f"Arquivo Zenodo ausente: {path}.") from exc
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(
                json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            )
        stream.flush()
        os.fsync(stream.fileno())


def _json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def _jsonl(path: Path, description: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise PipelineError(f"{description} deve conter objetos JSONL.")
    return rows


def _case_id(center: int, source_id: str) -> str:
    token = hashlib.sha256(
        f"{DATASET_ID}:Center{center}:{source_id}".encode("utf-8")
    ).hexdigest()[:20]
    return f"anon-gdeob-{token}"


def validate_zenodo_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Validate the pinned public record without inspecting the archive payload."""

    files = metadata.get("files") if isinstance(metadata, dict) else None
    license_id = metadata.get("metadata", {}).get("license", {}).get("id")
    if (
        metadata.get("id") != ZENODO_RECORD_ID
        or metadata.get("doi") != DATASET_DOI
        or metadata.get("status") != "published"
        or license_id != "cc-by-4.0"
        or not isinstance(files, list)
        or len(files) != 1
    ):
        raise PipelineError("Metadados Zenodo divergiram do registro público fixado.")
    item = files[0]
    if (
        item.get("key") != ARCHIVE_NAME
        or item.get("size") != ARCHIVE_BYTES
        or item.get("checksum") != f"md5:{ARCHIVE_MD5}"
    ):
        raise PipelineError("Arquivo Zenodo divergiu em nome, tamanho ou checksum.")
    return {
        "record_id": ZENODO_RECORD_ID,
        "record_revision": metadata.get("revision"),
        "record_doi": DATASET_DOI,
        "license": DATASET_LICENSE,
        "archive_name": ARCHIVE_NAME,
        "archive_bytes": ARCHIVE_BYTES,
        "archive_md5": ARCHIVE_MD5,
    }


def verify_archive(archive_path: Path) -> dict[str, Any]:
    archive = Path(archive_path).resolve()
    if not archive.is_file() or archive.stat().st_size != ARCHIVE_BYTES:
        raise PipelineError("PHLF.zip ausente ou com tamanho divergente.")
    checksum = _md5(archive)
    if checksum != ARCHIVE_MD5:
        raise PipelineError("PHLF.zip falhou no checksum MD5 publicado pelo Zenodo.")
    return {
        "path": str(archive),
        "bytes": archive.stat().st_size,
        "md5": checksum,
        "sha256": _sha256(archive),
    }


def freeze_hcc_hbp_contract(
    *,
    baseline_lock_path: Path,
    workspace_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Freeze an HCC-specific, HBP-only external contract alongside v1."""

    baseline = verify_v23_baseline_lock(
        lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    base = {
        "schema": CONTRACT_SCHEMA,
        "status": "frozen_before_images_are_extracted_or_protected_payloads_opened",
        "dataset": {
            "dataset_id": DATASET_ID,
            "zenodo_record_id": ZENODO_RECORD_ID,
            "dataset_doi": DATASET_DOI,
            "article_doi": ARTICLE_DOI,
            "license": DATASET_LICENSE,
            "archive_name": ARCHIVE_NAME,
            "archive_bytes": ARCHIVE_BYTES,
            "archive_md5": ARCHIVE_MD5,
            "case_count": EXPECTED_CASE_COUNT,
            "expected_hcc_count_from_publication": EXPECTED_HCC_COUNT,
            "expected_non_hcc_count_from_publication": EXPECTED_NON_HCC_COUNT,
            "centers": 3,
            "phase": "hepatobiliary_phase_gd_eob_dtpa",
            "all_cases_have_visible_liver_tumor": True,
        },
        "target_condition": "hcc_suspicion",
        "class_definition": {
            "POSITIVE": "hepatocellular_carcinoma",
            "NEGATIVE": "non_hcc_liver_tumor",
            "negative_does_not_mean_healthy": True,
        },
        "algorithm": {
            "name": "argos_v23_frozen_shape_fusion",
            "calibrator_signature": baseline["calibrator_signature"],
            "decision_threshold": baseline["decision_threshold"],
            "weights": {
                "v11": 0.8,
                "candidate_weighted_linearity": 0.2,
            },
            "recalibration_on_external_cohort_allowed": False,
        },
        "representation_gate": {
            "hbp_adapter_status": "must_be_frozen_label_blind_before_inference",
            "technical_pilot_may_not_read_labels_or_lesion_masks": True,
            "unchanged_v23_signal_semantics_required": True,
            "full_cohort_inference_allowed_before_gate": False,
        },
        "primary_gate": {
            "minimum_sensitivity": 0.75,
            "minimum_specificity": 0.75,
            "maximum_raw_input_end_to_end_seconds_per_case": 180.0,
            "technical_failure_counts_as_error": True,
            "inconclusive_counts_as_error": True,
            "wilson_95_percent_intervals_required": True,
            "confusion_matrix_required": True,
        },
        "execution_policy": {
            "one_shot_after_prediction_freeze": True,
            "predictions_frozen_before_labels": True,
            "no_case_exclusion_after_inference": True,
            "no_threshold_selection_on_external_cohort": True,
            "no_ground_truth_in_inference": True,
            "no_lesion_or_anatomical_annotation_in_inference": True,
            "human_review_required": True,
        },
        "baseline_lock_sha256": _sha256(Path(baseline_lock_path).resolve()),
        "candidate_images_bound": False,
        "protected_labels_bound": False,
        "ready_for_technical_pilot": False,
        "ready_for_full_inference": False,
        "qualified": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    contract = {**base, "contract_signature": _canonical_sha(base)}
    output = Path(output_path).resolve()
    if output.exists():
        existing = _json(output, "Contrato HCC-HBP existente")
        if existing != contract:
            raise PipelineError("Contrato HCC-HBP existente diverge; sobrescrita recusada.")
        return existing
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, contract)
    return contract


def verify_hcc_hbp_contract(
    *,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    contract = _json(contract_path, "Contrato HCC-HBP")
    signature = contract.get("contract_signature")
    unsigned = dict(contract)
    unsigned.pop("contract_signature", None)
    baseline = verify_v23_baseline_lock(
        lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    if (
        contract.get("schema") != CONTRACT_SCHEMA
        or contract.get("status")
        != "frozen_before_images_are_extracted_or_protected_payloads_opened"
        or signature != _canonical_sha(unsigned)
        or contract.get("target_condition") != "hcc_suspicion"
        or contract.get("dataset", {}).get("case_count") != EXPECTED_CASE_COUNT
        or contract.get("algorithm", {}).get("calibrator_signature")
        != baseline["calibrator_signature"]
        or contract.get("algorithm", {}).get("decision_threshold")
        != baseline["decision_threshold"]
        or contract.get("ready_for_full_inference") is not False
        or contract.get("qualified") is not False
    ):
        raise PipelineError("Contrato HCC-HBP ausente, adulterado ou divergente.")
    return contract


def _classify_archive_members(
    infos: list[zipfile.ZipInfo],
) -> tuple[list[tuple[zipfile.ZipInfo, int, str]], dict[str, Any]]:
    seen: set[str] = set()
    images: list[tuple[zipfile.ZipInfo, int, str]] = []
    protected_members = 0
    directory_members = 0
    unexpected: list[str] = []
    center_ids: dict[int, set[int]] = {1: set(), 2: set(), 3: set()}
    for info in infos:
        name = info.filename.replace("\\", "/")
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or name in seen
            or "\x00" in name
        ):
            raise PipelineError("PHLF.zip contém membro inseguro ou duplicado.")
        seen.add(name)
        if info.is_dir():
            directory_members += 1
            continue
        match = IMAGE_MEMBER.fullmatch(name)
        if match:
            center = int(match.group("center"))
            source_id = match.group("source_id")
            if int(source_id) in center_ids[center]:
                raise PipelineError("PHLF.zip contém imagem de caso duplicada.")
            center_ids[center].add(int(source_id))
            images.append((info, center, source_id))
            continue
        if any(term in name.lower() for term in PROTECTED_PATH_TERMS) or name.endswith(
            "/desktop.ini"
        ):
            protected_members += 1
            continue
        unexpected.append(name)
    if unexpected:
        raise PipelineError(
            f"PHLF.zip contém membro não classificado: {unexpected[0]}."
        )
    for center, expected in ((1, 88), (2, 94), (3, 38)):
        if center_ids[center] != set(range(1, expected + 1)):
            raise PipelineError(f"Inventário de imagens do Center{center} divergiu.")
    if len(images) != EXPECTED_CASE_COUNT:
        raise PipelineError("PHLF.zip não contém exatamente 220 imagens HBP.")
    images.sort(key=lambda item: (item[1], int(item[2])))
    return images, {
        "archive_member_count": len(infos),
        "directory_member_count": directory_members,
        "image_member_count": len(images),
        "protected_member_count": protected_members,
        "unexpected_member_count": 0,
    }


def inventory_archive(archive_path: Path) -> dict[str, Any]:
    """Inventory names only; do not read any protected member payload."""

    archive_info = verify_archive(archive_path)
    try:
        with zipfile.ZipFile(archive_path, "r") as bundle:
            _, counts = _classify_archive_members(bundle.infolist())
    except (OSError, zipfile.BadZipFile) as exc:
        raise PipelineError("PHLF.zip inválido ou corrompido.") from exc
    base = {
        "schema": ARCHIVE_INVENTORY_SCHEMA,
        "dataset_id": DATASET_ID,
        "archive": archive_info,
        **counts,
        "case_count_by_center": EXPECTED_CENTER_COUNTS,
        "labels_read": False,
        "lesion_masks_read": False,
        "protected_payloads_read": False,
        "only_member_names_were_inspected": True,
        "archive_integrity_verified_by_published_md5": True,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    return {**base, "inventory_signature": _canonical_sha(base)}


def _nifti_metadata(path: Path) -> dict[str, Any]:
    try:
        image = nib.load(str(path), mmap=True)
        shape = tuple(int(value) for value in image.shape)
        zooms = tuple(float(value) for value in image.header.get_zooms()[:3])
        affine = np.asarray(image.affine, dtype=float)
    except Exception as exc:  # nibabel raises several format-specific exceptions
        raise PipelineError(f"NIfTI HBP inválido: {path.name}.") from exc
    if (
        len(shape) != 3
        or any(value < 2 for value in shape)
        or len(zooms) != 3
        or any(not np.isfinite(value) or value <= 0 for value in zooms)
        or affine.shape != (4, 4)
        or not np.isfinite(affine).all()
    ):
        raise PipelineError(f"Geometria NIfTI HBP inválida: {path.name}.")
    return {
        "shape": list(shape),
        "spacing_mm": list(zooms),
        "orientation": list(nib.aff2axcodes(affine)),
    }


def extract_label_blind_images(
    *,
    archive_path: Path,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
    output_root: Path,
    progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Publish an image-only collection and a separated source mapping."""

    contract = verify_hcc_hbp_contract(
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    inventory = inventory_archive(archive_path)
    output = Path(output_root).resolve()
    if output.exists():
        raise PipelineError("Destino Gd-EOB já existe; sobrescrita recusada.")
    staging = output.with_name(f".{output.name}.incomplete-{uuid.uuid4().hex}")
    image_root = staging / "image_only"
    protected_root = staging / "protected_source"
    image_root.mkdir(parents=True)
    protected_root.mkdir(parents=True)
    rows: list[dict[str, Any]] = []
    protected_rows: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(archive_path, "r") as bundle:
            images, _ = _classify_archive_members(bundle.infolist())
            for index, (info, center, source_id) in enumerate(images, start=1):
                case_id = _case_id(center, source_id)
                relative = Path("images") / f"{case_id}.nii.gz"
                destination = image_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_suffix(destination.suffix + ".part")
                with bundle.open(info, "r") as source, temporary.open("wb") as sink:
                    shutil.copyfileobj(source, sink, length=1024 * 1024)
                    sink.flush()
                    os.fsync(sink.fileno())
                os.replace(temporary, destination)
                geometry = _nifti_metadata(destination)
                file_sha = _sha256(destination)
                row = {
                    "schema": IMAGE_CASE_SCHEMA,
                    "case_id": case_id,
                    "source_dataset_id": DATASET_ID,
                    "center_pseudonym": f"center-{center}",
                    "phase": "hepatobiliary_phase_gd_eob_dtpa",
                    "image": {
                        "relative_path": relative.as_posix(),
                        "bytes": destination.stat().st_size,
                        "sha256": file_sha,
                        **geometry,
                    },
                    "study_fingerprint_sha256": file_sha,
                    "ground_truth_read": False,
                    "lesion_masks_read": False,
                    "anatomical_annotations_used": False,
                    "research_only": True,
                    "clinical_use_allowed": False,
                }
                rows.append(row)
                protected_rows.append(
                    {
                        "case_id": case_id,
                        "source_locator_sha256": hashlib.sha256(
                            info.filename.encode("utf-8")
                        ).hexdigest(),
                        "source_center": center,
                        "source_subject_id": source_id,
                        "contains_label": False,
                        "contains_lesion_mask": False,
                    }
                )
                if progress is not None:
                    progress(index, len(images), case_id)
        _write_jsonl(image_root / "image_cases.jsonl", rows)
        image_manifest_sha = _sha256(image_root / "image_cases.jsonl")
        base = {
            "schema": IMAGE_COLLECTION_SCHEMA,
            "status": "label_blind_images_extracted_ready_for_technical_preflight",
            "dataset_id": DATASET_ID,
            "contract_signature": contract["contract_signature"],
            "archive_sha256": inventory["archive"]["sha256"],
            "archive_inventory_signature": inventory["inventory_signature"],
            "case_count": len(rows),
            "case_count_by_center": EXPECTED_CENTER_COUNTS,
            "image_manifest_sha256": image_manifest_sha,
            "labels_read": False,
            "lesion_masks_read": False,
            "anatomical_annotations_used": False,
            "protected_payloads_read": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        manifest = {**base, "collection_signature": _canonical_sha(base)}
        _write_json(image_root / "collection.json", manifest)
        _write_json(protected_root / "archive_inventory.json", inventory)
        _write_jsonl(protected_root / "source_mapping.jsonl", protected_rows)
        _write_json(
            staging / "separation_manifest.json",
            {
                "image_only_relative_root": "image_only",
                "protected_source_relative_root": "protected_source",
                "inference_must_only_receive_image_only_root": True,
                "labels_present": False,
                "lesion_masks_extracted": False,
                "clinicopathological_files_extracted": False,
                "anatomical_annotations_extracted": False,
            },
        )
        _publish_directory(staging, output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return verify_label_blind_images(
        image_root=output / "image_only",
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )


def verify_label_blind_images(
    *,
    image_root: Path,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    contract = verify_hcc_hbp_contract(
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    root = Path(image_root).resolve()
    manifest = _json(root / "collection.json", "Coleção image-only Gd-EOB")
    rows = _jsonl(root / "image_cases.jsonl", "Manifesto image-only Gd-EOB")
    unsigned = dict(manifest)
    signature = unsigned.pop("collection_signature", None)
    if (
        manifest.get("schema") != IMAGE_COLLECTION_SCHEMA
        or signature != _canonical_sha(unsigned)
        or manifest.get("contract_signature") != contract["contract_signature"]
        or manifest.get("case_count") != EXPECTED_CASE_COUNT
        or len(rows) != EXPECTED_CASE_COUNT
        or manifest.get("image_manifest_sha256")
        != _sha256(root / "image_cases.jsonl")
        or manifest.get("labels_read") is not False
        or manifest.get("lesion_masks_read") is not False
        or manifest.get("anatomical_annotations_used") is not False
        or manifest.get("protected_payloads_read") is not False
    ):
        raise PipelineError("Coleção image-only Gd-EOB adulterada ou insegura.")
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    centers: dict[str, int] = {key: 0 for key in EXPECTED_CENTER_COUNTS}
    for row in rows:
        image = row.get("image") if isinstance(row, dict) else None
        relative_text = image.get("relative_path") if isinstance(image, dict) else None
        relative = PurePosixPath(str(relative_text))
        case_id = row.get("case_id")
        center = row.get("center_pseudonym")
        if (
            row.get("schema") != IMAGE_CASE_SCHEMA
            or not isinstance(case_id, str)
            or not case_id.startswith("anon-gdeob-")
            or case_id in seen_ids
            or center not in centers
            or row.get("phase") != "hepatobiliary_phase_gd_eob_dtpa"
            or row.get("ground_truth_read") is not False
            or row.get("lesion_masks_read") is not False
            or row.get("anatomical_annotations_used") is not False
            or relative.is_absolute()
            or ".." in relative.parts
            or relative_text in seen_paths
            or any(term in str(relative_text).lower() for term in PROTECTED_PATH_TERMS)
        ):
            raise PipelineError("Caso image-only Gd-EOB inválido ou inseguro.")
        path = (root / Path(*relative.parts)).resolve()
        if (
            not path.is_relative_to(root)
            or not path.is_file()
            or path.stat().st_size != image.get("bytes")
            or _sha256(path) != image.get("sha256")
            or row.get("study_fingerprint_sha256") != image.get("sha256")
        ):
            raise PipelineError("Imagem HBP ausente, adulterada ou divergente.")
        geometry = _nifti_metadata(path)
        if any(image.get(key) != value for key, value in geometry.items()):
            raise PipelineError("Geometria HBP divergiu do manifesto congelado.")
        seen_ids.add(case_id)
        seen_paths.add(str(relative_text))
        centers[str(center)] += 1
    if centers != EXPECTED_CENTER_COUNTS:
        raise PipelineError("Distribuição por centro da coleção Gd-EOB divergiu.")
    return manifest


def build_label_blind_readiness(
    *,
    image_root: Path,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Record readiness for a technical pilot, never for full inference."""

    collection = verify_label_blind_images(
        image_root=image_root,
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    contract = verify_hcc_hbp_contract(
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    base = {
        "schema": READINESS_SCHEMA,
        "status": "ready_for_label_blind_technical_pilot_only",
        "dataset_id": DATASET_ID,
        "contract_signature": contract["contract_signature"],
        "collection_signature": collection["collection_signature"],
        "case_count": EXPECTED_CASE_COUNT,
        "labels_read": False,
        "lesion_masks_read": False,
        "ready_for_technical_pilot": True,
        "ready_for_full_inference": False,
        "blocking_gate": "hbp_representation_and_v23_signal_compatibility_not_yet_frozen",
        "research_only": True,
        "clinical_use_allowed": False,
    }
    readiness = {**base, "readiness_signature": _canonical_sha(base)}
    destination = Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_json(destination, readiness)
    return readiness


def verify_label_blind_readiness(
    *,
    readiness_path: Path,
    image_root: Path,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    collection = verify_label_blind_images(
        image_root=image_root,
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    contract = verify_hcc_hbp_contract(
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    readiness = _json(readiness_path, "Readiness label-blind Gd-EOB")
    signature = readiness.get("readiness_signature")
    unsigned = dict(readiness)
    unsigned.pop("readiness_signature", None)
    if (
        readiness.get("schema") != READINESS_SCHEMA
        or readiness.get("status") != "ready_for_label_blind_technical_pilot_only"
        or signature != _canonical_sha(unsigned)
        or readiness.get("contract_signature") != contract["contract_signature"]
        or readiness.get("collection_signature") != collection["collection_signature"]
        or readiness.get("case_count") != EXPECTED_CASE_COUNT
        or readiness.get("labels_read") is not False
        or readiness.get("lesion_masks_read") is not False
        or readiness.get("ready_for_technical_pilot") is not True
        or readiness.get("ready_for_full_inference") is not False
    ):
        raise PipelineError("Readiness label-blind Gd-EOB adulterado ou inseguro.")
    return readiness


__all__ = [
    "ARCHIVE_BYTES",
    "ARCHIVE_MD5",
    "CONTRACT_SCHEMA",
    "DATASET_ID",
    "EXPECTED_CASE_COUNT",
    "EXPECTED_CENTER_COUNTS",
    "EXPECTED_HCC_COUNT",
    "EXPECTED_NON_HCC_COUNT",
    "build_label_blind_readiness",
    "extract_label_blind_images",
    "freeze_hcc_hbp_contract",
    "inventory_archive",
    "validate_zenodo_metadata",
    "verify_archive",
    "verify_hcc_hbp_contract",
    "verify_label_blind_images",
    "verify_label_blind_readiness",
]

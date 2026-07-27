"""Prepare label-blind CHAOS MRI controls for the v21 specificity stress arm."""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
import pydicom
import SimpleITK as sitk
from PIL import Image

from dtwin.benchmark.liverhccseg_preparation import (
    _canonical_hash,
    _geometry,
    _hash,
    _publish,
    _resample_phase_to_reference,
    _same_geometry,
)
from dtwin.benchmark.public_independent_cohort import (
    INFERENCE_SCHEMA,
    PROTOCOL_SCHEMA,
    SOURCE_MAP_SCHEMA,
    _canonical_hash as _cohort_canonical_hash,
    _tree_fingerprint,
    anonymous_public_case_id,
)
from dtwin.core import PipelineError
from dtwin.datasets.chaos_download import (
    EXTRACTION_SCHEMA,
    verify_chaos_mri_extraction,
)
from dtwin.medgemma_screening import _write_json_atomic


CASE_SCHEMA = "argos-chaos-v21-blind-input-case-v1"
COHORT_SCHEMA = "argos-chaos-v21-blind-input-cohort-v1"
COHORT_ID = "public_independent_v21_liverhccseg_chaos"
CHAOS_ALIAS = "src-" + hashlib.sha256(b"chaos_mri").hexdigest()[:12]
ROLES = ("t1_in", "t1_out", "t2_spir", "liver_mask")
EXPECTED_PATH_SUFFIXES = {
    "t1_in": PurePosixPath("T1DUAL/DICOM_anon/InPhase"),
    "t1_out": PurePosixPath("T1DUAL/DICOM_anon/OutPhase"),
    "t2_spir": PurePosixPath("T2SPIR/DICOM_anon"),
}
LIVER_LABEL = 63
ALLOWED_ORGAN_LABELS = {0, 63, 126, 189, 252}


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{label} CHAOS v21 invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{label} CHAOS v21 deve ser objeto.")
    return value


def _load_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{label} CHAOS v21 invalido: {path}") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise PipelineError(f"{label} CHAOS v21 vazio ou invalido.")
    return rows


def _safe_source_path(root: Path, relative: str) -> Path:
    posix = PurePosixPath(str(relative).replace("\\", "/"))
    if posix.is_absolute() or ".." in posix.parts:
        raise PipelineError("Caminho operacional CHAOS inseguro.")
    path = (root / Path(*posix.parts)).resolve()
    if not path.is_relative_to(root) or not path.is_dir():
        raise PipelineError("Serie operacional CHAOS ausente ou fora da raiz.")
    return path


def _verify_blind_source_map(
    *,
    bundle_root: Path,
    raw_mr_root: Path,
    expected_protocol_signature: str,
    expected_case_count: int,
) -> list[dict[str, Any]]:
    bundle = Path(bundle_root).resolve()
    protocol_path = bundle / "cohort_protocol.json"
    inference_path = bundle / "inference_manifest.jsonl"
    source_path = bundle / "operational_source_map.jsonl"
    protocol = _load_object(protocol_path, "Protocolo publico")
    unsigned = dict(protocol)
    signature = str(unsigned.pop("protocol_signature", ""))
    if (
        protocol.get("schema") != PROTOCOL_SCHEMA
        or signature != _cohort_canonical_hash(unsigned)
        or signature != expected_protocol_signature
        or protocol.get("holdout_opened") is not False
        or protocol.get("ground_truth_read_during_inference") is not False
        or protocol.get("inference_manifest_sha256") != _hash(inference_path)
        or protocol.get("operational_source_map_sha256") != _hash(source_path)
    ):
        raise PipelineError("Protocolo publico CHAOS invalido ou adulterado.")
    inference_rows = _load_jsonl(inference_path, "Manifesto de inferencia")
    source_rows = _load_jsonl(source_path, "Mapa operacional")
    if len(inference_rows) != protocol.get("case_count") or len(source_rows) != len(inference_rows):
        raise PipelineError("Bundle publico CHAOS possui cardinalidade inconsistente.")
    inference = {str(row.get("case_id", "")): row for row in inference_rows}
    selected = [row for row in source_rows if row.get("root_alias") == CHAOS_ALIAS]
    if len(selected) != expected_case_count:
        raise PipelineError("Mapa operacional nao contem os controles CHAOS esperados.")
    verified: list[dict[str, Any]] = []
    for row in sorted(selected, key=lambda item: str(item.get("case_id", ""))):
        case_id = str(row.get("case_id", ""))
        blind = inference.get(case_id, {})
        subject = str(row.get("subject_relative_path", ""))
        raw_paths = row.get("raw_paths")
        if (
            row.get("schema") != SOURCE_MAP_SCHEMA
            or row.get("never_send_to_model") is not True
            or blind.get("schema") != INFERENCE_SCHEMA
            or blind.get("ground_truth_read_during_inference") is not False
            or blind.get("lesion_mask_available_to_inference") is not False
            or not subject.isdigit()
            or case_id != anonymous_public_case_id(COHORT_ID, "chaos_mri", subject)
            or not isinstance(raw_paths, list)
            or len(raw_paths) != 3
        ):
            raise PipelineError("Registro operacional CHAOS invalido ou nao cego.")
        expected = {
            (PurePosixPath(subject) / suffix).as_posix(): role
            for role, suffix in EXPECTED_PATH_SUFFIXES.items()
        }
        if set(raw_paths) != set(expected):
            raise PipelineError("Controle CHAOS nao possui exatamente T1 in/out e T2SPIR.")
        paths = [_safe_source_path(raw_mr_root, item) for item in raw_paths]
        fingerprint, file_count, total_bytes = _tree_fingerprint(paths, raw_mr_root)
        if (
            fingerprint != row.get("source_sha256")
            or fingerprint != blind.get("source_sha256")
            or file_count != blind.get("source_file_count")
            or total_bytes != blind.get("source_total_bytes")
        ):
            raise PipelineError("Fonte DICOM CHAOS divergiu do freeze publico.")
        verified.append({
            "case_id": case_id,
            "subject": subject,
            "series": {expected[token]: _safe_source_path(raw_mr_root, token) for token in raw_paths},
            "source_sha256": fingerprint,
        })
    return verified


def _ordered_dicom_files(directory: Path) -> list[Path]:
    records: list[tuple[float, int, Path]] = []
    for path in sorted(directory.glob("*.dcm")):
        try:
            ds = pydicom.dcmread(path, stop_before_pixels=True)
        except Exception as exc:  # noqa: BLE001
            raise PipelineError("Falha ao ler DICOM CHAOS durante preparacao.") from exc
        if str(getattr(ds, "Modality", "")).upper() != "MR":
            raise PipelineError("Serie CHAOS contem modalidade nao MR.")
        position = [float(value) for value in getattr(ds, "ImagePositionPatient", [])]
        orientation = [float(value) for value in getattr(ds, "ImageOrientationPatient", [])]
        if len(position) == 3 and len(orientation) == 6:
            normal = np.cross(np.asarray(orientation[:3]), np.asarray(orientation[3:]))
            location = float(np.dot(np.asarray(position), normal))
        else:
            location = float(getattr(ds, "InstanceNumber", len(records)))
        records.append((location, int(getattr(ds, "InstanceNumber", len(records))), path))
    records.sort(key=lambda item: (item[0], item[1], item[2].name))
    if len(records) < 3 or len({round(item[0], 5) for item in records}) != len(records):
        raise PipelineError("Serie DICOM CHAOS vazia, curta ou com planos duplicados.")
    return [item[2] for item in records]


def _read_volume(files: list[Path]) -> sitk.Image:
    try:
        image = sitk.ReadImage([str(path) for path in files], sitk.sitkFloat32)
    except RuntimeError as exc:
        raise PipelineError("Falha ao montar volume DICOM CHAOS.") from exc
    if image.GetDimension() != 3 or image.GetSize()[2] != len(files):
        raise PipelineError("Volume DICOM CHAOS possui geometria invalida.")
    return image


def _liver_mask_from_ground(files: list[Path], ground_dir: Path, reference: sitk.Image) -> sitk.Image:
    slices: list[np.ndarray] = []
    for dicom_path in files:
        png_path = ground_dir / f"{dicom_path.stem}.png"
        if not png_path.is_file():
            raise PipelineError("Mascara de orgao CHAOS ausente para plano T1 in-phase.")
        with Image.open(png_path) as image:
            array = np.asarray(image)
        values = {int(value) for value in np.unique(array)}
        if array.ndim != 2 or not values.issubset(ALLOWED_ORGAN_LABELS):
            raise PipelineError("Mascara de orgao CHAOS possui labels inesperados.")
        slices.append((array == LIVER_LABEL).astype(np.uint8))
    stack = np.stack(slices)
    if stack.shape != tuple(reversed(reference.GetSize())) or not np.any(stack):
        raise PipelineError("Mascara hepatica CHAOS vazia ou com geometria divergente.")
    mask = sitk.GetImageFromArray(stack)
    mask.CopyInformation(reference)
    return mask


def prepare_chaos_v21_blind_inputs(
    *,
    extracted_root: Path,
    bundle_root: Path,
    output_root: Path,
    expected_protocol_signature: str,
    expected_case_count: int = 20,
    minimum_liver_support: float = 0.95,
) -> dict[str, Any]:
    """Materialize three registered contrasts and only the liver organ mask."""

    extracted_root = Path(extracted_root).resolve()
    raw_mr_root = extracted_root / "Train_Sets" / "MR"
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Preparacao cega CHAOS ja existe; recuso sobrescrever.")
    extraction = verify_chaos_mri_extraction(
        extracted_root=extracted_root, expected_subject_count=expected_case_count
    )
    sources = _verify_blind_source_map(
        bundle_root=Path(bundle_root), raw_mr_root=raw_mr_root,
        expected_protocol_signature=expected_protocol_signature,
        expected_case_count=expected_case_count,
    )
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_root.name}-", dir=output_root.parent))
    cases: list[dict[str, Any]] = []
    try:
        for source in sources:
            case_id = source["case_id"]
            case_dir = staging / case_id
            case_dir.mkdir()
            files_by_role = {role: _ordered_dicom_files(path) for role, path in source["series"].items()}
            reference = _read_volume(files_by_role["t1_in"])
            mask = _liver_mask_from_ground(
                files_by_role["t1_in"],
                raw_mr_root / source["subject"] / "T1DUAL" / "Ground",
                reference,
            )
            records: list[dict[str, Any]] = []
            for role in ("t1_in", "t1_out", "t2_spir"):
                destination = case_dir / f"{role}.nii.gz"
                image = reference if role == "t1_in" else _read_volume(files_by_role[role])
                resampled = not _same_geometry(reference, image)
                support = 1.0
                if resampled:
                    support = _resample_phase_to_reference(
                        image, reference, mask, destination,
                        minimum_liver_support=minimum_liver_support,
                    )
                else:
                    sitk.WriteImage(sitk.Cast(image, sitk.sitkFloat32), str(destination), True)
                records.append({
                    "role": role,
                    "relative_path": f"{case_id}/{destination.name}",
                    "sha256": _hash(destination),
                    "bytes": destination.stat().st_size,
                    "resampled_to_t1_in_grid": resampled,
                    "interpolation": "linear" if resampled else "none",
                    "liver_support_fraction": support,
                })
            mask_path = case_dir / "liver_mask.nii.gz"
            sitk.WriteImage(sitk.Cast(mask, sitk.sitkUInt8), str(mask_path), True)
            records.append({
                "role": "liver_mask",
                "relative_path": f"{case_id}/{mask_path.name}",
                "sha256": _hash(mask_path),
                "bytes": mask_path.stat().st_size,
                "resampled_to_t1_in_grid": False,
                "interpolation": "none",
                "liver_support_fraction": 1.0,
            })
            if any("lesion" in path.name.lower() or "tumor" in path.name.lower() for path in case_dir.rglob("*")):
                raise PipelineError("Artefato de lesao apareceu na preparacao CHAOS.")
            manifest = {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "files": records,
                "reference_geometry": _geometry(reference),
                "reference_grid": "t1_in",
                "sequence_semantics": {
                    "t1_in": "T1-DUAL in-phase",
                    "t1_out": "T1-DUAL out-phase",
                    "t2_spir": "T2-SPIR",
                },
                "source_sha256": source["source_sha256"],
                "organ_mask_source": "CHAOS_public_multiorgan_ground_reduced_to_liver_label_63",
                "non_liver_organ_labels_discarded": True,
                "lesion_mask_present": False,
                "pathology_label_present": False,
                "ground_truth_class_read": False,
                "minimum_liver_support_fraction": minimum_liver_support,
                "research_only": True,
                "clinical_use_allowed": False,
                "requires_human_review": True,
            }
            manifest["case_signature"] = _canonical_hash(manifest)
            _write_json_atomic(case_dir / "input_manifest.json", manifest)
            cases.append({
                "case_id": case_id,
                "case_manifest": f"{case_id}/input_manifest.json",
                "case_manifest_sha256": _hash(case_dir / "input_manifest.json"),
                "case_signature": manifest["case_signature"],
            })
        cohort = {
            "schema": COHORT_SCHEMA,
            "cohort_id": COHORT_ID,
            "evaluation_scope": "secondary_negative_domain_shift_stress_only",
            "case_count": len(cases),
            "cases": cases,
            "roles": list(ROLES),
            "source_public_protocol_signature": expected_protocol_signature,
            "source_extracted_tree_sha256": extraction["extracted_tree_sha256"],
            "lesion_masks_copied": False,
            "pathology_labels_copied": False,
            "ground_truth_class_read": False,
            "combined_primary_metric_allowed": False,
            "holdout_opened": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        cohort["cohort_signature"] = _canonical_hash(cohort)
        _write_json_atomic(staging / "cohort_manifest.json", cohort)
        _publish(staging, output_root)
        return cohort
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_chaos_v21_blind_inputs(
    *, prepared_root: Path, expected_cohort_signature: str | None = None,
    expected_case_count: int = 20,
) -> dict[str, Any]:
    root = Path(prepared_root).resolve()
    cohort = _load_object(root / "cohort_manifest.json", "Coorte preparada")
    unsigned = dict(cohort)
    signature = str(unsigned.pop("cohort_signature", ""))
    cases = cohort.get("cases")
    if (
        cohort.get("schema") != COHORT_SCHEMA
        or signature != _canonical_hash(unsigned)
        or (expected_cohort_signature and signature != expected_cohort_signature)
        or not isinstance(cases, list)
        or len(cases) != expected_case_count
        or cohort.get("combined_primary_metric_allowed") is not False
        or cohort.get("ground_truth_class_read") is not False
        or cohort.get("lesion_masks_copied") is not False
        or cohort.get("pathology_labels_copied") is not False
        or cohort.get("holdout_opened") is not False
    ):
        raise PipelineError("Coorte CHAOS preparada e invalida ou adulterada.")
    ids: list[str] = []
    for record in cases:
        case_id = str(record.get("case_id", ""))
        ids.append(case_id)
        manifest_path = (root / str(record.get("case_manifest", ""))).resolve()
        if not manifest_path.is_relative_to(root) or _hash(manifest_path) != record.get("case_manifest_sha256"):
            raise PipelineError("Manifesto preparado CHAOS ausente ou adulterado.")
        manifest = _load_object(manifest_path, "Caso preparado")
        case_unsigned = dict(manifest)
        case_signature = str(case_unsigned.pop("case_signature", ""))
        if (
            manifest.get("schema") != CASE_SCHEMA
            or manifest.get("case_id") != case_id
            or case_signature != _canonical_hash(case_unsigned)
            or case_signature != record.get("case_signature")
            or manifest.get("lesion_mask_present") is not False
            or manifest.get("pathology_label_present") is not False
            or manifest.get("ground_truth_class_read") is not False
        ):
            raise PipelineError("Caso preparado CHAOS perdeu cegamento ou assinatura.")
        images: dict[str, sitk.Image] = {}
        file_records = manifest.get("files")
        if not isinstance(file_records, list) or {item.get("role") for item in file_records} != set(ROLES):
            raise PipelineError("Papeis CHAOS preparados estao incompletos.")
        for item in file_records:
            path = (root / str(item.get("relative_path", ""))).resolve()
            if (
                not path.is_relative_to(root)
                or not path.is_file()
                or _hash(path) != item.get("sha256")
                or path.stat().st_size != item.get("bytes")
                or float(item.get("liver_support_fraction", 0.0)) < float(manifest["minimum_liver_support_fraction"])
                or "lesion" in path.name.lower()
                or "tumor" in path.name.lower()
            ):
                raise PipelineError("Arquivo preparado CHAOS ausente, alterado ou inseguro.")
            images[str(item["role"])] = sitk.ReadImage(str(path))
        reference = images["t1_in"]
        if any(not _same_geometry(reference, image) for image in images.values()):
            raise PipelineError("Volumes preparados CHAOS nao compartilham a grade T1 in.")
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise PipelineError("Ordem ou unicidade dos casos CHAOS e invalida.")
    return {
        "schema": "argos-chaos-v21-blind-input-preflight-v1",
        "status": "ready_for_blind_panel_generation",
        "case_count": len(ids),
        "cohort_signature": signature,
        "all_file_hashes_passed": True,
        "all_geometries_passed": True,
        "minimum_liver_support_passed": True,
        "lesion_masks_present": False,
        "pathology_labels_present": False,
        "ground_truth_class_read": False,
        "combined_primary_metric_allowed": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }


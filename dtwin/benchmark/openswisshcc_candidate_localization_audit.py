"""Retrospective, ground-truth-isolated localization audit for OpenSwissHCC v16.

This module is deliberately separate from every inference path.  It may read
public manual lesion masks only after the frozen v16 predictions exist.  It
never imports or calls the MedGemma client and refuses paths containing a
holdout component.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk
from scipy import ndimage

from dtwin.core import PipelineError

PROTOCOL_SCHEMA = "argos-openswisshcc-v16-localizer-audit-protocol-v1"
EXTRACTION_SCHEMA = "argos-openswisshcc-v16-authorized-mask-extraction-v1"
AUDIT_SCHEMA = "argos-openswisshcc-v16-localizer-retrospective-audit-v1"
EXPECTED_ARCHIVE_MD5 = "e7df6554b20aeb941d697710e4201c18"
VENOUS_MASK_RE = re.compile(
    r"^derivatives/manual_lesion_annotations/(sub-\d{3})/dyn/"
    r"sub-\d{3}_acq-water_phase-venous_T1w-L(\d+)_seg\.nii\.gz$"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _write_json_atomic(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_csv_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise PipelineError("Auditoria v16 recusou CSV vazio.")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON invalido na auditoria v16: {path}.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"Objeto JSON esperado na auditoria v16: {path}.")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError
                rows.append(value)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise PipelineError(f"JSONL invalido na linha {number if 'number' in locals() else 0}: {path}.") from exc
    return rows


def _refuse_holdout(*paths: Path) -> None:
    for path in paths:
        parts = {part.lower() for part in Path(path).resolve().parts}
        if any("holdout" in part for part in parts):
            raise PipelineError("Auditoria v16 recusou caminho de holdout.")


def _geometry_equal(left: sitk.Image, right: sitk.Image) -> bool:
    return (
        left.GetSize() == right.GetSize()
        and np.allclose(left.GetSpacing(), right.GetSpacing(), rtol=0, atol=1e-5)
        and np.allclose(left.GetOrigin(), right.GetOrigin(), rtol=0, atol=1e-5)
        and np.allclose(left.GetDirection(), right.GetDirection(), rtol=0, atol=1e-5)
    )


def _manual_mask_index_aligned(mask: sitk.Image, reference: sitk.Image) -> bool:
    """Accept only sub-millimetric NIfTI header round-off; never resample."""

    return (
        mask.GetSize() == reference.GetSize()
        and np.allclose(mask.GetSpacing(), reference.GetSpacing(), rtol=0, atol=1e-7)
        and np.allclose(mask.GetOrigin(), reference.GetOrigin(), rtol=0, atol=1e-3)
        and np.allclose(mask.GetDirection(), reference.GetDirection(), rtol=0, atol=1e-6)
    )


def _case_subject_map(source_map_path: Path, case_ids: set[str]) -> dict[str, str]:
    mapped: dict[str, set[str]] = {case_id: set() for case_id in case_ids}
    for row in _jsonl(source_map_path):
        case_id = str(row.get("case_id", ""))
        if case_id in mapped:
            mapped[case_id].add(str(row.get("public_subject_id", "")))
    if any(len(subjects) != 1 for subjects in mapped.values()):
        raise PipelineError("Mapeamento caso-sujeito do desenvolvimento e ambiguo ou incompleto.")
    result = {case_id: next(iter(subjects)) for case_id, subjects in mapped.items()}
    if len(set(result.values())) != len(result):
        raise PipelineError("Sujeito publico duplicado na coorte v16.")
    return result


def _read_scores(path: Path, case_ids: set[str]) -> dict[str, dict[str, str]]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"case_id", "label", "selected_candidate_classification"}
    if not rows or not required.issubset(rows[0]):
        raise PipelineError("CSV de scores v16 sem contrato minimo.")
    indexed = {str(row["case_id"]): row for row in rows}
    if set(indexed) != case_ids or len(indexed) != len(rows):
        raise PipelineError("CSV de scores v16 divergiu da coorte congelada.")
    if any(row["label"] not in {"POSITIVE", "NEGATIVE"} for row in rows):
        raise PipelineError("Label inesperado no CSV de scores v16.")
    return indexed


def freeze_protocol(
    *,
    archive_path: Path,
    cohort_manifest_path: Path,
    scores_csv_path: Path,
    source_map_path: Path,
    input_manifest_path: Path,
    localizer_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Freeze the audit definitions without decoding any lesion-mask voxel."""

    paths = tuple(map(Path, (archive_path, cohort_manifest_path, scores_csv_path, source_map_path,
                            input_manifest_path, localizer_root, output_path)))
    _refuse_holdout(*paths)
    archive_path, cohort_manifest_path, scores_csv_path, source_map_path, input_manifest_path, localizer_root, output_path = paths
    if output_path.exists():
        raise PipelineError("Protocolo de auditoria v16 ja existe; sobrescrita recusada.")
    if _md5(archive_path) != EXPECTED_ARCHIVE_MD5:
        raise PipelineError("MD5 do derivatives.zip divergiu do publicado.")

    cohort = _load_json(cohort_manifest_path)
    if (
        cohort.get("schema") != "argos-openswisshcc-candidate-volume-cohort-v16"
        or int(cohort.get("case_count", -1)) != 87
        or cohort.get("inference_executed") is not False
        or cohort.get("ground_truth_read") is not False
        or cohort.get("dataset_lesion_mask_used") is not False
        or cohort.get("holdout_opened") is not False
    ):
        raise PipelineError("Coorte cega v16 invalida para auditoria retrospectiva.")
    cases = cohort.get("cases")
    if not isinstance(cases, list):
        raise PipelineError("Lista de casos v16 ausente.")
    case_ids = {str(item.get("case_id", "")) for item in cases}
    if len(case_ids) != 87 or any(not case_id.startswith("anon-openswiss-") for case_id in case_ids):
        raise PipelineError("IDs da coorte v16 invalidos.")
    scores = _read_scores(scores_csv_path, case_ids)
    subjects = _case_subject_map(source_map_path, case_ids)

    input_rows = _jsonl(input_manifest_path)
    if {str(row.get("case_id", "")) for row in input_rows} < case_ids:
        raise PipelineError("Manifesto de inputs nao cobre a coorte v16.")
    for case_id in case_ids:
        localizer_manifest = localizer_root / case_id / "localizer_manifest.json"
        candidate_mask = localizer_root / case_id / "liver_lesion_candidates_in_liver.nii.gz"
        if not localizer_manifest.is_file() or not candidate_mask.is_file():
            raise PipelineError(f"Artefato cego do localizador ausente: {case_id}.")

    with zipfile.ZipFile(archive_path) as archive:
        names = [info.filename for info in archive.infolist() if not info.is_dir()]
    if len(names) != len(set(names)) or any(Path(name).is_absolute() or ".." in Path(name).parts for name in names):
        raise PipelineError("Arquivo de derivacoes contem nomes inseguros ou duplicados.")
    venous_by_subject: dict[str, list[tuple[int, str]]] = {subject: [] for subject in subjects.values()}
    all_manual_counts = {subject: 0 for subject in subjects.values()}
    for name in names:
        parts = name.split("/")
        if len(parts) >= 4 and parts[:2] == ["derivatives", "manual_lesion_annotations"]:
            subject = parts[2]
            if subject in all_manual_counts:
                all_manual_counts[subject] += 1
        match = VENOUS_MASK_RE.fullmatch(name)
        if match and match.group(1) in venous_by_subject:
            venous_by_subject[match.group(1)].append((int(match.group(2)), name))
    for values in venous_by_subject.values():
        values.sort(key=lambda item: (item[0], item[1]))
        if len({lesion for lesion, _ in values}) != len(values):
            raise PipelineError("Lesao venosa duplicada no arquivo publico.")

    cases_protocol = []
    for case_id in sorted(case_ids):
        subject = subjects[case_id]
        masks = venous_by_subject[subject]
        cases_protocol.append(
            {
                "case_id": case_id,
                "public_subject_id": subject,
                "label_post_inference": scores[case_id]["label"],
                "manual_lesion_mask_count_all_phases": all_manual_counts[subject],
                "venous_masks": [
                    {"lesion_id": f"L{number}", "archive_member": name}
                    for number, name in masks
                ],
                "localizer_manifest_sha256": _sha256(localizer_root / case_id / "localizer_manifest.json"),
                "candidate_mask_sha256": _sha256(localizer_root / case_id / "liver_lesion_candidates_in_liver.nii.gz"),
            }
        )
    protocol: dict[str, Any] = {
        "schema": PROTOCOL_SCHEMA,
        "purpose": "retrospective_diagnostic_audit_of_v16_localizer",
        "case_count": 87,
        "positive_case_count": sum(row["label"] == "POSITIVE" for row in scores.values()),
        "negative_case_count": sum(row["label"] == "NEGATIVE" for row in scores.values()),
        "archive": {
            "name": archive_path.name,
            "md5": EXPECTED_ARCHIVE_MD5,
            "sha256": _sha256(archive_path),
            "manual_lesion_file_count": sum(all_manual_counts.values()),
        },
        "sources": {
            "cohort_manifest_sha256": _sha256(cohort_manifest_path),
            "scores_csv_sha256": _sha256(scores_csv_path),
            "source_map_sha256": _sha256(source_map_path),
            "input_manifest_sha256": _sha256(input_manifest_path),
        },
        "frozen_definitions": {
            "reference_phase": "t1_venous",
            "component_hit": "intersection_voxels_between_selected_v16_component_and_manual_venous_mask_gt_0",
            "stack_visibility_hit": "manual_venous_mask_voxel_inside_union_of_actual_t1_venous_crop_bboxes_and_rendered_z_indices_gt_0",
            "case_hit": "at_least_one_manual_venous_lesion_hit",
            "lesion_hit": "individual_manual_venous_lesion_hit",
            "confidence_interval": "wilson_95_percent",
            "primary_denominators": ["positive_cases_with_manual_venous_mask", "manual_venous_lesions_in_positive_cases"],
            "threshold_75_percent": "reference_only_not_a_posthoc_optimization_gate",
            "hcc_specificity": "not_claimed_because_public_archive_has_no_per_lesion_diagnosis_metadata",
        },
        "safety": {
            "retrospective_only": True,
            "inference_executed": False,
            "medgemma_called": False,
            "lesion_masks_used_for_inference": False,
            "lesion_masks_sent_to_medgemma": False,
            "holdout_opened": False,
            "development_only": True,
        },
        "cases": cases_protocol,
    }
    protocol["protocol_signature"] = _canonical_sha(protocol)
    _write_json_atomic(output_path, protocol)
    return protocol


def extract_authorized_venous_masks(*, archive_path: Path, protocol_path: Path, output_root: Path) -> dict[str, Any]:
    """Extract only the exact venous lesion members frozen in the protocol."""

    archive_path, protocol_path, output_root = map(Path, (archive_path, protocol_path, output_root))
    _refuse_holdout(archive_path, protocol_path, output_root)
    protocol = _load_json(protocol_path)
    signature = protocol.pop("protocol_signature", None)
    if protocol.get("schema") != PROTOCOL_SCHEMA or signature != _canonical_sha(protocol):
        raise PipelineError("Assinatura do protocolo de auditoria v16 invalida.")
    protocol["protocol_signature"] = signature
    if _sha256(archive_path) != protocol["archive"]["sha256"] or _md5(archive_path) != EXPECTED_ARCHIVE_MD5:
        raise PipelineError("Arquivo de derivacoes mudou apos congelamento.")
    if output_root.exists():
        raise PipelineError("Extracao autorizada ja existe; sobrescrita recusada.")

    temporary = output_root.with_name(f".{output_root.name}.{uuid.uuid4().hex}.tmp")
    records: list[dict[str, Any]] = []
    try:
        temporary.mkdir(parents=True)
        with zipfile.ZipFile(archive_path) as archive:
            info_by_name = {info.filename: info for info in archive.infolist() if not info.is_dir()}
            requested = [
                (case["case_id"], mask["lesion_id"], mask["archive_member"])
                for case in protocol["cases"] for mask in case["venous_masks"]
            ]
            if len({member for _, _, member in requested}) != len(requested):
                raise PipelineError("Membro de mascara repetido no protocolo.")
            for case_id, lesion_id, member in requested:
                if member not in info_by_name or not VENOUS_MASK_RE.fullmatch(member):
                    raise PipelineError("Mascara solicitada ausente ou fora do escopo venoso autorizado.")
                case_dir = temporary / case_id
                case_dir.mkdir(exist_ok=True)
                destination = case_dir / f"{lesion_id}_t1_venous_seg.nii.gz"
                with archive.open(info_by_name[member]) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
                records.append(
                    {
                        "case_id": case_id,
                        "lesion_id": lesion_id,
                        "archive_member": member,
                        "relative_path": destination.relative_to(temporary).as_posix(),
                        "bytes": destination.stat().st_size,
                        "sha256": _sha256(destination),
                    }
                )
        manifest = {
            "schema": EXTRACTION_SCHEMA,
            "protocol_signature": signature,
            "mask_count": len(records),
            "masks": records,
            "safety": protocol["safety"],
        }
        _write_json_atomic(temporary / "extraction_manifest.json", manifest)
        temporary.replace(output_root)
        return manifest
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _wilson(successes: int, total: int) -> list[float] | None:
    if total <= 0:
        return None
    z = 1.959963984540054
    p = successes / total
    denominator = 1.0 + z * z / total
    center = (p + z * z / (2.0 * total)) / denominator
    margin = z * math.sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total)) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def _metric(successes: int, total: int) -> dict[str, Any]:
    return {
        "successes": int(successes),
        "total": int(total),
        "fraction": None if total == 0 else successes / total,
        "percent": None if total == 0 else 100.0 * successes / total,
        "wilson_95_fraction": _wilson(successes, total),
    }


def _component_labels(candidate: np.ndarray, manifest: dict[str, Any]) -> tuple[np.ndarray, dict[int, int]]:
    labels, count = ndimage.label(candidate, structure=ndimage.generate_binary_structure(3, 3))
    expected = manifest.get("features", {}).get("components", [])
    if count != len(expected):
        raise PipelineError("Componentes candidatos divergiram na auditoria.")

    actual = []
    for component_id in range(1, count + 1):
        indices_zyx = np.argwhere(labels == component_id)
        actual.append(
            {
                "component_id": component_id,
                "voxels": int(indices_zyx.shape[0]),
                "centroid_index_xyz": [float(value) for value in indices_zyx.mean(axis=0)[::-1]],
            }
        )
    unmatched = list(actual)
    rank_to_id: dict[int, int] = {}
    for source in sorted(expected, key=lambda item: int(item["rank_by_volume"])):
        matches = [
            item for item in unmatched
            if item["voxels"] == int(source["voxels"])
            and np.allclose(
                item["centroid_index_xyz"],
                source["centroid_index_xyz"],
                rtol=0,
                atol=1e-5,
            )
        ]
        if len(matches) != 1:
            raise PipelineError("Volume/centro candidato divergiu na auditoria.")
        match = matches[0]
        unmatched.remove(match)
        rank_to_id[int(source["rank_by_volume"])] = int(match["component_id"])
    if len(rank_to_id) != count:
        raise PipelineError("Ranks candidatos duplicados na auditoria.")
    return labels, rank_to_id


def _actual_venous_visibility(case_dir: Path, shape_zyx: tuple[int, int, int]) -> np.ndarray:
    visible = np.zeros(shape_zyx, dtype=bool)
    case_manifest = _load_json(case_dir / "case_manifest.json")
    for stack in case_manifest.get("candidate_stacks", []):
        manifest_path = case_dir / stack["relative_directory"] / "manifest.json"
        if _sha256(manifest_path) != stack["manifest_sha256"]:
            raise PipelineError("Hash de stack candidato mudou antes da auditoria.")
        manifest = _load_json(manifest_path)
        groups = [group for group in manifest.get("groups", []) if group.get("role") == "t1_venous"]
        if len(groups) != 1:
            raise PipelineError("Grupo venoso unico ausente no stack v16.")
        group = groups[0]
        y0, y1, x0, x1 = map(int, group["crop_bbox_yxyx"])
        if not (0 <= y0 < y1 <= shape_zyx[1] and 0 <= x0 < x1 <= shape_zyx[2]):
            raise PipelineError("BBox venoso fora da geometria na auditoria.")
        for z in map(int, group["selected_source_indices_z"]):
            if not 0 <= z < shape_zyx[0]:
                raise PipelineError("Corte venoso fora da geometria na auditoria.")
            visible[z, y0:y1, x0:x1] = True
    return visible


def run_audit(
    *,
    protocol_path: Path,
    extraction_root: Path,
    cohort_root: Path,
    localizer_root: Path,
    input_manifest_path: Path,
    input_root: Path,
    scores_csv_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Decode authorized masks and calculate retrospective localization metrics."""

    paths = tuple(map(Path, (protocol_path, extraction_root, cohort_root, localizer_root,
                            input_manifest_path, input_root, scores_csv_path, output_root)))
    _refuse_holdout(*paths)
    protocol_path, extraction_root, cohort_root, localizer_root, input_manifest_path, input_root, scores_csv_path, output_root = paths
    if output_root.exists():
        raise PipelineError("Saida da auditoria v16 ja existe; sobrescrita recusada.")
    protocol = _load_json(protocol_path)
    signature = protocol.pop("protocol_signature", None)
    if protocol.get("schema") != PROTOCOL_SCHEMA or signature != _canonical_sha(protocol):
        raise PipelineError("Protocolo v16 adulterado antes da auditoria.")
    protocol["protocol_signature"] = signature
    extraction = _load_json(extraction_root / "extraction_manifest.json")
    if extraction.get("schema") != EXTRACTION_SCHEMA or extraction.get("protocol_signature") != signature:
        raise PipelineError("Extracao nao corresponde ao protocolo v16.")
    extraction_by_case: dict[str, list[dict[str, Any]]] = {}
    for record in extraction.get("masks", []):
        extraction_by_case.setdefault(record["case_id"], []).append(record)

    input_rows = {str(row["case_id"]): row for row in _jsonl(input_manifest_path)}
    case_ids = {case["case_id"] for case in protocol["cases"]}
    scores = _read_scores(scores_csv_path, case_ids)
    case_rows: list[dict[str, Any]] = []
    lesion_rows: list[dict[str, Any]] = []
    for case in protocol["cases"]:
        case_id = case["case_id"]
        row = input_rows.get(case_id)
        if row is None:
            raise PipelineError(f"Input do caso ausente na auditoria: {case_id}.")
        by_role = {item["role"]: item for item in row.get("files", [])}
        venous_item = by_role.get("t1_venous")
        if venous_item is None:
            raise PipelineError("T1 venoso ausente na auditoria.")
        venous_path = (input_root / venous_item["relative_path"]).resolve()
        if not venous_path.is_relative_to(input_root.resolve()) or _sha256(venous_path) != venous_item["sha256"]:
            raise PipelineError("Fonte venosa insegura ou com hash divergente.")
        reference = sitk.ReadImage(str(venous_path))

        localizer_dir = localizer_root / case_id
        localizer_manifest_path = localizer_dir / "localizer_manifest.json"
        candidate_path = localizer_dir / "liver_lesion_candidates_in_liver.nii.gz"
        if _sha256(localizer_manifest_path) != case["localizer_manifest_sha256"] or _sha256(candidate_path) != case["candidate_mask_sha256"]:
            raise PipelineError("Artefato do localizador mudou depois do protocolo.")
        localizer_manifest = _load_json(localizer_manifest_path)
        if (
            localizer_manifest.get("ground_truth_read") is not False
            or localizer_manifest.get("ground_truth_lesion_mask_used") is not False
            or localizer_manifest.get("final_decision") is not None
        ):
            raise PipelineError("Localizador nao cego detectado na auditoria.")
        candidate_img = sitk.ReadImage(str(candidate_path))
        if not _geometry_equal(candidate_img, reference):
            raise PipelineError("Geometria candidata divergiu da referencia venosa.")
        candidate = sitk.GetArrayFromImage(candidate_img) > 0
        component_labels, rank_to_id = _component_labels(candidate, localizer_manifest)
        case_manifest_path = cohort_root / case_id / "case_manifest.json"
        case_manifest = _load_json(case_manifest_path)
        if case_manifest.get("case_id") != case_id or case_manifest.get("gate", {}).get("ground_truth_read") is not False:
            raise PipelineError("Manifesto de caso v16 invalido na auditoria.")
        selected_ranks = list(map(int, case_manifest["selection"]["selected_component_ranks"]))
        selected_component = np.isin(component_labels, [rank_to_id[rank] for rank in selected_ranks])
        visible = _actual_venous_visibility(cohort_root / case_id, candidate.shape)

        masks = []
        for record in sorted(extraction_by_case.get(case_id, []), key=lambda value: value["lesion_id"]):
            mask_path = extraction_root / record["relative_path"]
            if _sha256(mask_path) != record["sha256"]:
                raise PipelineError("Mascara manual mudou depois da extracao autorizada.")
            mask_img = sitk.ReadImage(str(mask_path))
            if not _manual_mask_index_aligned(mask_img, reference):
                raise PipelineError(f"Geometria da mascara manual divergiu do T1 venoso: {case_id}/{record['lesion_id']}.")
            mask = sitk.GetArrayFromImage(mask_img) > 0
            if not mask.any():
                raise PipelineError("Mascara manual vazia na auditoria.")
            masks.append((record["lesion_id"], record["sha256"], mask))

        component_hits = 0
        visibility_hits = 0
        for lesion_id, mask_sha, mask in masks:
            voxels = int(mask.sum())
            component_overlap = int(np.logical_and(mask, selected_component).sum())
            visible_overlap = int(np.logical_and(mask, visible).sum())
            component_hit = component_overlap > 0
            visibility_hit = visible_overlap > 0
            component_hits += int(component_hit)
            visibility_hits += int(visibility_hit)
            lesion_rows.append(
                {
                    "case_id": case_id,
                    "label": scores[case_id]["label"],
                    "lesion_id": lesion_id,
                    "lesion_mask_sha256": mask_sha,
                    "lesion_voxels": voxels,
                    "lesion_volume_mm3": voxels * float(np.prod(reference.GetSpacing())),
                    "selected_component_intersection_voxels": component_overlap,
                    "component_hit": component_hit,
                    "component_lesion_coverage_fraction": component_overlap / voxels,
                    "visible_stack_intersection_voxels": visible_overlap,
                    "stack_visibility_hit": visibility_hit,
                    "visible_lesion_fraction": visible_overlap / voxels,
                }
            )
        label = scores[case_id]["label"]
        predicted_positive = scores[case_id]["selected_candidate_classification"] == "POSITIVA"
        case_rows.append(
            {
                "case_id": case_id,
                "label": label,
                "manual_venous_lesion_count": len(masks),
                "selected_component_count": len(selected_ranks),
                "candidate_stack_count": int(case_manifest["candidate_stack_count"]),
                "fallback_no_candidate": len(selected_ranks) == 0,
                "component_case_hit": bool(component_hits) if masks else "",
                "stack_visibility_case_hit": bool(visibility_hits) if masks else "",
                "component_lesion_hits": component_hits,
                "stack_visibility_lesion_hits": visibility_hits,
                "predicted_positive_v16": predicted_positive,
                "v16_case_correct": predicted_positive == (label == "POSITIVE"),
            }
        )

    positive_case_rows = [row for row in case_rows if row["label"] == "POSITIVE" and row["manual_venous_lesion_count"] > 0]
    positive_lesion_rows = [row for row in lesion_rows if row["label"] == "POSITIVE"]
    negative_case_rows = [row for row in case_rows if row["label"] == "NEGATIVE" and row["manual_venous_lesion_count"] > 0]
    summary = {
        "positive_cases_with_manual_venous_mask": len(positive_case_rows),
        "negative_cases_with_manual_venous_mask": len(negative_case_rows),
        "positive_manual_venous_lesion_count": len(positive_lesion_rows),
        "component_case_recall_positive": _metric(sum(bool(row["component_case_hit"]) for row in positive_case_rows), len(positive_case_rows)),
        "stack_visibility_case_recall_positive": _metric(sum(bool(row["stack_visibility_case_hit"]) for row in positive_case_rows), len(positive_case_rows)),
        "component_lesion_recall_positive": _metric(sum(bool(row["component_hit"]) for row in positive_lesion_rows), len(positive_lesion_rows)),
        "stack_visibility_lesion_recall_positive": _metric(sum(bool(row["stack_visibility_hit"]) for row in positive_lesion_rows), len(positive_lesion_rows)),
        "v16_true_positive_rate_when_stack_visible": _metric(
            sum(bool(row["predicted_positive_v16"]) for row in positive_case_rows if row["stack_visibility_case_hit"]),
            sum(bool(row["stack_visibility_case_hit"]) for row in positive_case_rows),
        ),
        "v16_true_positive_rate_when_stack_not_visible": _metric(
            sum(bool(row["predicted_positive_v16"]) for row in positive_case_rows if not row["stack_visibility_case_hit"]),
            sum(not bool(row["stack_visibility_case_hit"]) for row in positive_case_rows),
        ),
    }
    result: dict[str, Any] = {
        "schema": AUDIT_SCHEMA,
        "protocol_signature": signature,
        "case_count": len(case_rows),
        "manual_venous_mask_count": len(lesion_rows),
        "summary": summary,
        "interpretation_limits": [
            "Retrospective diagnostic audit; no threshold or model was selected from these masks.",
            "Manual masks identify annotated lesions visible on the venous phase, not lesion-level HCC diagnosis.",
            "Stack visibility is exact for rendered venous z-indices and crop boxes; other sequence masks were not opened.",
        ],
        "safety": {
            "inference_executed": False,
            "medgemma_called": False,
            "lesion_masks_used_for_inference": False,
            "lesion_masks_sent_to_medgemma": False,
            "holdout_opened": False,
            "development_only": True,
        },
    }
    result["audit_signature"] = _canonical_sha(result)
    temporary = output_root.with_name(f".{output_root.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.mkdir(parents=True)
        _write_csv_atomic(temporary / "case_localization.csv", case_rows)
        if lesion_rows:
            _write_csv_atomic(temporary / "lesion_localization.csv", lesion_rows)
        _write_json_atomic(temporary / "audit.json", result)
        temporary.replace(output_root)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return result


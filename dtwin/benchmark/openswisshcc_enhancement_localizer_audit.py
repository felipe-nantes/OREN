"""Retrospective development-only audit for the blind v22 enhancement proposals.

This module is intentionally isolated from every inference path.  It reads the
protected development labels and the already-authorized public venous lesion
masks only after blind proposal generation.  It never imports or calls a model
client and refuses every path containing a holdout component.
"""
from __future__ import annotations

import csv
import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import SimpleITK as sitk
from scipy import ndimage

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_enhancement_localizer import (
    ALGORITHM_VERSION,
    CASE_SCHEMA,
    COHORT_SCHEMA,
    THRESHOLDS,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic


AUDIT_SCHEMA = "argos-openswisshcc-enhancement-localizer-audit-v22"
EXTRACTION_SCHEMA = "argos-openswisshcc-v16-authorized-mask-extraction-v1"
LABEL_SCHEMA = "argos-openswisshcc-ground-truth-v1"
SELECTIONS: tuple[tuple[str, int | None], ...] = (
    ("all", None),
    ("top3", 3),
    ("top5", 5),
    ("top10", 10),
    ("top20", 20),
)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON invalido na auditoria de realce v22: {path}.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"Objeto JSON esperado na auditoria de realce v22: {path}.")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError
                rows.append(value)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        number = locals().get("line_number", 0)
        raise PipelineError(
            f"JSONL invalido na linha {number} da auditoria de realce v22: {path}."
        ) from exc
    return rows


def _refuse_holdout(*paths: Path) -> None:
    for path in paths:
        if any("holdout" in part.lower() for part in Path(path).resolve().parts):
            raise PipelineError("Auditoria de realce v22 recusou caminho de holdout.")


def _safe_relative(root: Path, relative: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or ".." in value.parts:
        raise PipelineError("Caminho relativo inseguro na auditoria de realce v22.")
    resolved = (root / value).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise PipelineError("Artefato escapou da raiz autorizada na auditoria v22.") from exc
    return resolved


def _validate_file(path: Path, *, expected_hash: str, expected_bytes: int) -> None:
    if (
        not path.is_file()
        or path.stat().st_size != int(expected_bytes)
        or _sha256(path) != str(expected_hash)
    ):
        raise PipelineError(f"Artefato ausente ou adulterado na auditoria v22: {path}.")


def _geometry_equal(left: sitk.Image, right: sitk.Image) -> bool:
    return (
        left.GetSize() == right.GetSize()
        and np.allclose(left.GetSpacing(), right.GetSpacing(), rtol=0, atol=1e-7)
        and np.allclose(left.GetOrigin(), right.GetOrigin(), rtol=0, atol=1e-3)
        and np.allclose(left.GetDirection(), right.GetDirection(), rtol=0, atol=1e-6)
    )


def _read_binary_mask(path: Path) -> tuple[sitk.Image, np.ndarray]:
    try:
        image = sitk.ReadImage(str(path))
        array = sitk.GetArrayFromImage(image)
    except RuntimeError as exc:
        raise PipelineError(f"Mascara NIfTI invalida na auditoria v22: {path}.") from exc
    if array.ndim != 3 or not np.isfinite(array).all():
        raise PipelineError(f"Mascara 3D finita esperada na auditoria v22: {path}.")
    return image, np.asarray(array > 0, dtype=bool)


def _distribution(values: Iterable[int]) -> dict[str, float | int | None]:
    array = np.asarray(list(values), dtype=np.float64)
    if array.size == 0:
        return {"count": 0, "mean": None, "median": None, "q25": None, "q75": None}
    return {
        "count": int(array.size),
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "q25": float(np.percentile(array, 25)),
        "q75": float(np.percentile(array, 75)),
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return float(numerator / denominator) if denominator else None


def _write_csv_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise PipelineError("Auditoria de realce v22 recusou CSV vazio.")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _report_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Auditoria retrospectiva do localizador de realce v22",
        "",
        "Esta auditoria usa somente o conjunto de desenvolvimento. As propostas foram geradas de forma cega antes da abertura dos labels e das mascaras publicas de lesao.",
        "",
        "## Coorte",
        "",
        f"- Casos declarados: {result['case_count']}",
        f"- Casos com realce multifasico disponivel: {result['available_case_count']}",
        f"- Positivos/negativos disponiveis: {result['available_positive_count']}/{result['available_negative_count']}",
        f"- Positivos com mascara venosa publica: {result['positive_cases_with_venous_masks']}",
        f"- Lesoes venosas publicas: {result['venous_lesion_count']}",
        "",
        "## Cobertura retrospectiva",
        "",
        "| Limiar | Selecao | Casos atingidos | Recall por caso | Lesoes atingidas | Recall por lesao |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for metric in result["metrics"]:
        case_recall = metric["case_recall"]
        lesion_recall = metric["lesion_recall"]
        lines.append(
            "| {threshold_key} | {selection} | {case_hits}/{case_denominator} | {case_pct} | "
            "{lesion_hits}/{lesion_denominator} | {lesion_pct} |".format(
                **metric,
                case_pct="n/a" if case_recall is None else f"{100 * case_recall:.2f}%",
                lesion_pct="n/a" if lesion_recall is None else f"{100 * lesion_recall:.2f}%",
            )
        )
    lines.extend(
        [
            "",
            "## Interpretacao obrigatoria",
            "",
            "- Presenca de proposta nao e classificacao diagnostica; portanto esta auditoria nao estima especificidade ou acuracia.",
            "- As mascaras publicas foram usadas apenas retrospectivamente para medir intersecao e nunca foram usadas na inferencia ou enviadas ao MedGemma.",
            "- Os casos sem registro multifasico foram excluidos apenas dos denominadores multifasicos e permanecem declarados.",
            "- O resultado nao qualifica o ARGOS e nao autoriza uso clinico.",
            "",
        ]
    )
    return "\n".join(lines)


def audit_enhancement_localizer(
    *,
    proposal_root: Path,
    labels_path: Path,
    authorized_extraction_root: Path,
    output_root: Path,
    expected_case_count: int = 87,
) -> dict[str, Any]:
    """Audit frozen blind enhancement proposals against development masks."""

    proposal_root = Path(proposal_root).resolve()
    labels_path = Path(labels_path).resolve()
    extraction_root = Path(authorized_extraction_root).resolve()
    output_root = Path(output_root).resolve()
    _refuse_holdout(proposal_root, labels_path, extraction_root, output_root)
    if output_root.exists():
        raise PipelineError("Saida da auditoria de realce v22 ja existe.")

    summary_path = proposal_root / "summary.json"
    summary = _load_json(summary_path)
    case_ids = summary.get("case_ids")
    unavailable = summary.get("unavailable_case_ids")
    manifest_hashes = summary.get("case_manifest_hashes")
    expected_thresholds = [float(value) for value in THRESHOLDS]
    if (
        summary.get("schema") != COHORT_SCHEMA
        or summary.get("status") != "complete_blind_proposals_with_declared_fallbacks"
        or summary.get("algorithm_version") != ALGORITHM_VERSION
        or int(summary.get("case_count", -1)) != expected_case_count
        or summary.get("labels_read") is not False
        or summary.get("ground_truth_lesion_masks_read") != 0
        or summary.get("inference_executed") is not False
        or summary.get("research_only") is not True
        or summary.get("clinical_use_allowed") is not False
        or summary.get("requires_human_review") is not True
        or summary.get("thresholds") != expected_thresholds
        or int(summary.get("minimum_component_voxels", -1)) != 8
        or not isinstance(case_ids, list)
        or not isinstance(unavailable, list)
        or not isinstance(manifest_hashes, dict)
    ):
        raise PipelineError("Resumo cego do localizador de realce v22 invalido.")
    case_ids = [str(value) for value in case_ids]
    unavailable_ids = {str(value) for value in unavailable}
    if (
        len(case_ids) != expected_case_count
        or len(set(case_ids)) != expected_case_count
        or not unavailable_ids <= set(case_ids)
        or int(summary.get("available_case_count", -1)) != expected_case_count - len(unavailable_ids)
        or set(manifest_hashes) != set(case_ids) - unavailable_ids
    ):
        raise PipelineError("Cobertura de casos inconsistente no resumo cego v22.")

    label_rows = _load_jsonl(labels_path)
    labels: dict[str, str] = {}
    for row in label_rows:
        case_id = str(row.get("case_id", ""))
        label = str(row.get("label", ""))
        if (
            row.get("schema") != LABEL_SCHEMA
            or case_id in labels
            or label not in {"POSITIVE", "NEGATIVE"}
        ):
            raise PipelineError("Labels protegidos invalidos na auditoria de realce v22.")
        labels[case_id] = label
    if not set(case_ids) <= set(labels):
        raise PipelineError("Labels protegidos nao cobrem integralmente a coorte v22.")
    ignored_label_case_ids = sorted(set(labels) - set(case_ids))

    extraction_path = extraction_root / "extraction_manifest.json"
    extraction = _load_json(extraction_path)
    mask_records = extraction.get("masks")
    if (
        extraction.get("schema") != EXTRACTION_SCHEMA
        or not isinstance(mask_records, list)
        or int(extraction.get("mask_count", -1)) != len(mask_records)
    ):
        raise PipelineError("Manifesto de mascaras autorizadas invalido na auditoria v22.")
    masks_by_case: dict[str, list[dict[str, Any]]] = {}
    seen_masks: set[tuple[str, str]] = set()
    for record in mask_records:
        case_id = str(record.get("case_id", ""))
        lesion_id = str(record.get("lesion_id", ""))
        key = (case_id, lesion_id)
        if case_id not in labels or not lesion_id or key in seen_masks:
            raise PipelineError("Mascara autorizada duplicada ou fora da coorte v22.")
        path = _safe_relative(extraction_root, str(record.get("relative_path", "")))
        _validate_file(
            path,
            expected_hash=str(record.get("sha256", "")),
            expected_bytes=int(record.get("bytes", -1)),
        )
        seen_masks.add(key)
        masks_by_case.setdefault(case_id, []).append({**record, "path": path})
    for records in masks_by_case.values():
        records.sort(key=lambda item: str(item["lesion_id"]))

    rows: list[dict[str, Any]] = []
    metrics_accumulator: dict[tuple[str, str], dict[str, Any]] = {}
    for threshold in THRESHOLDS:
        threshold_key = f"t{int(threshold)}"
        for selection, _ in SELECTIONS:
            metrics_accumulator[(threshold_key, selection)] = {
                "case_hits": 0,
                "case_denominator": 0,
                "lesion_hits": 0,
                "lesion_denominator": 0,
                "by_label": {
                    "POSITIVE": {"voxels": [], "components": [], "present": 0, "count": 0},
                    "NEGATIVE": {"voxels": [], "components": [], "present": 0, "count": 0},
                },
            }

    structure = ndimage.generate_binary_structure(3, 2)
    for case_id in case_ids:
        label = labels[case_id]
        if case_id in unavailable_ids:
            rows.append(
                {
                    "case_id": case_id,
                    "label": label,
                    "available": False,
                    "threshold_key": "",
                    "selection": "unavailable",
                    "candidate_voxels": "",
                    "selected_component_count": "",
                    "manual_venous_lesion_count": len(masks_by_case.get(case_id, [])),
                    "case_hit": "",
                    "lesion_hits": "",
                }
            )
            continue

        manifest_path = proposal_root / case_id / "manifest.json"
        if not manifest_path.is_file() or _sha256(manifest_path) != manifest_hashes[case_id]:
            raise PipelineError(f"Manifesto de caso ausente ou adulterado: {case_id}.")
        manifest = _load_json(manifest_path)
        proposals = manifest.get("proposals")
        if (
            manifest.get("schema") != CASE_SCHEMA
            or manifest.get("case_id") != case_id
            or manifest.get("algorithm_version") != ALGORITHM_VERSION
            or manifest.get("status") != "complete_blind_proposals"
            or manifest.get("dynamic_alignment_mode") != "registered_to_venous"
            or manifest.get("ground_truth_read") is not False
            or manifest.get("ground_truth_lesion_mask_used") is not False
            or manifest.get("metrics_calculated") is not False
            or manifest.get("final_decision") is not None
            or manifest.get("research_only") is not True
            or manifest.get("clinical_use_allowed") is not False
            or manifest.get("requires_human_review") is not True
            or not isinstance(proposals, list)
        ):
            raise PipelineError(f"Manifesto cego de caso invalido: {case_id}.")
        indexed = {str(item.get("threshold_key", "")): item for item in proposals}
        if set(indexed) != {f"t{int(value)}" for value in THRESHOLDS} or len(indexed) != len(proposals):
            raise PipelineError(f"Conjunto de limiares invalido no caso {case_id}.")

        lesion_images: list[tuple[sitk.Image, np.ndarray]] | None = None
        for threshold in THRESHOLDS:
            threshold_key = f"t{int(threshold)}"
            proposal = indexed[threshold_key]
            expected_name = f"joint_enhancement_proposals_{threshold_key}.nii.gz"
            if (
                float(proposal.get("threshold", -1)) != float(threshold)
                or proposal.get("filename") != expected_name
            ):
                raise PipelineError(f"Metadados de proposta invalidos no caso {case_id}.")
            mask_path = _safe_relative(proposal_root / case_id, expected_name)
            _validate_file(
                mask_path,
                expected_hash=str(proposal.get("sha256", "")),
                expected_bytes=int(proposal.get("bytes", -1)),
            )
            proposal_image, proposal_mask = _read_binary_mask(mask_path)
            labels_array, component_count = ndimage.label(proposal_mask, structure=structure)
            sizes = np.bincount(labels_array.ravel(), minlength=int(component_count) + 1)
            ranked_ids = sorted(range(1, int(component_count) + 1), key=lambda idx: (-int(sizes[idx]), idx))
            if (
                int(proposal.get("proposal_voxels", -1)) != int(proposal_mask.sum())
                or int(proposal.get("component_count", -1)) != int(component_count)
                or int(proposal.get("largest_component_voxels", -1))
                != (int(sizes[ranked_ids[0]]) if ranked_ids else 0)
                or any(int(sizes[index]) < 8 for index in ranked_ids)
            ):
                raise PipelineError(f"Estatisticas da proposta divergem do NIfTI: {case_id}/{threshold_key}.")

            if lesion_images is None:
                lesion_images = []
                for record in masks_by_case.get(case_id, []):
                    lesion_image, lesion_mask = _read_binary_mask(record["path"])
                    if not _geometry_equal(proposal_image, lesion_image):
                        raise PipelineError(f"Geometria proposta/lesao divergiu no caso {case_id}.")
                    lesion_images.append((lesion_image, lesion_mask))
            for selection, top_k in SELECTIONS:
                selected_ids = ranked_ids if top_k is None else ranked_ids[:top_k]
                selected_mask = np.isin(labels_array, selected_ids) if selected_ids else np.zeros_like(proposal_mask)
                lesion_hits = sum(int(np.any(selected_mask & lesion_mask)) for _, lesion_mask in lesion_images)
                case_hit: bool | None = bool(lesion_hits) if lesion_images else None
                accumulator = metrics_accumulator[(threshold_key, selection)]
                label_bucket = accumulator["by_label"][label]
                label_bucket["count"] += 1
                label_bucket["present"] += int(np.any(selected_mask))
                label_bucket["voxels"].append(int(selected_mask.sum()))
                label_bucket["components"].append(len(selected_ids))
                if label == "POSITIVE" and lesion_images:
                    accumulator["case_denominator"] += 1
                    accumulator["case_hits"] += int(bool(lesion_hits))
                    accumulator["lesion_denominator"] += len(lesion_images)
                    accumulator["lesion_hits"] += lesion_hits
                rows.append(
                    {
                        "case_id": case_id,
                        "label": label,
                        "available": True,
                        "threshold_key": threshold_key,
                        "selection": selection,
                        "candidate_voxels": int(selected_mask.sum()),
                        "selected_component_count": len(selected_ids),
                        "manual_venous_lesion_count": len(lesion_images),
                        "case_hit": "" if case_hit is None else case_hit,
                        "lesion_hits": lesion_hits,
                    }
                )

    metrics: list[dict[str, Any]] = []
    for threshold in THRESHOLDS:
        threshold_key = f"t{int(threshold)}"
        for selection, top_k in SELECTIONS:
            value = metrics_accumulator[(threshold_key, selection)]
            by_label: dict[str, Any] = {}
            for label, bucket in value["by_label"].items():
                by_label[label] = {
                    "case_count": bucket["count"],
                    "candidate_present_count": bucket["present"],
                    "candidate_present_rate": _ratio(bucket["present"], bucket["count"]),
                    "candidate_voxels": _distribution(bucket["voxels"]),
                    "selected_component_count": _distribution(bucket["components"]),
                }
            metrics.append(
                {
                    "threshold_key": threshold_key,
                    "threshold": float(threshold),
                    "selection": selection,
                    "top_k": top_k,
                    "case_hits": value["case_hits"],
                    "case_denominator": value["case_denominator"],
                    "case_recall": _ratio(value["case_hits"], value["case_denominator"]),
                    "lesion_hits": value["lesion_hits"],
                    "lesion_denominator": value["lesion_denominator"],
                    "lesion_recall": _ratio(value["lesion_hits"], value["lesion_denominator"]),
                    "candidate_burden_by_label": by_label,
                }
            )

    available_ids = set(case_ids) - unavailable_ids
    positive_with_masks = {
        case_id
        for case_id in available_ids
        if labels[case_id] == "POSITIVE" and masks_by_case.get(case_id)
    }
    result: dict[str, Any] = {
        "schema": AUDIT_SCHEMA,
        "status": "retrospective_development_audit_complete",
        "algorithm_version": ALGORITHM_VERSION,
        "case_count": len(case_ids),
        "available_case_count": len(available_ids),
        "unavailable_case_ids": sorted(unavailable_ids),
        "labels_outside_frozen_cohort_ignored": ignored_label_case_ids,
        "available_positive_count": sum(labels[case_id] == "POSITIVE" for case_id in available_ids),
        "available_negative_count": sum(labels[case_id] == "NEGATIVE" for case_id in available_ids),
        "positive_cases_with_venous_masks": len(positive_with_masks),
        "venous_lesion_count": sum(len(masks_by_case.get(case_id, [])) for case_id in positive_with_masks),
        "metrics": metrics,
        "source_hashes": {
            "proposal_summary_sha256": _sha256(summary_path),
            "development_labels_sha256": _sha256(labels_path),
            "authorized_extraction_manifest_sha256": _sha256(extraction_path),
        },
        "interpretation": {
            "candidate_presence_is_not_classification": True,
            "specificity_claimed": False,
            "accuracy_claimed": False,
            "unavailable_cases_excluded_only_from_multiphase_denominators": True,
        },
        "qualified": False,
        "development_only": True,
        "holdout_used": False,
        "inference_executed": False,
        "medgemma_called": False,
        "lesion_masks_used_for_inference": False,
        "lesion_masks_sent_to_medgemma": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }

    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._v22enh_audit_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json_atomic(staging / "audit.json", result)
        _write_csv_atomic(staging / "case_metrics.csv", rows)
        (staging / "report.md").write_text(_report_markdown(result), encoding="utf-8")
        _publish_directory(staging, output_root)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return result


__all__ = ["AUDIT_SCHEMA", "SELECTIONS", "audit_enhancement_localizer"]

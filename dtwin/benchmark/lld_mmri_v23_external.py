"""Freeze the independent LLD-MMRI v23 external-validation cohort.

The public annotation is used only to select HCC versus benign mimics and to
write protected labels. Raw UIDs, boxes and lesion masks are never persisted.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.benchmark.openswisshcc_v23_shape_fusion import _validated_calibrator
from dtwin.core import PipelineError, sha256_of
from dtwin.medgemma_screening import _write_json_atomic


PROTOCOL_SCHEMA = "argos-lld-mmri-v23-external-protocol-v1"
LABEL_SCHEMA = "argos-lld-mmri-v23-protected-label-v1"
MAPPING_SCHEMA = "argos-lld-mmri-v23-protected-source-map-v1"
REPO_ID = "wanglab/LLD-MMRI-MedSAM2"
REPO_REVISION = "b7e8da56b267587689d8440e8298205f3fc4914e"
REQUIRED_PHASES = (
    "T2WI",
    "DWI",
    "C-pre",
    "C+A",
    "C+V",
    "C+Delay",
    "In Phase",
    "Out Phase",
)
CATEGORY_INFO = {
    "Hepatic_hemangioma": 0,
    "Intrahepatic_cholangiocarcinoma": 1,
    "Hepatic_abscess": 2,
    "Hepatic_metastasis": 3,
    "Hepatic_cyst": 4,
    "FOCAL_NODULAR_HYPERPLASIA": 5,
    "Hepatocellular_carcinoma": 6,
}
POSITIVE_CATEGORY = 6
NEGATIVE_CATEGORIES = (0, 4, 5)
EXCLUDED_CATEGORIES = (1, 2, 3)


def _case_id(source_subject_id: str) -> str:
    digest = hashlib.sha256(f"argos-lld-mmri-v23:{source_subject_id}".encode()).hexdigest()
    return f"anon-lld-{digest[:16]}"


def _atomic_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)


def _subject_category(series: Any) -> int:
    if not isinstance(series, list) or len(series) != len(REQUIRED_PHASES):
        raise PipelineError("Sujeito LLD-MMRI sem exatamente oito fases.")
    phases, categories = [], set()
    for item in series:
        if not isinstance(item, dict):
            raise PipelineError("Serie LLD-MMRI invalida.")
        phases.append(item.get("phase"))
        lesions = item.get("annotation", {}).get("lesion", {})
        if not isinstance(lesions, dict) or not lesions:
            raise PipelineError("Serie LLD-MMRI sem anotacao categorial.")
        for lesion in lesions.values():
            category = lesion.get("category") if isinstance(lesion, dict) else None
            if isinstance(category, bool) or not isinstance(category, int):
                raise PipelineError("Categoria LLD-MMRI invalida.")
            categories.add(category)
    if set(phases) != set(REQUIRED_PHASES) or len(categories) != 1:
        raise PipelineError("Fases ou categorias LLD-MMRI inconsistentes.")
    return next(iter(categories))


def freeze_lld_mmri_v23_external_protocol(
    *, annotation_path: Path, calibrator_path: Path, output_dir: Path
) -> dict[str, Any]:
    annotation_path = Path(annotation_path).resolve()
    calibrator_path = Path(calibrator_path).resolve()
    try:
        annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
        calibrator = json.loads(calibrator_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Entrada do protocolo externo LLD-MMRI invalida.") from exc
    _validated_calibrator(calibrator)
    if annotation.get("Category_info") is None or annotation.get("Annotation_info") is None:
        raise PipelineError("Annotation LLD-MMRI sem secoes obrigatorias.")
    category_info = annotation["Category_info"]
    if any(category_info.get(name) != value for name, value in CATEGORY_INFO.items()):
        raise PipelineError("Taxonomia publica LLD-MMRI divergiu.")
    subjects = annotation["Annotation_info"]
    if not isinstance(subjects, dict) or len(subjects) != 498:
        raise PipelineError("Quantidade publica de sujeitos LLD-MMRI divergiu.")

    labels: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    excluded_counts = {str(category): 0 for category in EXCLUDED_CATEGORIES}
    selected_counts = {"POSITIVE": 0, "NEGATIVE": 0}
    seen: set[str] = set()
    for source_id in sorted(subjects):
        category = _subject_category(subjects[source_id])
        case_id = _case_id(source_id)
        if case_id in seen:
            raise PipelineError("Colisao de case_id LLD-MMRI.")
        seen.add(case_id)
        if category == POSITIVE_CATEGORY:
            label, subtype = "POSITIVE", "hcc"
        elif category in NEGATIVE_CATEGORIES:
            label = "NEGATIVE"
            subtype = {0: "hemangioma", 4: "hepatic_cyst", 5: "fnh"}[category]
        else:
            if category not in EXCLUDED_CATEGORIES:
                raise PipelineError("Categoria publica LLD-MMRI desconhecida.")
            excluded_counts[str(category)] += 1
            continue
        selected_counts[label] += 1
        labels.append(
            {
                "schema": LABEL_SCHEMA,
                "case_id": case_id,
                "label": label,
                "target_condition": "hcc_suspicion",
                "public_category": category,
                "subtype": subtype,
                "label_basis": "public_expert_annotation",
                "research_only": True,
                "clinical_use_allowed": False,
            }
        )
        mappings.append(
            {
                "schema": MAPPING_SCHEMA,
                "case_id": case_id,
                "source_subject_id": source_id,
                "required_phases": list(REQUIRED_PHASES),
                "raw_uids_persisted": False,
                "lesion_boxes_persisted": False,
                "lesion_masks_allowed_in_inference": False,
                "research_only": True,
                "clinical_use_allowed": False,
            }
        )
    if selected_counts != {"POSITIVE": 157, "NEGATIVE": 178} or excluded_counts != {
        "1": 58,
        "2": 54,
        "3": 51,
    }:
        raise PipelineError("Distribuicao publica LLD-MMRI divergiu do protocolo v23.")

    output = Path(output_dir).resolve()
    if output.exists():
        raise PipelineError("Protocolo externo LLD-MMRI v23 ja existe.")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f"._lldv23_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        labels_path = staging / "protected_ground_truth" / "labels.jsonl"
        mapping_path = staging / "protected_source" / "mapping.jsonl"
        _atomic_jsonl(labels_path, labels)
        _atomic_jsonl(mapping_path, mappings)
        base = {
            "schema": PROTOCOL_SCHEMA,
            "status": "frozen_before_external_images_and_predictions",
            "dataset_id": "lld_mmri_medsam2",
            "dataset_repo_id": REPO_ID,
            "dataset_revision": REPO_REVISION,
            "license": "CC-BY-NC-4.0_and_dataset_noncommercial_terms",
            "target_condition": "hcc_suspicion",
            "positive_definition": "public_category_6_hcc",
            "negative_definition": "public_categories_0_hemangioma_4_cyst_5_fnh",
            "excluded_before_inference": {
                "1_intrahepatic_cholangiocarcinoma": 58,
                "2_hepatic_abscess": 54,
                "3_hepatic_metastasis": 51,
            },
            "case_count": len(labels),
            "positive_count": selected_counts["POSITIVE"],
            "negative_count": selected_counts["NEGATIVE"],
            "case_ids": [row["case_id"] for row in labels],
            "required_phases": list(REQUIRED_PHASES),
            "calibrator_signature": calibrator["calibrator_signature"],
            "decision_threshold": calibrator["decision_threshold"],
            "primary_gate": {
                "minimum_sensitivity": 0.75,
                "minimum_specificity": 0.75,
                "maximum_seconds_per_case": 180.0,
                "inconclusive_counts_as_error": True,
            },
            "annotation_sha256": sha256_of(annotation_path),
            "calibrator_sha256": sha256_of(calibrator_path),
            "protected_labels_sha256": sha256_of(labels_path),
            "protected_mapping_sha256": sha256_of(mapping_path),
            "labels_parsed_only_after_v23_calibrator_frozen": True,
            "predictions_present_at_freeze": False,
            "images_downloaded_by_this_freeze": False,
            "lesion_masks_allowed_in_inference": False,
            "raw_uids_persisted": False,
            "holdout_openswisshcc_reused": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
            "qualified": False,
        }
        protocol = dict(base)
        protocol["protocol_signature"] = _canonical_sha(base)
        _write_json_atomic(staging / "protocol.json", protocol)
        staging.replace(output)
        return protocol
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = ["PROTOCOL_SCHEMA", "freeze_lld_mmri_v23_external_protocol", "_case_id"]

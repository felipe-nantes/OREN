"""Evaluate the frozen visual bundle on synthetic external stress v1.

This is deliberately a *technical stress* evaluator.  The backgrounds come
from NIH, but lesion signatures come from LLD-MMRI, a source cohort used to
develop the classifier.  Construction labels are not clinical ground truth.
Consequently, this module refuses to emit clinical specificity, external
validation, or publication claims even though it computes diagnostic metrics
that are useful for debugging the pipeline.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image

from dtwin.benchmark.synthetic_external_stress_v1 import verify_cohort
from dtwin.core import PipelineError
from dtwin.learning.exam_to_panels import build_exam_panels
from dtwin.learning.medsiglip_embeddings import (
    HuggingFaceMedSigLIPBackend,
    load_embedding_config,
)
from dtwin.learning.protocol import canonical_sha256, sha256_file
from dtwin.learning.visual_inference import classify_embeddings, load_production_bundle


SCHEMA = "argos-synthetic-external-stress-v1-evaluation"
RECORD_SCHEMA = "argos-synthetic-external-stress-v1-evaluation-record"
LABEL_TO_MODEL_CLASS = {
    "no_focal_lesion": "negative_unspecified",
    "fnh": "fnh",
    "hcc": "hcc",
    "hemangioma": "hemangioma",
    "simple_cyst": "hepatic_cyst",
}
LESION_CLASSES = ("fnh", "hcc", "hemangioma", "hepatic_cyst")


def _json(path: Path, description: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido: {path}") from exc


def _jsonl(path: Path, description: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido: {path}") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise PipelineError(f"{description} contém registro inválido.")
    return rows


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _append_record(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _atomic_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _exclusive_run_lock(output_root: Path):
    """OS-backed non-blocking lock, released even when the process is killed.

    A persistent lock file is harmless; the lock itself belongs to the open
    file descriptor, so a crashed process cannot leave a stale logical lock.
    """
    output_root.mkdir(parents=True, exist_ok=True)
    stream = (output_root / ".evaluation.lock").open("a+b")
    if stream.tell() == 0:
        stream.write(b"0")
        stream.flush()
    stream.seek(0)
    acquired = False
    try:
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise PipelineError("Outra avaliação sintética já está em execução.") from exc
        else:
            import fcntl

            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise PipelineError("Outra avaliação sintética já está em execução.") from exc
        acquired = True
        yield
    finally:
        try:
            if acquired:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()


def _canonicalize_identical_checkpoint_duplicates(
    checkpoint_path: Path,
    rows: list[dict[str, Any]],
    *,
    protocol_signature: str,
    recovery_path: Path,
) -> list[dict[str, Any]]:
    """Collapse byte-equivalent duplicate records and audit the recovery.

    Conflicting predictions are never selected silently; they abort instead.
    """
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("case_id"))].append(row)
    duplicates = {case_id: values for case_id, values in grouped.items() if len(values) > 1}
    if not duplicates:
        return rows
    conflicts = {
        case_id: values
        for case_id, values in duplicates.items()
        if len({json.dumps(value, ensure_ascii=False, sort_keys=True) for value in values}) != 1
    }
    if conflicts:
        raise PipelineError(
            f"Checkpoint contém predições duplicadas conflitantes para {len(conflicts)} caso(s)."
        )
    source_sha256 = sha256_file(checkpoint_path)
    canonical = [values[0] for values in grouped.values()]
    _atomic_jsonl(checkpoint_path, canonical)
    recovery_body = {
        "schema": "argos-synthetic-external-stress-v1-checkpoint-recovery",
        "protocol_signature": protocol_signature,
        "source_checkpoint_sha256": source_sha256,
        "recovered_checkpoint_sha256": sha256_file(checkpoint_path),
        "source_row_count": len(rows),
        "canonical_row_count": len(canonical),
        "duplicate_case_count": len(duplicates),
        "conflicting_duplicate_count": 0,
        "recovery_rule": "collapse_only_exactly_identical_records",
    }
    _atomic_json(
        recovery_path,
        {**recovery_body, "recovery_signature": canonical_sha256(recovery_body)},
    )
    return canonical


def _wilson(successes: int, total: int) -> list[float]:
    if total <= 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def _binary_metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    tp = tn = fp = fn = failures = 0
    rows = list(rows)
    for row in rows:
        expected_positive = row["binary_expected"] == "POSITIVE"
        if row.get("technical_failure"):
            failures += 1
            if expected_positive:
                fn += 1
            else:
                fp += 1
            continue
        predicted_positive = row["binary_prediction"] == "POSITIVE"
        if expected_positive and predicted_positive:
            tp += 1
        elif not expected_positive and not predicted_positive:
            tn += 1
        elif expected_positive:
            fn += 1
        else:
            fp += 1
    sensitivity = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    return {
        "case_count": len(rows),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "technical_failures": failures,
        "sensitivity_on_construction_labels": sensitivity,
        "negative_rejection_on_construction_labels": specificity,
        "balanced_accuracy_on_construction_labels": (sensitivity + specificity) / 2,
        "sensitivity_ci95_wilson_technical_only": _wilson(tp, tp + fn),
        "negative_rejection_ci95_wilson_technical_only": _wilson(tn, tn + fp),
    }


def summarize_records(rows: list[dict[str, Any]], class_names: list[str]) -> dict[str, Any]:
    """Pure aggregation used by both the real runner and unit tests."""
    if not rows:
        raise PipelineError("Avaliação sintética sem registros.")
    expected_counts = Counter(str(row["expected_model_class"]) for row in rows)
    confusion: dict[str, dict[str, int]] = {
        expected: {predicted: 0 for predicted in [*class_names, "technical_failure"]}
        for expected in sorted(expected_counts)
    }
    correct = Counter()
    totals = Counter()
    for row in rows:
        expected = str(row["expected_model_class"])
        predicted = (
            "technical_failure" if row.get("technical_failure") else str(row["predicted_model_class"])
        )
        if predicted not in confusion[expected]:
            raise PipelineError(f"Classe predita inesperada: {predicted}")
        confusion[expected][predicted] += 1
        totals[expected] += 1
        if expected == predicted:
            correct[expected] += 1
    by_class = {
        name: {
            "count": totals[name],
            "correct": correct[name],
            "recall_on_construction_labels": correct[name] / totals[name],
            "ci95_wilson_technical_only": _wilson(correct[name], totals[name]),
        }
        for name in sorted(totals)
    }
    lesion_recalls = [
        by_class[name]["recall_on_construction_labels"]
        for name in LESION_CLASSES
        if name in by_class
    ]
    return {
        "binary_technical_metrics": _binary_metrics(rows),
        "subtype_confusion_on_construction_labels": confusion,
        "by_expected_class": by_class,
        "lesion_subtype_balanced_accuracy_on_construction_labels": (
            sum(lesion_recalls) / len(lesion_recalls) if lesion_recalls else 0.0
        ),
        "fnh_recall_on_construction_labels": by_class.get("fnh", {}).get(
            "recall_on_construction_labels"
        ),
    }


def verify_evaluation(output_root: Path) -> dict[str, Any]:
    """Independently recompute signatures, counts and aggregate metrics."""
    output_root = Path(output_root).resolve()
    protocol = _json(output_root / "protocol.json", "Protocolo da avaliação")
    unsigned_protocol = dict(protocol)
    protocol_signature = unsigned_protocol.pop("protocol_signature", None)
    if protocol_signature != canonical_sha256(unsigned_protocol):
        raise PipelineError("Assinatura do protocolo da avaliação diverge.")
    checkpoint_path = output_root / "checkpoint_predictions.jsonl"
    rows = _jsonl(checkpoint_path, "Predições da avaliação")
    case_ids = [str(row.get("case_id")) for row in rows]
    if len(case_ids) != len(set(case_ids)):
        raise PipelineError("Predições da avaliação contêm case_id duplicado.")
    if len(rows) != int(protocol.get("case_count", -1)):
        raise PipelineError("Contagem de predições diverge do protocolo.")
    for row in rows:
        unsigned = dict(row)
        signature = unsigned.pop("record_signature", None)
        if signature != canonical_sha256(unsigned):
            raise PipelineError(f"Assinatura de predição diverge: {row.get('case_id')}")
        if row.get("protocol_signature") != protocol_signature:
            raise PipelineError("Predição pertence a outro protocolo.")
        if row.get("clinical_ground_truth") is not False:
            raise PipelineError("Predição sintética tenta declarar ground truth clínico.")

    report = _json(output_root / "evaluation.json", "Relatório da avaliação")
    unsigned_report = dict(report)
    report_signature = unsigned_report.pop("report_signature", None)
    if report_signature != canonical_sha256(unsigned_report):
        raise PipelineError("Assinatura do relatório da avaliação diverge.")
    if report.get("prediction_checkpoint_sha256") != sha256_file(checkpoint_path):
        raise PipelineError("Hash do checkpoint diverge do relatório.")
    if int(report.get("case_count", -1)) != len(rows):
        raise PipelineError("Contagem do relatório diverge do checkpoint.")
    forbidden = (
        "clinical_ground_truth",
        "external_clinical_validation_allowed",
        "publication_validation_claim_allowed",
        "specificity_estimation_allowed",
        "clinical_use_allowed",
    )
    if any(report.get(key) is not False for key in forbidden):
        raise PipelineError("Guardas de interpretação do relatório foram alteradas.")
    class_names = list(
        next(iter(report["subtype_confusion_on_construction_labels"].values())).keys()
    )
    class_names = [name for name in class_names if name != "technical_failure"]
    recomputed = summarize_records(rows, class_names)
    for key, value in recomputed.items():
        if report.get(key) != value:
            raise PipelineError(f"Métrica agregada diverge ao recomputar: {key}")
    verification_body = {
        "schema": "argos-synthetic-external-stress-v1-evaluation-verification",
        "status": "verified_synthetic_technical_stress_evaluation_only",
        "case_count": len(rows),
        "unique_case_count": len(set(case_ids)),
        "technical_failure_count": sum(bool(row.get("technical_failure")) for row in rows),
        "protocol_signature": protocol_signature,
        "report_signature": report_signature,
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "all_record_signatures_verified": True,
        "aggregate_metrics_recomputed": True,
        "clinical_ground_truth": False,
        "specificity_estimation_allowed": False,
        "external_clinical_validation_allowed": False,
    }
    return {
        **verification_body,
        "verification_signature": canonical_sha256(verification_body),
    }


def _load_cases(cohort_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = _json(cohort_root / "cohort_manifest.json", "Manifesto da coorte sintética")
    if manifest.get("status") != "synthetic_technical_stress_only":
        raise PipelineError("Coorte não está marcada como estresse técnico sintético.")
    forbidden = (
        "clinical_use_allowed",
        "external_clinical_validation_allowed",
        "publication_validation_claim_allowed",
        "specificity_estimation_allowed",
    )
    if any(manifest.get(key) is not False for key in forbidden):
        raise PipelineError("Guardas de alegação da coorte sintética foram alteradas.")
    cases_path = cohort_root / "cases.jsonl"
    if sha256_file(cases_path) != manifest.get("cases_jsonl_sha256"):
        raise PipelineError("cases.jsonl da coorte sintética foi alterado.")
    rows = _jsonl(cases_path, "Casos sintéticos")
    if len(rows) != int(manifest.get("case_count", -1)):
        raise PipelineError("Contagem de casos diverge do manifesto sintético.")
    if any(row.get("synthetic") is not True or row.get("clinical_ground_truth") is not False for row in rows):
        raise PipelineError("Caso sintético tenta declarar ground truth clínico.")
    return manifest, rows


def _case_paths(cohort_root: Path, row: dict[str, Any]) -> tuple[dict[str, Path], Path]:
    phases = {
        f"t1_{phase}": cohort_root / row["phases"][phase]["relative_path"]
        for phase in ("arterial", "venous", "delayed")
    }
    mask = cohort_root / row["liver_masks"]["venous"]["relative_path"]
    return phases, mask


def _score_case(bundle: Any, embeddings: np.ndarray) -> dict[str, Any]:
    binary = classify_embeddings(bundle, embeddings)
    probabilities = np.asarray(bundle.model.predict_proba(np.asarray(embeddings, dtype=np.float64)))
    model_classes = [int(value) for value in bundle.model.classes_]
    expected_indices = list(range(len(bundle.manifest["class_names"])))
    if model_classes != expected_indices or probabilities.shape[1] != len(expected_indices):
        raise PipelineError("Ordem das classes do modelo diverge do manifesto.")
    mean_probabilities = probabilities.mean(axis=0)
    predicted_index = int(np.argmax(mean_probabilities))
    return {
        "binary_prediction": binary["prediction"],
        "binary_score": binary["score"],
        "binary_threshold": binary["threshold"],
        "panel_count": binary["panel_count"],
        "predicted_model_class": bundle.manifest["class_names"][predicted_index],
        "mean_class_probabilities": {
            name: float(mean_probabilities[index])
            for index, name in enumerate(bundle.manifest["class_names"])
        },
    }


def _evaluate_synthetic_stress_locked(
    *,
    cohort_root: Path,
    bundle_root: Path,
    panel_config_path: Path,
    embedding_config_path: Path,
    output_root: Path,
    limit: int | None = None,
) -> dict[str, Any]:
    cohort_root = Path(cohort_root).resolve()
    output_root = Path(output_root).resolve()
    cohort_manifest, cases = _load_cases(cohort_root)
    verification = verify_cohort(cohort_root)
    if verification.get("status") != "verified_synthetic_technical_stress_only":
        raise PipelineError("Verificação integral da coorte sintética falhou.")
    if limit is not None:
        if limit < 1:
            raise PipelineError("limit deve ser positivo.")
        cases = cases[:limit]

    bundle = load_production_bundle(bundle_root)
    embedding_config = load_embedding_config(embedding_config_path)
    protocol_body = {
        "schema": "argos-synthetic-external-stress-v1-evaluation-protocol",
        "cohort_signature": cohort_manifest["cohort_signature"],
        "verification_signature": verification["verification_signature"],
        "bundle_signature": bundle.manifest["bundle_signature"],
        "panel_config_sha256": sha256_file(panel_config_path),
        "embedding_config_sha256": sha256_file(embedding_config_path),
        "case_count": len(cases),
        "limit": limit,
        "clinical_ground_truth": False,
        "source_cohort_overlap_with_training": True,
        "generalization_estimate_allowed": False,
        "specificity_estimation_allowed": False,
        "clinical_use_allowed": False,
    }
    protocol = {**protocol_body, "protocol_signature": canonical_sha256(protocol_body)}
    protocol_path = output_root / "protocol.json"
    if protocol_path.exists() and _json(protocol_path, "Protocolo existente") != protocol:
        raise PipelineError("Diretório de saída pertence a outro protocolo.")
    _atomic_json(protocol_path, protocol)

    checkpoint_path = output_root / "checkpoint_predictions.jsonl"
    completed = _jsonl(checkpoint_path, "Checkpoint") if checkpoint_path.exists() else []
    if any(row.get("protocol_signature") != protocol["protocol_signature"] for row in completed):
        raise PipelineError("Checkpoint pertence a outro protocolo.")
    completed = _canonicalize_identical_checkpoint_duplicates(
        checkpoint_path,
        completed,
        protocol_signature=protocol["protocol_signature"],
        recovery_path=output_root / "checkpoint_recovery.json",
    )
    completed_by_id = {str(row["case_id"]): row for row in completed}
    if len(completed_by_id) != len(completed):
        raise PipelineError("Checkpoint contém case_id duplicado.")

    pending_cases = [case for case in cases if str(case["case_id"]) not in completed_by_id]
    if pending_cases:
        backend = HuggingFaceMedSigLIPBackend(embedding_config)
    else:
        backend = None
    try:
        for index, case in enumerate(cases, start=1):
            case_id = str(case["case_id"])
            if case_id in completed_by_id:
                continue
            expected_class = LABEL_TO_MODEL_CLASS.get(str(case["label"]))
            if expected_class is None:
                raise PipelineError(f"Rótulo de construção desconhecido: {case['label']}")
            row: dict[str, Any] = {
                "schema": RECORD_SCHEMA,
                "case_id": case_id,
                "construction_label": case["label"],
                "expected_model_class": expected_class,
                "binary_expected": "POSITIVE" if expected_class == "hcc" else "NEGATIVE",
                "background_dependency_group": case["background_dependency_group"],
                "donor_dependency_group": case.get("donor_dependency_group"),
                "clinical_ground_truth": False,
                "source_cohort_overlap_with_training": case.get("donor_case_id") is not None,
                "technical_failure": True,
                "protocol_signature": protocol["protocol_signature"],
            }
            try:
                phases, mask = _case_paths(cohort_root, case)
                panels = build_exam_panels(
                    case_id=case_id,
                    phase_paths=phases,
                    coarse_liver_mask_path=mask,
                    output_dir=output_root / "panels" / case_id,
                    panel_config_path=panel_config_path,
                )
                images: list[Image.Image] = []
                try:
                    for path in panels.panel_paths:
                        with Image.open(path) as source:
                            if source.info:
                                raise PipelineError(f"PNG contém metadados: {path}")
                            images.append(source.convert("RGB"))
                    assert backend is not None
                    embeddings = backend.embed(images)
                finally:
                    for image in images:
                        image.close()
                row.update(_score_case(bundle, embeddings))
                row["panel_sha256"] = [sha256_file(path) for path in panels.panel_paths]
                row["technical_failure"] = False
            except Exception as exc:  # noqa: BLE001 - failure is persisted, never fabricated
                row["error"] = f"{type(exc).__name__}: {exc}"
            unsigned = dict(row)
            row["record_signature"] = canonical_sha256(unsigned)
            _append_record(checkpoint_path, row)
            completed_by_id[case_id] = row
            print(f"[{index}/{len(cases)}] {case_id} {row.get('predicted_model_class', 'TECHNICAL_FAILURE')}", flush=True)
    finally:
        if backend is not None:
            backend.close()

    ordered = [completed_by_id[str(case["case_id"])] for case in cases]
    summary = summarize_records(ordered, list(bundle.manifest["class_names"]))
    report_body = {
        "schema": SCHEMA,
        "protocol_signature": protocol["protocol_signature"],
        "cohort_signature": cohort_manifest["cohort_signature"],
        "bundle_signature": bundle.manifest["bundle_signature"],
        "case_count": len(ordered),
        "prediction_checkpoint_sha256": sha256_file(checkpoint_path),
        "source_cohort_overlap_with_training": True,
        "clinical_ground_truth": False,
        "external_clinical_validation_allowed": False,
        "publication_validation_claim_allowed": False,
        "specificity_estimation_allowed": False,
        "clinical_use_allowed": False,
        "interpretation": (
            "Technical stress only: NIH backgrounds are new, but lesions are constructed from "
            "LLD-MMRI signatures and labels are not radiologist-confirmed diagnoses."
        ),
        **summary,
    }
    report = {**report_body, "report_signature": canonical_sha256(report_body)}
    _atomic_json(output_root / "evaluation.json", report)
    _atomic_json(output_root / "evaluation_verification.json", verify_evaluation(output_root))
    return report


def evaluate_synthetic_stress(
    *,
    cohort_root: Path,
    bundle_root: Path,
    panel_config_path: Path,
    embedding_config_path: Path,
    output_root: Path,
    limit: int | None = None,
) -> dict[str, Any]:
    output_root = Path(output_root).resolve()
    with _exclusive_run_lock(output_root):
        return _evaluate_synthetic_stress_locked(
            cohort_root=cohort_root,
            bundle_root=bundle_root,
            panel_config_path=panel_config_path,
            embedding_config_path=embedding_config_path,
            output_root=output_root,
            limit=limit,
        )

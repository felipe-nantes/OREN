import hashlib
import json
from pathlib import Path

import pytest

from dtwin.benchmark.openswisshcc_evaluation import evaluate_reviewed_development_run
from dtwin.benchmark.openswisshcc_freeze import create_experiment_freeze
from dtwin.benchmark.openswisshcc_review import create_panel_review
from dtwin.core import PipelineError

MULTI = Path("configs/medgemma_local_4b_multiphase_fast_pathology.yaml")
FALLBACK = Path("configs/medgemma_local_4b_venous_fallback_pathology.yaml")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate(root: Path, case_id: str, *, fallback: bool = False) -> None:
    case = root / case_id
    case.mkdir(parents=True)
    panel = case / "panel.png"
    panel.write_bytes(case_id.encode())
    config = FALLBACK if fallback else MULTI
    candidate = {
        "case_id": case_id,
        "candidate_signature": f"signature-{case_id}",
        "candidate_version": "fallback-v1" if fallback else "multiphase-v1",
        "panel_filename": panel.name,
        "panel_sha256": _sha(panel),
        "panel_bytes": panel.stat().st_size,
        "config_sha256": _sha(config),
        "research_only": True,
        "clinical_use_allowed": False,
    }
    if fallback:
        candidate["candidate_kind"] = "venous_single_phase_fallback"
    (case / "candidate_manifest.json").write_text(json.dumps(candidate), encoding="utf-8")


def _foundation(tmp_path: Path):
    panels = tmp_path / "panels"
    ids = ["anon-positive", "anon-negative"]
    _candidate(panels, ids[0])
    _candidate(panels, ids[1], fallback=True)
    freeze_path = tmp_path / "freeze.json"
    freeze = create_experiment_freeze(
        panel_root=panels,
        multiphase_config=MULTI,
        fallback_config=FALLBACK,
        output_path=freeze_path,
        expected_case_count=2,
    )
    review_path = tmp_path / "review.json"
    review = create_panel_review(
        panel_root=panels,
        case_ids=ids,
        output_path=review_path,
        reviewer="human-reviewer",
        confirmations={
            "no_visible_phi": True,
            "multiphase_alignment_acceptable": True,
            "liver_framing_acceptable": True,
        },
    )
    return panels, freeze_path, freeze, review_path, review, ids


def _report(root: Path, case_id: str, prediction: str, seconds: float) -> dict:
    case = root / case_id
    case.mkdir(parents=True)
    envelope = {
        "case_id": case_id,
        "status": "pending_review",
        "report": {
            "resultado_hipotese": prediction,
            "confianca": "moderada",
        },
    }
    report = case / "medgemma_report.json"
    report.write_text(json.dumps(envelope), encoding="utf-8")
    manifest = {
        "case_id": case_id,
        "ground_truth_read": False,
        "report_sha256": _sha(report),
    }
    (case / "inference_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return {
        "case_id": case_id,
        "status": "success_pending_human_review",
        "prediction": prediction,
        "elapsed_seconds": seconds,
        "report_sha256": _sha(report),
    }


def _inference(
    tmp_path: Path, freeze: dict, review: dict, ids: list[str],
    *, first_prediction: str = "POSITIVA", second_status: str = "success"
) -> Path:
    root = tmp_path / "inference"
    records = [_report(root, ids[0], first_prediction, 20.0)]
    if second_status == "success":
        records.append(_report(root, ids[1], "NEGATIVA", 25.0))
    elif second_status == "timeout":
        records.append(
            {
                "case_id": ids[1],
                "status": "timeout",
                "elapsed_seconds": 180.0,
                "within_time_limit": False,
                "error": "timeout",
            }
        )
    summary = {
        "schema": "argos-openswisshcc-inference-batch-v1",
        "case_count": len(records),
        "records": records,
        "review_signature": review["review_signature"],
        "experiment_signature": freeze["experiment_signature"],
        "ground_truth_read": False,
        "metrics_calculated": False,
    }
    (root / "inference_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return root


def _labels(path: Path, ids: list[str]) -> Path:
    rows = [
        {
            "schema": "argos-openswisshcc-ground-truth-v1",
            "case_id": ids[0],
            "public_subject_id": "sub-a",
            "label": "POSITIVE",
            "target_condition": "hcc_presence",
            "label_basis": "openswisshcc_participants_tsv",
            "review_status": "dataset_expert_validated",
        },
        {
            "schema": "argos-openswisshcc-ground-truth-v1",
            "case_id": ids[1],
            "public_subject_id": "sub-b",
            "label": "NEGATIVE",
            "target_condition": "hcc_presence",
            "label_basis": "openswisshcc_participants_tsv",
            "review_status": "dataset_expert_validated",
        },
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _evaluate(tmp_path: Path, *, first_prediction="POSITIVA", second_status="success"):
    panels, freeze_path, freeze, review_path, review, ids = _foundation(tmp_path)
    inference = _inference(
        tmp_path, freeze, review, ids,
        first_prediction=first_prediction,
        second_status=second_status,
    )
    labels = _labels(tmp_path / "labels.jsonl", ids)
    result = evaluate_reviewed_development_run(
        panel_root=panels,
        review_path=review_path,
        freeze_path=freeze_path,
        inference_root=inference,
        protected_labels_path=labels,
        output_dir=tmp_path / "evaluation",
        multiphase_config=MULTI,
        fallback_config=FALLBACK,
        expected_case_count=2,
        expected_positive=1,
        expected_negative=1,
    )
    return result, tmp_path / "evaluation"


def test_evaluation_opens_truth_only_after_complete_inference_and_passes(tmp_path):
    result, output = _evaluate(tmp_path)
    assert result["metrics"]["primary"]["sensitivity"] == 1.0
    assert result["metrics"]["primary"]["specificity"] == 1.0
    assert result["timing"]["passed"] is True
    assert result["passed"] is True
    assert result["ground_truth_opened_after_inference"] is True
    assert (output / "qualification_gate.json").is_file()
    assert (output / "summary.md").is_file()


def test_inconclusive_and_timeout_are_penalized_in_primary_metrics(tmp_path):
    result, _ = _evaluate(
        tmp_path,
        first_prediction="INCONCLUSIVA",
        second_status="timeout",
    )
    assert result["metrics"]["primary"]["sensitivity"] == 0.0
    assert result["metrics"]["primary"]["specificity"] == 0.0
    assert result["metrics"]["primary"]["inconclusive_count"] == 1
    assert result["metrics"]["primary"]["timeout_count"] == 1
    assert result["timing"]["passed"] is False
    assert result["passed"] is False


def test_incomplete_inference_aborts_before_missing_ground_truth_is_opened(tmp_path):
    panels, freeze_path, freeze, review_path, review, ids = _foundation(tmp_path)
    inference = _inference(tmp_path, freeze, review, ids)
    summary_path = inference / "inference_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["records"] = summary["records"][:1]
    summary["case_count"] = 1
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(PipelineError, match="coorte congelada"):
        evaluate_reviewed_development_run(
            panel_root=panels,
            review_path=review_path,
            freeze_path=freeze_path,
            inference_root=inference,
            protected_labels_path=tmp_path / "does-not-exist.jsonl",
            output_dir=tmp_path / "evaluation",
            multiphase_config=MULTI,
            fallback_config=FALLBACK,
            expected_case_count=2,
            expected_positive=1,
            expected_negative=1,
        )


def test_evaluation_rejects_unexpected_protected_counts(tmp_path):
    panels, freeze_path, freeze, review_path, review, ids = _foundation(tmp_path)
    inference = _inference(tmp_path, freeze, review, ids)
    labels = _labels(tmp_path / "labels.jsonl", ids)
    with pytest.raises(PipelineError, match="Contagem protegida inesperada"):
        evaluate_reviewed_development_run(
            panel_root=panels,
            review_path=review_path,
            freeze_path=freeze_path,
            inference_root=inference,
            protected_labels_path=labels,
            output_dir=tmp_path / "evaluation",
            multiphase_config=MULTI,
            fallback_config=FALLBACK,
            expected_case_count=2,
            expected_positive=2,
            expected_negative=0,
        )

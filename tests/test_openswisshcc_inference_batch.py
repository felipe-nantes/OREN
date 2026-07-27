import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from dtwin.benchmark.openswisshcc_freeze import create_experiment_freeze
from dtwin.benchmark.openswisshcc_inference_batch import run_reviewed_inference_batch
from dtwin.benchmark.openswisshcc_review import create_panel_review
from dtwin.core import PipelineError


MULTI = Path("configs/medgemma_local_4b_multiphase_fast_pathology.yaml")
FALLBACK = Path("configs/medgemma_local_4b_venous_fallback_pathology.yaml")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate(root: Path, case_id: str, *, fallback: bool) -> None:
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
        "panel_manifest_filename": "panel_manifest.json",
        "panel_sha256": _sha(panel),
        "panel_bytes": panel.stat().st_size,
        "config_sha256": _sha(config),
        "research_only": True,
        "clinical_use_allowed": False,
    }
    if fallback:
        candidate["candidate_kind"] = "venous_single_phase_fallback"
    (case / "candidate_manifest.json").write_text(json.dumps(candidate), encoding="utf-8")


def _setup(tmp_path: Path) -> tuple[Path, Path, Path, list[str]]:
    panels = tmp_path / "panels"
    ids = ["anon-multi", "anon-fallback"]
    _candidate(panels, ids[0], fallback=False)
    _candidate(panels, ids[1], fallback=True)
    freeze = tmp_path / "freeze.json"
    create_experiment_freeze(
        panel_root=panels,
        multiphase_config=MULTI,
        fallback_config=FALLBACK,
        output_path=freeze,
        expected_case_count=2,
    )
    review = tmp_path / "review.json"
    create_panel_review(
        panel_root=panels,
        case_ids=ids,
        output_path=review,
        reviewer="human-reviewer",
        confirmations={
            "no_visible_phi": True,
            "multiphase_alignment_acceptable": True,
            "liver_framing_acceptable": True,
        },
    )
    return panels, review, freeze, ids


class FakeHealthClient:
    def check_ready(self):
        return {
            "status": "ready",
            "model_id": "google/medgemma-1.5-4b-it",
            "model_version": "MedGemma 1.5 4B Instruction-Tuned",
            "contract": "dtwin-medgemma-v1",
        }


def _successful_runner(configs_seen: list[str]):
    def run(command, *, timeout, cwd):
        case_id = command[command.index("--case-id") + 1]
        output = Path(command[command.index("--out") + 1]) / case_id
        configs_seen.append(command[command.index("--config") + 1])
        assert "--freeze" in command
        output.mkdir(parents=True)
        report = output / "medgemma_report.json"
        report.write_text(json.dumps({"case_id": case_id}), encoding="utf-8")
        manifest = {
            "case_id": case_id,
            "prediction": "NEGATIVA",
            "ground_truth_read": False,
            "report_sha256": _sha(report),
            "effective_config_sha256": "effective",
            "elapsed_seconds": 10.0,
        }
        (output / "inference_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout=json.dumps(manifest), stderr="")
    return run


def _run(tmp_path: Path, *, runner):
    panels, review, freeze, ids = _setup(tmp_path)
    return run_reviewed_inference_batch(
        panel_root=panels,
        review_path=review,
        freeze_path=freeze,
        output_root=tmp_path / "run",
        multiphase_config=MULTI,
        fallback_config=FALLBACK,
        case_ids=ids,
        expected_case_count=2,
        runner=runner,
        client_factory=lambda config: FakeHealthClient(),
    )


def test_batch_routes_candidates_and_requires_freeze(tmp_path):
    configs_seen: list[str] = []
    summary = _run(tmp_path, runner=_successful_runner(configs_seen))
    assert summary["status_counts"] == {"success_pending_human_review": 2}
    assert summary["experiment_signature"]
    assert summary["ground_truth_read"] is False
    assert summary["metrics_calculated"] is False
    assert {Path(value).name for value in configs_seen} == {MULTI.name, FALLBACK.name}


def test_batch_records_external_timeout_and_continues(tmp_path):
    calls = 0
    success = _successful_runner([])

    def runner(command, *, timeout, cwd):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise subprocess.TimeoutExpired(command, timeout)
        return success(command, timeout=timeout, cwd=cwd)

    summary = _run(tmp_path, runner=runner)
    assert summary["status_counts"] == {"timeout": 1, "success_pending_human_review": 1}
    assert calls == 2


def test_batch_refuses_existing_run_directory(tmp_path):
    panels, review, freeze, _ = _setup(tmp_path)
    output = tmp_path / "run"
    output.mkdir()
    with pytest.raises(PipelineError, match="já existe"):
        run_reviewed_inference_batch(
            panel_root=panels,
            review_path=review,
            freeze_path=freeze,
            output_root=output,
            multiphase_config=MULTI,
            fallback_config=FALLBACK,
            expected_case_count=2,
            client_factory=lambda config: FakeHealthClient(),
        )


def test_batch_rejects_freeze_for_different_panel_bytes(tmp_path):
    panels, review, freeze, _ = _setup(tmp_path)
    (panels / "anon-multi" / "panel.png").write_bytes(b"changed")
    with pytest.raises(PipelineError, match="Hash do painel"):
        run_reviewed_inference_batch(
            panel_root=panels,
            review_path=review,
            freeze_path=freeze,
            output_root=tmp_path / "run",
            multiphase_config=MULTI,
            fallback_config=FALLBACK,
            expected_case_count=2,
            client_factory=lambda config: FakeHealthClient(),
        )

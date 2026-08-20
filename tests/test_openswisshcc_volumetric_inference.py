from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_volumetric_gate import (
    _canonical_sha256,
    create_volumetric_freeze,
    create_volumetric_review,
)
from dtwin.benchmark.openswisshcc_volumetric_inference import (
    infer_frozen_volumetric_case,
    run_frozen_volumetric_inference,
)
from dtwin.core import PipelineError

CONFIGS = {
    "multiphase": Path("configs/medgemma_local_4b_multiphase_volumetric_choice_pathology.yaml"),
    "venous": Path("configs/medgemma_local_4b_venous_volumetric_choice_pathology.yaml"),
    "venous_high_contrast": Path(
        "configs/medgemma_local_4b_venous_volumetric_high_contrast_choice_pathology.yaml"
    ),
}


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def _frozen(tmp_path: Path):
    root = tmp_path / "panels"
    case_id = "anon-openswiss-inference-unit"
    case = root / case_id
    case.mkdir(parents=True)
    image_paths = []
    for number in (1, 2):
        path = case / f"panel_{number:03d}.png"
        path.write_bytes(f"safe-panel-{number}".encode())
        image_paths.append(path)
    panels = [
        {
            "panel_number": number,
            "panel_total": 2,
            "image": path.name,
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
            "axial_interval": [number * 2, number * 2 + 1],
        }
        for number, path in enumerate(image_paths, start=1)
    ]
    coverage = {
        "expected_axial_indices": [2, 3, 4, 5],
        "first_liver_slice": 2,
        "last_liver_slice": 5,
        "missing_axial_indices": [],
        "duplicate_axial_indices": [],
        "total_liver_voxels": 100,
        "covered_liver_voxels": 100,
        "coverage_percent": 100.0,
        "gate_passed": True,
        "gate_rule": "covered_liver_voxels == total_liver_voxels",
    }
    panel_manifest = {
        "case_id": case_id,
        "panel_strategy": "volumetric_blocks",
        "panel_sha256": panels[0]["sha256"],
        "input_volume_sha256": "b" * 64,
        "input_liver_mask_sha256": "c" * 64,
        "lesion_pre_marked": False,
        "coverage": coverage,
        "panels": [{key: item[key] for key in (
            "panel_number", "panel_total", "image", "sha256", "axial_interval"
        )} for item in panels],
    }
    panel_manifest_path = case / "medgemma_liver_screening_manifest.json"
    _write(panel_manifest_path, panel_manifest)
    signature = "a" * 64
    candidate = {
        "schema": "argos-public-liver-mri-volumetric-candidate-v1",
        "case_id": case_id,
        "candidate_kind": "multiphase_rgb",
        "candidate_version": "unit-vol-v1",
        "candidate_signature": signature,
        "panel_strategy": "volumetric_blocks",
        "panel_filename": panels[0]["image"],
        "panel_sha256": panels[0]["sha256"],
        "panel_bytes": panels[0]["bytes"],
        "panel_manifest_filename": panel_manifest_path.name,
        "panel_image_count": 2,
        "panels": panels,
        "panel_set_sha256": _canonical_sha256(panels),
        "coverage": coverage,
        "config_sha256": _sha256(CONFIGS["multiphase"]),
        "visible_phi_confirmed": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "ground_truth_read": False,
    }
    _write(case / "candidate_manifest.json", candidate)
    summary = {
        "case_id": case_id,
        "candidate_kind": "multiphase_rgb",
        "candidate_signature": signature,
        "panel_image_count": 2,
        "panel_set_sha256": candidate["panel_set_sha256"],
        "total_liver_voxels": 100,
        "covered_liver_voxels": 100,
    }
    _write(root / "cohort_manifest.json", {
        "schema": "argos-openswisshcc-volumetric-candidate-cohort-v1",
        "case_count": 1,
        "panel_image_count": 2,
        "cases": [summary],
        "cohort_signature": _canonical_sha256([summary]),
        "research_only": True,
        "clinical_use_allowed": False,
        "ground_truth_read": False,
        "inference_executed": False,
    })
    review_path = tmp_path / "review.json"
    create_volumetric_review(
        panel_root=root,
        output_path=review_path,
        reviewer="human-unit-test",
        expected_case_count=1,
        confirmations={
            "no_visible_phi": True,
            "all_panels_open_and_uncorrupted": True,
            "liver_framing_acceptable": True,
            "multiphase_alignment_acceptable": True,
            "volumetric_sequence_acceptable": True,
        },
    )
    freeze_path = tmp_path / "freeze.json"
    freeze = create_volumetric_freeze(
        panel_root=root,
        review_path=review_path,
        config_paths=CONFIGS,
        output_path=freeze_path,
        experiment_version="unit-volumetric-inference-v1",
        expected_case_count=1,
    )
    return root, case_id, review_path, freeze_path, freeze


def _report(state: str) -> dict:
    return {
        "resultado_hipotese": state,
        "resumo_do_achado": f"Classificacao {state}",
        "localizacao_aproximada": "Nao determinada.",
        "sinais_visuais_observados": ["Escolha restrita."],
        "confianca": "moderada",
        "limitacoes_da_analise": ["Pesquisa; revisao humana obrigatoria."],
        "necessidade_de_revisao_humana": True,
        "alvo_da_triagem": "lesao_focal_hepatica_suspeita",
        "ha_lesao_focal_suspeita": state == "POSITIVA",
        "ha_variante_anatomica_benigna": False,
        "ha_pseudolesao_ou_artefato": False,
        "tipo_alteracao_nao_alvo": "none",
        "justificativa_da_separacao": "Escolha restrita sem narrativa clinica.",
    }


class FakeClient:
    def __init__(self, states: list[str], fail_at: int | None = None):
        self.states = states
        self.fail_at = fail_at
        self.calls: list[tuple[str, str]] = []
        self.last_response_audit: dict = {}
        self.last_timings: dict = {}

    def generate(self, panel_path: Path, prompt: str) -> dict:
        call = len(self.calls) + 1
        self.calls.append((Path(panel_path).name, prompt))
        if self.fail_at == call:
            raise PipelineError("synthetic intermediate failure")
        state = self.states[call - 1]
        self.last_response_audit = {
            "response_mode": "choice_classification",
            "choice_probabilities": {"POSITIVA": 0.7, "NEGATIVA": 0.2, "INCONCLUSIVA": 0.1},
        }
        self.last_timings = {"client_total": 0.01}
        return _report(state)


def test_case_calls_every_panel_and_aggregates_any_positive(tmp_path: Path):
    root, case_id, review, freeze_path, freeze = _frozen(tmp_path)
    client = FakeClient(["NEGATIVA", "POSITIVA"])
    out = tmp_path / "run"
    result = infer_frozen_volumetric_case(
        case_id=case_id, panel_root=root, review_path=review, freeze_path=freeze_path,
        config_paths=CONFIGS, output_root=out, expected_case_count=1,
        client=client, verified_freeze=freeze,
    )
    assert result["prediction"] == "POSITIVA"
    assert len(client.calls) == 2
    assert "painel 1/2" in client.calls[0][1]
    report = json.loads((out / case_id / "medgemma_report.json").read_text(encoding="utf-8"))
    assert len(report["panel_reports"]) == 2
    assert report["qualification"]["ground_truth_read"] is False


def test_intermediate_failure_publishes_no_final_report(tmp_path: Path):
    root, case_id, review, freeze_path, freeze = _frozen(tmp_path)
    out = tmp_path / "run"
    with pytest.raises(PipelineError, match="synthetic intermediate"):
        infer_frozen_volumetric_case(
            case_id=case_id, panel_root=root, review_path=review, freeze_path=freeze_path,
            config_paths=CONFIGS, output_root=out, expected_case_count=1,
            client=FakeClient(["NEGATIVA", "POSITIVA"], fail_at=2), verified_freeze=freeze,
        )
    case = out / case_id
    assert not (case / "medgemma_report.json").exists()
    failure = json.loads((case / "inference_failure.json").read_text(encoding="utf-8"))
    assert failure["completed_panel_count"] == 1
    assert failure["failed_panel"]["panel_number"] == 2


def test_batch_summary_is_blinded_and_reusable(tmp_path: Path):
    root, case_id, review, freeze_path, _ = _frozen(tmp_path)
    created: list[FakeClient] = []

    def factory(_config):
        client = FakeClient(["NEGATIVA", "NEGATIVA"])
        created.append(client)
        return client

    out = tmp_path / "run"
    summary = run_frozen_volumetric_inference(
        panel_root=root, review_path=review, freeze_path=freeze_path,
        config_paths=CONFIGS, output_root=out, expected_case_count=1,
        client_factory=factory,
    )
    assert summary["status"] == "complete"
    assert summary["ground_truth_read"] is False
    assert summary["metrics_calculated"] is False
    assert len(created[0].calls) == 2
    again = run_frozen_volumetric_inference(
        panel_root=root, review_path=review, freeze_path=freeze_path,
        config_paths=CONFIGS, output_root=out, expected_case_count=1,
        client_factory=lambda _config: pytest.fail("completed run must be reused"),
    )
    assert again == summary
    manifest = json.loads((out / case_id / "inference_manifest.json").read_text(encoding="utf-8"))
    assert manifest["prediction"] == "NEGATIVA"

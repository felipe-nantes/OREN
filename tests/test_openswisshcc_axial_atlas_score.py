from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from dtwin.benchmark import openswisshcc_axial_atlas_score as score
from dtwin.benchmark.openswisshcc_axial_atlas import (
    CASE_SCHEMA,
    COHORT_SCHEMA,
    PROTOCOL_SIGNATURE,
    REQUIRED_REVIEW_CONFIRMATIONS,
    build_axial_atlas_gallery,
    record_axial_atlas_review,
)
from dtwin.core import PipelineError, sha256_of


def _write_bundle(
    tmp_path: Path,
    *,
    size: int = 640,
    kind: str = "multiphase_rgb",
) -> tuple[Path, str]:
    root = tmp_path / "atlas"
    case_id = "anon-openswiss-test0001"
    case_dir = root / case_id
    case_dir.mkdir(parents=True)
    frames = []
    for number in range(1, 6):
        filename = f"axial_atlas_frame_{number:03d}_of_005.png"
        path = case_dir / filename
        Image.new("RGB", (size, size), (number, number, number)).save(path)
        frames.append(
            {
                "frame_number": number,
                "frame_total": 5,
                "image": filename,
                "sha256": sha256_of(path),
                "bytes": path.stat().st_size,
                "size_pixels": [size, size],
                "axial_interval": [10 + 4 * (number - 1), 13 + 4 * (number - 1)],
                "tiles": [],
            }
        )
    indices = list(range(10, 30))
    manifest = {
        "schema_version": CASE_SCHEMA,
        "protocol_signature": PROTOCOL_SIGNATURE,
        "case_id": case_id,
        "ground_truth_read": False,
        "lesion_mask_read": False,
        "holdout_read": False,
        "source": {"candidate_kind": kind},
        "atlas": {
            "frame_count": 5,
            "tile_count": 20,
            "gate_passed": True,
            "represented_axial_indices": indices,
            "expected_axial_indices": indices,
            "atlas_set_sha256": "a" * 64,
        },
        "frames": frames,
    }
    manifest_path = case_dir / "axial_atlas_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    cohort = {
        "schema_version": COHORT_SCHEMA,
        "protocol_signature": PROTOCOL_SIGNATURE,
        "case_count": 1,
        "frame_count": 5,
        "tile_count": 20,
        "ground_truth_read": False,
        "lesion_mask_read": False,
        "holdout_read": False,
        "eligible_for_inference": False,
        "all_gates_passed": True,
        "cases": [
            {
                "case_id": case_id,
                "manifest": f"{case_id}/axial_atlas_manifest.json",
                "manifest_sha256": sha256_of(manifest_path),
                "frame_count": 5,
                "tile_count": 20,
                "atlas_set_sha256": "a" * 64,
                "source_candidate_kind": kind,
                "gate_passed": True,
            }
        ],
    }
    (root / "cohort_manifest.json").write_text(json.dumps(cohort), encoding="utf-8")
    return root, case_id


def _protocol() -> dict:
    return {
        "model_id": "google/medgemma-1.5-4b-it",
        "model_version": "MedGemma 1.5 4B Instruction-Tuned",
        "instruction": score.INSTRUCTION,
        "endpoint_url": "http://127.0.0.1:8001/score-volume",
        "protocol_signature": "b" * 64,
        "scoring": {"response_prefix": score.RESPONSE_PREFIX},
    }


def _response(*, choice: str = "POSITIVA") -> dict:
    probabilities = {
        "POSITIVA": 0.8,
        "NEGATIVA": 0.1,
        "INCONCLUSIVA": 0.1,
    }
    return {
        "contract": score.CONTRACT,
        "model_id": "google/medgemma-1.5-4b-it",
        "model_version": "MedGemma 1.5 4B Instruction-Tuned",
        "slice_count": 5,
        "choice": choice,
        "choice_probabilities": probabilities,
        "scoring_method": score.SCORING_METHOD,
        "choice_token_metadata": {
            label: {"first_token_id": index + 10, "token_count": 1}
            for index, label in enumerate(score.CHOICES)
        },
        "tie_detected": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
        "timings_seconds": {"generation_seconds": 2.5},
    }


def test_bundle_accepts_native_640_and_768(tmp_path: Path) -> None:
    first, _ = _write_bundle(tmp_path / "a", size=640)
    second, _ = _write_bundle(tmp_path / "b", size=768)
    assert score.validate_atlas_bundle(first)["maximum_frames"] == 5
    assert score.validate_atlas_bundle(second)["maximum_frames"] == 5


def test_bundle_rejects_tampered_frame(tmp_path: Path) -> None:
    root, case_id = _write_bundle(tmp_path)
    frame = next((root / case_id).glob("*.png"))
    frame.write_bytes(frame.read_bytes() + b"tamper")
    with pytest.raises(PipelineError, match="adulterado"):
        score.validate_atlas_bundle(root)


def test_query_explains_rgb_and_venous_fallback(tmp_path: Path) -> None:
    rgb_root, _ = _write_bundle(tmp_path / "rgb", kind="multiphase_rgb")
    gray_root, _ = _write_bundle(
        tmp_path / "gray", kind="venous_single_phase_fallback"
    )
    rgb = score.validate_atlas_bundle(rgb_root)["cases"][0]["manifest"]
    gray = score.validate_atlas_bundle(gray_root)["cases"][0]["manifest"]
    assert "fusao RGB" in score.atlas_query(rgb)
    assert "escala de cinza" in score.atlas_query(gray)
    assert "10 ao 29" in score.atlas_query(rgb)


def test_full_review_scope_is_required_and_hash_bound(tmp_path: Path) -> None:
    root, _ = _write_bundle(tmp_path)
    gallery = tmp_path / "gallery"
    build_axial_atlas_gallery(root, gallery)
    review_path = tmp_path / "review.json"
    record_axial_atlas_review(
        gallery_root=gallery,
        out_path=review_path,
        reviewer="jm",
        confirmations={key: True for key in REQUIRED_REVIEW_CONFIRMATIONS},
        approved=True,
        approval_scope="blind_4b_scoring",
        reviewed_at_utc="2026-07-17T12:00:00+00:00",
    )
    bundle = score.validate_atlas_bundle(root)
    review = score.validate_scoring_review(
        gallery_root=gallery, review_path=review_path, bundle=bundle
    )
    assert review["status"] == "approved_for_blind_4b_scoring"

    review["case_count"] = 2
    review_path.write_text(json.dumps(review), encoding="utf-8")
    with pytest.raises(PipelineError, match="ausente, divergente"):
        score.validate_scoring_review(
            gallery_root=gallery, review_path=review_path, bundle=bundle
        )


def test_pilot_review_scope_cannot_authorize_scoring(tmp_path: Path) -> None:
    root, _ = _write_bundle(tmp_path)
    gallery = tmp_path / "gallery"
    build_axial_atlas_gallery(root, gallery)
    review_path = tmp_path / "review.json"
    record_axial_atlas_review(
        gallery_root=gallery,
        out_path=review_path,
        reviewer="jm",
        confirmations={key: True for key in REQUIRED_REVIEW_CONFIRMATIONS},
        approved=True,
        approval_scope="full87_generation",
    )
    with pytest.raises(PipelineError, match="ausente, divergente"):
        score.validate_scoring_review(
            gallery_root=gallery,
            review_path=review_path,
            bundle=score.validate_atlas_bundle(root),
        )


def test_score_case_uses_one_request_and_persists_continuous_score(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root, _ = _write_bundle(tmp_path)
    case = score.validate_atlas_bundle(root)["cases"][0]
    calls = []

    def fake_request(request, timeout):
        calls.append((request, timeout))
        return _response()

    monkeypatch.setattr(score, "_request_json", fake_request)
    result = score._score_case(
        case=case,
        protocol=_protocol(),
        health={"model_id": "google/medgemma-1.5-4b-it"},
        out_path=tmp_path / "prediction.json",
    )
    assert len(calls) == 1
    assert calls[0][1] == 180.0
    assert result["classification"] == "POSITIVA"
    assert result["log_odds_positive_vs_negative"] == pytest.approx(
        score.score_log_odds({"POSITIVA": 0.8, "NEGATIVA": 0.1})
    )
    assert result["ground_truth_read"] is False
    assert result["holdout_opened"] is False


def test_score_case_rejects_response_contract_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root, _ = _write_bundle(tmp_path)
    case = score.validate_atlas_bundle(root)["cases"][0]
    invalid = _response(choice="NEGATIVA")
    monkeypatch.setattr(score, "_request_json", lambda *_args, **_kwargs: invalid)
    with pytest.raises(PipelineError, match="argmax"):
        score._score_case(
            case=case,
            protocol=_protocol(),
            health={},
            out_path=tmp_path / "prediction.json",
        )


def test_existing_prediction_revalidates_log_odds_and_hashes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root, _ = _write_bundle(tmp_path)
    case = score.validate_atlas_bundle(root)["cases"][0]
    monkeypatch.setattr(score, "_request_json", lambda *_args, **_kwargs: _response())
    path = tmp_path / "prediction.json"
    score._score_case(case=case, protocol=_protocol(), health={}, out_path=path)
    assert score._validate_existing_prediction(path, case, _protocol())["time_gate_passed"]
    value = json.loads(path.read_text(encoding="utf-8"))
    value["log_odds_positive_vs_negative"] += 1
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(PipelineError, match="Log-odds"):
        score._validate_existing_prediction(path, case, _protocol())


def test_score_log_odds_rejects_nonfinite() -> None:
    with pytest.raises(PipelineError, match="inválidas"):
        score.score_log_odds({"POSITIVA": float("nan"), "NEGATIVA": 0.5})


def test_frozen_protocol_declares_one_call_no_retry_and_180s(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bundle = {
        "cohort_sha256": "a" * 64,
        "case_ids": [f"anon-openswiss-{index:016x}" for index in range(87)],
        "case_count": 87,
        "maximum_frames": 20,
    }
    review = {"review_signature": "b" * 64}
    monkeypatch.setattr(score, "validate_atlas_bundle", lambda _root: bundle)
    monkeypatch.setattr(score, "validate_scoring_review", lambda **_kwargs: review)
    monkeypatch.setattr(
        score,
        "load_screening_config",
        lambda _path: {
            "medgemma": {
                "model_id": "google/medgemma-1.5-4b-it",
                "model_version": "MedGemma 1.5 4B Instruction-Tuned",
                "endpoint_url": "http://127.0.0.1:8001/generate",
            }
        },
    )
    review_path = tmp_path / "review.json"
    review_path.write_text("{}", encoding="utf-8")
    protocol = score.freeze_score_protocol(
        atlas_root=tmp_path / "atlas",
        gallery_root=tmp_path / "gallery",
        review_path=review_path,
        config_path=tmp_path / "config.yaml",
        out_path=tmp_path / "protocol.json",
    )
    assert protocol["scoring"]["requests_per_case"] == 1
    assert protocol["scoring"]["automatic_retries"] == 0
    assert protocol["case_time_gate_seconds"] == 180.0
    assert protocol["maximum_image_edge"] == 768
    assert protocol["ground_truth_read"] is False


def test_timing_selection_is_blind_deterministic_and_representation_balanced() -> None:
    cases = []
    specs = [
        ("a", 5, 640, "multiphase_rgb"),
        ("b", 20, 640, "venous_single_phase_fallback"),
        ("c", 18, 768, "multiphase_rgb"),
        ("d", 10, 768, "multiphase_rgb"),
        ("e", 8, 640, "venous_single_phase_fallback"),
        ("f", 12, 768, "multiphase_rgb"),
    ]
    for suffix, frame_count, edge, representation in specs:
        cases.append(
            {
                "case_id": f"anon-openswiss-{suffix}",
                "frame_count": frame_count,
                "manifest_sha256": suffix * 64,
                "atlas_set_sha256": (suffix.upper()) * 64,
                "manifest": {
                    "source": {"candidate_kind": representation},
                    "frames": [
                        {"size_pixels": [edge, edge]} for _ in range(frame_count)
                    ],
                },
            }
        )
    first = score.select_timing_cases({"cases": cases})
    second = score.select_timing_cases({"cases": list(reversed(cases))})
    assert first == second
    assert len(first) == 4
    assert len({row["case_id"] for row in first}) == 4
    assert {row["representation"] for row in first} == {
        "multiphase_rgb",
        "venous_single_phase_fallback",
    }
    assert all("label" not in row for row in first)

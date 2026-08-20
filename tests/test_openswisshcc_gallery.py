import hashlib
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_freeze import create_experiment_freeze
from dtwin.benchmark.openswisshcc_gallery import build_review_gallery

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
    manifest = {
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
        manifest["candidate_kind"] = "venous_single_phase_fallback"
    (case / "candidate_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_gallery_is_truth_free_non_authoritative_and_complete(tmp_path):
    panels = tmp_path / "panels"
    _candidate(panels, "anon-multi", fallback=False)
    _candidate(panels, "anon-fallback", fallback=True)
    freeze = tmp_path / "freeze.json"
    create_experiment_freeze(
        panel_root=panels,
        multiphase_config=MULTI,
        fallback_config=FALLBACK,
        output_path=freeze,
        expected_case_count=2,
    )
    output = tmp_path / "gallery"
    manifest = build_review_gallery(
        panel_root=panels,
        freeze_path=freeze,
        output_dir=output,
        multiphase_config=MULTI,
        fallback_config=FALLBACK,
        expected_case_count=2,
    )
    assert manifest["case_count"] == 2
    assert manifest["ground_truth_read"] is False
    assert manifest["inference_executed"] is False
    assert manifest["authoritative_approval"] is False
    assert {entry["candidate_kind"] for entry in manifest["entries"]} == {
        "multiphase_rgb", "venous_single_phase_fallback"
    }
    html = (output / "index.html").read_text(encoding="utf-8")
    assert "0/0 casos completos" in html
    assert "Não aprova inferência" in html
    assert "authoritative_approval:false" in html
    assert "development_labels" not in html
    assert (output / "review_gallery_manifest.json").is_file()

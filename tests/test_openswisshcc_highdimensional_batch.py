import json
from pathlib import Path

from PIL import Image

import dtwin.benchmark.openswisshcc_highdimensional_batch as batch
from dtwin.benchmark.openswisshcc_highdimensional import CONTRACT, SCHEMA
from dtwin.core import PipelineError, sha256_of

CASE_IDS = [
    "anon-openswiss-0123456789abcdef",
    "anon-openswiss-fedcba9876543210",
]


def _source_summary(tmp_path: Path, *, ground_truth_read=False):
    path = tmp_path / "summary.json"
    path.write_text(json.dumps({
        "schema": "blind-source-v1",
        "case_count": 2,
        "case_ids": list(reversed(CASE_IDS)),
        "excluded_technical_case_id": "anon-openswiss-aaaaaaaaaaaaaaaa",
        "ground_truth_read": ground_truth_read,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }) + "\n", encoding="utf-8")
    return path


def _stack_manifest(case_id: str, root: Path):
    root.mkdir(parents=True)
    images = []
    for order in range(1, 6):
        path = root / f"slice_{order:03d}.png"
        Image.new("RGB", (16, 16), (order, order, order)).save(path, format="PNG")
        images.append({
            "order": order,
            "source_index_lps_z": order,
            "filename": path.name,
            "sha256": sha256_of(path),
            "bytes": path.stat().st_size,
            "width": 16,
            "height": 16,
            "mode": "RGB",
            "contains_liver_mask": True,
        })
    manifest = {
        "schema": SCHEMA,
        "contract": CONTRACT,
        "case_id": case_id,
        "source": {
            "volume_sha256": "1" * 64,
            "liver_mask_sha256": "2" * 64,
        },
        "sampling": {"maximum_slices": 50},
        "liver_mask_audit": {"coverage_fraction": 1.0},
        "slice_count": 5,
        "images": images,
        "gate": {
            "passed": True,
            "ground_truth_used": False,
            "lesion_mask_used": False,
            "phi_metadata_included": False,
        },
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def _valid_bundle(tmp_path: Path):
    root = tmp_path / "bundle"
    stacks = []
    for case_id in CASE_IDS:
        stack_root = root / "stacks" / case_id
        manifest = _stack_manifest(case_id, stack_root)
        stacks.append({
            "case_id": case_id,
            "stack_manifest_relative_path": f"stacks/{case_id}/manifest.json",
            "stack_manifest_sha256": sha256_of(stack_root / "manifest.json"),
            "slice_count": 5,
            "liver_coverage_fraction": 1.0,
            "source_volume_sha256": manifest["source"]["volume_sha256"],
            "source_liver_mask_sha256": manifest["source"]["liver_mask_sha256"],
        })
    base = {
        "schema": batch.BUNDLE_SCHEMA,
        "status": "blind_stacks_complete",
        "source_summary_sha256": "3" * 64,
        "source_summary_schema": "blind-source-v1",
        "case_count": 2,
        "case_ids": CASE_IDS,
        "maximum_slices": 50,
        "stacks": stacks,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    value = dict(base)
    value["bundle_signature"] = batch._canonical_hash(base)
    (root / "bundle.json").write_text(
        json.dumps(value, sort_keys=True) + "\n", encoding="utf-8"
    )
    return root


def test_prepare_bundle_uses_sorted_blind_ids_and_cap(tmp_path, monkeypatch):
    source = _source_summary(tmp_path)
    calls = []

    def fake_build(*, out_root, case_id, maximum_slices, **_kwargs):
        calls.append((case_id, maximum_slices))
        root = Path(out_root) / case_id
        root.mkdir(parents=True)
        manifest = {
            "slice_count": 5,
            "liver_mask_audit": {"coverage_fraction": 1.0},
            "source": {"volume_sha256": "1" * 64, "liver_mask_sha256": "2" * 64},
        }
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return manifest

    monkeypatch.setattr(batch, "build_highdimensional_stack", fake_build)
    result = batch.prepare_highdimensional_blind_bundle(
        source_summary_path=source,
        inputs_manifest_path=tmp_path / "unused.jsonl",
        input_root=tmp_path / "unused",
        out_root=tmp_path / "prepared",
        maximum_slices=50,
    )

    assert result["case_ids"] == CASE_IDS
    assert calls == [(CASE_IDS[0], 50), (CASE_IDS[1], 50)]
    assert result["ground_truth_read"] is False
    assert result["holdout_opened"] is False


def test_prepare_rejects_source_that_read_ground_truth(tmp_path):
    try:
        batch.prepare_highdimensional_blind_bundle(
            source_summary_path=_source_summary(tmp_path, ground_truth_read=True),
            inputs_manifest_path=tmp_path / "unused.jsonl",
            input_root=tmp_path / "unused",
            out_root=tmp_path / "prepared",
        )
    except PipelineError as exc:
        assert "preparação cega" in str(exc)
    else:
        raise AssertionError("Bundle com ground truth aberto deveria ser recusado")


def test_validate_and_freeze_batch_are_hash_bound_and_idempotent(tmp_path, monkeypatch):
    root = _valid_bundle(tmp_path)
    validated = batch.validate_highdimensional_blind_bundle(root)
    assert validated["case_ids"] == CASE_IDS
    monkeypatch.setattr(batch, "load_screening_config", lambda _path: {"medgemma": {
        "endpoint_url": "http://127.0.0.1:8001/generate",
        "model_id": "google/medgemma-1.5-4b-it",
        "model_version": "MedGemma 1.5 4B Instruction-Tuned",
    }})
    out = tmp_path / "protocol.json"
    first = batch.freeze_highdimensional_batch_protocol(
        bundle_root=root, config_path=Path("ignored"), out_path=out
    )
    second = batch.freeze_highdimensional_batch_protocol(
        bundle_root=root, config_path=Path("ignored"), out_path=out
    )
    assert first == second
    assert first["case_count"] == 2
    assert first["maximum_slices"] == 50
    assert first["generation"]["automatic_retries"] == 0

    (root / "stacks" / CASE_IDS[0] / "slice_001.png").write_bytes(b"tampered")
    try:
        batch.validate_highdimensional_blind_bundle(root)
    except PipelineError as exc:
        assert "Hash de imagem" in str(exc)
    else:
        raise AssertionError("Imagem adulterada deveria invalidar o bundle")

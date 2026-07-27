from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.benchmark import lld_mmri_v23_segmentation_pilot as module
from dtwin.core import PipelineError


def _sources(tmp_path: Path, monkeypatch):
    root = tmp_path / "download"
    images = root / "images"
    images.mkdir(parents=True)
    cases = []
    for index in range(2):
        case_id = f"anon-lld-{index:016d}"
        path = images / f"{case_id}.nii.gz"
        image = sitk.GetImageFromArray(np.ones((8, 16, 20), dtype=np.float32))
        sitk.WriteImage(image, str(path), useCompression=True)
        cases.append(
            {"case_id": case_id, "images": {"t1_venous": {"relative_path": f"images/{path.name}"}}}
        )
    manifest = {"protocol_signature": "p" * 64, "cases": cases}
    monkeypatch.setattr(module, "validate_lld_mmri_v23_download", lambda **_: manifest)
    monkeypatch.setattr(
        module,
        "verify_lld_mmri_v23_geometry_audit",
        lambda **_: {"audit_signature": "a" * 64},
    )
    return root


def _segmenter(source: Path, destination: Path):
    reference = sitk.ReadImage(str(source))
    mask = sitk.Image(reference.GetSize(), sitk.sitkUInt8)
    mask.CopyInformation(reference)
    mask += 1
    sitk.WriteImage(mask, str(destination), useCompression=True)
    return {"engine": "synthetic", "elapsed_seconds": 0.01, "fast": False}


def test_pilot_is_label_blind_and_never_inference_eligible(monkeypatch, tmp_path: Path):
    download = _sources(tmp_path, monkeypatch)
    output = tmp_path / "pilot"
    result = module.run_lld_mmri_v23_segmentation_pilot(
        protocol_root=tmp_path / "protocol",
        download_root=download,
        geometry_audit_root=tmp_path / "audit",
        output_root=output,
        segment_liver=_segmenter,
        case_count=2,
    )
    assert result["case_count"] == 2
    assert result["ground_truth_read"] is False
    assert result["lesion_masks_read"] == 0
    assert result["technical_timing_only"] is True
    assert result["eligible_for_inference"] is False
    assert result["end_to_end_time_measured"] is False
    assert result["qualified"] is False
    assert result["all_dynamic_liver_support_at_least_99_percent"] is True
    assert len((output / "cases.jsonl").read_text(encoding="utf-8").splitlines()) == 2
    verified = module.verify_lld_mmri_v23_segmentation_pilot(
        protocol_root=tmp_path / "protocol",
        download_root=download,
        geometry_audit_root=tmp_path / "audit",
        pilot_root=output,
        expected_pilot_signature=result["pilot_signature"],
    )
    assert verified["pilot_signature"] == result["pilot_signature"]
    mask = output / result["case_ids"][0] / "liver_mask_venous.nii.gz"
    mask.write_bytes(b"tampered")
    with pytest.raises(PipelineError, match="adulterado|invalido"):
        module.verify_lld_mmri_v23_segmentation_pilot(
            protocol_root=tmp_path / "protocol",
            download_root=download,
            geometry_audit_root=tmp_path / "audit",
            pilot_root=output,
        )


def test_pilot_rejects_non_frozen_selection_size(monkeypatch, tmp_path: Path):
    download = _sources(tmp_path, monkeypatch)
    with pytest.raises(PipelineError, match="ao menos 1"):
        module.run_lld_mmri_v23_segmentation_pilot(
            protocol_root=tmp_path / "protocol",
            download_root=download,
            geometry_audit_root=tmp_path / "audit",
            output_root=tmp_path / "pilot",
            segment_liver=_segmenter,
            case_count=0,
        )


def test_checkpoint_writer_keeps_last_valid_generation(tmp_path: Path):
    path = tmp_path / "checkpoint_rows.jsonl"
    first = [{"case_id": "one", "value": 1}]
    second = [*first, {"case_id": "two", "value": 2}]
    module._write_checkpoint_rows_atomic(path, first)
    module._write_checkpoint_rows_atomic(path, second)
    backup = tmp_path / "checkpoint_rows.backup.jsonl"
    assert [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] == second
    assert [json.loads(line) for line in backup.read_text(encoding="utf-8").splitlines()] == first

    path.write_bytes(b"\x00" * path.stat().st_size)
    third = [*second, {"case_id": "three", "value": 3}]
    module._write_checkpoint_rows_atomic(path, third)
    assert [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] == third
    assert [json.loads(line) for line in backup.read_text(encoding="utf-8").splitlines()] == first


def test_audit_rejects_case_count_above_frozen_cohort(monkeypatch, tmp_path: Path):
    download = _sources(tmp_path, monkeypatch)
    with pytest.raises(PipelineError, match="exceder o coorte congelado"):
        module.run_lld_mmri_v23_segmentation_pilot(
            protocol_root=tmp_path / "protocol",
            download_root=download,
            geometry_audit_root=tmp_path / "audit",
            output_root=tmp_path / "pilot",
            segment_liver=_segmenter,
            case_count=3,
        )


def test_invalid_primary_mask_uses_fast_fallback_and_records_both_attempts(
    monkeypatch,
    tmp_path: Path,
):
    download = _sources(tmp_path, monkeypatch)

    def invalid_primary(source: Path, destination: Path):
        reference = sitk.ReadImage(str(source))
        mask = sitk.Image(reference.GetSize(), sitk.sitkUInt8)
        mask.CopyInformation(reference)
        mask[0, 0, 0] = 1
        sitk.WriteImage(mask, str(destination), useCompression=True)
        return {"engine": "synthetic", "fast": False}

    result = module.run_lld_mmri_v23_segmentation_pilot(
        protocol_root=tmp_path / "protocol",
        download_root=download,
        geometry_audit_root=tmp_path / "audit",
        output_root=tmp_path / "fallback",
        segment_liver=invalid_primary,
        fallback_segment_liver=_segmenter,
        case_count=1,
    )
    row = json.loads(
        (tmp_path / "fallback" / "cases.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert result["segmentation_fallback_case_count"] == 1
    assert row["segmentation_fallback_used"] is True
    assert row["segmentation_selected_attempt"] == "fallback_fast_3mm"
    assert [attempt["status"] for attempt in row["segmentation_attempts"]] == [
        "failed_gate",
        "passed_gate",
    ]


def test_primary_and_fallback_failure_aborts_without_checkpointing_case(
    monkeypatch,
    tmp_path: Path,
):
    download = _sources(tmp_path, monkeypatch)

    def no_mask(_source: Path, _destination: Path):
        return {"engine": "synthetic"}

    with pytest.raises(PipelineError, match="primary_full_resolution.*fallback_fast_3mm"):
        module.run_lld_mmri_v23_segmentation_pilot(
            protocol_root=tmp_path / "protocol",
            download_root=download,
            geometry_audit_root=tmp_path / "audit",
            output_root=tmp_path / "both-fail",
            segment_liver=no_mask,
            fallback_segment_liver=no_mask,
            case_count=1,
        )
    incomplete = tmp_path / ".both-fail.incomplete"
    assert (incomplete / "checkpoint_rows.jsonl").read_text(encoding="utf-8") == ""


def test_full_audit_can_record_technical_failure_and_continue(monkeypatch, tmp_path: Path):
    download = _sources(tmp_path, monkeypatch)
    calls = 0

    def fail_first(source: Path, destination: Path):
        nonlocal calls
        calls += 1
        if calls <= 2:
            return {"engine": "synthetic", "fast": calls == 2}
        return _segmenter(source, destination)

    output = tmp_path / "technical-failure"
    result = module.run_lld_mmri_v23_segmentation_pilot(
        protocol_root=tmp_path / "protocol",
        download_root=download,
        geometry_audit_root=tmp_path / "audit",
        output_root=output,
        segment_liver=fail_first,
        fallback_segment_liver=fail_first,
        case_count=2,
        continue_on_technical_failure=True,
    )
    rows = [json.loads(line) for line in (output / "cases.jsonl").read_text(encoding="utf-8").splitlines()]
    assert result["segmentation_technical_failure_case_count"] == 1
    assert result["technical_failures_count_as_errors"] is True
    assert rows[0]["segmentation_status"] == "technical_failure_no_valid_liver_mask"
    assert rows[0]["technical_failure_counts_as_error"] is True
    assert rows[0]["mask_sha256"] is None
    assert not (output / rows[0]["case_id"]).exists()
    assert rows[1]["segmentation_status"] == "valid_liver_mask"
    verified = module.verify_lld_mmri_v23_segmentation_pilot(
        protocol_root=tmp_path / "protocol",
        download_root=download,
        geometry_audit_root=tmp_path / "audit",
        pilot_root=output,
    )
    assert verified["segmentation_technical_failure_case_count"] == 1


def test_checkpoint_with_technical_failure_resumes_without_requiring_mask(
    monkeypatch, tmp_path: Path
):
    download = _sources(tmp_path, monkeypatch)
    output = tmp_path / "resume-technical"
    def no_mask(_source: Path, _destination: Path):
        return {"engine": "synthetic"}

    def interrupt_after_checkpoint(_item: dict):
        raise PipelineError("interrupt after technical failure")

    with pytest.raises(PipelineError, match="interrupt"):
        module.run_lld_mmri_v23_segmentation_pilot(
            protocol_root=tmp_path / "protocol",
            download_root=download,
            geometry_audit_root=tmp_path / "audit",
            output_root=output,
            segment_liver=no_mask,
            fallback_segment_liver=no_mask,
            case_count=2,
            continue_on_technical_failure=True,
            progress=interrupt_after_checkpoint,
        )
    incomplete = tmp_path / ".resume-technical.incomplete"
    rows = [json.loads(line) for line in (incomplete / "checkpoint_rows.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["segmentation_status"] == "technical_failure_no_valid_liver_mask"

    result = module.run_lld_mmri_v23_segmentation_pilot(
        protocol_root=tmp_path / "protocol",
        download_root=download,
        geometry_audit_root=tmp_path / "audit",
        output_root=output,
        segment_liver=_segmenter,
        fallback_segment_liver=_segmenter,
        case_count=2,
        continue_on_technical_failure=True,
    )
    assert result["case_count"] == 2
    assert result["segmentation_technical_failure_case_count"] == 1


def test_full_audit_checkpoints_failure_and_resumes_without_resegmenting_first_case(
    monkeypatch,
    tmp_path: Path,
):
    download = _sources(tmp_path, monkeypatch)
    output = tmp_path / "audit"
    calls: list[str] = []

    def fail_second(source: Path, destination: Path):
        calls.append(source.name)
        if len(calls) == 2:
            raise PipelineError("synthetic second-case failure")
        return _segmenter(source, destination)

    with pytest.raises(PipelineError, match="second-case"):
        module.run_lld_mmri_v23_segmentation_pilot(
            protocol_root=tmp_path / "protocol",
            download_root=download,
            geometry_audit_root=tmp_path / "audit_gate",
            output_root=output,
            segment_liver=fail_second,
            case_count=2,
        )
    incomplete = tmp_path / ".audit.incomplete"
    failure = json.loads((incomplete / "failure.json").read_text(encoding="utf-8"))
    assert failure["completed_case_count"] == 1
    assert failure["case_id"] == "anon-lld-0000000000000001"
    assert not output.exists()

    resumed_calls: list[str] = []

    def resumed(source: Path, destination: Path):
        resumed_calls.append(source.name)
        return _segmenter(source, destination)

    result = module.run_lld_mmri_v23_segmentation_pilot(
        protocol_root=tmp_path / "protocol",
        download_root=download,
        geometry_audit_root=tmp_path / "audit_gate",
        output_root=output,
        segment_liver=resumed,
        case_count=2,
    )
    assert result["case_count"] == 2
    assert len(resumed_calls) == 1
    assert not incomplete.exists()


def test_lowest_coverage_selection_is_label_blind_and_deterministic(
    monkeypatch,
    tmp_path: Path,
):
    download = _sources(tmp_path, monkeypatch)
    harmonized = tmp_path / "harmonized"
    rows = []
    for index, support in ((0, 0.90), (1, 0.50)):
        case_id = f"anon-lld-{index:016d}"
        case_dir = harmonized / "cases" / case_id
        case_dir.mkdir(parents=True)
        source = download / "images" / f"{case_id}.nii.gz"
        destination = case_dir / "t1_venous.nii.gz"
        destination.write_bytes(source.read_bytes())
        rows.append(
            {
                "case_id": case_id,
                "files": [
                    {
                        "role": role,
                        "relative_path": f"cases/{case_id}/t1_venous.nii.gz",
                        "whole_reference_grid_support_fraction": support,
                    }
                    for role in ("t1_native", "t1_arterial", "t1_venous", "t1_delayed")
                ],
            }
        )
    (harmonized / "cases.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    monkeypatch.setattr(
        module,
        "verify_lld_mmri_v23_harmonization",
        lambda **_: {"harmonization_signature": "h" * 64},
    )
    monkeypatch.setattr(
        module,
        "dynamic_liver_support_fractions",
        lambda *_: {role: 1.0 for role in module.DYNAMIC_ROLES},
    )
    result = module.run_lld_mmri_v23_segmentation_pilot(
        protocol_root=tmp_path / "protocol",
        download_root=download,
        geometry_audit_root=None,
        failed_audit_root=tmp_path / "failed_audit",
        harmonization_root=harmonized,
        output_root=tmp_path / "lowest",
        segment_liver=_segmenter,
        case_count=1,
        selection="lowest_whole_grid_support",
    )
    assert result["case_ids"] == ["anon-lld-0000000000000001"]
    assert result["selection"] == "lowest_whole_grid_support_no_labels"
    serialized = json.dumps(result).lower()
    assert "label" not in serialized or result["ground_truth_read"] is False

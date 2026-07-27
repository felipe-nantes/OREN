from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.benchmark.lld_mmri_v23_download import download_lld_mmri_v23_images
from dtwin.benchmark.lld_mmri_v23_geometry_audit import audit_lld_mmri_v23_geometry
from dtwin.benchmark.lld_mmri_v23_harmonization import (
    harmonize_lld_mmri_v23_dynamic_t1,
)
from dtwin.benchmark.lld_mmri_v23_external import (
    MAPPING_SCHEMA,
    PROTOCOL_SCHEMA,
    REPO_ID,
    REPO_REVISION,
)
from dtwin.benchmark.lld_mmri_v23_preparation import (
    INPUT_SCHEMA,
    PREPARATION_SCHEMA,
    prepare_lld_mmri_v23_blind_inputs,
    isolated_total_mr_liver_segmenter,
    liver_segments_mr_union_segmenter,
    total_mr_liver_segmenter,
    verify_lld_mmri_v23_blind_inputs,
)
from dtwin.benchmark.lld_mmri_v23_segmentation_pilot import (
    run_lld_mmri_v23_segmentation_pilot,
)
from dtwin.benchmark.lld_mmri_v23_technical_amendment import (
    freeze_lld_mmri_v23_technical_amendment,
)
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError, sha256_of


SUFFIXES = ["C+A", "C+Delay", "C+V", "C-pre", "DWI", "InPhase", "OutPhase", "T2WI"]


def test_isolated_segmenter_returns_receipt_and_output(tmp_path: Path):
    source = tmp_path / "source.nii.gz"
    source.write_bytes(b"source")
    worker = tmp_path / "worker.py"
    worker.write_text(
        "import argparse, json, shutil\n"
        "p=argparse.ArgumentParser(); p.add_argument('--source'); p.add_argument('--output'); "
        "p.add_argument('--receipt'); p.add_argument('--device'); p.add_argument('--fast', action='store_true'); a=p.parse_args()\n"
        "shutil.copyfile(a.source,a.output)\n"
        "open(a.receipt,'w',encoding='utf-8').write(json.dumps({'engine':'fake','fast':a.fast}))\n",
        encoding="utf-8",
    )
    output = tmp_path / "mask.nii.gz"
    receipt = isolated_total_mr_liver_segmenter(
        source,
        output,
        fast=True,
        timeout_seconds=5,
        python_executable=sys.executable,
        worker_path=worker,
    )
    assert output.read_bytes() == b"source"
    assert receipt["engine"] == "fake"
    assert receipt["fast"] is True
    assert receipt["execution_isolation"] == "subprocess_tree_timeout_v1"


def test_isolated_segmenter_hard_timeout_removes_partial_output(tmp_path: Path):
    source = tmp_path / "source.nii.gz"
    source.write_bytes(b"source")
    worker = tmp_path / "sleep_worker.py"
    worker.write_text(
        "import argparse, time\n"
        "p=argparse.ArgumentParser(); p.add_argument('--source'); p.add_argument('--output'); "
        "p.add_argument('--receipt'); p.add_argument('--device'); p.add_argument('--fast', action='store_true'); a=p.parse_args()\n"
        "open(a.output,'wb').write(b'partial')\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    output = tmp_path / "mask.nii.gz"
    with pytest.raises(PipelineError, match="timeout tecnico"):
        isolated_total_mr_liver_segmenter(
            source,
            output,
            timeout_seconds=1,
            python_executable=sys.executable,
            worker_path=worker,
        )
    assert not output.exists()


def test_preparation_checkpoint_recovers_last_fsynced_backup(tmp_path: Path):
    from dtwin.benchmark import lld_mmri_v23_preparation as module

    path = tmp_path / "checkpoint_cases.jsonl"
    first = [{"row": {"case_id": "one"}, "receipt": {"case_id": "one"}}]
    second = first + [
        {"row": {"case_id": "two"}, "receipt": {"case_id": "two"}}
    ]
    module._write_jsonl_checkpoint_atomic(path, first)
    module._write_jsonl_checkpoint_atomic(path, second)
    path.write_bytes(b"\x00" * path.stat().st_size)
    assert module._load_jsonl_checkpoint(path) == first
    assert module._valid_jsonl_checkpoint(path)


def test_preparation_checkpoint_retries_transient_windows_reader_lock(
    monkeypatch, tmp_path: Path
):
    from dtwin.benchmark import lld_mmri_v23_preparation as module

    path = tmp_path / "checkpoint_cases.jsonl"
    module._write_jsonl_checkpoint_atomic(path, [{"case_id": "one"}])
    original_replace = Path.replace
    calls = 0

    def transiently_locked(source: Path, target: Path):
        nonlocal calls
        if Path(target) == path and calls < 2:
            calls += 1
            raise PermissionError(5, "transient reader lock", str(target))
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", transiently_locked)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    values = [{"case_id": "one"}, {"case_id": "two"}]
    module._write_jsonl_checkpoint_atomic(path, values)

    assert calls == 2
    assert module._load_jsonl_checkpoint(path) == values


def _protocol(tmp_path: Path, *, case_count: int = 1) -> Path:
    root = tmp_path / "protocol"
    mapping = root / "protected_source" / "mapping.jsonl"
    mapping.parent.mkdir(parents=True)
    rows = [
        {
            "schema": MAPPING_SCHEMA,
            "case_id": f"anon-lld-{index:016d}",
            "source_subject_id": f"MR-{index:03d}",
            "lesion_masks_allowed_in_inference": False,
            "raw_uids_persisted": False,
        }
        for index in range(case_count)
    ]
    mapping.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    base = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_before_external_images_and_predictions",
        "dataset_repo_id": REPO_ID,
        "dataset_revision": REPO_REVISION,
        "case_count": case_count,
        "case_ids": [row["case_id"] for row in rows],
        "protected_mapping_sha256": sha256_of(mapping),
        "lesion_masks_allowed_in_inference": False,
    }
    protocol = dict(base)
    protocol["protocol_signature"] = _canonical_sha(base)
    (root / "protocol.json").write_text(json.dumps(protocol), encoding="utf-8")
    return root


def _write_image(path: Path, *, origin=(0.0, 0.0, 0.0)) -> None:
    z, y, x = np.indices((8, 16, 20))
    array = (20 + x + 2 * y + 3 * z).astype(np.int16)
    image = sitk.GetImageFromArray(array)
    image.SetSpacing((1.5, 1.5, 2.5))
    image.SetOrigin(origin)
    sitk.WriteImage(image, str(path), useCompression=True)


def _download(
    tmp_path: Path, *, mismatch_role: str | None = None, case_count: int = 1
) -> tuple[Path, Path]:
    protocol = _protocol(tmp_path, case_count=case_count)
    destination = tmp_path / "download"
    repo_files = [
        f"images/MR-{index:03d}_1_{suffix}_0000.nii.gz"
        for index in range(case_count)
        for suffix in SUFFIXES
    ]

    def downloader(**kwargs):
        path = destination / kwargs["filename"]
        path.parent.mkdir(parents=True, exist_ok=True)
        mismatch = mismatch_role and f"_{mismatch_role}_0000.nii.gz" in path.name
        _write_image(path, origin=(3.0, 0.0, 0.0) if mismatch else (0.0, 0.0, 0.0))
        return str(path)

    download_lld_mmri_v23_images(
        protocol_root=protocol,
        destination=destination,
        accept_license=True,
        repo_files=repo_files,
        downloader=downloader,
    )
    return protocol, destination


def _segmenter(source: Path, destination: Path):
    reference = sitk.ReadImage(str(source))
    array = np.zeros(tuple(reversed(reference.GetSize())), dtype=np.uint8)
    array[1:-1, 2:-2, 2:-2] = 1
    mask = sitk.GetImageFromArray(array)
    mask.CopyInformation(reference)
    sitk.WriteImage(mask, str(destination), useCompression=True)
    return {"engine": "synthetic-test", "elapsed_seconds": 0.01}


def _audit(tmp_path: Path, protocol: Path, download: Path) -> Path:
    output = tmp_path / "geometry_audit"
    audit_lld_mmri_v23_geometry(
        protocol_root=protocol,
        download_root=download,
        output_root=output,
    )
    return output


def test_real_segmenter_uses_isolated_ephemeral_totalseg_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "venous.nii.gz"
    destination = tmp_path / "liver.nii.gz"
    weights = tmp_path / "weights"
    weights.mkdir()
    _write_image(source)
    monkeypatch.setenv("TOTALSEG_HOME_DIR", "original-home")
    monkeypatch.setenv("TOTALSEG_WEIGHTS_PATH", str(weights))

    import totalsegmentator.python_api as python_api

    def fake_totalsegmentator(**kwargs):
        runtime_home = Path(os.environ["TOTALSEG_HOME_DIR"])
        config = json.loads((runtime_home / "config.json").read_text(encoding="utf-8"))
        assert runtime_home != Path("original-home")
        assert Path(os.environ["TOTALSEG_WEIGHTS_PATH"]) == weights.resolve()
        assert config["send_usage_stats"] is False
        assert config["statistics_disclaimer_shown"] is True
        reference = sitk.ReadImage(kwargs["input"])
        mask = sitk.Image(reference.GetSize(), sitk.sitkUInt8)
        mask.CopyInformation(reference)
        sitk.WriteImage(mask, str(Path(kwargs["output"]) / "liver.nii.gz"))

    monkeypatch.setattr(python_api, "totalsegmentator", fake_totalsegmentator)
    receipt = total_mr_liver_segmenter(source, destination)
    assert destination.is_file()
    assert receipt["runtime_config"] == "ephemeral_isolated_v1"
    assert receipt["usage_stats_enabled"] is False
    assert os.environ["TOTALSEG_HOME_DIR"] == "original-home"
    assert os.environ["TOTALSEG_WEIGHTS_PATH"] == str(weights)


def test_real_segmenter_restores_environment_after_totalseg_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "venous.nii.gz"
    weights = tmp_path / "weights"
    weights.mkdir()
    _write_image(source)
    monkeypatch.setenv("TOTALSEG_HOME_DIR", "original-home")
    monkeypatch.setenv("TOTALSEG_WEIGHTS_PATH", str(weights))

    import totalsegmentator.python_api as python_api

    def fail_totalsegmentator(**_kwargs):
        raise RuntimeError("synthetic worker failure")

    monkeypatch.setattr(python_api, "totalsegmentator", fail_totalsegmentator)
    with pytest.raises(PipelineError, match="synthetic worker failure"):
        total_mr_liver_segmenter(source, tmp_path / "liver.nii.gz")
    assert os.environ["TOTALSEG_HOME_DIR"] == "original-home"
    assert os.environ["TOTALSEG_WEIGHTS_PATH"] == str(weights)


def test_dedicated_mr_segments_segmenter_unions_all_eight_classes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "venous.nii.gz"
    destination = tmp_path / "liver_union.nii.gz"
    weights = tmp_path / "weights"
    weights.mkdir()
    _write_image(source)
    monkeypatch.setenv("TOTALSEG_WEIGHTS_PATH", str(weights))
    import totalsegmentator.python_api as python_api

    def fake_totalsegmentator(**kwargs):
        assert kwargs["task"] == "liver_segments_mr"
        reference = sitk.ReadImage(kwargs["input"])
        for index in range(1, 9):
            array = np.zeros(tuple(reversed(reference.GetSize())), dtype=np.uint8)
            array[1, index, index] = 1
            segment = sitk.GetImageFromArray(array)
            segment.CopyInformation(reference)
            sitk.WriteImage(
                segment,
                str(Path(kwargs["output"]) / f"liver_segment_{index}.nii.gz"),
            )

    monkeypatch.setattr(python_api, "totalsegmentator", fake_totalsegmentator)
    receipt = liver_segments_mr_union_segmenter(source, destination)
    union = np.asarray(sitk.GetArrayFromImage(sitk.ReadImage(str(destination)))) > 0
    assert int(union.sum()) == 8
    assert receipt["task"] == "liver_segments_mr"
    assert len(receipt["union_classes"]) == 8


def test_prepares_eight_phases_and_only_automatic_liver_mask(tmp_path: Path):
    protocol, download = _download(tmp_path)
    audit = _audit(tmp_path, protocol, download)
    output = tmp_path / "prepared"
    result = prepare_lld_mmri_v23_blind_inputs(
        protocol_root=protocol,
        download_root=download,
        geometry_audit_root=audit,
        output_root=output,
        segment_liver=_segmenter,
    )
    assert result["schema"] == PREPARATION_SCHEMA
    assert result["case_count"] == 1
    assert result["image_count"] == 8
    assert result["automatic_liver_mask_count"] == 1
    assert result["labels_read"] is False
    assert result["lesion_masks_read"] == 0
    rows = [json.loads(line) for line in (output / "inputs.jsonl").read_text().splitlines()]
    assert rows[0]["schema"] == INPUT_SCHEMA
    assert len(rows[0]["files"]) == 9
    assert rows[0]["automatic_liver_mask"] is True
    assert rows[0]["pathology_label_present"] is False
    names = {path.name for path in (output / "inputs" / rows[0]["case_id"]).iterdir()}
    assert names == {
        "t1_native.nii.gz",
        "t1_arterial.nii.gz",
        "t1_venous.nii.gz",
        "t1_delayed.nii.gz",
        "t2.nii.gz",
        "dwi.nii.gz",
        "t1_in_phase.nii.gz",
        "t1_out_phase.nii.gz",
        "liver_mask_venous.nii.gz",
    }
    serialized = json.dumps(result).lower() + (output / "inputs.jsonl").read_text().lower()
    assert "mr-000" not in serialized
    verified = verify_lld_mmri_v23_blind_inputs(
        protocol_root=protocol,
        prepared_root=output,
        expected_preparation_signature=result["preparation_signature"],
    )
    assert verified["status"] == "ready_for_label_blind_panel_generation"
    assert verified["labels_read"] is False
    assert verified["lesion_masks_read"] == 0


def test_preparation_reuses_only_verified_complete_segmentation_audit(tmp_path: Path):
    protocol, download = _download(tmp_path)
    audit = _audit(tmp_path, protocol, download)
    segmentation_audit = tmp_path / "segmentation_audit"
    audited = run_lld_mmri_v23_segmentation_pilot(
        protocol_root=protocol,
        download_root=download,
        geometry_audit_root=audit,
        output_root=segmentation_audit,
        segment_liver=_segmenter,
        case_count=1,
    )

    def forbidden_resegmentation(_source: Path, _destination: Path):
        raise AssertionError("a mascara verificada deveria ser reutilizada")

    output = tmp_path / "prepared_from_audit"
    result = prepare_lld_mmri_v23_blind_inputs(
        protocol_root=protocol,
        download_root=download,
        geometry_audit_root=audit,
        output_root=output,
        segment_liver=forbidden_resegmentation,
        segmentation_audit_root=segmentation_audit,
        expected_segmentation_audit_signature=audited["pilot_signature"],
    )
    assert result["segmentation_source_type"] == "verified_full_cohort_segmentation_audit"
    assert result["segmentation_audit_signature"] == audited["pilot_signature"]
    receipt = result["case_receipts"][0]["segmentation"]
    assert receipt["resegmented"] is False
    assert receipt["source_mask_sha256"] == json.loads(
        (segmentation_audit / "cases.jsonl").read_text(encoding="utf-8")
    )["mask_sha256"]
    verified = verify_lld_mmri_v23_blind_inputs(
        protocol_root=protocol,
        prepared_root=output,
        expected_preparation_signature=result["preparation_signature"],
    )
    assert verified["status"] == "ready_for_label_blind_panel_generation"


def test_dynamic_t1_geometry_mismatch_aborts_atomically(tmp_path: Path):
    protocol, download = _download(tmp_path, mismatch_role="C+A")
    audit = _audit(tmp_path, protocol, download)
    output = tmp_path / "prepared"
    with pytest.raises(PipelineError, match="Gate geometrico"):
        prepare_lld_mmri_v23_blind_inputs(
            protocol_root=protocol,
            download_root=download,
            geometry_audit_root=audit,
            output_root=output,
            segment_liver=_segmenter,
        )
    assert not output.exists()


def test_preparation_accepts_only_verified_harmonization_after_failed_audit(tmp_path: Path):
    protocol, download = _download(tmp_path, mismatch_role="C+A")
    failed_audit = _audit(tmp_path, protocol, download)
    harmonized = tmp_path / "harmonized"
    harmonization = harmonize_lld_mmri_v23_dynamic_t1(
        protocol_root=protocol,
        download_root=download,
        failed_audit_root=failed_audit,
        output_root=harmonized,
    )
    output = tmp_path / "prepared_harmonized"
    result = prepare_lld_mmri_v23_blind_inputs(
        protocol_root=protocol,
        download_root=download,
        geometry_audit_root=None,
        failed_audit_root=failed_audit,
        harmonization_root=harmonized,
        output_root=output,
        segment_liver=_segmenter,
    )
    assert result["source_gate_type"] == "verified_dynamic_t1_harmonization"
    assert result["source_gate_signature"] == harmonization["harmonization_signature"]
    assert result["all_dynamic_liver_support_at_least_99_percent"] is True
    verified = verify_lld_mmri_v23_blind_inputs(
        protocol_root=protocol,
        prepared_root=output,
        expected_preparation_signature=result["preparation_signature"],
    )
    assert verified["status"] == "ready_for_label_blind_panel_generation"


def test_partial_fov_requires_signed_amendment_and_is_persisted(
    monkeypatch,
    tmp_path: Path,
):
    protocol, download = _download(tmp_path, mismatch_role="C+A")
    failed_audit = _audit(tmp_path, protocol, download)
    harmonized = tmp_path / "harmonized"
    harmonize_lld_mmri_v23_dynamic_t1(
        protocol_root=protocol,
        download_root=download,
        failed_audit_root=failed_audit,
        output_root=harmonized,
    )
    segmentation_audit = tmp_path / "segmentation_audit"
    audited = run_lld_mmri_v23_segmentation_pilot(
        protocol_root=protocol,
        download_root=download,
        geometry_audit_root=None,
        failed_audit_root=failed_audit,
        harmonization_root=harmonized,
        output_root=segmentation_audit,
        segment_liver=_segmenter,
        case_count=1,
    )
    from dtwin.benchmark import lld_mmri_v23_harmonization as harmonization_module
    from dtwin.benchmark import lld_mmri_v23_segmentation_pilot as segmentation_module
    from dtwin.benchmark import lld_mmri_v23_technical_amendment as amendment_module

    monkeypatch.setattr(
        harmonization_module,
        "dynamic_liver_support_fractions",
        lambda *_: {
            "t1_native": 1.0,
            "t1_arterial": 0.98,
            "t1_venous": 1.0,
            "t1_delayed": 0.45,
        },
    )
    monkeypatch.setattr(
        segmentation_module,
        "verify_lld_mmri_v23_segmentation_pilot",
        lambda **_: audited,
    )
    amendment_base = {
        "schema": amendment_module.AMENDMENT_SCHEMA,
        "segmentation_audit_signature": audited["pilot_signature"],
        "case_ids": ["anon-lld-0000000000000000"],
        "ground_truth_read": False,
        "lesion_masks_read": 0,
        "technical_failures": {
            "case_count": 0,
            "case_ids": [],
            "excluded_from_inference": True,
            "count_as_primary_metric_errors": True,
            "mask_fabrication_allowed": False,
        },
        "policy": {
            "reference_phase": "t1_venous",
            "reference_phase_requires_full_liver_coverage": True,
            "panel_partial_fov_policy": "venous_grayscale",
            "partial_fov_cases_excluded_from_primary_metrics": False,
        },
    }
    amendment = dict(amendment_base)
    amendment["amendment_signature"] = _canonical_sha(amendment_base)
    amendment_root = tmp_path / "amendment"
    amendment_root.mkdir()
    (amendment_root / "amendment.json").write_text(
        json.dumps(amendment), encoding="utf-8"
    )
    monkeypatch.setattr(
        amendment_module,
        "verify_lld_mmri_v23_technical_amendment",
        lambda **_: amendment,
    )
    output = tmp_path / "prepared_partial"
    result = prepare_lld_mmri_v23_blind_inputs(
        protocol_root=protocol,
        download_root=download,
        geometry_audit_root=None,
        failed_audit_root=failed_audit,
        harmonization_root=harmonized,
        segmentation_audit_root=segmentation_audit,
        expected_segmentation_audit_signature=audited["pilot_signature"],
        technical_amendment_root=amendment_root,
        expected_technical_amendment_signature=amendment["amendment_signature"],
        config_path=Path("configs/medgemma_local_4b_lld_v23_uniform9_choice.yaml"),
        profile_path=Path("profiles/figado.yaml"),
        output_root=output,
        segment_liver=_segmenter,
    )
    assert result["minimum_dynamic_liver_support_fraction"] == 0.45
    assert result["all_dynamic_liver_support_at_least_99_percent"] is False
    assert result["technical_amendment_signature"] == amendment["amendment_signature"]
    assert (output / "technical_amendment.json").is_file()
    verified = verify_lld_mmri_v23_blind_inputs(
        protocol_root=protocol,
        prepared_root=output,
        expected_preparation_signature=result["preparation_signature"],
    )
    assert verified["status"] == "ready_for_label_blind_panel_generation"


def test_preparation_excludes_signed_technical_failure_but_preserves_error_contract(
    tmp_path: Path,
):
    protocol, download = _download(tmp_path, mismatch_role="C+A", case_count=2)
    failed_audit = _audit(tmp_path, protocol, download)
    harmonized = tmp_path / "harmonized"
    harmonize_lld_mmri_v23_dynamic_t1(
        protocol_root=protocol,
        download_root=download,
        failed_audit_root=failed_audit,
        output_root=harmonized,
    )

    def selective_segmenter(source: Path, destination: Path):
        if "0000000000000001" not in str(source):
            return _segmenter(source, destination)
        reference = sitk.ReadImage(str(source))
        mask = sitk.Image(reference.GetSize(), sitk.sitkUInt8)
        mask.CopyInformation(reference)
        sitk.WriteImage(mask, str(destination), useCompression=True)
        return {"engine": "synthetic-empty", "elapsed_seconds": 0.01}

    segmentation_audit = tmp_path / "segmentation_audit"
    audited = run_lld_mmri_v23_segmentation_pilot(
        protocol_root=protocol,
        download_root=download,
        geometry_audit_root=None,
        failed_audit_root=failed_audit,
        harmonization_root=harmonized,
        output_root=segmentation_audit,
        segment_liver=selective_segmenter,
        case_count=2,
        continue_on_technical_failure=True,
    )
    assert audited["segmentation_technical_failure_case_count"] == 1
    amendment_root = tmp_path / "amendment"
    amendment = freeze_lld_mmri_v23_technical_amendment(
        protocol_root=protocol,
        download_root=download,
        failed_audit_root=failed_audit,
        harmonization_root=harmonized,
        segmentation_audit_root=segmentation_audit,
        config_path=Path("configs/medgemma_local_4b_lld_v23_uniform9_choice.yaml"),
        profile_path=Path("profiles/figado.yaml"),
        output_root=amendment_root,
    )
    output = tmp_path / "prepared_with_failure"
    result = prepare_lld_mmri_v23_blind_inputs(
        protocol_root=protocol,
        download_root=download,
        geometry_audit_root=None,
        failed_audit_root=failed_audit,
        harmonization_root=harmonized,
        segmentation_audit_root=segmentation_audit,
        expected_segmentation_audit_signature=audited["pilot_signature"],
        technical_amendment_root=amendment_root,
        expected_technical_amendment_signature=amendment["amendment_signature"],
        config_path=Path("configs/medgemma_local_4b_lld_v23_uniform9_choice.yaml"),
        profile_path=Path("profiles/figado.yaml"),
        output_root=output,
        segment_liver=_segmenter,
    )
    assert result["protocol_case_count"] == 2
    assert result["case_count"] == 1
    assert result["technical_failure_case_count"] == 1
    assert result["technical_failure_case_ids"] == [
        "anon-lld-0000000000000001"
    ]
    assert result["technical_failures_count_as_primary_metric_errors"] is True
    assert not (output / "inputs" / "anon-lld-0000000000000001").exists()
    verified = verify_lld_mmri_v23_blind_inputs(
        protocol_root=protocol,
        prepared_root=output,
        expected_preparation_signature=result["preparation_signature"],
    )
    assert verified["protocol_case_count"] == 2
    assert verified["case_count"] == 1
    assert verified["technical_failure_case_count"] == 1


def test_invalid_automatic_liver_mask_aborts_atomically(tmp_path: Path):
    protocol, download = _download(tmp_path)
    audit = _audit(tmp_path, protocol, download)
    output = tmp_path / "prepared"

    def empty_segmenter(source: Path, destination: Path):
        reference = sitk.ReadImage(str(source))
        mask = sitk.Image(reference.GetSize(), sitk.sitkUInt8)
        mask.CopyInformation(reference)
        sitk.WriteImage(mask, str(destination))
        return None

    with pytest.raises(PipelineError, match="pequena demais"):
        prepare_lld_mmri_v23_blind_inputs(
            protocol_root=protocol,
            download_root=download,
            geometry_audit_root=audit,
            output_root=output,
            segment_liver=empty_segmenter,
        )
    assert not output.exists()


def test_preparation_refuses_overwrite(tmp_path: Path):
    protocol, download = _download(tmp_path)
    audit = _audit(tmp_path, protocol, download)
    output = tmp_path / "prepared"
    prepare_lld_mmri_v23_blind_inputs(
        protocol_root=protocol,
        download_root=download,
        geometry_audit_root=audit,
        output_root=output,
        segment_liver=_segmenter,
    )
    with pytest.raises(PipelineError, match="sobrescrita"):
        prepare_lld_mmri_v23_blind_inputs(
            protocol_root=protocol,
            download_root=download,
            geometry_audit_root=audit,
            output_root=output,
            segment_liver=_segmenter,
        )


def test_preparation_verifier_rejects_tampered_phase(tmp_path: Path):
    protocol, download = _download(tmp_path)
    audit = _audit(tmp_path, protocol, download)
    output = tmp_path / "prepared"
    prepare_lld_mmri_v23_blind_inputs(
        protocol_root=protocol,
        download_root=download,
        geometry_audit_root=audit,
        output_root=output,
        segment_liver=_segmenter,
    )
    phase = output / "inputs" / "anon-lld-0000000000000000" / "t1_venous.nii.gz"
    phase.write_bytes(b"tampered")
    with pytest.raises(PipelineError, match="adulterado"):
        verify_lld_mmri_v23_blind_inputs(
            protocol_root=protocol,
            prepared_root=output,
        )

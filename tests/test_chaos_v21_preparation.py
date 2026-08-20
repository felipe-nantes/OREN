import hashlib
import io
import json
import zipfile
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from dtwin.benchmark.chaos_v21_preparation import (
    COHORT_ID,
    prepare_chaos_v21_blind_inputs,
    verify_chaos_v21_blind_inputs,
)
from dtwin.benchmark.public_independent_cohort import (
    INFERENCE_SCHEMA,
    PROTOCOL_SCHEMA,
    SOURCE_MAP_SCHEMA,
    _canonical_hash,
    _tree_fingerprint,
    anonymous_public_case_id,
)
from dtwin.core import PipelineError
from dtwin.datasets.chaos_download import (
    ChaosDownloadSpec,
    download_chaos_train,
    extract_chaos_mri_train,
)
from tools.make_synthetic_case import write_dicom_series


def _write_jsonl(path: Path, rows) -> str:
    payload = "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path):
    source = tmp_path / "source"
    subject = source / "Train_Sets/MR/1"
    volume = np.arange(3 * 8 * 8, dtype=np.int16).reshape(3, 8, 8)
    paths = {
        "t1_in": subject / "T1DUAL/DICOM_anon/InPhase",
        "t1_out": subject / "T1DUAL/DICOM_anon/OutPhase",
        "t2_spir": subject / "T2SPIR/DICOM_anon",
    }
    for index, directory in enumerate(paths.values(), 1):
        write_dicom_series(directory, volume + index, modality="MR")
    liver = np.zeros((8, 8), dtype=np.uint8)
    liver[2:6, 2:6] = 63
    liver[0, 0] = 126
    for role, ground in (("t1_in", subject / "T1DUAL/Ground"), ("t2_spir", subject / "T2SPIR/Ground")):
        ground.mkdir(parents=True)
        for dicom in paths[role].glob("*.dcm"):
            Image.fromarray(liver).save(ground / f"{dicom.stem}.png")

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            archive.write(path, path.relative_to(source).as_posix())
    payload = archive_buffer.getvalue()
    spec = ChaosDownloadSpec(
        filename="CHAOS_Train_Sets.zip", url="https://example.invalid/train.zip",
        size_bytes=len(payload), md5=hashlib.md5(payload).hexdigest(),
        record_id="test", version="test",
    )

    @contextmanager
    def opener(_url):
        yield io.BytesIO(payload)

    download_chaos_train(
        output_dir=tmp_path / "download", accept_license=True,
        accepted_by="jm", spec=spec, opener=opener,
    )
    extracted = tmp_path / "extracted"
    extract_chaos_mri_train(
        download_root=tmp_path / "download", output_dir=extracted,
        spec=spec, expected_subject_count=1,
    )

    raw_root = extracted / "Train_Sets/MR"
    raw_paths = [
        "1/T1DUAL/DICOM_anon/InPhase",
        "1/T1DUAL/DICOM_anon/OutPhase",
        "1/T2SPIR/DICOM_anon",
    ]
    fingerprint, count, total = _tree_fingerprint([raw_root / path for path in raw_paths], raw_root)
    case_id = anonymous_public_case_id(COHORT_ID, "chaos_mri", "1")
    inference = [{
        "schema": INFERENCE_SCHEMA, "case_id": case_id, "input_format": "DICOM",
        "series_or_volume_count": 3, "source_file_count": count,
        "source_total_bytes": total, "source_sha256": fingerprint,
        "research_only": True, "clinical_use_allowed": False,
        "requires_human_review": True, "ground_truth_read_during_inference": False,
        "lesion_mask_available_to_inference": False,
    }]
    source_rows = [{
        "schema": SOURCE_MAP_SCHEMA, "case_id": case_id,
        "root_alias": "src-" + hashlib.sha256(b"chaos_mri").hexdigest()[:12],
        "subject_relative_path": "1", "raw_paths": raw_paths,
        "source_sha256": fingerprint, "never_send_to_model": True,
    }]
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    inference_hash = _write_jsonl(bundle / "inference_manifest.jsonl", inference)
    source_hash = _write_jsonl(bundle / "operational_source_map.jsonl", source_rows)
    protocol = {
        "schema": PROTOCOL_SCHEMA, "cohort_id": COHORT_ID, "case_count": 1,
        "inference_manifest_sha256": inference_hash,
        "operational_source_map_sha256": source_hash,
        "protected_labels_sha256": "0" * 64, "registry_sha256": {},
        "selection_policy": "all_subjects_grouped_before_inference",
        "ground_truth_read_during_inference": False, "holdout_opened": False,
        "research_only": True, "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    protocol["protocol_signature"] = _canonical_hash(protocol)
    (bundle / "cohort_protocol.json").write_text(json.dumps(protocol), encoding="utf-8")
    return extracted, bundle, protocol["protocol_signature"]


def test_prepares_registered_label_blind_chaos_case(tmp_path: Path):
    extracted, bundle, signature = _fixture(tmp_path)
    output = tmp_path / "prepared"
    result = prepare_chaos_v21_blind_inputs(
        extracted_root=extracted, bundle_root=bundle, output_root=output,
        expected_protocol_signature=signature, expected_case_count=1,
    )
    assert result["case_count"] == 1
    assert result["ground_truth_class_read"] is False
    assert result["combined_primary_metric_allowed"] is False
    preflight = verify_chaos_v21_blind_inputs(
        prepared_root=output, expected_cohort_signature=result["cohort_signature"],
        expected_case_count=1,
    )
    assert preflight["status"] == "ready_for_blind_panel_generation"
    case_dir = next(path for path in output.iterdir() if path.is_dir())
    assert {path.name for path in case_dir.glob("*.nii.gz")} == {
        "t1_in.nii.gz", "t1_out.nii.gz", "t2_spir.nii.gz", "liver_mask.nii.gz",
    }
    assert not any("lesion" in path.name or "tumor" in path.name for path in output.rglob("*"))


def test_preparation_rejects_wrong_public_protocol_signature(tmp_path: Path):
    extracted, bundle, _signature = _fixture(tmp_path)
    with pytest.raises(PipelineError, match="Protocolo publico"):
        prepare_chaos_v21_blind_inputs(
            extracted_root=extracted, bundle_root=bundle, output_root=tmp_path / "prepared",
            expected_protocol_signature="0" * 64, expected_case_count=1,
        )


def test_preflight_rejects_changed_prepared_volume(tmp_path: Path):
    extracted, bundle, signature = _fixture(tmp_path)
    output = tmp_path / "prepared"
    result = prepare_chaos_v21_blind_inputs(
        extracted_root=extracted, bundle_root=bundle, output_root=output,
        expected_protocol_signature=signature, expected_case_count=1,
    )
    volume = next(output.rglob("t1_out.nii.gz"))
    volume.write_bytes(volume.read_bytes() + b"changed")
    with pytest.raises(PipelineError, match="alterado"):
        verify_chaos_v21_blind_inputs(
            prepared_root=output, expected_cohort_signature=result["cohort_signature"],
            expected_case_count=1,
        )


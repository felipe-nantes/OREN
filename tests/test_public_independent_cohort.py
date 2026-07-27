import json
from pathlib import Path

import pytest

from dtwin.benchmark.public_independent_cohort import (
    PublicSource,
    build_public_independent_cohort,
    verify_public_independent_cohort,
)
from dtwin.core import PipelineError
from dtwin.datasets.schema import REGISTRY_SCHEMA


def _registry(root: Path, dataset: str, role: str, subjects: int = 2) -> Path:
    rows = []
    for subject in range(subjects):
        for series in range(2):
            relative = f"subject-{subject:02d}/series-{series:02d}"
            directory = root / relative
            directory.mkdir(parents=True)
            (directory / "image.dcm").write_bytes(f"{dataset}-{subject}-{series}".encode())
            rows.append({
                "schema": REGISTRY_SCHEMA,
                "case_id": f"{dataset}-{subject}-{series}",
                "series_id": f"hash-{subject}-{series}",
                "dataset_id": dataset,
                "dataset_name": dataset,
                "rag_class": role,
                "label": "documented",
                "negative_subtype": "normal" if role == "negative" else None,
                "positive_subtype": "hcc_suspicious" if role == "positive" else None,
                "phenotype_tags": [],
                "modality": "MR",
                "source_format": "dicom",
                "dicom_original": True,
                "nifti_original": False,
                "derived_from": None,
                "sequence_or_phase": "unknown",
                "body_region": "abdomen_liver",
                "raw_path": relative,
                "annotation_path": f"subject-{subject:02d}/tumor.nii.gz" if role == "positive" else None,
                "has_segmentation": role == "positive",
                "source_url": "https://example.invalid",
                "clinical_use_allowed": False,
                "research_only": True,
                "review_status": "pending_review",
                "limitations": [],
                "warnings": [],
                "metadata": {},
            })
    path = root.parent / f"{dataset}.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _sources(tmp_path: Path, subjects: int = 2) -> list[PublicSource]:
    positive_root = tmp_path / "positive"
    negative_root = tmp_path / "negative"
    return [
        PublicSource("pos", "positive", _registry(positive_root, "pos", "positive", subjects), positive_root, "src-positive", 1),
        PublicSource("neg", "negative", _registry(negative_root, "neg", "negative", subjects), negative_root, "src-negative", 1),
    ]


def _lines(path: Path):
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


def test_build_separates_inference_sources_and_protected_labels(tmp_path):
    out = tmp_path / "bundle"
    result = build_public_independent_cohort(
        cohort_id="v21-test", sources=_sources(tmp_path), output_dir=out,
        minimum_subjects_per_role={"positive": 2, "negative": 2},
    )

    inference = _lines(out / "inference_manifest.jsonl")
    source_map = _lines(out / "operational_source_map.jsonl")
    labels = _lines(out / "protected_ground_truth" / "protected_labels.jsonl")
    encoded_inference = json.dumps(inference)

    assert result["case_count"] == 4
    assert result["role_counts"] == {"positive": 2, "negative": 2}
    assert [row["case_id"] for row in inference] == [row["case_id"] for row in labels]
    assert all(row["case_id"].startswith("anon-public-") for row in inference)
    assert "label" not in encoded_inference and "dataset_id" not in encoded_inference
    assert "annotation" not in encoded_inference and "rag_class" not in encoded_inference
    assert all(row["never_send_to_model"] is True for row in source_map)
    assert {row["label"] for row in labels} == {"positive", "negative"}


def test_protocol_hashes_exact_artifacts_and_declares_confounding(tmp_path):
    out = tmp_path / "bundle"
    result = build_public_independent_cohort(
        cohort_id="v21-test", sources=_sources(tmp_path), output_dir=out,
    )
    protocol = json.loads((out / "cohort_protocol.json").read_text("utf-8"))
    audit = json.loads((out / "protected_ground_truth" / "selection_audit.json").read_text("utf-8"))

    assert protocol["protocol_signature"] == result["protocol_signature"]
    assert protocol["ground_truth_read_during_inference"] is False
    assert protocol["holdout_opened"] is False
    assert audit["dataset_class_confounding"] is True
    assert audit["qualified_as_final_publication_evidence"] is False


def test_subject_series_are_grouped_exactly_once(tmp_path):
    out = tmp_path / "bundle"
    build_public_independent_cohort(cohort_id="v21-test", sources=_sources(tmp_path, 3), output_dir=out)
    inference = _lines(out / "inference_manifest.jsonl")
    source_map = _lines(out / "operational_source_map.jsonl")

    assert len(inference) == 6
    assert len({row["case_id"] for row in inference}) == 6
    assert all(row["series_or_volume_count"] == 2 for row in inference)
    assert all(len(row["raw_paths"]) == 2 for row in source_map)


def test_case_ids_and_order_are_deterministic_across_output_locations(tmp_path):
    sources = _sources(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    build_public_independent_cohort(cohort_id="v21-test", sources=sources, output_dir=first)
    build_public_independent_cohort(cohort_id="v21-test", sources=sources, output_dir=second)

    assert (first / "inference_manifest.jsonl").read_bytes() == (second / "inference_manifest.jsonl").read_bytes()
    assert (first / "cohort_protocol.json").read_bytes() == (second / "cohort_protocol.json").read_bytes()


def test_source_file_change_changes_fingerprint(tmp_path):
    sources = _sources(tmp_path)
    first = tmp_path / "first"
    build_public_independent_cohort(cohort_id="v21-test", sources=sources, output_dir=first)
    before = _lines(first / "inference_manifest.jsonl")
    (sources[0].root / "subject-00" / "series-00" / "image.dcm").write_bytes(b"changed")
    second = tmp_path / "second"
    build_public_independent_cohort(cohort_id="v21-test", sources=sources, output_dir=second)
    after = _lines(second / "inference_manifest.jsonl")

    assert [row["source_sha256"] for row in before] != [row["source_sha256"] for row in after]


def test_rejects_role_mismatch_before_writing_output(tmp_path):
    sources = _sources(tmp_path)
    bad = PublicSource("pos", "negative", sources[0].registry_path, sources[0].root, "src-bad", 1)
    out = tmp_path / "bundle"
    with pytest.raises(PipelineError, match="rag_class divergente"):
        build_public_independent_cohort(cohort_id="v21-test", sources=[bad, sources[1]], output_dir=out)
    assert not out.exists()


def test_rejects_unsafe_path_and_missing_minimum(tmp_path):
    sources = _sources(tmp_path, subjects=1)
    rows = _lines(sources[0].registry_path)
    rows[0]["raw_path"] = "../outside"
    sources[0].registry_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    with pytest.raises(PipelineError, match="raw_path inseguro"):
        build_public_independent_cohort(cohort_id="v21-test", sources=sources, output_dir=tmp_path / "bad")

    clean = _sources(tmp_path / "clean", subjects=1)
    with pytest.raises(PipelineError, match="Coorte insuficiente"):
        build_public_independent_cohort(
            cohort_id="v21-test", sources=clean, output_dir=tmp_path / "too-small",
            minimum_subjects_per_role={"positive": 2, "negative": 2},
        )


def test_refuses_overwrite_of_frozen_bundle(tmp_path):
    sources = _sources(tmp_path)
    out = tmp_path / "bundle"
    build_public_independent_cohort(cohort_id="v21-test", sources=sources, output_dir=out)
    with pytest.raises(PipelineError, match="recuso sobrescrever"):
        build_public_independent_cohort(cohort_id="v21-test", sources=sources, output_dir=out)


def test_preflight_verifies_artifacts_and_sources_without_parsing_labels(tmp_path, monkeypatch):
    sources = _sources(tmp_path)
    out = tmp_path / "bundle"
    built = build_public_independent_cohort(cohort_id="v21-test", sources=sources, output_dir=out)
    from dtwin.benchmark import public_independent_cohort as module
    original = module._read_jsonl
    parsed = []

    def tracked(path):
        parsed.append(Path(path))
        return original(path)

    monkeypatch.setattr(module, "_read_jsonl", tracked)
    result = verify_public_independent_cohort(
        bundle_dir=out,
        sources=sources,
        expected_protocol_signature=built["protocol_signature"],
    )

    assert result["status"] == "ready_for_blind_inference"
    assert result["protected_labels_parsed"] is False
    assert not any(path.name == "protected_labels.jsonl" for path in parsed)


def test_preflight_rejects_manifest_and_source_tampering(tmp_path):
    sources = _sources(tmp_path)
    out = tmp_path / "bundle"
    build_public_independent_cohort(cohort_id="v21-test", sources=sources, output_dir=out)
    manifest = out / "inference_manifest.jsonl"
    manifest.write_bytes(manifest.read_bytes() + b"\n")
    with pytest.raises(PipelineError, match="Hash inconsistente"):
        verify_public_independent_cohort(bundle_dir=out, sources=sources)

    clean = tmp_path / "clean"
    build_public_independent_cohort(cohort_id="v21-test-clean", sources=sources, output_dir=clean)
    (sources[0].root / "subject-00" / "series-00" / "image.dcm").write_bytes(b"tampered")
    with pytest.raises(PipelineError, match="Fonte alterada"):
        verify_public_independent_cohort(bundle_dir=clean, sources=sources)


def test_preflight_rejects_wrong_expected_signature(tmp_path):
    sources = _sources(tmp_path)
    out = tmp_path / "bundle"
    build_public_independent_cohort(cohort_id="v21-test", sources=sources, output_dir=out)
    with pytest.raises(PipelineError, match="assinatura esperada"):
        verify_public_independent_cohort(
            bundle_dir=out, sources=sources, expected_protocol_signature="0" * 64,
        )

import csv
import json
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.core import PipelineError
from dtwin.volumetry import (
    VOLUMETRY_CONTRACT,
    VOLUMETRY_CONTRACT_V2,
    VOLUMETRY_CSV_NAME,
    VOLUMETRY_JSON_NAME,
    VOLUMETRY_SCHEMA,
    VolumetryStructure,
    build_volumetry_manifest,
    verify_volumetry_artifacts,
)


def _image(array: np.ndarray, spacing=(2.0, 3.0, 4.0)) -> sitk.Image:
    image = sitk.GetImageFromArray(array)
    image.SetSpacing(spacing)
    image.SetOrigin((10.0, -20.0, 30.0))
    return image


def _write(path: Path, array: np.ndarray, spacing=(2.0, 3.0, 4.0)) -> Path:
    sitk.WriteImage(_image(array, spacing), str(path), useCompression=True)
    return path


def test_volumetry_uses_mask_voxels_and_physical_spacing(tmp_path):
    shape = (4, 5, 6)
    reference = _write(tmp_path / "volume.nii.gz", np.zeros(shape, np.float32))
    mask = np.zeros(shape, np.uint8)
    mask[1:3, 1:4, 2:6] = 1  # 24 voxels; 24 mm³ each.
    liver = _write(tmp_path / "liver.nii.gz", mask)

    manifest = build_volumetry_manifest(
        reference_volume=reference,
        structures=[VolumetryStructure("orgao", "Fígado", liver, "organ")],
        output_dir=tmp_path / "outputs",
        case_id="anon-volumetry",
    )

    assert manifest["schema"] == VOLUMETRY_SCHEMA
    assert manifest["contract"] == VOLUMETRY_CONTRACT
    assert manifest["mesh_is_authoritative_for_volume"] is False
    measured = manifest["structures"][0]
    assert measured["voxel_count"] == 24
    assert measured["voxel_volume_mm3"] == 24.0
    assert measured["volume_ml"] == pytest.approx(0.576)
    assert measured["percent_of_whole_liver"] == 100.0
    assert measured["dimensions_lps_mm"] == {
        "left_right": 8.0,
        "anterior_posterior": 9.0,
        "superior_inferior": 8.0,
    }


def test_volumetry_default_organ_e_figado_com_alias_v2_identico(tmp_path):
    """RIM-01: sem `organ`, o manifesto continua tendo TODAS as chaves v1
    inalteradas (compat total) e GANHA as v2 como cópia exata — fígado
    nunca perde whole_liver/whole_liver_summary/percent_of_whole_liver."""
    shape = (4, 5, 6)
    reference = _write(tmp_path / "volume.nii.gz", np.zeros(shape, np.float32))
    mask = np.zeros(shape, np.uint8)
    mask[1:3, 1:4, 2:6] = 1
    liver = _write(tmp_path / "liver.nii.gz", mask)

    manifest = build_volumetry_manifest(
        reference_volume=reference,
        structures=[VolumetryStructure("orgao", "Fígado", liver, "organ")],
        output_dir=tmp_path / "outputs",
        case_id="anon-volumetry-v2",
    )

    assert manifest["organ"] == "figado"
    assert manifest["contract"] == VOLUMETRY_CONTRACT
    assert manifest["contract_v2"] == VOLUMETRY_CONTRACT_V2
    assert manifest["structures"][0]["measurement_class"] == "whole_liver"
    assert manifest["organ_summary"] == manifest["whole_liver_summary"]
    assert manifest["structures"][0]["percent_of_organ"] == (
        manifest["structures"][0]["percent_of_whole_liver"]
    )
    with (tmp_path / "outputs" / VOLUMETRY_CSV_NAME).open(encoding="utf-8") as f:
        cabecalho = f.readline()
    assert "percent_of_whole_liver" in cabecalho and "percent_of_organ" in cabecalho


def test_volumetry_organ_nao_figado_usa_whole_organ(tmp_path):
    """Órgão par (rim): measurement_class do agregado vira genérico; as
    chaves hepáticas v1 continuam presentes (compat estrutural), mas
    marcadas com a semântica correta, não "whole_liver" para um rim."""
    shape = (4, 5, 6)
    reference = _write(tmp_path / "volume.nii.gz", np.zeros(shape, np.float32))
    mask = np.zeros(shape, np.uint8)
    mask[1:3, 1:4, 2:6] = 1
    orgao = _write(tmp_path / "orgao.nii.gz", mask)

    manifest = build_volumetry_manifest(
        reference_volume=reference,
        structures=[VolumetryStructure("orgao", "Rins", orgao, "organ")],
        output_dir=tmp_path / "outputs",
        case_id="anon-volumetry-rim",
        organ="rins",
    )

    assert manifest["organ"] == "rins"
    assert manifest["structures"][0]["measurement_class"] == "whole_organ"
    assert manifest["organ_summary"]["volume_ml"] == manifest["whole_liver_summary"]["volume_ml"]


def test_volumetry_rejects_mask_on_different_geometry(tmp_path):
    reference = _write(tmp_path / "volume.nii.gz", np.zeros((4, 4, 4), np.float32))
    mask = _write(
        tmp_path / "mask.nii.gz",
        np.ones((4, 4, 4), np.uint8),
        spacing=(1.0, 1.0, 1.0),
    )
    with pytest.raises(PipelineError, match="mesma geometria"):
        build_volumetry_manifest(
            reference_volume=reference,
            structures=[VolumetryStructure("orgao", "Fígado", mask, "organ")],
            output_dir=tmp_path / "outputs",
        )


def test_candidate_volume_is_explicitly_unconfirmed(tmp_path):
    shape = (5, 5, 5)
    reference = _write(tmp_path / "volume.nii.gz", np.zeros(shape, np.float32))
    liver_array = np.ones(shape, np.uint8)
    candidate_array = np.zeros(shape, np.uint8)
    candidate_array[2:4, 2:4, 2:4] = 1
    liver = _write(tmp_path / "liver.nii.gz", liver_array)
    candidate = _write(tmp_path / "candidate.nii.gz", candidate_array)
    manifest = build_volumetry_manifest(
        reference_volume=reference,
        structures=[
            VolumetryStructure("orgao", "Fígado", liver, "organ"),
            VolumetryStructure("candidato", "Região candidata", candidate, "candidate"),
        ],
        output_dir=tmp_path / "outputs",
    )
    measured = next(row for row in manifest["structures"] if row["role"] == "candidato")
    assert measured["measurement_class"] == "automatic_unconfirmed_candidate"
    assert measured["interpretation"] == "automatic_unconfirmed_region_not_a_confirmed_lesion"
    assert measured["percent_of_whole_liver"] == pytest.approx(8 / 125 * 100)


def test_eight_couinaud_masks_must_exactly_partition_liver(tmp_path):
    shape = (2, 2, 8)
    reference = _write(tmp_path / "volume.nii.gz", np.zeros(shape, np.float32))
    liver_array = np.ones(shape, np.uint8)
    liver = _write(tmp_path / "liver.nii.gz", liver_array)
    structures = [VolumetryStructure("orgao", "Fígado", liver, "organ")]
    roman = ("i", "ii", "iii", "iv", "v", "vi", "vii", "viii")
    for index, suffix in enumerate(roman):
        segment = np.zeros(shape, np.uint8)
        segment[:, :, index] = 1
        path = _write(tmp_path / f"segment_{suffix}.nii.gz", segment)
        structures.append(
            VolumetryStructure(f"couinaud_{suffix}", f"Segmento {suffix}", path, "segment")
        )
    manifest = build_volumetry_manifest(
        reference_volume=reference,
        structures=structures,
        output_dir=tmp_path / "outputs",
    )
    partition = manifest["couinaud_partition"]
    assert partition["gate_passed"] is True
    assert partition["liver_coverage_percent"] == 100.0
    assert partition["missing_liver_voxels"] == 0
    assert partition["overlapping_segment_voxels"] == 0
    assert sum(
        row["percent_of_whole_liver"]
        for row in manifest["structures"]
        if row["measurement_class"] == "couinaud_segment"
    ) == pytest.approx(100.0)


def test_incomplete_couinaud_partition_is_not_published_as_usable(tmp_path):
    shape = (3, 3, 3)
    reference = _write(tmp_path / "volume.nii.gz", np.zeros(shape, np.float32))
    liver = _write(tmp_path / "liver.nii.gz", np.ones(shape, np.uint8))
    segment_array = np.zeros(shape, np.uint8)
    segment_array[:, :, :1] = 1
    segment = _write(tmp_path / "segment_i.nii.gz", segment_array)
    manifest = build_volumetry_manifest(
        reference_volume=reference,
        structures=[
            VolumetryStructure("orgao", "Fígado", liver, "organ"),
            VolumetryStructure("couinaud_i", "Segmento I", segment, "segment"),
        ],
        output_dir=tmp_path / "outputs",
    )
    partition = manifest["couinaud_partition"]
    assert partition["available"] is True
    assert partition["gate_passed"] is False
    measured = next(row for row in manifest["structures"] if row["role"] == "couinaud_i")
    assert measured["technical_quality"]["usable"] is False
    assert "couinaud_partition_gate_failed" in measured["technical_quality"]["warnings"]


def test_volumetry_persists_json_and_csv_atomically(tmp_path):
    shape = (4, 4, 4)
    reference = _write(tmp_path / "volume.nii.gz", np.zeros(shape, np.float32))
    liver = _write(tmp_path / "liver.nii.gz", np.ones(shape, np.uint8))
    output = tmp_path / "outputs"
    manifest = build_volumetry_manifest(
        reference_volume=reference,
        structures=[VolumetryStructure("orgao", "Fígado", liver, "organ")],
        output_dir=output,
    )
    persisted = json.loads((output / VOLUMETRY_JSON_NAME).read_text(encoding="utf-8"))
    assert persisted == manifest
    with (output / VOLUMETRY_CSV_NAME).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert rows[0]["role"] == "orgao"
    assert float(rows[0]["volume_ml"]) == pytest.approx(manifest["structures"][0]["volume_ml"])
    assert not list(output.glob("*.tmp"))


def test_volumetry_reports_technical_range_and_quality_from_adaptive_receipt(tmp_path):
    shape = (8, 8, 8)
    reference = _write(tmp_path / "volume.nii.gz", np.zeros(shape, np.float32))
    liver_array = np.zeros(shape, np.uint8)
    liver_array[1:7, 1:7, 1:7] = 1
    liver = _write(tmp_path / "liver.nii.gz", liver_array)
    manifest = build_volumetry_manifest(
        reference_volume=reference,
        structures=[VolumetryStructure("orgao", "Fígado", liver, "organ")],
        output_dir=tmp_path / "outputs",
        segmentation_quality={
            "adaptive": {
                "selected_output": "protected_fusion",
                "primary": {"volume_ml": 4.8},
                "secondary": {"volume_ml": 5.4},
                "agreement": {"dice": 0.95, "jaccard": 0.91},
            }
        },
    )
    summary = manifest["whole_liver_summary"]
    assert summary["segmentation_source"] == "protected_fusion"
    assert summary["quality"]["grade"] == "A"
    assert summary["technical_range_ml"]["source_count"] == 3
    assert summary["technical_range_ml"]["lower_ml"] == pytest.approx(4.8)


def test_single_mask_volumetry_is_transparently_graded_b(tmp_path):
    shape = (6, 6, 6)
    reference = _write(tmp_path / "volume.nii.gz", np.zeros(shape, np.float32))
    liver = _write(tmp_path / "liver.nii.gz", np.ones(shape, np.uint8))
    manifest = build_volumetry_manifest(
        reference_volume=reference,
        structures=[VolumetryStructure("orgao", "Fígado", liver, "organ")],
        output_dir=tmp_path / "outputs",
    )
    assert manifest["whole_liver_summary"]["quality"]["grade"] == "B"
    assert "cross_source_agreement_not_available" in manifest["whole_liver_summary"]["quality"]["reasons"]


def test_independent_verifier_detects_csv_tampering(tmp_path):
    shape = (5, 5, 5)
    reference = _write(tmp_path / "volume.nii.gz", np.zeros(shape, np.float32))
    liver = _write(tmp_path / "liver.nii.gz", np.ones(shape, np.uint8))
    output = tmp_path / "outputs"
    build_volumetry_manifest(
        reference_volume=reference,
        structures=[VolumetryStructure("orgao", "Fígado", liver, "organ")],
        output_dir=output,
    )
    receipt = verify_volumetry_artifacts(output)
    assert receipt["status"] == "verified"
    (output / VOLUMETRY_CSV_NAME).write_text("tampered\n", encoding="utf-8")
    with pytest.raises(PipelineError, match="Hash do CSV"):
        verify_volumetry_artifacts(output)

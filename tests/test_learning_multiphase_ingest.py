from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.core import PipelineError
from dtwin.learning import multiphase_ingest as mi


def test_normalize_phase_name_handles_aliases_accents_and_separators():
    assert mi.normalize_phase_name("arterial") == mi.ARTERIAL
    assert mi.normalize_phase_name("Fase_Arterial") == mi.ARTERIAL
    assert mi.normalize_phase_name("PORTAL") == mi.VENOUS
    assert mi.normalize_phase_name("fase tardia") == mi.DELAYED
    assert mi.normalize_phase_name("t1-delayed") == mi.DELAYED
    assert mi.normalize_phase_name("scout") is None


def _touch(path: Path, name: str = "img.dcm"):
    path.mkdir(parents=True, exist_ok=True)
    (path / name).write_bytes(b"x")


def test_discover_phase_folders_finds_three_phases(tmp_path):
    case = tmp_path / "caso-001"
    _touch(case / "arterial")
    _touch(case / "venous")
    _touch(case / "delayed")
    found = mi.discover_phase_folders(case)
    assert set(found) == set(mi.REQUIRED_PHASES)
    assert found[mi.ARTERIAL].name == "arterial"


def test_discover_phase_folders_tolerates_wrapper_directory(tmp_path):
    # Users commonly drag a study folder, adding one nesting level.
    case = tmp_path / "caso-002"
    study = case / "ESTUDO_RM_ABDOME"
    _touch(study / "Arterial")
    _touch(study / "Venoso")
    _touch(study / "Tardio")
    found = mi.discover_phase_folders(case)
    assert set(found) == set(mi.REQUIRED_PHASES)


def test_discover_phase_folders_requires_all_three(tmp_path):
    case = tmp_path / "caso-003"
    _touch(case / "arterial")
    _touch(case / "venous")
    with pytest.raises(PipelineError, match="sem as fases obrigatórias"):
        mi.discover_phase_folders(case)


def test_discover_phase_folders_fails_closed_on_ambiguity(tmp_path):
    case = tmp_path / "caso-004"
    _touch(case / "arterial")
    _touch(case / "arterial_repeat" if False else case / "AP")  # second arterial alias
    _touch(case / "venous")
    _touch(case / "delayed")
    with pytest.raises(PipelineError, match="Fases ambíguas"):
        mi.discover_phase_folders(case)


def test_discover_phase_folders_ignores_empty_phase_folder(tmp_path):
    case = tmp_path / "caso-005"
    (case / "arterial").mkdir(parents=True)  # empty -> not a usable phase
    _touch(case / "venous")
    _touch(case / "delayed")
    with pytest.raises(PipelineError, match="sem as fases obrigatórias"):
        mi.discover_phase_folders(case)


def _image(size=(8, 8, 4), origin=(0.0, 0.0, 0.0), spacing=(1.0, 1.0, 2.0), value=1.0):
    array = np.full(size[::-1], value, dtype=np.float32)
    image = sitk.GetImageFromArray(array)
    image.SetOrigin(origin)
    image.SetSpacing(spacing)
    return image


def test_harmonize_resamples_onto_reference_grid_with_full_coverage():
    reference = _image()  # 8x8x4 @ (1,1,2) -> 8x8x8 mm
    # Finer grid over the SAME physical extent: half the spacing needs twice the
    # voxels, otherwise the acquisition would physically cover a smaller region.
    moving = _image(size=(16, 16, 8), spacing=(0.5, 0.5, 1.0), value=7.0)
    output, coverage = mi.harmonize_to_reference(moving, reference)
    assert output.GetSize() == reference.GetSize()
    assert output.GetSpacing() == reference.GetSpacing()
    assert coverage > 0.9  # moving covers the reference region


def test_harmonize_flags_acquisition_covering_smaller_physical_extent():
    # Same voxel count but half the spacing = only 1/8 of the reference volume.
    reference = _image()
    smaller = _image(spacing=(0.5, 0.5, 1.0))
    _output, coverage = mi.harmonize_to_reference(smaller, reference)
    assert coverage < mi.MINIMUM_COVERAGE


def test_harmonize_reports_low_coverage_for_disjoint_acquisition():
    reference = _image()
    far_away = _image(origin=(500.0, 500.0, 500.0))
    _output, coverage = mi.harmonize_to_reference(far_away, reference)
    assert coverage < 0.1


def test_build_multiphase_case_rejects_low_coverage(tmp_path, monkeypatch):
    case_upload = tmp_path / "caso-006"
    for name in ("arterial", "venous", "delayed"):
        _touch(case_upload / name)

    reference = _image()
    segmented = tmp_path / "seg"
    segmented.mkdir()
    sitk.WriteImage(reference, str(segmented / "volume.nii.gz"))
    mask = sitk.Cast(reference, sitk.sitkUInt8)
    sitk.WriteImage(mask, str(segmented / "mask_organ.nii.gz"))

    # arterial acquisition sits far from the reference -> must fail loudly
    monkeypatch.setattr(mi, "read_phase_series", lambda d, **k: _image(origin=(500.0, 500.0, 500.0)))
    with pytest.raises(PipelineError, match="não correspondem"):
        mi.build_multiphase_case(
            case_id="caso-006",
            case_upload_dir=case_upload,
            output_dir=tmp_path / "out",
            segment_venous=lambda venous_dir, work_dir: segmented,
        )


def test_build_multiphase_case_produces_panel_ready_inputs(tmp_path, monkeypatch):
    case_upload = tmp_path / "caso-007"
    for name in ("arterial", "venous", "delayed"):
        _touch(case_upload / name)

    reference = _image()
    segmented = tmp_path / "seg"
    segmented.mkdir()
    sitk.WriteImage(reference, str(segmented / "volume.nii.gz"))
    sitk.WriteImage(sitk.Cast(reference, sitk.sitkUInt8), str(segmented / "mask_organ.nii.gz"))
    monkeypatch.setattr(mi, "read_phase_series", lambda d, **k: _image(value=3.0))

    result = mi.build_multiphase_case(
        case_id="caso-007",
        case_upload_dir=case_upload,
        output_dir=tmp_path / "out",
        segment_venous=lambda venous_dir, work_dir: segmented,
    )
    assert set(result.phase_paths) == set(mi.REQUIRED_PHASES)
    # venous reference is the segmentation's own volume, so mask and phases align
    assert result.phase_paths[mi.VENOUS] == segmented / "volume.nii.gz"
    assert result.coarse_liver_mask_path == segmented / "mask_organ.nii.gz"
    for phase in (mi.ARTERIAL, mi.DELAYED):
        assert result.phase_paths[phase].is_file()
        harmonized = sitk.ReadImage(str(result.phase_paths[phase]))
        assert harmonized.GetSize() == reference.GetSize()  # shares the 3D grid
    assert result.coverage[mi.VENOUS] == 1.0


def test_build_multiphase_case_requires_segmentation_outputs(tmp_path):
    case_upload = tmp_path / "caso-008"
    for name in ("arterial", "venous", "delayed"):
        _touch(case_upload / name)
    empty = tmp_path / "empty_seg"
    empty.mkdir()
    with pytest.raises(PipelineError, match="Segmentação não produziu"):
        mi.build_multiphase_case(
            case_id="caso-008",
            case_upload_dir=case_upload,
            output_dir=tmp_path / "out",
            segment_venous=lambda venous_dir, work_dir: empty,
        )

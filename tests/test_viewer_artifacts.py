from pathlib import Path

import numpy as np
import pyvista as pv
import SimpleITK as sitk

from dtwin.core import array_to_image, read_image, save_image
from dtwin.viewer_artifacts import (
    acquisition_summary,
    generate_reference_images,
    lesion_segment_overlap,
    nearest_surface_relationships,
)
from .conftest import make_sphere_mask


def test_reference_generator_accepts_singleton_4d_volume(synthetic_case, tmp_path):
    volume = read_image(synthetic_case.volume)
    volume_4d = sitk.JoinSeries([volume])
    path = tmp_path / "volume_4d.nii.gz"
    save_image(volume_4d, path)

    result = generate_reference_images(
        path,
        synthetic_case.mask_organ,
        tmp_path / "references",
    )

    assert result["views"]["axial"]["frames"]
    assert result["views"]["coronal"]["orientation_labels"]["top"] == "S"
    assert result["views"]["sagittal"]["orientation_labels"]["left"] == "A"


def test_reference_generator_centres_all_orientations_on_segmented_candidate(
    synthetic_case, tmp_path
):
    reference = read_image(synthetic_case.mask_organ)
    shape = tuple(reversed(reference.GetSize()))
    candidate = make_sphere_mask(shape, (23, 24, 25), 2)
    candidate_path = tmp_path / "candidate.nii.gz"
    save_image(array_to_image(candidate, reference, np.uint8), candidate_path)

    result = generate_reference_images(
        synthetic_case.volume,
        synthetic_case.mask_organ,
        tmp_path / "candidate_references",
        candidate_path,
    )

    axial = result["views"]["axial"]
    selected_axial = axial["frames"][axial["default_frame_index"]]
    assert axial["selection_basis"] == "maximum_unconfirmed_candidate_cross_section"
    assert selected_axial["candidate_visible_in_plane"] is True
    for orientation in ("coronal", "sagittal"):
        view = result["views"][orientation]
        assert view["selection_basis"] == "maximum_unconfirmed_candidate_cross_section"
        assert view["frames"][0]["candidate_visible_in_plane"] is True


def test_acquisition_summary_discloses_interpolation(synthetic_case):
    summary = acquisition_summary(
        synthetic_case.volume,
        synthetic_case.mask_organ,
        mesh_isotropic_spacing_mm=0.8,
        mesh_smoothing_sigma_mm=2.0,
    )
    assert summary["modality"] == "MR"
    assert summary["mesh_isotropic_spacing_mm"] == 0.8
    assert "interpolação" in summary["interpolation_disclosure"]
    assert summary["liver_axial_planes"] > 0


def test_nearest_relationships_only_exist_with_manual_lesion():
    lesion = pv.Sphere(radius=1.0, center=(0, 0, 0))
    vessel = pv.Sphere(radius=1.0, center=(5, 0, 0))
    relationships = nearest_surface_relationships(
        {"lesao": lesion, "veia_porta": vessel},
        ["veia_porta", "ausente"],
    )
    assert len(relationships) == 1
    assert relationships[0]["target_role"] == "veia_porta"
    assert 2.5 < relationships[0]["minimum_surface_distance_mm"] < 3.5
    assert nearest_surface_relationships({"veia_porta": vessel}, ["veia_porta"]) == []


def test_nearest_relationships_accept_unconfirmed_candidate_source():
    candidate = pv.Sphere(radius=1.0, center=(0, 0, 0))
    vessel = pv.Sphere(radius=1.0, center=(5, 0, 0))
    relationships = nearest_surface_relationships(
        {"candidato": candidate, "veia_porta": vessel},
        ["veia_porta"],
        source_role="candidato",
    )
    assert relationships[0]["source_role"] == "candidato"


def test_lesion_overlap_reports_dominant_couinaud_segment(synthetic_case, tmp_path):
    reference = read_image(synthetic_case.mask_organ)
    shape = tuple(reversed(reference.GetSize()))
    segment_a = make_sphere_mask(shape, (20, 20, 20), 6)
    segment_b = make_sphere_mask(shape, (8, 8, 8), 2)
    path_a = tmp_path / "segment_a.nii.gz"
    path_b = tmp_path / "segment_b.nii.gz"
    save_image(array_to_image(segment_a, reference, np.uint8), path_a)
    save_image(array_to_image(segment_b, reference, np.uint8), path_b)

    context = lesion_segment_overlap(
        synthetic_case.mask_lesion,
        {"couinaud_i": path_a, "couinaud_ii": path_b},
    )

    assert context is not None
    assert context["dominant_segment_role"] == "couinaud_i"
    assert context["not_surgical_planning"] is True

import json
from collections import Counter
from pathlib import Path

import numpy as np

from dtwin.benchmark.synthetic_external_stress_v1 import (
    CLASS_CATEGORY,
    DEFAULT_TARGETS,
    build_plan,
    download_required_masks,
    implant_lesion,
    required_mask_files,
    synthesize_lesion_free_liver,
)


def _sources():
    return {
        "hemangioma": [f"hem-{i}" for i in range(79)],
        "simple_cyst": [f"cyst-{i}" for i in range(53)],
        "fnh": [f"fnh-{i}" for i in range(46)],
        "hcc": [f"hcc-{i}" for i in range(157)],
    }


def test_plan_has_exact_counts_and_declares_dependencies():
    plan = build_plan(
        nih_cases=[f"train_{i:03d}" for i in range(195)],
        lld_cases=_sources(),
    )
    assert len(plan) == 330
    assert Counter(row["label"] for row in plan) == Counter(DEFAULT_TARGETS)
    assert len({row["background_case_id"] for row in plan}) == 195
    assert max(Counter(row["background_case_id"] for row in plan).values()) == 2
    assert all(row["donor_case_id"] is None for row in plan if row["label"] == "no_focal_lesion")
    assert all(row["donor_case_id"] is not None for row in plan if row["label"] != "no_focal_lesion")


def test_required_masks_are_three_per_unique_donor():
    plan = build_plan(
        nih_cases=[f"test_{i:03d}" for i in range(195)],
        lld_cases=_sources(),
    )
    unique_donors = {row["donor_case_id"] for row in plan if row["donor_case_id"]}
    files = required_mask_files(plan)
    assert len(files) == 3 * len(unique_donors)
    assert all(path.startswith("labels/") and path.endswith(".nii.gz") for path in files)


def test_download_masks_is_public_revision_bound(tmp_path: Path):
    plan = [
        {
            "donor_case_id": "MR1",
            "donor_category": CLASS_CATEGORY["fnh"],
        }
    ]
    calls = []

    def downloader(**kwargs):
        calls.append(kwargs)
        path = tmp_path / kwargs["filename"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"mask")
        return str(path)

    paths = download_required_masks(
        plan=plan,
        lld_root=tmp_path,
        downloader=downloader,
        workers=2,
    )
    assert len(paths) == 3
    assert all(call["repo_type"] == "dataset" for call in calls)
    assert len({call["revision"] for call in calls}) == 1


def _toy_volume():
    shape = (24, 48, 48)
    mask = np.zeros(shape, dtype=bool)
    mask[4:20, 8:40, 8:40] = True
    base = np.full(shape, 20, dtype=np.int16)
    base[mask] = 100
    base[10:14, 20:25, 20:25] = 500
    arrays = {
        "arterial": base.copy(),
        "venous": (base * 1.2).astype(np.int16),
        "delayed": (base * 1.1).astype(np.int16),
    }
    return arrays, mask


def test_lesion_free_synthesis_removes_focal_hotspot_and_preserves_background():
    arrays, mask = _toy_volume()
    result = synthesize_lesion_free_liver(arrays, mask, seed=7)
    assert result["arterial"][~mask].tolist() == arrays["arterial"][~mask].tolist()
    assert float(result["arterial"][10:14, 20:25, 20:25].mean()) < 200
    assert not np.array_equal(result["arterial"], result["venous"])


def test_implant_is_inside_liver_and_changes_each_phase():
    arrays, mask = _toy_volume()
    clean = synthesize_lesion_free_liver(arrays, mask, seed=11)
    signature = {
        "extent_mm_zyx": [12.0, 16.0, 16.0],
        "phases": {
            "arterial": {"contrast_z": 2.5, "texture_ratio": 0.8},
            "venous": {"contrast_z": 0.5, "texture_ratio": 0.7},
            "delayed": {"contrast_z": 0.1, "texture_ratio": 0.6},
        },
    }
    implanted, lesions = implant_lesion(clean, mask, (1.0, 1.0, 2.0), signature, seed=12)
    for phase in ("arterial", "venous", "delayed"):
        lesion = lesions[phase]
        assert lesion.sum() >= 64
        assert not np.any(lesion & ~mask)
        assert np.any(implanted[phase][lesion] != clean[phase][lesion])

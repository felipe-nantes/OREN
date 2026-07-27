from __future__ import annotations

import numpy as np
import pytest

from dtwin.benchmark.openswisshcc_enhancement_localizer import (
    THRESHOLDS,
    build_enhancement_proposals,
)
from dtwin.core import PipelineError


def test_proposals_use_frozen_thresholds_and_remove_tiny_components():
    joint = np.zeros((8, 12, 12), dtype=np.float32)
    analysis = np.ones_like(joint, dtype=bool)
    joint[2:5, 3:6, 3:6] = 4.5
    joint[0, 0, 0] = 8.0
    result = build_enhancement_proposals(
        joint_enhancement=joint, analysis_mask=analysis, spacing_xyz=(1.0, 1.0, 2.0)
    )
    assert tuple(item["threshold"] for item in result.values()) == THRESHOLDS
    assert all(item["proposal_voxels"] == 27 for item in result.values())
    assert all(item["component_count"] == 1 for item in result.values())
    assert result["t4"]["proposal_volume_mm3"] == 54.0


def test_proposals_reject_nonfinite_map():
    joint = np.ones((4, 4, 4), dtype=np.float32)
    joint[1, 1, 1] = np.nan
    with pytest.raises(PipelineError, match="invalido"):
        build_enhancement_proposals(
            joint_enhancement=joint,
            analysis_mask=np.ones_like(joint, dtype=bool),
            spacing_xyz=(1.0, 1.0, 1.0),
        )

from __future__ import annotations

import numpy as np

from dtwin.learning.localized_candidate_features import localized_dynamic_features


def test_localized_dynamic_feature_contract_is_fixed_and_finite():
    shape = (7, 12, 12)
    z = np.linspace(-1, 2, np.prod(shape), dtype=np.float32).reshape(shape)
    state = {
        "analysis_mask": np.ones(shape, dtype=bool),
        "arterial_relative": z,
        "arterial_over_venous": z * 0.25,
        "arterial_over_delayed": z * 0.5,
        "venous_over_delayed": z * 0.25,
        "joint_enhancement": np.maximum(z, 0),
    }
    vector, names = localized_dynamic_features(
        state, [[0, 7], [1, 11], [1, 11]], proposal_voxels=70,
        component_rank=2, center_zyx=[3, 6, 6],
    )
    assert vector.shape == (87,)
    assert len(names) == len(set(names)) == 87
    assert np.isfinite(vector).all()
    assert names[-6:] == [
        "proposal_density", "component_rank", "center_z_relative",
        "center_y_relative", "center_x_relative", "liver_fraction",
    ]

from __future__ import annotations

import numpy as np

from dtwin.learning.medsiglip_head_classifier import _fit, _scores


def test_nonlinear_head_keeps_case_boundaries_and_scores():
    vectors = {
        f"p{i}": np.asarray([1.0 + i, 0.2, -0.1], dtype=np.float64)
        for i in range(8)
    }
    vectors.update(
        {
            f"n{i}": np.asarray([-1.0 - i, -0.2, 0.1], dtype=np.float64)
            for i in range(8)
        }
    )
    labels = {case_id: int(case_id.startswith("p")) for case_id in vectors}
    model = _fit(
        list(vectors),
        vectors,
        labels,
        hidden_units=4,
        alpha=0.01,
        seed=3,
        max_iter=100,
    )
    scores = _scores(model, list(vectors), vectors)
    assert set(scores) == set(vectors)
    assert all(0.0 <= value <= 1.0 for value in scores.values())

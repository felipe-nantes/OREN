from __future__ import annotations

from dtwin.benchmark.gd_eob_hbp_pilot import (
    PILOT_CASE_COUNT,
    _static_signal_compatibility,
    select_pilot_cases,
)


def _rows() -> list[dict]:
    rows = []
    for center, count in (("center-1", 88), ("center-2", 94), ("center-3", 38)):
        for index in range(count):
            rows.append(
                {
                    "case_id": f"anon-gdeob-{index:018x}{center[-1]}a",
                    "center_pseudonym": center,
                }
            )
    return rows


def test_pilot_selection_is_deterministic_balanced_and_label_free():
    rows = _rows()
    first = select_pilot_cases(rows)
    second = select_pilot_cases(list(reversed(rows)))
    assert first == second
    assert len(first) == len(set(first)) == PILOT_CASE_COUNT == 9
    by_id = {row["case_id"]: row for row in rows}
    assert [by_id[case_id]["center_pseudonym"] for case_id in first].count(
        "center-1"
    ) == 3
    assert [by_id[case_id]["center_pseudonym"] for case_id in first].count(
        "center-2"
    ) == 3
    assert [by_id[case_id]["center_pseudonym"] for case_id in first].count(
        "center-3"
    ) == 3


def test_static_gate_rejects_direct_v23_because_dynamic_shape_is_missing(tmp_path):
    required = (
        "dtwin/benchmark/openswisshcc_v11_fusion.py",
        "dtwin/benchmark/openswisshcc_candidate_shape.py",
        "dtwin/benchmark/openswisshcc_enhancement_maps.py",
        "dtwin/benchmark/lld_mmri_v23_shape.py",
    )
    for relative in required:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("source", encoding="utf-8")
    result = _static_signal_compatibility(tmp_path)
    assert result["exact_v23_score_computable"] is False
    assert result["direct_external_validation_of_frozen_v23_allowed"] is False
    shape = result["required_signals"]["candidate_weighted_linearity"]
    assert shape["input_available"] is False
    assert "native, arterial, venous and delayed" in shape["reason"]

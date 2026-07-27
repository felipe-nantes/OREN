import hashlib
from pathlib import Path

import pytest

from dtwin.benchmark.openswisshcc_configs import (
    authorized_config_paths,
    parse_extra_configs,
    resolve_candidate_config,
)
from dtwin.core import PipelineError


MULTI = Path("configs/medgemma_local_4b_multiphase_fast_pathology.yaml")
FALLBACK = Path("configs/medgemma_local_4b_venous_review_fallback_pathology.yaml")
CONTRAST = Path("configs/medgemma_local_4b_venous_review_fallback_high_contrast_pathology.yaml")


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_extra_config_is_selected_by_authorized_key_and_hash():
    paths = authorized_config_paths(
        multiphase_config=MULTI,
        fallback_config=FALLBACK,
        additional_configs={"venous_single_phase_fallback_high_contrast": CONTRAST},
    )
    key, path = resolve_candidate_config(
        {
            "candidate_kind": "venous_single_phase_fallback",
            "config_sha256": _sha(CONTRAST),
        },
        paths,
    )
    assert key == "venous_single_phase_fallback_high_contrast"
    assert path == CONTRAST.resolve()


def test_extra_config_rejects_arbitrary_key_and_hash_mismatch():
    with pytest.raises(PipelineError, match="não autorizada"):
        authorized_config_paths(
            multiphase_config=MULTI,
            fallback_config=FALLBACK,
            additional_configs={"browser_path": CONTRAST},
        )
    paths = authorized_config_paths(
        multiphase_config=MULTI,
        fallback_config=FALLBACK,
    )
    with pytest.raises(PipelineError, match="registro autorizado"):
        resolve_candidate_config(
            {
                "candidate_kind": "venous_single_phase_fallback",
                "config_sha256": "0" * 64,
            },
            paths,
        )


def test_parse_extra_configs_requires_unique_key_value_pairs():
    assert parse_extra_configs(["venous_single_phase_fallback_high_contrast=x.yaml"])[
        "venous_single_phase_fallback_high_contrast"
    ] == Path("x.yaml")
    with pytest.raises(PipelineError, match="duplicada"):
        parse_extra_configs(["venous_single_phase_fallback_x=a", "venous_single_phase_fallback_x=b"])

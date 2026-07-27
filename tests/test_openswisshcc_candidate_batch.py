import json

import pytest

from dtwin.core import PipelineError
from tools.build_openswisshcc_candidates import _case_ids


def test_case_ids_read_only_neutral_manifest(tmp_path):
    folder = tmp_path / "manifests"
    folder.mkdir()
    (folder / "development_inputs.jsonl").write_text(
        json.dumps({"case_id": "anon-b", "files": []}) + "\n"
        + json.dumps({"case_id": "anon-a", "files": []}) + "\n",
        encoding="utf-8",
    )
    assert _case_ids(tmp_path) == ["anon-a", "anon-b"]


@pytest.mark.parametrize("protected", ["label", "truth", "hcc", "positive", "negative"])
def test_case_ids_reject_ground_truth_fields(tmp_path, protected):
    folder = tmp_path / "manifests"
    folder.mkdir()
    (folder / "development_inputs.jsonl").write_text(
        json.dumps({"case_id": "anon-a", protected: "x"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(PipelineError, match="ground truth"):
        _case_ids(tmp_path)


def test_case_ids_reject_duplicate_or_nonanonymous(tmp_path):
    folder = tmp_path / "manifests"
    folder.mkdir()
    (folder / "development_inputs.jsonl").write_text(
        json.dumps({"case_id": "sub-001"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(PipelineError, match="inválido"):
        _case_ids(tmp_path)


import json
from pathlib import Path
import tomllib

from tools.score_medsiglip_panel import _write_json_atomic


def test_medgemma_extra_declares_siglip_tokenizer_runtime_dependencies():
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["optional-dependencies"]["medgemma"]
    assert any(item.startswith("protobuf>=") for item in dependencies)
    assert any(item.startswith("sentencepiece>=") for item in dependencies)


def test_medsiglip_cli_atomic_writer_replaces_file(tmp_path):
    output = tmp_path / "scores.json"
    _write_json_atomic(output, {"version": 1})
    _write_json_atomic(output, {"version": 2, "final_decision": None})
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "version": 2,
        "final_decision": None,
    }
    assert not (tmp_path / ".scores.json.tmp").exists()

from pathlib import Path

import pytest

from tools.verify_graphify_argos import is_blocked_source, verify_graph


ROOT = Path(__file__).resolve().parents[1]


def test_graphify_scan_excludes_medical_and_generated_data() -> None:
    ignored = (ROOT / ".graphifyignore").read_text(encoding="utf-8")
    for protected_path in ("casos/", "data/", "datasets/", "dicoms/", "rag/"):
        assert protected_path in ignored
    for protected_suffix in ("*.dcm", "*.nii", "*.nii.gz", "*.safetensors"):
        assert protected_suffix in ignored


def test_graphify_build_is_local_code_only() -> None:
    wrapper = (ROOT / "tools" / "graphify_argos.ps1").read_text(encoding="utf-8")
    assert "extract . --code-only" in wrapper
    assert "GEMINI_API_KEY" not in wrapper
    assert "OPENAI_API_KEY" not in wrapper


def test_graphify_install_is_reproducibly_pinned() -> None:
    setup = (ROOT / "tools" / "setup_graphify_argos.ps1").read_text(encoding="utf-8")
    assert "https://github.com/Graphify-Labs/graphify.git" in setup
    assert "7fe58b0b0f3873be9a21c30106b8b8527c353aa6" in setup
    assert '"$sourceDir[neo4j]"' in setup


def test_graphify_is_separate_from_clinical_graphrag() -> None:
    wrapper = (ROOT / "tools" / "graphify_argos.ps1").read_text(encoding="utf-8")
    assert "graphify-out\\graph.json" in wrapper
    assert "configs\\graphrag_neo4j.yaml" not in wrapper


@pytest.mark.parametrize(
    "source",
    [
        "casos/example/panel.py",
        "data/private/loader.py",
        ".codex-tmp/graphify-source/graphify/cli.py",
        "dicoms/case/image.dcm",
        "artifacts/mesh.nii.gz",
    ],
)
def test_graphify_verifier_blocks_protected_sources(source: str) -> None:
    assert is_blocked_source(source)


def test_graphify_verifier_allows_clinical_graphrag_source_code(tmp_path: Path) -> None:
    graph = tmp_path / "graph.json"
    graph.write_text(
        '{"nodes":[{"source_file":"dtwin/graphrag/query.py"}],'
        '"links":[{"source":"a","target":"b"}]}',
        encoding="utf-8",
    )
    result = verify_graph(graph)
    assert result["valid"] is True
    assert result["blocked_sources"] == 0

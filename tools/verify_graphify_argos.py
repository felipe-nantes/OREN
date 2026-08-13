"""Independent safety and integrity checks for the ARGOS Graphify output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
from typing import Any


BLOCKED_ROOTS = {
    ".codex",
    ".codex-backups",
    ".codex-temp",
    ".codex-tmp",
    ".local",
    ".medgemma",
    "artifacts",
    "casos",
    "data",
    "datasets",
    "dicom",
    "dicoms",
    "experiments",
    "rag",
}
BLOCKED_SUFFIXES = (
    ".dcm",
    ".dicom",
    ".nii",
    ".nii.gz",
    ".nrrd",
    ".mha",
    ".mhd",
    ".stl",
    ".vtp",
    ".vtk",
    ".glb",
    ".gltf",
    ".safetensors",
)


def normalize_source_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


def is_blocked_source(value: str) -> bool:
    normalized = normalize_source_path(value)
    parts = PurePosixPath(normalized).parts
    if parts and parts[0].lower() in BLOCKED_ROOTS:
        return True
    lowered = normalized.lower()
    return lowered.endswith(BLOCKED_SUFFIXES)


def verify_graph(graph_path: Path) -> dict[str, Any]:
    payload = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes = payload.get("nodes")
    links = payload.get("links")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("graph.json has no nodes")
    if not isinstance(links, list) or not links:
        raise ValueError("graph.json has no links")

    blocked = sorted(
        {
            source
            for node in nodes
            if isinstance(node, dict)
            for source in [node.get("source_file")]
            if isinstance(source, str) and is_blocked_source(source)
        }
    )
    if blocked:
        sample = ", ".join(blocked[:10])
        raise ValueError(f"blocked medical/generated sources entered graph: {sample}")

    return {
        "valid": True,
        "nodes": len(nodes),
        "links": len(links),
        "blocked_sources": 0,
        "code_only_boundary": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--graph",
        type=Path,
        default=Path("graphify-out/graph.json"),
    )
    args = parser.parse_args()
    print(json.dumps(verify_graph(args.graph), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

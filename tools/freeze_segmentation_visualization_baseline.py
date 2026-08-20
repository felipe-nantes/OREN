"""Freeze or independently verify the current segmentation/viewer baseline.

APOSENTADO em 2026-08-20 (HUMAN_DECISOES item 16): o baseline v1 e registro
historico congelado; nenhum verificador programatico o consome e nenhum
freeze v2 foi autorizado. Mantido apenas como ferramenta manual de referencia.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

SCHEMA = "argos-segmentation-visualization-baseline-v1"
# webapp/seg_worker.py removido em 2026-08-20 (HUMAN_DECISOES item 15):
# launcher legado inalcancavel; o worker ativo e dtwin/seg_worker.py.
TRACKED_FILES = (
    "profiles/figado.yaml",
    "webapp/server.py",
    "dtwin/stages.py",
    "viewer/app.js",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_snapshot(repo: Path) -> dict[str, Any]:
    files: dict[str, str] = {}
    for relative in TRACKED_FILES:
        path = repo / relative
        if not path.is_file():
            raise RuntimeError(f"Arquivo do baseline ausente: {relative}")
        files[relative] = _sha256(path)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {
        "schema": SCHEMA,
        "git_commit": commit,
        "files": files,
        "contract": {
            "classification_mask": "mask_organ.nii.gz",
            "classification_mask_immutable": True,
            "organ_backend": "totalsegmentator_mri",
            "organ_task": "total_mr",
            "visualization_mask_preference": [
                "mask_organ_union.nii.gz",
                "mask_organ.nii.gz",
            ],
            "union_phases": ["arterial", "venous", "delayed"],
            "research_only": True,
            "human_review_required": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    snapshot = build_snapshot(repo)
    output = args.out.resolve()
    if args.verify:
        persisted = json.loads(output.read_text(encoding="utf-8"))
        if persisted != snapshot:
            raise SystemExit("Baseline divergiu do snapshot congelado.")
        print(json.dumps({"status": "verified", "schema": SCHEMA}, sort_keys=True))
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "frozen", "out": str(output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

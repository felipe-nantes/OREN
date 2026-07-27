import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote

from dtwin.benchmark.openswisshcc_multisequence_batch import (
    COHORT_SCHEMA,
    build_multisequence_gallery,
)
from dtwin.benchmark.openswisshcc_multisequence_panel import SCHEMA


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_gallery_src_resolves_from_final_gallery_directory(tmp_path):
    root = tmp_path / "cohort"
    case = root / "anon-a"
    case.mkdir(parents=True)
    image = case / "panel.png"
    image.write_bytes(b"png")
    panel = {
        "panel_number": 1,
        "image": image.name,
        "sha256": _sha(image),
        "bytes": image.stat().st_size,
        "trace_plane_index": 3,
    }
    manifest = {
        "schema": SCHEMA,
        "ground_truth_read": False,
        "lesion_mask_used": False,
        "panel_count": 1,
        "panels": [panel],
    }
    mpath = case / "multisequence_manifest.json"
    mpath.write_text(json.dumps(manifest), encoding="utf-8")
    cases = [{"case_id": "anon-a", "manifest_sha256": _sha(mpath)}]
    cohort = {
        "schema": COHORT_SCHEMA,
        "case_count": 1,
        "cases": cases,
        "cohort_signature": "signed",
        "ground_truth_read": False,
        "inference_executed": False,
    }
    (root / "cohort_manifest.json").write_text(json.dumps(cohort), encoding="utf-8")
    gallery = tmp_path / "gallery"
    build_multisequence_gallery(panel_root=root, output_dir=gallery, expected_case_count=1)
    page = (gallery / "index.html").read_text(encoding="utf-8")
    src = re.search(r'<img loading="lazy" src="([^"]+)"', page).group(1)
    assert (gallery / unquote(src)).resolve() == image.resolve()

"""Submit a real multiphase DICOM exam through the Docker HTTP boundary."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import pydicom
import requests


PHASE_TERMS = {
    "precontrast": ("vibe_pre", "vibe pre"),
    "arterial": ("arterial",),
    "venous": ("portal", "venous"),
    "delayed": ("early delayed", "5 min delayed", "delayed"),
}


def _series(root: Path) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            ds = pydicom.dcmread(
                path,
                stop_before_pixels=True,
                specific_tags=[
                    "SeriesInstanceUID",
                    "SeriesDescription",
                    "ProtocolName",
                    "Modality",
                    "ImageType",
                ],
            )
        except Exception:  # noqa: BLE001
            continue
        if str(getattr(ds, "Modality", "")).upper() != "MR":
            continue
        uid = str(getattr(ds, "SeriesInstanceUID", "")) or str(path.parent)
        item = grouped.setdefault(
            uid,
            {
                "description": str(getattr(ds, "SeriesDescription", "")),
                "protocol": str(getattr(ds, "ProtocolName", "")),
                "image_type": [str(value) for value in getattr(ds, "ImageType", [])],
                "files": [],
            },
        )
        item["files"].append(path)
    return list(grouped.values())


def _select_phases(root: Path) -> dict[str, list[Path]]:
    selected: dict[str, list[Path]] = {}
    for phase, terms in PHASE_TERMS.items():
        candidates = []
        for item in _series(root):
            text = f"{item['description']} {item['protocol']}".lower()
            image_type = {part.upper() for part in item["image_type"]}
            if not any(term in text for term in terms):
                continue
            # Prefer original axial acquisitions over derived coronal MPRs.
            score = len(item["files"])
            if "ORIGINAL" in image_type:
                score += 10_000
            if "MPR" not in image_type:
                score += 1_000
            candidates.append((score, item))
        if not candidates:
            raise RuntimeError(f"No MR series found for phase {phase}")
        chosen = max(candidates, key=lambda pair: pair[0])[1]
        selected[phase] = sorted(chosen["files"])
    return selected


def run(
    base_url: str,
    dicom_root: Path,
    timeout_seconds: int,
    *,
    enhanced_3d: bool = False,
) -> dict[str, Any]:
    phases = _select_phases(dicom_root)
    handles = []
    files = []
    relpaths = []
    try:
        for phase, paths in phases.items():
            for index, path in enumerate(paths, start=1):
                handle = path.open("rb")
                handles.append(handle)
                files.append(
                    (
                        "files",
                        (f"{phase}_{index:04d}.dcm", handle, "application/dicom"),
                    )
                )
                relpaths.append(f"{phase}/{path.name}")
        started = time.monotonic()
        response = requests.post(
            f"{base_url.rstrip('/')}/api/analyze",
            files=files,
            data={
                "relpaths": json.dumps(relpaths),
                "enhanced_3d": "1" if enhanced_3d else "0",
            },
            timeout=600,
        )
        response.raise_for_status()
        submitted = response.json()
    finally:
        for handle in handles:
            handle.close()

    job_id = submitted["job_id"]
    deadline = time.monotonic() + timeout_seconds
    history = []
    while time.monotonic() < deadline:
        status_response = requests.get(
            f"{base_url.rstrip('/')}/api/status/{job_id}", timeout=30
        )
        status_response.raise_for_status()
        status = status_response.json()
        point = {
            "state": status.get("state"),
            "step": status.get("step"),
            "progress": status.get("progress"),
        }
        if not history or history[-1] != point:
            history.append(point)
            print(json.dumps(point, ensure_ascii=False), flush=True)
        if status.get("state") == "done":
            result = status.get("result") or {}
            if result.get("status") != "concluido":
                raise RuntimeError(
                    "Docker E2E job did not conclude: "
                    + json.dumps(result, ensure_ascii=False)
                )
            if not result.get("viewer_ready") or not result.get("viewer_url"):
                raise RuntimeError("Docker E2E job concluded without 3D viewer")
            viewer = requests.get(
                f"{base_url.rstrip('/')}{result['viewer_url']}", timeout=60
            )
            viewer.raise_for_status()
            manifest = requests.get(
                f"{base_url.rstrip('/')}/api/jobs/{job_id}/model/viewer_manifest.json",
                timeout=60,
            )
            manifest.raise_for_status()
            manifest_payload = manifest.json()
            if not manifest_payload.get("meshes"):
                raise RuntimeError("Viewer manifest contains no meshes")
            elapsed = time.monotonic() - started
            return {
                "schema": "argos-docker-e2e-smoke-v1",
                "passed": True,
                "job_id": job_id,
                "elapsed_seconds": round(elapsed, 3),
                "submitted_files": len(relpaths),
                "phase_file_counts": {
                    phase: len(paths) for phase, paths in phases.items()
                },
                "analysis_scenario": status.get("analysis_scenario"),
                "result_status": result.get("status"),
                "viewer_ready": True,
                "mesh_count": len(manifest_payload["meshes"]),
                "enhanced_3d": enhanced_3d,
                "durations_seconds": result.get("durations_seconds"),
                "history": history,
            }
        time.sleep(3)
    raise TimeoutError(f"Docker E2E job {job_id} exceeded {timeout_seconds}s")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--dicom-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--enhanced-3d", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/docker-validation/e2e-smoke.json"),
    )
    args = parser.parse_args()
    result = run(
        args.base_url,
        args.dicom_root,
        args.timeout_seconds,
        enhanced_3d=args.enhanced_3d,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

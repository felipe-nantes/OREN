"""Independent, fail-closed validation of a completed Docker webapp job."""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _get_json(session: requests.Session, url: str, *, verify: bool = True) -> dict[str, Any]:
    response = session.get(url, timeout=60, verify=verify)
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object from {url}")
    return value


def _asset_specs(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    for mesh in manifest.get("meshes") or []:
        assets.append(
            {
                "filename": mesh["stl"],
                "sha256": (mesh.get("metrics") or {}).get("mesh_sha256"),
                "kind": "mesh",
            }
        )
        xr_asset = mesh.get("xr_asset")
        if isinstance(xr_asset, dict):
            assets.append(
                {
                    "filename": xr_asset["stl"],
                    "sha256": xr_asset.get("sha256"),
                    "kind": "xr_mesh",
                }
            )
    views = (manifest.get("reference_images") or {}).get("views") or {}
    for view in views.values():
        for frame in view.get("frames") or []:
            assets.append(
                {
                    "filename": frame["file"],
                    "sha256": frame.get("sha256"),
                    "kind": "reference_image",
                }
            )
    volumetry = manifest.get("volumetry") or {}
    volumetry_artifacts = volumetry.get("artifacts") or {}
    if volumetry_artifacts.get("json"):
        assets.append(
            {
                "filename": volumetry_artifacts["json"],
                "sha256": None,
                "kind": "volumetry_json",
            }
        )
    if volumetry_artifacts.get("csv"):
        assets.append(
            {
                "filename": volumetry_artifacts["csv"],
                "sha256": volumetry_artifacts.get("csv_sha256"),
                "kind": "volumetry_csv",
            }
        )
    return assets


def verify_job(
    *,
    job_id: str,
    http_base: str,
    https_base: str,
    verify_https: bool,
) -> dict[str, Any]:
    session = requests.Session()
    http_base = http_base.rstrip("/")
    https_base = https_base.rstrip("/")
    checks: dict[str, Any] = {}

    status = _get_json(session, f"{http_base}/api/status/{job_id}")
    result = status.get("result") or {}
    if status.get("state") != "done" or result.get("status") != "concluido":
        raise RuntimeError("Job is not durably completed")
    if not result.get("viewer_ready"):
        raise RuntimeError("Completed job does not expose a ready viewer")
    checks["completed_job"] = True

    viewer_response = session.get(f"{http_base}{result['viewer_url']}", timeout=60)
    viewer_response.raise_for_status()
    if "OREN" not in viewer_response.text:
        raise RuntimeError("Viewer shell does not contain the OREN identity")
    checks["viewer_shell"] = True

    manifest = _get_json(
        session, f"{http_base}/api/jobs/{job_id}/model/viewer_manifest.json"
    )
    meshes = manifest.get("meshes") or []
    if manifest.get("schema") != "argos-viewer-manifest-v2" or not meshes:
        raise RuntimeError("Viewer manifest v2 or meshes are missing")
    roles = {item.get("role") for item in meshes}
    if "orgao" not in roles:
        raise RuntimeError("Whole-liver mesh is absent")
    organ = next(item for item in meshes if item.get("role") == "orgao")
    organ_metrics = organ.get("metrics") or {}
    if organ_metrics.get("reconstruction_quality_gate_passed") is not True:
        raise RuntimeError("Whole-liver reconstruction quality gate failed")
    checks["organ_reconstruction_gate"] = True

    asset_results = []
    for asset in _asset_specs(manifest):
        filename = asset["filename"]
        response = session.get(
            f"{http_base}/api/jobs/{job_id}/model/{filename}", timeout=120
        )
        response.raise_for_status()
        actual_hash = _sha256(response.content)
        if asset.get("sha256") and actual_hash != asset["sha256"]:
            raise RuntimeError(f"Hash mismatch for {filename}")
        asset_results.append(
            {
                "filename": filename,
                "kind": asset["kind"],
                "bytes": len(response.content),
                "sha256": actual_hash,
            }
        )
    checks["authorized_assets"] = len(asset_results)

    volumetry = manifest.get("volumetry") or {}
    structures = volumetry.get("structures") or []
    whole_liver = next((item for item in structures if item.get("role") == "orgao"), None)
    if not whole_liver or float(whole_liver.get("volume_ml") or 0) <= 0:
        raise RuntimeError("Authoritative whole-liver volumetry is absent")
    if (whole_liver.get("technical_quality") or {}).get("usable") is not True:
        raise RuntimeError("Whole-liver volumetry is not technically usable")
    checks["whole_liver_volume_ml"] = whole_liver["volume_ml"]
    checks["couinaud_partition_gate"] = (volumetry.get("couinaud_partition") or {}).get(
        "gate_passed"
    )

    catalog = _get_json(session, f"{http_base}/api/jobs/{job_id}/rgb-panels")
    if catalog.get("count", 0) < 1:
        raise RuntimeError("No RGB screening panels are exposed")
    for panel in catalog["panels"]:
        response = session.get(f"{http_base}{panel['url']}", timeout=60)
        response.raise_for_status()
        if _sha256(response.content) != panel["sha256"]:
            raise RuntimeError(f"RGB panel hash mismatch: {panel['filename']}")
    checks["rgb_panels"] = catalog["count"]

    candidate = result.get("candidate_localization") or {}
    if candidate:
        if candidate.get("ground_truth_lesion_mask_used") is not False:
            raise RuntimeError("Candidate localizer did not prove ground-truth isolation")
        if candidate.get("used_by_screening_inference") is not False:
            raise RuntimeError("Post-inference candidate leaked into screening inference")
        checks["candidate_ground_truth_isolation"] = True

    patient = session.post(
        f"{https_base}/api/jobs/{job_id}/xr-session",
        json={"role": "patient", "ttl_minutes": 15},
        timeout=60,
        verify=verify_https,
    )
    patient.raise_for_status()
    patient_payload = patient.json()
    parsed = urlparse(patient_payload["viewer_url"])
    if parsed.scheme != "https" or "xr_token=" not in parsed.fragment:
        raise RuntimeError("XR session is not an HTTPS fragment-token URL")
    patient_token = parsed.fragment.split("xr_token=", 1)[1]
    session_read = _get_json(
        session,
        f"{https_base}/api/jobs/{job_id}/xr-session/{patient_token}",
        verify=verify_https,
    )
    if session_read.get("role") != "patient":
        raise RuntimeError("XR patient session role changed")
    forbidden = session.post(
        f"{https_base}/api/jobs/{job_id}/xr-session/{patient_token}/approval",
        json={"status": "revision_requested"},
        timeout=60,
        verify=verify_https,
    )
    if forbidden.status_code != 403:
        raise RuntimeError("Patient XR session could register a clinical review")
    clinician = session.post(
        f"{https_base}/api/jobs/{job_id}/xr-session",
        json={"role": "clinician", "ttl_minutes": 15},
        timeout=60,
        verify=verify_https,
    )
    clinician.raise_for_status()
    if "xr_token=" not in urlparse(clinician.json()["viewer_url"]).fragment:
        raise RuntimeError("Clinician XR session token is absent")
    checks["xr_https_role_separation"] = True

    traversal = session.get(
        f"{http_base}/api/jobs/{job_id}/model/..%2Fviewer_manifest.json", timeout=30
    )
    if traversal.status_code not in {404, 422}:
        raise RuntimeError("Model asset path traversal was not rejected")
    checks["path_traversal_rejected"] = True

    return {
        "schema": "argos-docker-job-verification-v1",
        "passed": True,
        "job_id": job_id,
        "analysis_scenario": status.get("analysis_scenario"),
        "enhanced_3d": status.get("enhanced_3d"),
        "prediction": result.get("prediction"),
        "durations_seconds": result.get("durations_seconds"),
        "checks": checks,
        "asset_count": len(asset_results),
        "assets": asset_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--http-base", default="http://127.0.0.1:8080")
    parser.add_argument("--https-base", default="https://127.0.0.1:8443")
    parser.add_argument("--verify-https", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/docker-validation/job-verification.json"),
    )
    args = parser.parse_args()
    if not args.verify_https:
        requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
        ssl._create_default_https_context = ssl._create_unverified_context
    result = verify_job(
        job_id=args.job_id,
        http_base=args.http_base,
        https_base=args.https_base,
        verify_https=args.verify_https,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

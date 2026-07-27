"""High-resolution multisequence ROI panels from model-derived lesion candidates."""
from __future__ import annotations

import hashlib
import html
import json
import math
import shutil
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk
from PIL import Image, ImageDraw
from scipy import ndimage

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_lesion_localizer import CASE_SCHEMA as LOCALIZER_CASE_SCHEMA, RUN_SCHEMA as LOCALIZER_RUN_SCHEMA
from dtwin.core import PipelineError
from dtwin.medgemma_panel import _render_tile
from dtwin.medgemma_screening import _write_json_atomic

CASE_SCHEMA = "argos-openswisshcc-localizer-roi-case-v1"
COHORT_SCHEMA = "argos-openswisshcc-localizer-roi-cohort-v1"


def _canonical(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _load(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON ROI v10 invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("JSON ROI v10 deve ser objeto.")
    return value


def _rows(path):
    try:
        return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Manifesto de inputs ROI v10 invalido.") from exc


def _safe(root, item):
    path = (root / str(item["relative_path"])).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size != int(item["bytes"]) or _sha256(path) != item["sha256"]:
        raise PipelineError("Input ROI v10 mudou ou saiu da raiz.")
    return path


def _input_index(manifest_path, input_root):
    root = Path(input_root).resolve()
    indexed = {}
    for row in _rows(manifest_path):
        case_id = str(row.get("case_id", ""))
        files = row.get("files", [])
        if row.get("schema") != "argos-public-liver-mri-input-v1" or not case_id.startswith("anon-") or case_id in indexed or row.get("research_only") is not True or row.get("clinical_use_allowed") is not False:
            raise PipelineError("Registro ROI v10 inseguro.")
        if any("lesion" in (str(x.get("role", "")) + str(x.get("relative_path", ""))).lower() for x in files):
            raise PipelineError("Arquivo de lesao do dataset proibido no ROI v10.")
        by = {str(x["role"]): x for x in files}
        traces = sorted((r for r in by if r.startswith("dwi_trace_run_")), key=lambda r: int(r.rsplit("_", 1)[-1]))
        t2 = "t2_blade" if "t2_blade" in by else "t2_haste" if "t2_haste" in by else None
        roles = ["t1_venous", t2, traces[-1] if traces else None, "dwi_adc", "liver_mask_venous"]
        if None in roles or any(r not in by for r in roles):
            raise PipelineError("Modalidade obrigatoria ausente no ROI v10.")
        indexed[case_id] = {
            "roles": roles,
            "paths": {r: _safe(root, by[r]) for r in roles},
            "hashes": {r: by[r]["sha256"] for r in roles},
        }
    return indexed


def _window(array, bbox, z):
    y0, y1, x0, x1 = bbox
    values = np.asarray(array[z, y0:y1, x0:x1], dtype=np.float32).ravel()
    values = values[np.isfinite(values)]
    nonzero = values[values != 0]
    if len(nonzero) >= 50:
        values = nonzero
    if len(values) < 10:
        raise PipelineError("ROI v10 sem intensidades suficientes.")
    lo, hi = np.percentile(values, [1, 99]).astype(float)
    if hi - lo < 1e-6:
        raise PipelineError("ROI v10 sem contraste.")
    return lo, hi


def _bbox(index, image, roi_mm):
    x, y, _ = index
    sx, sy, _ = image.GetSize()
    spx, spy, _ = image.GetSpacing()
    hx = max(16, int(math.ceil(roi_mm / (2 * spx))))
    hy = max(16, int(math.ceil(roi_mm / (2 * spy))))
    cx = int(round(x))
    cy = int(round(y))
    return max(0, cy - hy), min(sy, cy + hy + 1), max(0, cx - hx), min(sx, cx + hx + 1)


def _available(index, image):
    return all(-0.5 <= float(v) <= float(s) - 0.5 for v, s in zip(index, image.GetSize(), strict=True))


def _render_case(*, case_id, source, localizer_dir, destination, max_components, tile_size, roi_mm, max_image_pixels, max_input_bytes):
    lm = _load(localizer_dir / "localizer_manifest.json")
    candidate = localizer_dir / "liver_lesion_candidates_in_liver.nii.gz"
    if lm.get("schema") != LOCALIZER_CASE_SCHEMA or lm.get("case_id") != case_id or lm.get("status") != "candidate_scores_only_no_decision" or lm.get("ground_truth_read") is not False or lm.get("ground_truth_lesion_mask_used") is not False or lm.get("final_decision") is not None or _sha256(candidate) != lm.get("filtered_candidate_mask_sha256"):
        raise PipelineError("Caso localizador invalido para ROI v10.")
    roles = source["roles"][:-1]
    paths = source["paths"]
    images = {r: sitk.ReadImage(str(paths[r])) for r in source["roles"]}
    arrays = {r: sitk.GetArrayFromImage(images[r]) for r in roles}
    candidate_img = sitk.ReadImage(str(candidate))
    candidate_arr = sitk.GetArrayFromImage(candidate_img) > 0
    if candidate_img.GetSize() != images["t1_venous"].GetSize() or candidate_img.GetOrigin() != images["t1_venous"].GetOrigin() or candidate_img.GetSpacing() != images["t1_venous"].GetSpacing() or candidate_img.GetDirection() != images["t1_venous"].GetDirection():
        raise PipelineError("Geometria candidata ROI v10 divergiu do T1.")
    labels, count = ndimage.label(candidate_arr, structure=ndimage.generate_binary_structure(3, 3))
    components = []
    for cid in range(1, count + 1):
        idx = np.argwhere(labels == cid)
        components.append((int(idx.shape[0]), cid, idx.mean(axis=0)[::-1]))
    components.sort(reverse=True, key=lambda x: (x[0], -x[1]))
    components = components[:max_components]
    if not components:
        liver = sitk.GetArrayFromImage(images["liver_mask_venous"]) > 0
        idx = np.argwhere(liver)
        if not len(idx):
            raise PipelineError("Mascara hepatica vazia no fallback ROI v10.")
        components = [(0, 0, idx.mean(axis=0)[::-1])]
    destination.mkdir()
    panels = []
    render_roles = ["t1_venous", roles[1], roles[2], "dwi_adc"]
    total = len(components)
    for number, (voxels, cid, center_xyz) in enumerate(components, 1):
        physical = images["t1_venous"].TransformContinuousIndexToPhysicalPoint(tuple(float(v) for v in center_xyz))
        canvas = Image.new("RGB", (tile_size * 2, tile_size * 2), (10, 14, 20))
        tiles = []
        for tile_number, role in enumerate(render_roles, 1):
            index = images[role].TransformPhysicalPointToContinuousIndex(physical)
            available = _available(index, images[role])
            if available:
                _, _, z = [int(round(v)) for v in index]
                bbox = _bbox(index, images[role], roi_mm)
                lo, hi = _window(arrays[role], bbox, z)
                component_mask = (labels[z] == cid) if role == "t1_venous" and cid else np.zeros_like(arrays[role][z], dtype=bool)
                if cid:
                    label = "T1 VENOSO | CONTORNO AMARELO = CANDIDATO DO LOCALIZADOR, NAO GT" if role == "t1_venous" else f"{role.upper()} | MESMO CENTRO FISICO"
                else:
                    label = f"{role.upper()} | SEM CANDIDATO - FALLBACK NO CENTRO HEPATICO"
                tile = _render_tile(arrays[role][z], component_mask, label, tile_size, lo, hi, images[role].GetSpacing()[1], images[role].GetSpacing()[0], 2, (255, 205, 40), crop_bbox=bbox, show_contour=bool(cid and role == "t1_venous"))
            else:
                index = None
                bbox = None
                lo = hi = None
                tile = Image.new("RGB", (tile_size, tile_size), (10, 14, 20))
                ImageDraw.Draw(tile).text((16, 16), f"{role.upper()} | FORA DO FOV", fill=(255, 190, 80))
            canvas.paste(tile, (((tile_number - 1) % 2) * tile_size, ((tile_number - 1) // 2) * tile_size))
            tiles.append({"tile_number": tile_number, "role": role, "available_in_fov": available, "index_xyz": None if index is None else [float(v) for v in index], "crop_bbox_yxyx": None if bbox is None else list(bbox), "window": None if lo is None else [lo, hi], "candidate_contour_shown": bool(available and cid and role == "t1_venous")})
        filename = f"medgemma_localizer_roi_{number:03d}_of_{total:03d}.png"
        path = destination / filename
        if canvas.width * canvas.height > max_image_pixels:
            raise PipelineError("Painel ROI v10 excede pixels.")
        canvas.save(path, format="PNG", optimize=True)
        if path.stat().st_size > max_input_bytes:
            raise PipelineError("Painel ROI v10 excede bytes.")
        panels.append({"panel_number": number, "panel_total": total, "image": filename, "bytes": path.stat().st_size, "sha256": _sha256(path), "component_rank": number if cid else None, "component_voxels": voxels, "physical_center_lps_xyz": [float(v) for v in physical], "fallback_no_candidate": cid == 0, "fallback_reason": "no_model_derived_candidate" if cid == 0 else None, "tiles": tiles})
    manifest = {"schema": CASE_SCHEMA, "case_id": case_id, "representation": "model_localizer_high_resolution_multisequence_roi_2x2", "panel_count": len(panels), "panels": panels, "source_sha256": source["hashes"], "localizer_manifest_sha256": _sha256(localizer_dir / "localizer_manifest.json"), "candidate_mask_is_model_derived": True, "ground_truth_lesion_mask_used": False, "ground_truth_read": False, "inference_executed": False, "research_only": True, "clinical_use_allowed": False, "requires_human_review": True}
    _write_json_atomic(destination / "roi_manifest.json", manifest)
    return manifest


def build_roi_pilot(*, localizer_run: Path, input_manifest: Path, input_root: Path, output_root: Path, max_components: int = 3, tile_size: int = 448, roi_mm: float = 80, max_image_pixels: int = 4_000_000, max_input_bytes: int = 8_000_000):
    if not 1 <= max_components <= 5 or tile_size < 256 or not 40 <= roi_mm <= 140:
        raise PipelineError("Parametros ROI v10 invalidos.")
    localizer_run = Path(localizer_run).resolve()
    summary = _load(localizer_run / "summary.json")
    if summary.get("schema") != LOCALIZER_RUN_SCHEMA or summary.get("status") != "complete_scores_only_no_decision" or summary.get("ground_truth_read") is not False or summary.get("ground_truth_lesion_mask_used") is not False or summary.get("final_decision") is not None:
        raise PipelineError("Run localizador v10 invalido para ROI.")
    sources = _input_index(input_manifest, input_root)
    out = Path(output_root).resolve()
    if out.exists():
        raise PipelineError("Destino ROI v10 ja existe.")
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = out.parent / f"._v10roi_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    records = []
    try:
        for case_id in summary["case_ids"]:
            if case_id not in sources:
                raise PipelineError("Caso ROI v10 ausente no manifesto.")
            manifest = _render_case(case_id=case_id, source=sources[case_id], localizer_dir=localizer_run / case_id, destination=staging / case_id, max_components=max_components, tile_size=tile_size, roi_mm=roi_mm, max_image_pixels=max_image_pixels, max_input_bytes=max_input_bytes)
            records.append({"case_id": case_id, "panel_count": manifest["panel_count"], "manifest_sha256": _sha256(staging / case_id / "roi_manifest.json"), "panels": [{"image": p["image"], "sha256": p["sha256"]} for p in manifest["panels"]]})
        body = []
        for n, record in enumerate(records, 1):
            cards = ''.join(f'<figure><img loading="lazy" src="{html.escape(record["case_id"] + "/" + p["image"])}"><figcaption>{html.escape(p["image"])}</figcaption></figure>' for p in record["panels"])
            body.append(f'<section><h2>{n}. {html.escape(record["case_id"])}</h2><div class="grid">{cards}</div></section>')
        page = '<!doctype html><html><head><meta charset="utf-8"><title>ARGOS v10 ROI review</title><style>body{background:#091019;color:#e8edf2;font:15px system-ui;margin:24px}section{border-top:1px solid #334155;padding:18px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:14px}figure{margin:0;background:#111827;padding:10px}img{width:100%;height:auto}figcaption{margin-top:6px;color:#aeb8c5}</style></head><body><h1>ARGOS v10 - revisao tecnica de ROIs do localizador</h1><p>Contorno amarelo: candidato derivado do modelo, nunca ground truth. Painel sem contorno e identificado como fallback: nenhum candidato foi produzido; avaliar apenas enquadramento e qualidade. Avaliar tambem correspondencia anatomica, contraste e ausencia de PHI.</p>' + ''.join(body) + '</body></html>'
        (staging / "index.html").write_text(page, encoding="utf-8")
        cohort = {"schema": COHORT_SCHEMA, "case_count": len(records), "panel_count": sum(r["panel_count"] for r in records), "cases": records, "source_localizer_summary_sha256": _sha256(localizer_run / "summary.json"), "gallery_signature": _canonical(records), "ground_truth_lesion_mask_used": False, "ground_truth_read": False, "inference_executed": False, "research_only": True, "clinical_use_allowed": False, "requires_human_review": True}
        _write_json_atomic(staging / "cohort_manifest.json", cohort)
        _publish_directory(staging, out)
        return cohort
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

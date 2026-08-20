"""Dynamic-contrast ROI panels paired with v10 model-derived candidates."""
from __future__ import annotations

import html
import shutil
import uuid
from pathlib import Path

import numpy as np
import SimpleITK as sitk
from PIL import Image, ImageDraw
from scipy import ndimage

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_lesion_localizer import (
    CASE_SCHEMA as LOCALIZER_CASE_SCHEMA,
)
from dtwin.benchmark.openswisshcc_lesion_localizer import (
    RUN_SCHEMA as LOCALIZER_RUN_SCHEMA,
)
from dtwin.benchmark.openswisshcc_localizer_roi import (
    _available,
    _bbox,
    _canonical,
    _load,
    _rows,
    _safe,
    _window,
)
from dtwin.core import PipelineError
from dtwin.medgemma_panel import _render_tile
from dtwin.medgemma_screening import _write_json_atomic

CASE_SCHEMA = "argos-openswisshcc-localizer-enhancement-roi-case-v1"
COHORT_SCHEMA = "argos-openswisshcc-localizer-enhancement-roi-cohort-v1"
ROLES = ["t1_native", "t1_arterial_registered", "t1_venous", "t1_delayed_registered"]


def _inputs(manifest_path, input_root):
    root = Path(input_root).resolve()
    result = {}
    required = ("t1_native", "t1_venous", "liver_mask_venous")
    for row in _rows(manifest_path):
        case_id = str(row.get("case_id", ""))
        files = row.get("files", [])
        if row.get("schema") != "argos-public-liver-mri-input-v1" or not case_id.startswith("anon-") or case_id in result or row.get("research_only") is not True or row.get("clinical_use_allowed") is not False:
            raise PipelineError("Input de realce ROI v10 inseguro.")
        if any("lesion" in (str(x.get("role", "")) + str(x.get("relative_path", ""))).lower() for x in files):
            raise PipelineError("Arquivo de lesao do dataset proibido no realce ROI v10.")
        by = {str(x["role"]): x for x in files}
        if any(role not in by for role in required):
            raise PipelineError("T1 nativo/venoso ou mascara hepatica ausente no realce ROI v10.")
        result[case_id] = {"paths": {r: _safe(root, by[r]) for r in required}, "hashes": {r: by[r]["sha256"] for r in required}}
    return result


def _registered(case_id, registration_root):
    root = (Path(registration_root).resolve() / case_id).resolve()
    manifest = _load(root / "alignment_manifest.json")
    if manifest.get("schema") != "argos-public-liver-mri-alignment-v1" or manifest.get("case_id") != case_id or manifest.get("reference_phase") != "venous" or manifest.get("research_only") is not True or manifest.get("clinical_use_allowed") is not False:
        raise PipelineError("Registro dinamico ROI v10 invalido.")
    by = {x.get("phase"): x for x in manifest.get("outputs", [])}
    result = {}
    for phase, role in (("art", "t1_arterial_registered"), ("del", "t1_delayed_registered")):
        item = by.get(phase)
        if not item:
            raise PipelineError("Fase registrada ausente no realce ROI v10.")
        path = (root / str(item["filename"])).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size != int(item["bytes"]) or _sha256(path) != item["sha256"]:
            raise PipelineError("Hash/bytes da fase registrada divergiram.")
        result[role] = {"path": path, "sha256": item["sha256"], "source_role": manifest.get("arterial_input_role") if phase == "art" else "t1_delayed"}
    return result


def _components(candidate_img, max_components):
    arr = sitk.GetArrayFromImage(candidate_img) > 0
    labels, count = ndimage.label(arr, structure=ndimage.generate_binary_structure(3, 3))
    items = []
    for cid in range(1, count + 1):
        idx = np.argwhere(labels == cid)
        items.append((int(idx.shape[0]), cid, idx.mean(axis=0)[::-1]))
    items.sort(reverse=True, key=lambda x: (x[0], -x[1]))
    return labels, items[:max_components]


def _placeholder(role, reason, tile_size):
    tile = Image.new("RGB", (tile_size, tile_size), (10, 14, 20))
    description = "FORA DO FOV" if reason == "fora_do_fov" else "SEM CONTRASTE UTIL NO ROI"
    draw = ImageDraw.Draw(tile)
    draw.text((16, 16), f"{role.upper()} | INDISPONIVEL", fill=(255, 190, 80))
    draw.text((16, 40), description, fill=(220, 226, 232))
    return tile


def _liver_fallback_center(source, reference):
    liver_img = sitk.ReadImage(str(source["paths"]["liver_mask_venous"]))
    if liver_img.GetSize() != reference.GetSize() or liver_img.GetOrigin() != reference.GetOrigin() or liver_img.GetSpacing() != reference.GetSpacing() or liver_img.GetDirection() != reference.GetDirection():
        raise PipelineError("Geometria da mascara hepatica divergiu do T1 venoso no fallback dinamico.")
    indices = np.argwhere(sitk.GetArrayFromImage(liver_img) > 0)
    if not len(indices):
        raise PipelineError("Mascara hepatica vazia no fallback dinamico v10.")
    return indices.mean(axis=0)[::-1]


def _render_case(case_id, source, registered, localizer_dir, destination, max_components, tile_size, roi_mm, max_image_pixels, max_input_bytes):
    lm = _load(localizer_dir / "localizer_manifest.json")
    candidate = localizer_dir / "liver_lesion_candidates_in_liver.nii.gz"
    if lm.get("schema") != LOCALIZER_CASE_SCHEMA or lm.get("case_id") != case_id or lm.get("status") != "candidate_scores_only_no_decision" or lm.get("ground_truth_read") is not False or lm.get("ground_truth_lesion_mask_used") is not False or lm.get("final_decision") is not None or _sha256(candidate) != lm.get("filtered_candidate_mask_sha256"):
        raise PipelineError("Caso localizador invalido no realce ROI v10.")
    paths = {**source["paths"], **{r: x["path"] for r, x in registered.items()}}
    images = {r: sitk.ReadImage(str(paths[r])) for r in ROLES}
    arrays = {r: sitk.GetArrayFromImage(images[r]) for r in ROLES}
    candidate_img = sitk.ReadImage(str(candidate))
    ref = images["t1_venous"]
    if candidate_img.GetSize() != ref.GetSize() or candidate_img.GetOrigin() != ref.GetOrigin() or candidate_img.GetSpacing() != ref.GetSpacing() or candidate_img.GetDirection() != ref.GetDirection():
        raise PipelineError("Geometria candidata divergiu do T1 venoso no realce ROI.")
    labels, components = _components(candidate_img, max_components)
    if not components:
        components = [(0, 0, _liver_fallback_center(source, ref))]
    destination.mkdir()
    panels = []
    total = len(components)
    labels_text = {
        "t1_native": "T1 NATIVO | MESMO CENTRO FISICO",
        "t1_arterial_registered": "T1 ARTERIAL REGISTRADO | MESMO CENTRO FISICO",
        "t1_venous": "T1 VENOSO | CONTORNO AMARELO = CANDIDATO DO LOCALIZADOR, NAO GT",
        "t1_delayed_registered": "T1 TARDIO REGISTRADO | MESMO CENTRO FISICO",
    }
    for number, (voxels, cid, center_xyz) in enumerate(components, 1):
        physical = ref.TransformContinuousIndexToPhysicalPoint(tuple(float(v) for v in center_xyz))
        canvas = Image.new("RGB", (tile_size * 2, tile_size * 2), (10, 14, 20))
        tiles = []
        for tile_number, role in enumerate(ROLES, 1):
            raw_index = images[role].TransformPhysicalPointToContinuousIndex(physical)
            geometry_in_fov = _available(raw_index, images[role])
            index = [float(v) for v in raw_index]
            bbox = None
            lo = hi = None
            reason = None
            available = geometry_in_fov
            if geometry_in_fov:
                _, _, z = [int(round(v)) for v in raw_index]
                bbox = _bbox(raw_index, images[role], roi_mm)
                try:
                    lo, hi = _window(arrays[role], bbox, z)
                except PipelineError:
                    available = False
                    reason = "sem_contraste_no_roi"
            else:
                available = False
                reason = "fora_do_fov"
            if available:
                mask = (labels[z] == cid) if role == "t1_venous" and cid else np.zeros_like(arrays[role][z], dtype=bool)
                label = labels_text[role] if cid else f"{role.upper()} | SEM CANDIDATO - FALLBACK NO CENTRO HEPATICO"
                tile = _render_tile(arrays[role][z], mask, label, tile_size, lo, hi, images[role].GetSpacing()[1], images[role].GetSpacing()[0], 2, (255, 205, 40), crop_bbox=bbox, show_contour=bool(role == "t1_venous" and cid))
            else:
                tile = _placeholder(role, reason, tile_size)
            canvas.paste(tile, (((tile_number - 1) % 2) * tile_size, ((tile_number - 1) // 2) * tile_size))
            tiles.append({"tile_number": tile_number, "role": role, "available_in_fov": available, "geometry_in_fov": geometry_in_fov, "unavailable_reason": reason, "index_xyz": index, "crop_bbox_yxyx": None if bbox is None else list(bbox), "window": None if lo is None else [lo, hi], "candidate_contour_shown": bool(available and role == "t1_venous" and cid)})
        usable = sum(1 for tile in tiles if tile["available_in_fov"])
        venous = next(tile for tile in tiles if tile["role"] == "t1_venous")
        if not venous["available_in_fov"] or usable < 2:
            raise PipelineError("Painel de realce ROI sem evidencia minima: T1 venoso valido e duas fases utilizaveis sao obrigatorios.")
        filename = f"medgemma_localizer_enhancement_roi_{number:03d}_of_{total:03d}.png"
        path = destination / filename
        if canvas.width * canvas.height > max_image_pixels:
            raise PipelineError("Painel de realce ROI excede pixels.")
        canvas.save(path, format="PNG", optimize=True)
        if path.stat().st_size > max_input_bytes:
            raise PipelineError("Painel de realce ROI excede bytes.")
        panels.append({"panel_number": number, "panel_total": total, "image": filename, "bytes": path.stat().st_size, "sha256": _sha256(path), "component_rank": number if cid else None, "component_voxels": voxels, "physical_center_lps_xyz": [float(v) for v in physical], "fallback_no_candidate": cid == 0, "fallback_reason": "no_model_derived_candidate" if cid == 0 else None, "usable_phase_count": usable, "tiles": tiles})
    manifest = {"schema": CASE_SCHEMA, "case_id": case_id, "representation": "model_localizer_dynamic_enhancement_roi_2x2", "panel_count": len(panels), "panels": panels, "source_sha256": source["hashes"], "registered_source_sha256": {r: x["sha256"] for r, x in registered.items()}, "registered_source_roles": {r: x["source_role"] for r, x in registered.items()}, "localizer_manifest_sha256": _sha256(localizer_dir / "localizer_manifest.json"), "candidate_mask_is_model_derived": True, "ground_truth_lesion_mask_used": False, "ground_truth_read": False, "inference_executed": False, "research_only": True, "clinical_use_allowed": False, "requires_human_review": True}
    _write_json_atomic(destination / "enhancement_roi_manifest.json", manifest)
    return manifest


def build_enhancement_roi_pilot(*, localizer_run: Path, input_manifest: Path, input_root: Path, registration_root: Path, output_root: Path, max_components: int = 3, tile_size: int = 448, roi_mm: float = 80, max_image_pixels: int = 4_000_000, max_input_bytes: int = 8_000_000):
    if not 1 <= max_components <= 5 or tile_size < 256 or not 40 <= roi_mm <= 140:
        raise PipelineError("Parametros de realce ROI v10 invalidos.")
    localizer_run = Path(localizer_run).resolve()
    summary = _load(localizer_run / "summary.json")
    if summary.get("schema") != LOCALIZER_RUN_SCHEMA or summary.get("status") != "complete_scores_only_no_decision" or summary.get("ground_truth_read") is not False or summary.get("ground_truth_lesion_mask_used") is not False or summary.get("final_decision") is not None:
        raise PipelineError("Run localizador invalido para realce ROI.")
    sources = _inputs(input_manifest, input_root)
    out = Path(output_root).resolve()
    if out.exists():
        raise PipelineError("Destino de realce ROI ja existe.")
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = out.parent / f"._v10enhroi_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    records = []
    try:
        for case_id in summary["case_ids"]:
            if case_id not in sources:
                raise PipelineError("Caso ausente nos inputs de realce ROI.")
            manifest = _render_case(case_id, sources[case_id], _registered(case_id, registration_root), localizer_run / case_id, staging / case_id, max_components, tile_size, roi_mm, max_image_pixels, max_input_bytes)
            records.append({"case_id": case_id, "panel_count": manifest["panel_count"], "manifest_sha256": _sha256(staging / case_id / "enhancement_roi_manifest.json"), "panels": [{"image": p["image"], "sha256": p["sha256"]} for p in manifest["panels"]]})
        cards = []
        for n, record in enumerate(records, 1):
            figures = ''.join(f'<figure><img loading="lazy" src="{html.escape(record["case_id"] + "/" + p["image"])}"><figcaption>{html.escape(p["image"])}</figcaption></figure>' for p in record["panels"])
            cards.append(f'<section><h2>{n}. {html.escape(record["case_id"])}</h2><div class="grid">{figures}</div></section>')
        page = '<!doctype html><html><head><meta charset="utf-8"><title>ARGOS v10 enhancement ROI review</title><style>body{background:#091019;color:#e8edf2;font:15px system-ui;margin:24px}section{border-top:1px solid #334155;padding:18px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:14px}figure{margin:0;background:#111827;padding:10px}img{width:100%}figcaption{color:#aeb8c5;margin-top:6px}</style></head><body><h1>ARGOS v10 - revisao tecnica de ROIs de realce dinamico</h1><p>Nativo, arterial registrado, venoso e tardio registrado no mesmo centro fisico. Contorno amarelo: candidato do modelo, nunca ground truth. Tiles sem contraste util ou fora do FOV aparecem como indisponiveis e nunca sao sintetizados.</p>' + ''.join(cards) + '</body></html>'
        (staging / "index.html").write_text(page, encoding="utf-8")
        cohort = {"schema": COHORT_SCHEMA, "case_count": len(records), "panel_count": sum(r["panel_count"] for r in records), "cases": records, "source_localizer_summary_sha256": _sha256(localizer_run / "summary.json"), "gallery_signature": _canonical(records), "ground_truth_lesion_mask_used": False, "ground_truth_read": False, "inference_executed": False, "research_only": True, "clinical_use_allowed": False, "requires_human_review": True}
        _write_json_atomic(staging / "cohort_manifest.json", cohort)
        _publish_directory(staging, out)
        return cohort
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

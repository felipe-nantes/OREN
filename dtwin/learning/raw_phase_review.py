"""Build a label-blind review gallery for automatically resolved DICOM phases.

The gallery is a technical gate.  It never reads ground-truth labels or lesion
masks and it does not certify that a phase is clinically correct.  It lets a
human reviewer compare the automatically selected arterial, venous and delayed
series at matching physical locations before those series are used in a
benchmark.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from collections.abc import Iterable
from html import escape
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk
from PIL import Image, ImageDraw, ImageFont

from dtwin.core import PipelineError
from dtwin.learning.multiphase_ingest import harmonize_to_reference, read_phase_series
from dtwin.learning.raw_dicom_phase_resolver import (
    ARTERIAL,
    DELAYED,
    VENOUS,
    resolve_raw_dicom_phases,
)

SCHEMA = "argos-raw-phase-review-gallery-v1"
PHASES = (ARTERIAL, VENOUS, DELAYED)
PHASE_LABELS = {
    ARTERIAL: "ARTERIAL",
    VENOUS: "VENOSA / PORTAL",
    DELAYED: "TARDIA",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _window(arrays: Iterable[np.ndarray]) -> tuple[float, float]:
    finite = np.concatenate([array[np.isfinite(array)].ravel() for array in arrays])
    if finite.size == 0:
        return 0.0, 1.0
    low, high = np.percentile(finite, (1.0, 99.5))
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        low, high = float(np.min(finite)), float(np.max(finite))
    if high <= low:
        high = low + 1.0
    return float(low), float(high)


def _uint8(slice_: np.ndarray, low: float, high: float) -> np.ndarray:
    scaled = np.clip((slice_.astype(np.float32) - low) / (high - low), 0.0, 1.0)
    return np.asarray(np.rint(scaled * 255.0), dtype=np.uint8)


def _render_panel(images: dict[str, sitk.Image], output: Path) -> dict[str, Any]:
    reference = images[VENOUS]
    aligned: dict[str, sitk.Image] = {VENOUS: reference}
    coverage: dict[str, float] = {VENOUS: 1.0}
    for phase in (ARTERIAL, DELAYED):
        aligned[phase], coverage[phase] = harmonize_to_reference(images[phase], reference)

    arrays = {phase: sitk.GetArrayFromImage(aligned[phase]).astype(np.float32) for phase in PHASES}
    depth = arrays[VENOUS].shape[0]
    if depth < 3:
        raise PipelineError("Volume multifásico com menos de três cortes axiais.")
    indices = [int(round((depth - 1) * fraction)) for fraction in (0.35, 0.50, 0.65)]
    low, high = _window(arrays.values())

    tile_w, tile_h, title_h, gap = 480, 480, 58, 8
    canvas = Image.new("RGB", (3 * tile_w + 4 * gap, 3 * (tile_h + title_h) + 4 * gap), "#05070b")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for row, phase in enumerate(PHASES):
        for column, index in enumerate(indices):
            source = _uint8(arrays[phase][index], low, high)
            tile = Image.fromarray(source, mode="L").convert("RGB")
            tile.thumbnail((tile_w, tile_h), Image.Resampling.LANCZOS)
            x = gap + column * (tile_w + gap)
            y = gap + row * (tile_h + title_h + gap)
            canvas.paste(tile, (x + (tile_w - tile.width) // 2, y + title_h + (tile_h - tile.height) // 2))
            relative = 100.0 * index / max(depth - 1, 1)
            draw.text((x + 8, y + 7), PHASE_LABELS[phase], fill="#f4d35e", font=font)
            draw.text(
                (x + 8, y + 29),
                f"axial {index} | posição relativa {relative:.1f}%",
                fill="#e6edf7",
                font=font,
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=False, compress_level=9)
    return {
        "reference_phase": VENOUS,
        "relative_levels": [0.35, 0.50, 0.65],
        "axial_indices_on_reference": indices,
        "shared_window": {"percentiles": [1.0, 99.5], "low": low, "high": high},
        "resampled_coverage": {key: round(value, 8) for key, value in coverage.items()},
    }


def _gallery_html(entries: list[dict[str, Any]], exclusions: list[dict[str, Any]], signature: str) -> str:
    data = json.dumps(entries, ensure_ascii=False, sort_keys=True).replace("<", "\\u003c")
    exclusion_html = "".join(
        f"<li><code>{escape(item['case_id'])}</code>: {escape(item['reason'])}</li>" for item in exclusions
    ) or "<li>Nenhuma exclusão técnica.</li>"
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' file:; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>ARGOS — revisão cega das fases DICOM</title>
<style>
:root{{color-scheme:dark;font-family:Inter,system-ui,sans-serif;background:#08111f;color:#e7eef8}}body{{margin:0}}
header{{position:sticky;top:0;z-index:2;background:#101d31;padding:16px 22px;border-bottom:1px solid #304b70}}
h1{{font-size:21px;margin:0 0 8px}}.notice{{color:#f4d35e;font-weight:700}}main{{max-width:1550px;margin:auto;padding:18px;display:grid;gap:18px}}
.card{{background:#101d31;border:2px solid #304b70;border-radius:10px;overflow:hidden}}.card.ok{{border-color:#42b883}}
.meta{{padding:12px 15px;display:flex;gap:18px;justify-content:space-between;flex-wrap:wrap}}.hash{{font:11px ui-monospace,monospace;color:#9fb0c8}}
img{{display:block;width:100%;height:auto;background:#000}}fieldset{{border:0;border-top:1px solid #304b70;margin:0;padding:12px 15px;display:grid;gap:8px}}
label{{display:flex;gap:8px}}footer{{padding:20px;color:#9fb0c8}}code{{word-break:break-all}}
</style></head><body><header><h1>ARGOS — revisão cega da resolução automática de fases</h1>
<div class="notice">Gate técnico: não contém diagnóstico, label ou máscara de lesão.</div>
<div>Assinatura: <code>{escape(signature)}</code> · <span id="progress">0/{len(entries)}</span> revisados</div></header>
<main id="grid"></main><footer><strong>Exclusões técnicas:</strong><ul>{exclusion_html}</ul>
Avalie continuidade anatômica entre linhas, realce vascular arterial, aspecto portal/venoso, plausibilidade da fase tardia e ausência de SUB/MPR/MIP.</footer>
<script>
const entries={data}; const signature={json.dumps(signature)}; const key=`argos-raw-phase-review-${{signature}}`;
let state={{}};try{{state=JSON.parse(localStorage.getItem(key)||'{{}}')}}catch(_){{}}
const criteria=[['alignment','Mesmo nível anatômico e alinhamento aceitável nas três fases'],['timing','Ordem arterial → venosa → tardia é plausível'],['original','Não parece reconstrução SUB, MPR ou MIP']];
const grid=document.getElementById('grid');
function done(id){{return criteria.every(([k])=>state[id]?.[k]===true)}}
function update(){{let n=0;document.querySelectorAll('.card').forEach(c=>{{const ok=done(c.dataset.id);c.classList.toggle('ok',ok);if(ok)n++}});document.getElementById('progress').textContent=`${{n}}/${{entries.length}} revisados`;localStorage.setItem(key,JSON.stringify(state))}}
for(const item of entries){{const card=document.createElement('article');card.className='card';card.dataset.id=item.case_id;
card.innerHTML=`<div class="meta"><div><strong>${{item.sequence}}. ${{item.case_id}}</strong><br>${{item.method}} · confiança técnica ${{item.confidence}}<br>séries A/V/T: ${{item.series_numbers.join(' / ')}}</div><div class="hash">SHA-256: ${{item.panel_sha256}}</div></div><a href="${{item.image}}" target="_blank"><img loading="lazy" src="${{item.image}}"></a>`;
const fs=document.createElement('fieldset');for(const [k,t] of criteria){{const l=document.createElement('label'),b=document.createElement('input');b.type='checkbox';b.checked=state[item.case_id]?.[k]===true;b.onchange=()=>{{state[item.case_id]||={{}};state[item.case_id][k]=b.checked;update()}};l.append(b,document.createTextNode(t));fs.append(l)}}card.append(fs);grid.append(card)}}update();
</script></body></html>"""


def build_raw_phase_review_gallery(
    *, cases: list[dict[str, str]], source_roots: list[Path], output_dir: Path
) -> dict[str, Any]:
    """Resolve raw studies and atomically publish a pseudonymized review gallery.

    ``cases`` must contain only ``case_id`` and ``source_name``.  The caller is
    responsible for constructing this label-blind projection before calling.
    """
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError(f"A galeria já existe e não será sobrescrita: {output_dir}")
    roots = [Path(root).resolve() for root in source_roots]
    staging = output_dir.with_name(f".{output_dir.name}.staging.{uuid.uuid4().hex}")
    staging.mkdir(parents=True)
    entries: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    try:
        for sequence, case in enumerate(cases, start=1):
            case_id, source_name = case["case_id"], case["source_name"]
            matches = [root / source_name for root in roots if (root / source_name).is_dir()]
            if len(matches) != 1:
                exclusions.append({"case_id": case_id, "reason": f"fonte encontrada {len(matches)} vez(es)"})
                continue
            case_root = staging / "resolved" / case_id
            try:
                resolution = resolve_raw_dicom_phases(matches[0], case_root)
                resolution_manifest = json.loads(resolution.manifest_path.read_text(encoding="utf-8"))
                images = {phase: read_phase_series(resolution.phase_dirs[phase]) for phase in PHASES}
                panel = staging / "panels" / f"{case_id}_phases.png"
                rendering = _render_panel(images, panel)
            except Exception as exc:  # one incomplete public case must be auditable, not fatal
                exclusions.append({"case_id": case_id, "reason": str(exc)})
                shutil.rmtree(case_root, ignore_errors=True)
                continue
            selected = resolution_manifest["selected"]
            entries.append({
                "sequence": sequence,
                "case_id": case_id,
                "method": resolution.method,
                "confidence": resolution.confidence,
                "series_numbers": [selected[phase]["series_number"] for phase in PHASES],
                "series_hashes": [selected[phase]["series_hash"] for phase in PHASES],
                "panel_sha256": _sha256(panel),
                "image": panel.relative_to(staging).as_posix(),
                "rendering": rendering,
            })
        canonical = json.dumps({"schema": SCHEMA, "entries": entries, "exclusions": exclusions}, sort_keys=True, separators=(",", ":"))
        signature = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        manifest = {
            "schema": SCHEMA,
            "protocol_signature": signature,
            "requested_cases": len(cases),
            "eligible_cases": len(entries),
            "excluded_cases": len(exclusions),
            "ground_truth_read": False,
            "lesion_masks_read": False,
            "inference_executed": False,
            "research_only": True,
            "entries": entries,
            "exclusions": exclusions,
        }
        (staging / "review_gallery_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (staging / "index.html").write_text(_gallery_html(entries, exclusions, signature), encoding="utf-8")
        # Resolved DICOMs are unnecessary after rendering and must not be copied into the gallery.
        shutil.rmtree(staging / "resolved", ignore_errors=True)
        staging.replace(output_dir)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = ["build_raw_phase_review_gallery"]

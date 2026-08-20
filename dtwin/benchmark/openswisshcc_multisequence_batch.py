"""Atomic cohort and blind review gallery for OpenSwissHCC multisequence v9."""
from __future__ import annotations

import hashlib
import html
import json
import os
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_multisequence_audit import _rows
from dtwin.benchmark.openswisshcc_multisequence_panel import (
    SCHEMA,
    generate_multisequence_panel_set,
)
from dtwin.core import PipelineError

COHORT_SCHEMA = "argos-openswisshcc-multisequence-cohort-v1"
GALLERY_SCHEMA = "argos-openswisshcc-multisequence-gallery-v1"
FORBIDDEN = {"label", "truth", "hcc", "positive", "negative", "lesion_mask"}


def _canonical(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON multissequencia invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("JSON multissequencia deve ser objeto.")
    return value


def build_multisequence_cohort(*, input_root: Path, manifest_path: Path, output_root: Path,
                               expected_case_count: int = 88, tile_size: int = 448,
                               renderer: Callable[..., dict[str, Any]] = generate_multisequence_panel_set) -> dict[str, Any]:
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Destino multissequencia ja existe; nao sera sobrescrito.")
    rows = _rows(Path(manifest_path).resolve())
    if len(rows) != expected_case_count:
        raise PipelineError(f"Coorte possui {len(rows)} casos; esperado {expected_case_count}.")
    if any(FORBIDDEN & set(row) for row in rows):
        raise PipelineError("Manifesto de entrada contem ground truth protegido.")
    case_ids = sorted(str(row.get("case_id", "")) for row in rows)
    if len(set(case_ids)) != expected_case_count or any(not c.startswith("anon-") for c in case_ids):
        raise PipelineError("case_id multissequencia invalido ou duplicado.")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._multiseq_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        cases = []
        for case_id in case_ids:
            result = renderer(case_id=case_id, input_root=input_root, manifest_path=manifest_path,
                              output_root=staging, tile_size=tile_size)
            coverage = result.get("coverage", {})
            if (result.get("schema") != SCHEMA or result.get("case_id") != case_id
                    or result.get("ground_truth_read") is not False
                    or result.get("lesion_mask_used") is not False
                    or coverage.get("gate_passed") is not True
                    or coverage.get("missing_trace_planes") != []
                    or coverage.get("duplicate_trace_planes") != []
                    or result.get("panel_count", 0) < 1):
                raise PipelineError(f"Caso multissequencia invalido: {case_id}.")
            cases.append({"case_id": case_id, "panel_count": result["panel_count"],
                          "trace_role": result["trace_role"], "t2_role": result["t2_role"],
                          "manifest_sha256": _sha256(staging / case_id / "multisequence_manifest.json")})
        manifest = {"schema": COHORT_SCHEMA, "case_count": len(cases),
                    "panel_count": sum(c["panel_count"] for c in cases),
                    "max_panels_per_case": max(c["panel_count"] for c in cases),
                    "cases": cases, "cohort_signature": _canonical(cases),
                    "research_only": True, "clinical_use_allowed": False,
                    "ground_truth_read": False, "lesion_mask_used": False,
                    "inference_executed": False, "requires_human_review": True}
        (staging / "cohort_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _publish_directory(staging, output_root)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def build_multisequence_gallery(*, panel_root: Path, output_dir: Path,
                                expected_case_count: int = 88) -> dict[str, Any]:
    panel_root, output_dir = Path(panel_root).resolve(), Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError("Destino da galeria multissequencia ja existe.")
    cohort = _load(panel_root / "cohort_manifest.json")
    if (cohort.get("schema") != COHORT_SCHEMA or cohort.get("case_count") != expected_case_count
            or cohort.get("ground_truth_read") is not False or cohort.get("inference_executed") is not False):
        raise PipelineError("Coorte multissequencia insegura ou incompatÃ­vel.")
    sections, signed = [], []
    for index, item in enumerate(cohort.get("cases", []), 1):
        case_id = str(item.get("case_id", "")); case_dir = (panel_root / case_id).resolve()
        if not case_dir.is_relative_to(panel_root) or not case_dir.is_dir():
            raise PipelineError("Diretorio de caso multissequencia inseguro.")
        mpath = case_dir / "multisequence_manifest.json"; manifest = _load(mpath)
        if (_sha256(mpath) != item.get("manifest_sha256") or manifest.get("schema") != SCHEMA
                or manifest.get("ground_truth_read") is not False or manifest.get("lesion_mask_used") is not False):
            raise PipelineError(f"Manifesto multissequencia divergente: {case_id}.")
        figures, panel_records = [], []
        for expected, panel in enumerate(manifest.get("panels", []), 1):
            rel = PurePosixPath(str(panel.get("image", ""))); path = (case_dir / rel.name).resolve()
            if (rel.is_absolute() or ".." in rel.parts or len(rel.parts) != 1 or not path.is_relative_to(case_dir)
                    or not path.is_file() or panel.get("panel_number") != expected
                    or _sha256(path) != panel.get("sha256") or path.stat().st_size != panel.get("bytes")):
                raise PipelineError(f"Painel multissequencia divergente: {case_id}/{expected}.")
            src = quote(Path(os.path.relpath(path, output_dir)).as_posix(), safe="/._-")
            figures.append(f'<figure><img loading="lazy" src="{src}" alt="{html.escape(case_id)} {expected}"><figcaption>Painel {expected}/{manifest["panel_count"]} Â· TRACE {panel["trace_plane_index"]}</figcaption></figure>')
            panel_records.append({k: panel[k] for k in ("panel_number", "image", "sha256", "bytes", "trace_plane_index")})
        if len(panel_records) != manifest.get("panel_count"):
            raise PipelineError("Contagem de paineis multissequencia divergente.")
        sections.append(f'<details><summary>{index}. {html.escape(case_id)} Â· {len(panel_records)} painÃ©is</summary><div class="grid">{"".join(figures)}</div></details>')
        signed.append({"case_id": case_id, "panels": panel_records})
    if len(signed) != expected_case_count:
        raise PipelineError("Galeria nao contem a coorte esperada.")
    output_dir.parent.mkdir(parents=True, exist_ok=True); staging = output_dir.parent / f"._msgallery_{uuid.uuid4().hex[:8]}"; staging.mkdir()
    try:
        page = '<!doctype html><meta charset="utf-8"><title>ARGOS v9 revisÃ£o cega</title><style>body{font:15px system-ui;background:#0d1117;color:#eee;margin:24px}details{border:1px solid #345;margin:10px;padding:12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:10px}img{width:100%}figure{margin:0}figcaption{color:#aaa}</style><h1>OpenSwissHCC multissequÃªncia v9</h1><p>RevisÃ£o humana obrigatÃ³ria. Verifique correspondÃªncia anatÃ´mica, enquadramento, contraste e ausÃªncia de PHI. Esta galeria nÃ£o autoriza inferÃªncia.</p>' + ''.join(sections)
        (staging / "index.html").write_text(page, encoding="utf-8")
        result = {"schema": GALLERY_SCHEMA, "case_count": len(signed),
                  "panel_count": sum(len(c["panels"]) for c in signed), "cases": signed,
                  "source_cohort_signature": cohort["cohort_signature"], "gallery_signature": _canonical(signed),
                  "authoritative_approval": False, "ground_truth_read": False, "inference_executed": False,
                  "research_only": True, "clinical_use_allowed": False}
        (staging / "gallery_manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _publish_directory(staging, output_dir); return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True); raise



"""Local, non-authoritative review gallery for volumetric candidate sets."""
from __future__ import annotations

import hashlib
import html
import json
import os
import shutil
import uuid
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from dtwin.benchmark.openswisshcc_alignment import (
    _load_json,
    _publish_directory,
    _sha256,
)
from dtwin.benchmark.openswisshcc_volumetric_batch import COHORT_SCHEMA
from dtwin.core import PipelineError

GALLERY_SCHEMA = "argos-openswisshcc-volumetric-review-gallery-v1"


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validated_case(root: Path, item: dict) -> dict:
    case_id = str(item.get("case_id", ""))
    case_dir = (root / case_id).resolve()
    if not case_id.startswith("anon-") or not case_dir.is_relative_to(root) or not case_dir.is_dir():
        raise PipelineError("Caso volumetrico ausente ou inseguro.")
    candidate = _load_json(case_dir / "candidate_manifest.json")
    if candidate.get("case_id") != case_id or candidate.get("candidate_signature") != item.get("candidate_signature"):
        raise PipelineError("Candidato volumetrico diverge do manifesto da coorte.")
    if candidate.get("research_only") is not True or candidate.get("clinical_use_allowed") is not False:
        raise PipelineError("Candidato volumetrico perdeu salvaguardas de pesquisa.")
    if candidate.get("ground_truth_read") is not False or candidate.get("eligible_for_inference") is not False:
        raise PipelineError("Candidato volumetrico foi liberado prematuramente.")
    coverage = candidate.get("coverage")
    if (
        not isinstance(coverage, dict)
        or coverage.get("gate_passed") is not True
        or coverage.get("covered_liver_voxels") != coverage.get("total_liver_voxels")
    ):
        raise PipelineError("Candidato volumetrico nao possui cobertura exata.")
    raw_panels = candidate.get("panels")
    if not isinstance(raw_panels, list) or len(raw_panels) != candidate.get("panel_image_count"):
        raise PipelineError("Colecao de paineis volumetricos e incompatível.")
    panels: list[dict] = []
    for expected, panel in enumerate(raw_panels, start=1):
        relative = PurePosixPath(str(panel.get("image", "")))
        path = (case_dir / relative.name).resolve()
        if (
            relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 1
            or not path.is_relative_to(case_dir) or not path.is_file()
            or int(panel.get("panel_number", expected)) != expected
            or _sha256(path) != panel.get("sha256")
            or path.stat().st_size != panel.get("bytes")
        ):
            raise PipelineError(f"Painel volumetrico divergente no caso {case_id}.")
        panels.append(
            {
                "panel_number": expected,
                "image": relative.name,
                "sha256": panel["sha256"],
                "bytes": panel["bytes"],
                "absolute_path": path,
            }
        )
    if _canonical_sha256(raw_panels) != candidate.get("panel_set_sha256"):
        raise PipelineError("Hash da colecao volumetrica diverge.")
    return {
        "case_id": case_id,
        "candidate_kind": candidate.get("candidate_kind"),
        "candidate_signature": candidate.get("candidate_signature"),
        "panel_set_sha256": candidate.get("panel_set_sha256"),
        "panel_count": len(panels),
        "panels": panels,
    }


def build_volumetric_review_gallery(
    *, panel_root: Path, output_dir: Path, expected_case_count: int = 88
) -> dict:
    panel_root = Path(panel_root).resolve()
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError("Destino da galeria volumetrica ja existe.")
    cohort = _load_json(panel_root / "cohort_manifest.json")
    if cohort.get("schema") != COHORT_SCHEMA or cohort.get("case_count") != expected_case_count:
        raise PipelineError("Manifesto da coorte volumetrica e incompatível.")
    if cohort.get("ground_truth_read") is not False or cohort.get("inference_executed") is not False:
        raise PipelineError("Coorte volumetrica viola isolamento antes da revisao.")
    raw_cases = cohort.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) != expected_case_count:
        raise PipelineError("Lista de casos volumetricos e incompatível.")
    cases = [_validated_case(panel_root, item) for item in raw_cases]
    if len({item["case_id"] for item in cases}) != expected_case_count:
        raise PipelineError("Galeria volumetrica contem casos duplicados.")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.parent / f"._volgallery_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        sections: list[str] = []
        manifest_cases: list[dict] = []
        for index, case in enumerate(cases, start=1):
            images: list[str] = []
            signed_panels: list[dict] = []
            for panel in case["panels"]:
                relative = Path(os.path.relpath(panel["absolute_path"], staging)).as_posix()
                src = quote(relative, safe="/._-")
                images.append(
                    '<figure><img loading="lazy" src="{}" alt="{} painel {}/{}">'
                    '<figcaption>Painel {}/{} &middot; <code>{}</code></figcaption></figure>'.format(
                        src,
                        html.escape(case["case_id"]),
                        panel["panel_number"],
                        case["panel_count"],
                        panel["panel_number"],
                        case["panel_count"],
                        html.escape(panel["sha256"][:16]),
                    )
                )
                signed_panels.append(
                    {key: panel[key] for key in ("panel_number", "image", "sha256", "bytes")}
                )
            sections.append(
                '<details class="case"><summary><strong>{}. {}</strong> '
                '<span>{} &middot; {} paineis</span></summary><div class="grid">{}</div></details>'.format(
                    index,
                    html.escape(case["case_id"]),
                    html.escape(str(case["candidate_kind"])),
                    case["panel_count"],
                    "".join(images),
                )
            )
            manifest_cases.append(
                {
                    "case_id": case["case_id"],
                    "candidate_kind": case["candidate_kind"],
                    "candidate_signature": case["candidate_signature"],
                    "panel_set_sha256": case["panel_set_sha256"],
                    "panel_count": case["panel_count"],
                    "panels": signed_panels,
                }
            )
        page = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ARGOS - revisao volumetrica</title>
<style>body{font:15px system-ui;background:#0d1117;color:#e6edf3;margin:0}main{max-width:1500px;margin:auto;padding:24px}h1{margin:0 0 8px}.notice{background:#172033;border:1px solid #35517b;padding:14px;border-radius:10px;margin:16px 0}.case{border:1px solid #30363d;border-radius:10px;margin:12px 0;background:#161b22}.case summary{cursor:pointer;padding:14px}.case summary span{float:right;color:#9da7b3}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:12px;padding:12px}figure{margin:0;background:#0d1117;border-radius:8px;overflow:hidden}img{display:block;width:100%;height:auto}figcaption{padding:8px;color:#9da7b3}code{font-size:12px}</style></head><body><main>
<h1>Revisao volumetrica OpenSwissHCC</h1><div class="notice"><strong>Gate humano, uso em pesquisa.</strong> Revise todos os paineis de cada caso: ausencia de PHI visivel, enquadramento do figado, contraste e continuidade da cobertura. Esta galeria nao aprova inferencia automaticamente.</div>
__SECTIONS__ </main></body></html>""".replace("__SECTIONS__", "".join(sections))
        (staging / "index.html").write_text(page, encoding="utf-8")
        manifest = {
            "schema": GALLERY_SCHEMA,
            "case_count": len(manifest_cases),
            "panel_image_count": sum(item["panel_count"] for item in manifest_cases),
            "source_cohort_signature": cohort["cohort_signature"],
            "cases": manifest_cases,
            "gallery_signature": _canonical_sha256(manifest_cases),
            "authoritative_approval": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "ground_truth_read": False,
            "inference_executed": False,
        }
        (staging / "gallery_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _publish_directory(staging, output_dir)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise




"""Render the label-blind LiverHccSeg v21 uniform-9 technical gallery."""
from __future__ import annotations

import hashlib
import html
import json
import shutil
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image

from dtwin.benchmark.liverhccseg_preparation import verify_liverhccseg_blind_inputs
from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.core import PipelineError, load_profile
from dtwin.medgemma_client import load_screening_config, model_trace
from dtwin.medgemma_panel_multiphase import generate_liver_panel_multiphase
from dtwin.medgemma_screening import _write_json_atomic


CASE_SCHEMA = "argos-liverhccseg-v21-uniform9-panel-case-v1"
COHORT_SCHEMA = "argos-liverhccseg-v21-uniform9-panel-cohort-v1"
GALLERY_SCHEMA = "argos-liverhccseg-v21-uniform9-gallery-v1"
ROLE_TO_PHASE = {"art": "t1_arterial", "pv": "t1_venous", "del": "t1_delayed"}


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON v21 invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"JSON v21 nao e objeto: {path}")
    return value


def _canonical_sha(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_relative(root: Path, relative: str) -> Path:
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts:
        raise PipelineError("Caminho preparado v21 inseguro.")
    path = (root / Path(*posix.parts)).resolve()
    if not path.is_relative_to(root):
        raise PipelineError("Caminho preparado v21 escapou da raiz.")
    return path


def _validate_config(path: Path) -> dict[str, Any]:
    config = load_screening_config(path)
    panel = config.get("panel", {})
    med = config.get("medgemma", {})
    if (
        panel.get("mode") != "multiphase_fusion"
        or panel.get("strategy") != "uniform_9"
        or int(panel.get("axial_slices", 9)) != 9
        or med.get("response_mode") != "choice_classification"
        or med.get("model_id") != "google/medgemma-1.5-4b-it"
        or med.get("model_parameter_scale") != "4B"
        or int(med.get("timeout_seconds", 0)) > 120
        or int(med.get("max_retries", 1)) != 0
        or config.get("rag", {}).get("enabled") is not False
    ):
        raise PipelineError("Config v21 nao preserva o leitor v11/v4 uniform_9 cego.")
    return config


def _case_files(prepared_root: Path, case_record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Path]]:
    manifest_path = _safe_relative(prepared_root, str(case_record.get("case_manifest", "")))
    if not manifest_path.is_file() or _sha256(manifest_path) != case_record.get("case_manifest_sha256"):
        raise PipelineError("Manifesto preparado v21 ausente ou adulterado.")
    manifest = _load(manifest_path)
    if (
        manifest.get("case_id") != case_record.get("case_id")
        or manifest.get("lesion_mask_present") is not False
        or manifest.get("pathology_label_present") is not False
    ):
        raise PipelineError("Manifesto preparado v21 perdeu isolamento de labels/lesao.")
    files: dict[str, Path] = {}
    for item in manifest.get("files", []):
        role = str(item.get("role", ""))
        path = _safe_relative(prepared_root, str(item.get("relative_path", "")))
        if role in files or not path.is_file() or _sha256(path) != item.get("sha256"):
            raise PipelineError("Arquivo preparado v21 ausente, duplicado ou adulterado.")
        if "tumor" in path.name.lower() or "lesion" in path.name.lower():
            raise PipelineError("Arquivo de lesao apareceu no workspace de paineis.")
        files[role] = path
    required = set(ROLE_TO_PHASE.values()) | {"liver_mask"}
    if required - set(files):
        raise PipelineError("Caso v21 sem fases ou mascara hepatica obrigatoria.")
    return manifest, files


def build_liverhccseg_uniform9_panels(
    *,
    prepared_root: Path,
    output_root: Path,
    config_path: Path,
    profile_path: Path,
    expected_case_count: int = 14,
    expected_prepared_signature: str | None = None,
) -> dict[str, Any]:
    """Render all cases atomically; outputs remain ineligible until human review."""

    prepared_root = Path(prepared_root).resolve()
    output_root = Path(output_root).resolve()
    config_path = Path(config_path).resolve()
    profile_path = Path(profile_path).resolve()
    preflight = verify_liverhccseg_blind_inputs(
        prepared_root=prepared_root,
        expected_case_count=expected_case_count,
        expected_cohort_signature=expected_prepared_signature,
    )
    config = _validate_config(config_path)
    cohort_path = prepared_root / "cohort_manifest.json"
    cohort = _load(cohort_path)
    if output_root.exists():
        raise PipelineError("Coorte de paineis LiverHccSeg v21 ja existe.")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._liverhccseg_v21_panels_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    records: list[dict[str, Any]] = []
    try:
        for case_record in cohort["cases"]:
            case_id = str(case_record["case_id"])
            source_manifest, files = _case_files(prepared_root, case_record)
            case_dir = staging / case_id
            case_dir.mkdir()
            case_manifest_path = case_dir / "case_manifest.json"
            _write_json_atomic(case_manifest_path, {
                "case_id": case_id,
                "policy": "anonymize",
                "regulatory_state": "PESQUISA",
                "modality": "MRI",
            })
            result = generate_liver_panel_multiphase(
                phase_paths={phase: files[role] for phase, role in ROLE_TO_PHASE.items()},
                liver_mask_path=files["liver_mask"],
                case_manifest_path=case_manifest_path,
                organ_profile=load_profile(profile_path),
                screening_config=config,
                output_dir=case_dir,
                model_trace=model_trace(config),
                visible_phi_confirmed=False,
            )
            panel_manifest = _load(result.manifest_path)
            if (
                panel_manifest.get("case_id") != case_id
                or panel_manifest.get("lesion_pre_marked") is not False
                or panel_manifest.get("panel_count") != 11
                or len(tuple(result.panel_paths)) != 1
                or panel_manifest.get("visible_phi_confirmed") is not False
            ):
                raise PipelineError("Painel v21 violou estrategia, cegamento ou gate visual.")
            with Image.open(result.panel_path) as image:
                width, height = image.size
                metadata_keys = sorted(image.info)
            if metadata_keys:
                raise PipelineError("PNG v21 contem metadados inesperados.")
            panel_sha = _sha256(result.panel_path)
            signature = _canonical_sha({
                "case_id": case_id,
                "source_case_signature": source_manifest["case_signature"],
                "config_sha256": _sha256(config_path),
                "profile_sha256": _sha256(profile_path),
                "panel_sha256": panel_sha,
                "panel_manifest_sha256": _sha256(result.manifest_path),
            })
            manifest = {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "status": "rendered_pending_human_review",
                "candidate_signature": signature,
                "source_case_signature": source_manifest["case_signature"],
                "panel_filename": result.panel_path.name,
                "panel_sha256": panel_sha,
                "panel_bytes": result.panel_path.stat().st_size,
                "panel_width": width,
                "panel_height": height,
                "panel_manifest_filename": result.manifest_path.name,
                "panel_manifest_sha256": _sha256(result.manifest_path),
                "visible_phi_confirmed": False,
                "eligible_for_inference": False,
                "lesion_mask_used": False,
                "pathology_label_used": False,
                "ground_truth_read": False,
                "holdout_opened": False,
                "research_only": True,
                "clinical_use_allowed": False,
                "requires_human_review": True,
            }
            _write_json_atomic(case_dir / "candidate_manifest.json", manifest)
            records.append({
                "case_id": case_id,
                "candidate_manifest": f"{case_id}/candidate_manifest.json",
                "candidate_manifest_sha256": _sha256(case_dir / "candidate_manifest.json"),
                "candidate_signature": signature,
                "panel": f"{case_id}/{result.panel_path.name}",
                "panel_sha256": panel_sha,
            })
        summary = {
            "schema": COHORT_SCHEMA,
            "status": "complete_pending_human_review",
            "case_count": len(records),
            "case_ids": [record["case_id"] for record in records],
            "cases": records,
            "prepared_cohort_signature": preflight["cohort_signature"],
            "prepared_cohort_manifest_sha256": _sha256(cohort_path),
            "config_sha256": _sha256(config_path),
            "profile_sha256": _sha256(profile_path),
            "all_panels_uniform9": True,
            "all_panels_pending_human_review": True,
            "lesion_masks_used": False,
            "pathology_labels_used": False,
            "ground_truth_read": False,
            "holdout_opened": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        summary["cohort_signature"] = _canonical_sha(summary)
        _write_json_atomic(staging / "cohort_manifest.json", summary)
        _publish_directory(staging, output_root)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def build_liverhccseg_uniform9_gallery(*, panel_root: Path, output_dir: Path) -> dict[str, Any]:
    """Create a local, label-free visual gate for the 14 external panels."""

    panel_root = Path(panel_root).resolve()
    output_dir = Path(output_dir).resolve()
    cohort_path = panel_root / "cohort_manifest.json"
    cohort = _load(cohort_path)
    if (
        cohort.get("schema") != COHORT_SCHEMA
        or cohort.get("status") != "complete_pending_human_review"
        or cohort.get("ground_truth_read") is not False
        or cohort.get("holdout_opened") is not False
    ):
        raise PipelineError("Coorte v21 nao esta pronta para galeria tecnica.")
    if output_dir.exists():
        raise PipelineError("Galeria v21 ja existe.")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.parent / f"._liverhccseg_v21_gallery_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        cards: list[str] = []
        gallery_cases: list[dict[str, Any]] = []
        for number, record in enumerate(cohort["cases"], start=1):
            case_id = str(record["case_id"])
            source = _safe_relative(panel_root, str(record["panel"]))
            if not source.is_file() or _sha256(source) != record["panel_sha256"]:
                raise PipelineError("Painel v21 ausente ou adulterado antes da galeria.")
            filename = f"{number:02d}_{case_id}.png"
            shutil.copy2(source, staging / filename)
            if _sha256(staging / filename) != record["panel_sha256"]:
                raise PipelineError("Copia da galeria v21 divergiu do painel fonte.")
            cards.append(
                '<article class="card">'
                f'<h2>{number}. {html.escape(case_id)}</h2>'
                f'<img src="{html.escape(filename)}" alt="Painel técnico {number}">'
                '<p>Avaliar: fígado visível, orientação plausível, crop completo, '
                'fusão RGB interpretável, contorno sem esconder parênquima e ausência de PHI.</p>'
                '</article>'
            )
            gallery_cases.append({"number": number, "case_id": case_id, "image": filename, "sha256": record["panel_sha256"]})
        document = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>ARGOS v21 — LiverHccSeg, gate técnico cego</title><style>
body{font-family:system-ui;background:#111827;color:#e5e7eb;margin:0;padding:24px}h1{margin-top:0}
.notice{background:#1f2937;border:1px solid #4b5563;padding:16px;border-radius:10px;margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(560px,1fr));gap:20px}
.card{background:#1f2937;padding:14px;border-radius:10px}.card img{width:100%;height:auto;background:#000}
.card h2{font-size:16px}.card p{color:#cbd5e1;font-size:14px}</style></head><body>
<h1>ARGOS v21 — galeria técnica cega LiverHccSeg</h1>
<div class="notice"><b>Não avalie diagnóstico.</b> Esta revisão confirma somente qualidade técnica. 
Nenhum label ou máscara de lesão está disponível nesta galeria. Os painéis continuam inelegíveis para inferência até aprovação explícita.</div>
<main class="grid">""" + "".join(cards) + "</main></body></html>"
        (staging / "index.html").write_text(document, encoding="utf-8")
        manifest = {
            "schema": GALLERY_SCHEMA,
            "status": "pending_human_review",
            "case_count": len(gallery_cases),
            "cases": gallery_cases,
            "source_cohort_sha256": _sha256(cohort_path),
            "index_sha256": _sha256(staging / "index.html"),
            "reviewer": None,
            "approved": False,
            "ground_truth_read": False,
            "holdout_opened": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        manifest["gallery_signature"] = _canonical_sha(manifest)
        _write_json_atomic(staging / "gallery_manifest.json", manifest)
        _publish_directory(staging, output_dir)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

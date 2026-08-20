"""Render the final OpenSwissHCC holdout gallery without opening ground truth."""
from __future__ import annotations

import hashlib
import html
import json
import shutil
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_holdout import (
    HOLDOUT_AUDIT_SCHEMA,
    HOLDOUT_INPUT_SCHEMA,
)
from dtwin.core import PipelineError, load_profile
from dtwin.medgemma_client import load_screening_config, model_trace
from dtwin.medgemma_panel import generate_liver_panel
from dtwin.medgemma_panel_multiphase import generate_liver_panel_multiphase
from dtwin.medgemma_screening import _write_json_atomic

CASE_SCHEMA = "argos-openswisshcc-holdout-uniform9-panel-case-v1"
COHORT_SCHEMA = "argos-openswisshcc-holdout-uniform9-panel-cohort-v1"
GALLERY_SCHEMA = "argos-openswisshcc-holdout-uniform9-gallery-v1"


def _load(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON holdout inválido: {path}.") from exc


def _canonical_sha(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_file(root: Path, relative: str) -> Path:
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts:
        raise PipelineError("Caminho inseguro no holdout.")
    path = (root / Path(*posix.parts)).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise PipelineError("Arquivo holdout ausente ou fora da raiz.")
    return path


def _validate_config(path: Path, *, mode: str) -> dict[str, Any]:
    config = load_screening_config(path)
    panel = config.get("panel", {})
    med = config.get("medgemma", {})
    if (
        panel.get("mode") != mode
        or panel.get("strategy") != "uniform_9"
        or int(panel.get("axial_slices", 9)) != 9
        or med.get("response_mode") != "choice_classification"
        or med.get("model_id") != "google/medgemma-1.5-4b-it"
        or med.get("model_parameter_scale") != "4B"
        or int(med.get("timeout_seconds", 0)) > 120
        or int(med.get("max_retries", 1)) != 0
        or config.get("rag", {}).get("enabled") is not False
    ):
        raise PipelineError("Config holdout não preserva o leitor v21 congelado.")
    return config


def _input_rows(prepared_root: Path) -> list[dict[str, Any]]:
    path = prepared_root / "manifests" / "holdout_inputs.jsonl"
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Manifesto label-blind do holdout inválido.") from exc
    if len(rows) != 44 or len({row.get("case_id") for row in rows}) != 44:
        raise PipelineError("Manifesto holdout não contém exatamente 44 casos únicos.")
    for row in rows:
        serialized = json.dumps(row, ensure_ascii=False).lower()
        if (
            row.get("schema") != HOLDOUT_INPUT_SCHEMA
            or row.get("split") != "holdout_blind"
            or "sub-" in serialized
            or "hcc" in serialized
            or "label" in serialized
            or "lesion" in serialized
        ):
            raise PipelineError("Input holdout perdeu o cegamento.")
    return rows


def _files(prepared_root: Path, row: dict[str, Any]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for item in row.get("files", []):
        role = str(item.get("role", ""))
        path = _safe_file(prepared_root / "inputs", str(item.get("relative_path", "")))
        if role in result or _sha256(path) != item.get("sha256"):
            raise PipelineError("Arquivo holdout duplicado ou adulterado.")
        result[role] = path
    required = {"t1_venous", "liver_mask_venous"}
    if required - set(result):
        raise PipelineError("Caso holdout sem fase/máscara venosa.")
    return result


def _aligned_paths(alignment_root: Path, case_id: str, expected_sha: str) -> dict[str, Path]:
    case_dir = (alignment_root / case_id).resolve()
    manifest_path = case_dir / "alignment_manifest.json"
    if _sha256(manifest_path) != expected_sha:
        raise PipelineError("Manifesto de alinhamento holdout adulterado.")
    manifest = _load(manifest_path)
    outputs = {}
    for item in manifest.get("outputs", []):
        path = _safe_file(case_dir, str(item.get("filename", "")))
        if _sha256(path) != item.get("sha256"):
            raise PipelineError("Volume alinhado holdout adulterado.")
        outputs[str(item.get("phase"))] = path
    if set(outputs) != {"art", "del"}:
        raise PipelineError("Alinhamento holdout não contém arterial e tardia.")
    return outputs


def build_holdout_uniform9_panels(
    *,
    prepared_root: Path,
    prepared_audit_path: Path,
    alignment_root: Path,
    alignment_summary_path: Path,
    multiphase_config_path: Path,
    fallback_config_path: Path,
    profile_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Render 44 immutable candidates pending a human technical gate."""

    prepared_root = Path(prepared_root).resolve()
    alignment_root = Path(alignment_root).resolve()
    output_root = Path(output_root).resolve()
    audit = _load(prepared_audit_path)
    alignment = _load(alignment_summary_path)
    if (
        audit.get("schema") != HOLDOUT_AUDIT_SCHEMA
        or audit.get("status") != "label_blind_holdout_preparation_verified"
        or audit.get("labels_read") is not False
        or audit.get("lesion_masks_read") != 0
    ):
        raise PipelineError("Auditoria label-blind do holdout inválida.")
    if (
        alignment.get("schema") != "argos-openswisshcc-holdout-alignment-summary-v1"
        or alignment.get("case_count") != 44
        or alignment.get("holdout_ground_truth_opened") is not False
        or alignment.get("labels_read") is not False
        or alignment.get("lesion_masks_read") != 0
    ):
        raise PipelineError("Resumo de alinhamento holdout inválido.")
    rows = _input_rows(prepared_root)
    if audit.get("input_manifest_sha256") != _sha256(
        prepared_root / "manifests" / "holdout_inputs.jsonl"
    ):
        raise PipelineError("Manifesto holdout divergiu da auditoria.")
    aligned_hashes = {item["case_id"]: item["sha256"] for item in alignment["alignments"]}
    fallback_ids = {item["case_id"] for item in alignment["technical_fallbacks"]}
    case_ids = {str(row["case_id"]) for row in rows}
    if set(aligned_hashes) | fallback_ids != case_ids or set(aligned_hashes) & fallback_ids:
        raise PipelineError("Contabilidade de alinhamentos/fallbacks do holdout inválida.")
    multiphase_config = _validate_config(multiphase_config_path, mode="multiphase_fusion")
    fallback_config = _validate_config(fallback_config_path, mode="single_grayscale")
    profile = load_profile(profile_path)
    if output_root.exists():
        raise PipelineError("Coorte de painéis holdout já existe.")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._holdout_panels_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    records = []
    try:
        for row in rows:
            case_id = str(row["case_id"])
            files = _files(prepared_root, row)
            case_dir = staging / case_id
            case_dir.mkdir()
            case_manifest_path = case_dir / "case_manifest.json"
            _write_json_atomic(
                case_manifest_path,
                {
                    "case_id": case_id,
                    "policy": "anonymize",
                    "regulatory_state": "PESQUISA",
                    "modality": "MRI",
                },
            )
            if case_id in fallback_ids:
                kind = "venous_single_phase_fallback"
                result = generate_liver_panel(
                    volume_path=files["t1_venous"],
                    liver_mask_path=files["liver_mask_venous"],
                    case_manifest_path=case_manifest_path,
                    organ_profile=profile,
                    screening_config=fallback_config,
                    output_dir=case_dir,
                    model_trace=model_trace(fallback_config),
                    visible_phi_confirmed=False,
                )
                source_hashes = {
                    "venous": _sha256(files["t1_venous"]),
                    "liver_mask_venous": _sha256(files["liver_mask_venous"]),
                }
            else:
                kind = "multiphase_rgb"
                aligned = _aligned_paths(alignment_root, case_id, aligned_hashes[case_id])
                result = generate_liver_panel_multiphase(
                    phase_paths={"art": aligned["art"], "pv": files["t1_venous"], "del": aligned["del"]},
                    liver_mask_path=files["liver_mask_venous"],
                    case_manifest_path=case_manifest_path,
                    organ_profile=profile,
                    screening_config=multiphase_config,
                    output_dir=case_dir,
                    model_trace=model_trace(multiphase_config),
                    visible_phi_confirmed=False,
                )
                source_hashes = {
                    "art_registered": _sha256(aligned["art"]),
                    "venous": _sha256(files["t1_venous"]),
                    "del_registered": _sha256(aligned["del"]),
                    "liver_mask_venous": _sha256(files["liver_mask_venous"]),
                }
            panel_manifest = _load(result.manifest_path)
            if (
                panel_manifest.get("case_id") != case_id
                or panel_manifest.get("lesion_pre_marked") is not False
                or panel_manifest.get("panel_count") != 11
                or len(tuple(result.panel_paths)) != 1
                or panel_manifest.get("visible_phi_confirmed") is not False
            ):
                raise PipelineError("Painel holdout violou o contrato congelado.")
            with Image.open(result.panel_path) as image:
                width, height = image.size
                if image.info:
                    raise PipelineError("PNG holdout contém metadados inesperados.")
            panel_sha = _sha256(result.panel_path)
            signature = _canonical_sha(
                {
                    "case_id": case_id,
                    "kind": kind,
                    "source_hashes": source_hashes,
                    "panel_sha256": panel_sha,
                    "panel_manifest_sha256": _sha256(result.manifest_path),
                }
            )
            candidate = {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "candidate_kind": kind,
                "status": "rendered_pending_human_review",
                "candidate_signature": signature,
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
                "holdout_ground_truth_opened": False,
                "research_only": True,
                "clinical_use_allowed": False,
                "requires_human_review": True,
            }
            _write_json_atomic(case_dir / "candidate_manifest.json", candidate)
            records.append(
                {
                    "case_id": case_id,
                    "candidate_kind": kind,
                    "candidate_manifest": f"{case_id}/candidate_manifest.json",
                    "candidate_manifest_sha256": _sha256(case_dir / "candidate_manifest.json"),
                    "candidate_signature": signature,
                    "panel": f"{case_id}/{result.panel_path.name}",
                    "panel_sha256": panel_sha,
                }
            )
        summary = {
            "schema": COHORT_SCHEMA,
            "status": "complete_pending_human_review",
            "case_count": len(records),
            "multiphase_case_count": sum(item["candidate_kind"] == "multiphase_rgb" for item in records),
            "venous_fallback_case_count": sum(item["candidate_kind"] != "multiphase_rgb" for item in records),
            "cases": records,
            "prepared_audit_sha256": _sha256(prepared_audit_path),
            "alignment_summary_sha256": _sha256(alignment_summary_path),
            "multiphase_config_sha256": _sha256(multiphase_config_path),
            "fallback_config_sha256": _sha256(fallback_config_path),
            "profile_sha256": _sha256(profile_path),
            "all_panels_uniform9": True,
            "all_panels_pending_human_review": True,
            "lesion_masks_used": False,
            "pathology_labels_used": False,
            "holdout_ground_truth_opened": False,
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


def build_holdout_uniform9_gallery(*, panel_root: Path, output_dir: Path) -> dict[str, Any]:
    """Build a diagnostic-label-free local technical review page."""

    panel_root = Path(panel_root).resolve()
    output_dir = Path(output_dir).resolve()
    cohort_path = panel_root / "cohort_manifest.json"
    cohort = _load(cohort_path)
    if (
        cohort.get("schema") != COHORT_SCHEMA
        or cohort.get("status") != "complete_pending_human_review"
        or cohort.get("holdout_ground_truth_opened") is not False
        or cohort.get("case_count") != 44
    ):
        raise PipelineError("Coorte holdout não está apta à galeria técnica.")
    if output_dir.exists():
        raise PipelineError("Galeria holdout já existe.")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.parent / f"._holdout_gallery_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        cards = []
        gallery_cases = []
        for index, item in enumerate(cohort["cases"], start=1):
            case_id = str(item["case_id"])
            panel = _safe_file(panel_root, str(item["panel"]))
            if _sha256(panel) != item.get("panel_sha256"):
                raise PipelineError("Painel holdout adulterado antes da galeria.")
            destination_name = f"case-{index:03d}.png"
            shutil.copyfile(panel, staging / destination_name)
            digest = _sha256(staging / destination_name)
            kind = str(item["candidate_kind"])
            cards.append(
                f'<article><h2>{index:02d}. {html.escape(case_id)}</h2>'
                f'<p>{html.escape(kind)}</p><img src="{destination_name}" alt="Painel técnico {index}"></article>'
            )
            gallery_cases.append(
                {"index": index, "case_id": case_id, "candidate_kind": kind, "image": destination_name, "sha256": digest}
            )
        document = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>ARGOS — gate técnico holdout OpenSwissHCC</title><style>
body{font-family:system-ui;background:#10151c;color:#eef2f7;margin:20px} .notice{background:#243247;padding:16px;border-radius:10px}
main{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:18px;margin-top:18px} article{background:#18212d;padding:12px;border-radius:10px}
img{width:100%;height:auto;background:#000} h2{font-size:16px;margin:0 0 6px} p{color:#b8c5d6}</style></head><body>
<h1>Gate técnico — holdout OpenSwissHCC 045–088</h1><div class="notice">Avalie somente visibilidade do fígado, crop, orientação, registro RGB e ausência de PHI ou marcação de lesão. Não procure diagnóstico. Ground truth e máscaras de lesão permanecem fechados.</div><main>""" + "".join(cards) + "</main></body></html>"
        (staging / "index.html").write_text(document, encoding="utf-8")
        manifest = {
            "schema": GALLERY_SCHEMA,
            "status": "pending_human_review",
            "case_count": len(gallery_cases),
            "cases": gallery_cases,
            "panel_cohort_sha256": _sha256(cohort_path),
            "index_sha256": _sha256(staging / "index.html"),
            "holdout_ground_truth_opened": False,
            "lesion_masks_used": False,
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

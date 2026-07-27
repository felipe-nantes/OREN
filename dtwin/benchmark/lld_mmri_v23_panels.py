"""Uniform-9 technical panels for the frozen LLD-MMRI v23 cohort."""
from __future__ import annotations

import html
import json
import math
import shutil
import time
import uuid
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from PIL import Image

from dtwin.benchmark.liverhccseg_v21_panels import _validate_config
from dtwin.benchmark.lld_mmri_v23_preparation import (
    INPUT_SCHEMA,
    MASK_ROLE,
    _load_jsonl_checkpoint,
    _write_jsonl_checkpoint_atomic,
    verify_lld_mmri_v23_blind_inputs,
)
from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError, load_profile
from dtwin.medgemma_client import model_trace
from dtwin.medgemma_panel_multiphase import generate_liver_panel_multiphase
from dtwin.medgemma_screening import _write_json_atomic


CASE_SCHEMA = "argos-lld-mmri-v23-uniform9-panel-case-v1"
COHORT_SCHEMA = "argos-lld-mmri-v23-uniform9-panel-cohort-v1"
GALLERY_SCHEMA = "argos-lld-mmri-v23-uniform9-gallery-v1"
ROLE_TO_PHASE = {"art": "t1_arterial", "pv": "t1_venous", "del": "t1_delayed"}


def _safe(root: Path, relative_text: str) -> Path:
    relative = PurePosixPath(relative_text)
    if relative.is_absolute() or ".." in relative.parts:
        raise PipelineError("Caminho LLD-MMRI de painel inseguro.")
    path = (root / Path(*relative.parts)).resolve()
    if not path.is_relative_to(root):
        raise PipelineError("Caminho LLD-MMRI de painel escapou da raiz.")
    return path


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON LLD-MMRI invalido: {path}.") from exc
    if not isinstance(value, dict):
        raise PipelineError("JSON LLD-MMRI deve ser objeto.")
    return value


def _prepared_rows(prepared_root: Path, case_ids: list[str]) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in (prepared_root / "inputs.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Inputs preparados LLD-MMRI invalidos.") from exc
    if [row.get("case_id") for row in rows] != case_ids:
        raise PipelineError("Ordem preparada LLD-MMRI divergiu do protocolo.")
    return rows


def _case_files(prepared_root: Path, row: dict[str, Any]) -> dict[str, Path]:
    if (
        row.get("schema") != INPUT_SCHEMA
        or row.get("lesion_mask_present") is not False
        or row.get("pathology_label_present") is not False
        or row.get("ground_truth_read") is not False
    ):
        raise PipelineError("Input LLD-MMRI perdeu o cegamento.")
    root = (prepared_root / "inputs").resolve()
    files: dict[str, Path] = {}
    for item in row.get("files", []):
        role = str(item.get("role", ""))
        relative = str(item.get("relative_path", ""))
        path = _safe(root, relative)
        if (
            role in files
            or any(term in (role + " " + relative).lower() for term in ("lesion", "label", "ground_truth"))
            or not path.is_file()
            or path.stat().st_size != item.get("bytes")
            or _sha256(path) != item.get("sha256")
        ):
            raise PipelineError("Arquivo preparado LLD-MMRI ausente ou adulterado.")
        files[role] = path
    required = set(ROLE_TO_PHASE.values()) | {MASK_ROLE}
    if required - set(files):
        raise PipelineError("Caso LLD-MMRI sem fases dinamicas ou mascara hepatica.")
    return files


def build_lld_mmri_v23_uniform9_panels(
    *,
    protocol_root: Path,
    prepared_root: Path,
    output_root: Path,
    config_path: Path,
    profile_path: Path,
    expected_preparation_signature: str | None = None,
) -> dict[str, Any]:
    """Render the exact v11/v4 reader representation, pending human review."""

    protocol_root = Path(protocol_root).resolve()
    prepared_root = Path(prepared_root).resolve()
    output_root = Path(output_root).resolve()
    config_path = Path(config_path).resolve()
    profile_path = Path(profile_path).resolve()
    preflight = verify_lld_mmri_v23_blind_inputs(
        protocol_root=protocol_root,
        prepared_root=prepared_root,
        expected_preparation_signature=expected_preparation_signature,
    )
    config = _validate_config(config_path)
    prepared_case_ids = list(_load(prepared_root / "summary.json")["case_ids"])
    rows = _prepared_rows(prepared_root, prepared_case_ids)
    if preflight["case_count"] != len(rows):
        raise PipelineError("Preflight e inputs LLD-MMRI divergiram.")
    protocol_case_count = int(preflight.get("protocol_case_count", preflight["case_count"]))
    technical_failure_case_ids = list(
        preflight.get("technical_failure_case_ids", [])
    )
    if (
        preflight.get("technical_failure_case_count", 0)
        != len(technical_failure_case_ids)
        or protocol_case_count != len(rows) + len(technical_failure_case_ids)
        or set(prepared_case_ids) & set(technical_failure_case_ids)
    ):
        raise PipelineError("Contrato 335/321/14 divergiu antes dos paineis.")
    if output_root.exists():
        raise PipelineError("Paineis LLD-MMRI v23 existentes; sobrescrita recusada.")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.with_name(f".{output_root.name}.incomplete")
    checkpoint_context = {
        "schema": "argos-lld-mmri-v23-panel-checkpoint-v1",
        "preparation_signature": preflight["preparation_signature"],
        "inputs_sha256": preflight["inputs_sha256"],
        "config_sha256": _sha256(config_path),
        "profile_sha256": _sha256(profile_path),
        "case_ids": prepared_case_ids,
        "protocol_case_count": protocol_case_count,
        "technical_failure_case_ids": technical_failure_case_ids,
        "ground_truth_read": False,
        "lesion_masks_used": False,
    }
    checkpoint_context["checkpoint_signature"] = _canonical_sha(checkpoint_context)
    checkpoint_path = staging / "checkpoint_cases.jsonl"
    if staging.exists():
        try:
            persisted_context = _load(staging / "checkpoint_context.json")
            records = _load_jsonl_checkpoint(checkpoint_path)
        except PipelineError as exc:
            raise PipelineError("Checkpoint de paineis LLD-MMRI invalido.") from exc
        if persisted_context != checkpoint_context:
            raise PipelineError("Checkpoint de paineis pertence a outro protocolo.")
        if [record.get("case_id") for record in records] != prepared_case_ids[: len(records)]:
            raise PipelineError("Ordem do checkpoint de paineis foi adulterada.")
        for record in records:
            case_id = str(record["case_id"])
            panel = _safe(staging, str(record.get("panel", "")))
            candidate = _safe(staging, str(record.get("candidate_manifest", "")))
            if (
                not panel.is_file()
                or not candidate.is_file()
                or _sha256(panel) != record.get("panel_sha256")
                or _sha256(candidate) != record.get("candidate_manifest_sha256")
            ):
                raise PipelineError("Hash do checkpoint de paineis divergiu.")
    else:
        staging.mkdir()
        _write_json_atomic(staging / "checkpoint_context.json", checkpoint_context)
        records = []
        _write_jsonl_checkpoint_atomic(checkpoint_path, records)
    try:
        current_case_id: str | None = None
        for row in rows[len(records):]:
            case_started = time.perf_counter()
            case_id = str(row["case_id"])
            current_case_id = case_id
            files = _case_files(prepared_root, row)
            case_dir = staging / case_id
            if case_dir.exists():
                if not case_dir.resolve().is_relative_to(staging.resolve()):
                    raise PipelineError("Diretorio parcial inseguro nos paineis.")
                shutil.rmtree(case_dir)
            case_dir.mkdir()
            case_manifest = case_dir / "case_manifest.json"
            _write_json_atomic(
                case_manifest,
                {
                    "case_id": case_id,
                    "policy": "anonymize",
                    "regulatory_state": "PESQUISA",
                    "modality": "MRI",
                },
            )
            result = generate_liver_panel_multiphase(
                phase_paths={phase: files[role] for phase, role in ROLE_TO_PHASE.items()},
                liver_mask_path=files[MASK_ROLE],
                case_manifest_path=case_manifest,
                organ_profile=load_profile(profile_path),
                screening_config=config,
                output_dir=case_dir,
                model_trace=model_trace(config),
                visible_phi_confirmed=False,
                phase_support_fractions={
                    phase: float(row["dynamic_liver_support_fraction"][role])
                    for phase, role in ROLE_TO_PHASE.items()
                },
            )
            panel_manifest = _load(result.manifest_path)
            if (
                panel_manifest.get("case_id") != case_id
                or panel_manifest.get("lesion_pre_marked") is not False
                or panel_manifest.get("panel_count") != 11
                or len(tuple(result.panel_paths)) != 1
                or panel_manifest.get("visible_phi_confirmed") is not False
            ):
                raise PipelineError("Painel LLD-MMRI violou uniform_9 ou cegamento.")
            with Image.open(result.panel_path) as image:
                width, height = image.size
                metadata = sorted(image.info)
            if metadata:
                raise PipelineError("PNG LLD-MMRI contem metadados inesperados.")
            panel_sha = _sha256(result.panel_path)
            base = {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "status": "rendered_pending_human_review",
                "source_case_signature": row["case_signature"],
                "panel_filename": result.panel_path.name,
                "panel_sha256": panel_sha,
                "panel_bytes": result.panel_path.stat().st_size,
                "panel_width": width,
                "panel_height": height,
                "panel_manifest_filename": result.manifest_path.name,
                "panel_manifest_sha256": _sha256(result.manifest_path),
                "elapsed_seconds": time.perf_counter() - case_started,
                "visible_phi_confirmed": False,
                "eligible_for_inference": False,
                "lesion_mask_used": False,
                "pathology_label_used": False,
                "ground_truth_read": False,
                "research_only": True,
                "clinical_use_allowed": False,
                "requires_human_review": True,
            }
            manifest = dict(base)
            manifest["candidate_signature"] = _canonical_sha(base)
            _write_json_atomic(case_dir / "candidate_manifest.json", manifest)
            records.append(
                {
                    "case_id": case_id,
                    "candidate_manifest": f"{case_id}/candidate_manifest.json",
                    "candidate_manifest_sha256": _sha256(case_dir / "candidate_manifest.json"),
                    "candidate_signature": manifest["candidate_signature"],
                    "panel": f"{case_id}/{result.panel_path.name}",
                    "panel_sha256": panel_sha,
                    "elapsed_seconds": manifest["elapsed_seconds"],
                }
            )
            _write_jsonl_checkpoint_atomic(checkpoint_path, records)
        base = {
            "schema": COHORT_SCHEMA,
            "status": "complete_pending_human_review",
            "protocol_case_count": protocol_case_count,
            "case_count": len(records),
            "case_ids": prepared_case_ids,
            "technical_failure_case_count": len(technical_failure_case_ids),
            "technical_failure_case_ids": technical_failure_case_ids,
            "technical_failures_excluded_from_inference": True,
            "technical_failures_count_as_primary_metric_errors": True,
            "cases": records,
            "preparation_signature": preflight["preparation_signature"],
            "inputs_sha256": preflight["inputs_sha256"],
            "config_sha256": _sha256(config_path),
            "profile_sha256": _sha256(profile_path),
            "all_panels_uniform9": True,
            "all_panels_pending_human_review": True,
            "lesion_masks_used": False,
            "pathology_labels_used": False,
            "ground_truth_read": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        summary = dict(base)
        summary["cohort_signature"] = _canonical_sha(base)
        _write_json_atomic(staging / "cohort_manifest.json", summary)
        (staging / "checkpoint_context.json").unlink(missing_ok=True)
        checkpoint_path.unlink(missing_ok=True)
        (staging / "checkpoint_cases.backup.jsonl").unlink(missing_ok=True)
        (staging / "failure.json").unlink(missing_ok=True)
        _publish_directory(staging, output_root)
        return summary
    except Exception as exc:
        _write_json_atomic(
            staging / "failure.json",
            {
                "schema": "argos-lld-mmri-v23-panel-checkpoint-failure-v1",
                "case_id": current_case_id,
                "completed_case_count": len(records),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "ground_truth_read": False,
                "lesion_masks_used": False,
                "resumable_after_root_cause_review": True,
            },
        )
        raise


def build_lld_mmri_v23_uniform9_gallery(
    *, panel_root: Path, output_dir: Path
) -> dict[str, Any]:
    """Create a local label-blind gallery; approval remains a separate action."""

    panel_root = Path(panel_root).resolve()
    output_dir = Path(output_dir).resolve()
    cohort_path = panel_root / "cohort_manifest.json"
    cohort = _load(cohort_path)
    unsigned = dict(cohort)
    signature = unsigned.pop("cohort_signature", None)
    if (
        cohort.get("schema") != COHORT_SCHEMA
        or cohort.get("status") != "complete_pending_human_review"
        or signature != _canonical_sha(unsigned)
        or cohort.get("ground_truth_read") is not False
        or cohort.get("lesion_masks_used") is not False
        or cohort.get("protocol_case_count")
        != cohort.get("case_count", 0) + cohort.get("technical_failure_case_count", 0)
        or cohort.get("technical_failure_case_count")
        != len(cohort.get("technical_failure_case_ids", []))
        or cohort.get("technical_failures_excluded_from_inference") is not True
        or cohort.get("technical_failures_count_as_primary_metric_errors") is not True
    ):
        raise PipelineError("Coorte LLD-MMRI nao esta pronta para galeria.")
    if output_dir.exists():
        raise PipelineError("Galeria LLD-MMRI v23 existente; sobrescrita recusada.")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.parent / f"._lldv23gallery_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    (staging / "images").mkdir()
    cases: list[dict[str, Any]] = []
    cards: list[str] = []
    try:
        for number, record in enumerate(cohort["cases"], 1):
            elapsed = record.get("elapsed_seconds")
            if (
                isinstance(elapsed, bool)
                or not isinstance(elapsed, (int, float))
                or not math.isfinite(float(elapsed))
                or float(elapsed) < 0
            ):
                raise PipelineError("Tempo de renderizacao do painel LLD-MMRI invalido.")
            source = _safe(panel_root, str(record["panel"]))
            if not source.is_file() or _sha256(source) != record["panel_sha256"]:
                raise PipelineError("Painel LLD-MMRI ausente ou adulterado.")
            name = f"{number:03d}_{record['case_id']}.png"
            target = staging / "images" / name
            shutil.copyfile(source, target)
            if _sha256(target) != record["panel_sha256"]:
                raise PipelineError("Copia da galeria LLD-MMRI divergiu.")
            relative = f"images/{name}"
            cases.append(
                {
                    "number": number,
                    "case_id": record["case_id"],
                    "image": relative,
                    "sha256": record["panel_sha256"],
                }
            )
            cards.append(
                '<article class="card">'
                f'<h2>{number}. {html.escape(str(record["case_id"]))}</h2>'
                f'<img loading="lazy" src="{html.escape(relative)}" alt="Painel técnico {number}">'
                '<p>Avaliar fígado visível, crop completo, orientação, fusão RGB, '
                'contorno e ausência de PHI. Não avaliar diagnóstico.</p></article>'
            )
        document = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>ARGOS v23 — LLD-MMRI, gate técnico cego</title><style>
body{font-family:system-ui;background:#111827;color:#e5e7eb;margin:0;padding:24px}
.notice,.card{background:#1f2937;border-radius:10px;padding:14px}.notice{margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(560px,1fr));gap:20px}
.card img{width:100%;height:auto;background:#000}.card h2{font-size:16px}.card p{color:#cbd5e1}</style>
</head><body><h1>ARGOS v23 — galeria técnica cega LLD-MMRI</h1>
<div class="notice"><b>Não avalie diagnóstico.</b> Confirme apenas qualidade técnica. Nenhum label ou máscara de lesão está disponível. A inferência permanece bloqueada até aprovação explícita de todos os casos.</div>
<main class="grid">""" + "".join(cards) + "</main></body></html>"
        (staging / "index.html").write_text(document, encoding="utf-8")
        base = {
            "schema": GALLERY_SCHEMA,
            "status": "pending_human_review",
            "case_count": len(cases),
            "protocol_case_count": cohort.get("protocol_case_count", len(cases)),
            "technical_failure_case_count": cohort.get(
                "technical_failure_case_count", 0
            ),
            "technical_failure_case_ids": cohort.get(
                "technical_failure_case_ids", []
            ),
            "technical_failures_excluded_from_inference": cohort.get(
                "technical_failures_excluded_from_inference", True
            ),
            "technical_failures_count_as_primary_metric_errors": cohort.get(
                "technical_failures_count_as_primary_metric_errors", True
            ),
            "cases": cases,
            "source_cohort_sha256": _sha256(cohort_path),
            "source_cohort_signature": cohort["cohort_signature"],
            "index_sha256": _sha256(staging / "index.html"),
            "reviewer": None,
            "approved": False,
            "ground_truth_read": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        manifest = dict(base)
        manifest["gallery_signature"] = _canonical_sha(base)
        _write_json_atomic(staging / "gallery_manifest.json", manifest)
        _publish_directory(staging, output_dir)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = [
    "CASE_SCHEMA",
    "COHORT_SCHEMA",
    "GALLERY_SCHEMA",
    "build_lld_mmri_v23_uniform9_gallery",
    "build_lld_mmri_v23_uniform9_panels",
]

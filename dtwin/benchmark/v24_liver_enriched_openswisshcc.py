"""Predeclare and render the OpenSwissHCC v24 liver-enriched candidate.

This stage is deliberately label-free.  It freezes how a future liver-enriched
signal may enter the v23 family, then renders a deterministic technical pilot
that must pass human review before full-cohort inference.
"""
from __future__ import annotations

import copy
import hashlib
import html
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.lld_mmri_v23_preparation import (
    _load_jsonl_checkpoint,
    _write_jsonl_checkpoint_atomic,
)
from dtwin.benchmark.openswisshcc_alignment import _publish_directory
from dtwin.benchmark.openswisshcc_enhancement_maps import _registered_paths
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.benchmark.v23_retrospective_multicohort_phase3 import (
    _safe_declared_file,
    verify_phase3_exact_v23_signals,
)
from dtwin.benchmark.v23_retrospective_multicohort_phase4 import (
    verify_phase4_evaluation,
)
from dtwin.core import PipelineError
from dtwin.medgemma_client import load_screening_config, model_trace
from dtwin.medgemma_panel_liver_enriched import (
    LIVER_ENRICHED_POLICY,
    generate_liver_enriched_panel_set_multiphase,
)
from dtwin.medgemma_screening import _write_json_atomic


PROTOCOL_SCHEMA = "argos-openswisshcc-v24-liver-enriched-protocol-v1"
PILOT_SCHEMA = "argos-openswisshcc-v24-liver-enriched-pilot-v1"
GALLERY_SCHEMA = "argos-openswisshcc-v24-liver-enriched-gallery-v1"
REVIEW_SCHEMA = "argos-openswisshcc-v24-liver-enriched-review-v1"
FULL_SCHEMA = "argos-openswisshcc-v24-liver-enriched-full-cohort-v1"
FULL_VERIFICATION_SCHEMA = (
    "argos-openswisshcc-v24-liver-enriched-full-verification-v1"
)
DEVELOPMENT_INPUT_SCHEMA = "argos-public-liver-mri-input-v1"
HOLDOUT_INPUT_SCHEMA = "argos-public-liver-mri-holdout-input-v1"
DEV_MODE_SCHEMA = "argos-openswisshcc-candidate-volume-cohort-v16"
HOLDOUT_ALIGNMENT_SCHEMA = "argos-openswisshcc-holdout-alignment-summary-v1"
PILOT_CASE_COUNT = 10


def _load(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def _jsonl(path: Path, description: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise PipelineError(f"{description} sem objetos JSONL.")
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise PipelineError(f"Artefato ausente: {path}.") from exc
    return digest.hexdigest()


def _inputs(
    development_manifest: Path, holdout_manifest: Path
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for split, path, schema in (
        ("development", Path(development_manifest).resolve(), DEVELOPMENT_INPUT_SCHEMA),
        ("holdout_consumed", Path(holdout_manifest).resolve(), HOLDOUT_INPUT_SCHEMA),
    ):
        root = path.parent.parent / "inputs"
        for row in _jsonl(path, f"Inputs {split}"):
            case_id, files = row.get("case_id"), row.get("files")
            if (
                row.get("schema") != schema
                or not isinstance(case_id, str)
                or case_id in indexed
                or row.get("research_only") is not True
                or row.get("clinical_use_allowed") is not False
                or not isinstance(files, list)
            ):
                raise PipelineError("Input v24 inválido ou duplicado.")
            by_role = {item.get("role"): item for item in files if isinstance(item, dict)}
            if not {"t1_venous", "liver_mask_venous"} <= set(by_role):
                raise PipelineError(f"Input v24 sem venosa/máscara hepática: {case_id}.")
            indexed[case_id] = {
                "split": split,
                "venous": _safe_declared_file(root, by_role["t1_venous"]),
                "mask": _safe_declared_file(root, by_role["liver_mask_venous"]),
                "hashes": {
                    "t1_venous": by_role["t1_venous"]["sha256"],
                    "liver_mask_venous": by_role["liver_mask_venous"]["sha256"],
                },
            }
    return indexed


def _modes(
    *,
    development_mode_manifest: Path,
    holdout_alignment_summary: Path,
    eligible_ids: set[str],
) -> dict[str, str]:
    dev = _load(development_mode_manifest, "Modos de desenvolvimento v16")
    cases = dev.get("cases")
    if (
        dev.get("schema") != DEV_MODE_SCHEMA
        or dev.get("case_count") != 87
        or not isinstance(cases, list)
        or len(cases) != 87
    ):
        raise PipelineError("Manifesto de modos development inválido.")
    modes: dict[str, str] = {}
    for row in cases:
        case_id, mode = row.get("case_id"), row.get("dynamic_alignment_mode")
        if (
            not isinstance(case_id, str)
            or case_id in modes
            or mode not in {
                "registered_to_venous",
                "original_unregistered_physical_center",
            }
        ):
            raise PipelineError("Modo development v24 inválido.")
        modes[case_id] = (
            "registered_multiphase_rgb"
            if mode == "registered_to_venous"
            else "venous_replicated_grayscale"
        )
    hold = _load(holdout_alignment_summary, "Alinhamento holdout")
    if (
        hold.get("schema") != HOLDOUT_ALIGNMENT_SCHEMA
        or hold.get("labels_read") is not False
        or hold.get("lesion_masks_read") != 0
        or not isinstance(hold.get("alignments"), list)
    ):
        raise PipelineError("Resumo de alinhamento holdout inválido.")
    for row in hold["alignments"]:
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or case_id in modes:
            raise PipelineError("Caso holdout v24 duplicado.")
        modes[case_id] = "registered_multiphase_rgb"
    if set(modes) != eligible_ids:
        missing = sorted(eligible_ids - set(modes))
        extra = sorted(set(modes) - eligible_ids)
        raise PipelineError(f"Modos v24 divergem dos elegíveis; missing={missing}, extra={extra}.")
    return modes


def _pilot_ids(modes: dict[str, str]) -> list[str]:
    fallback = sorted(
        case_id
        for case_id, mode in modes.items()
        if mode == "venous_replicated_grayscale"
    )
    aligned = sorted(
        (
            case_id
            for case_id, mode in modes.items()
            if mode == "registered_multiphase_rgb"
        ),
        key=lambda case_id: hashlib.sha256(
            f"v24-liver-enriched-pilot|{case_id}".encode()
        ).hexdigest(),
    )
    selected = fallback + aligned[: PILOT_CASE_COUNT - len(fallback)]
    if len(selected) != PILOT_CASE_COUNT or len(set(selected)) != PILOT_CASE_COUNT:
        raise PipelineError("Seleção determinística do piloto v24 falhou.")
    return selected


def freeze_v24_liver_enriched_protocol(
    *,
    phase4_evaluation_root: Path,
    phase4_prediction_root: Path,
    phase3_root: Path,
    phase2_root: Path,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
    development_manifest: Path,
    holdout_manifest: Path,
    development_mode_manifest: Path,
    holdout_alignment_summary: Path,
    config_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    phase4 = verify_phase4_evaluation(
        evaluation_root=phase4_evaluation_root,
        prediction_root=phase4_prediction_root,
        phase3_root=phase3_root,
        phase2_root=phase2_root,
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    if phase4.get("status") != "phase4_statistical_gate_failed":
        raise PipelineError("v24 só pode iniciar após o resultado v23 puro congelado.")
    phase3 = verify_phase3_exact_v23_signals(
        phase3_root=phase3_root,
        phase2_root=phase2_root,
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    signal_rows = _jsonl(
        Path(phase3_root) / phase3["artifacts"]["exact_v23_signals"],
        "Sinais elegíveis v24",
    )
    eligible_ids = {str(row["case_id"]) for row in signal_rows}
    inputs = _inputs(development_manifest, holdout_manifest)
    if not eligible_ids <= set(inputs):
        raise PipelineError("Inputs v24 não cobrem os casos elegíveis.")
    modes = _modes(
        development_mode_manifest=development_mode_manifest,
        holdout_alignment_summary=holdout_alignment_summary,
        eligible_ids=eligible_ids,
    )
    config = load_screening_config(config_path)
    if (
        config.get("panel", {}).get("spatial_focus") != "liver_enriched_full_fov"
        or config.get("medgemma", {}).get("response_mode") != "choice_classification"
        or config.get("rag", {}).get("enabled") is not False
    ):
        raise PipelineError("Config v24 deve mudar apenas a representação liver-enriched.")
    pilot_ids = _pilot_ids(modes)
    body = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_before_v24_liver_enriched_signal_generation",
        "candidate_id": "v24_candidate_1_v23_plus_liver_enriched",
        "predeclared_order_index": 1,
        "source_v23_evaluation_signature": phase4["evaluation_signature"],
        "source_v23_phase3_signature": phase3["phase3_signature"],
        "case_count": 132,
        "signal_eligible_case_count": len(eligible_ids),
        "technical_failures_carried_forward": 2,
        "eligible_case_ids": sorted(eligible_ids),
        "representation": {
            "spatial_policy": LIVER_ENRICHED_POLICY,
            "registered_multiphase_rgb_count": sum(
                mode == "registered_multiphase_rgb" for mode in modes.values()
            ),
            "venous_replicated_grayscale_count": sum(
                mode == "venous_replicated_grayscale" for mode in modes.values()
            ),
            "panels_per_case": "2_or_3",
            "mask_scope": "coarse_axial_localization_only_not_rendered_not_cropped",
        },
        "new_signal": {
            "name": "liver_enriched_max_positive_probability",
            "definition": "maximum_panel_probability_for_choice_POSITIVA",
            "direction": "higher_more_suspicious",
            "discrete_choice_not_used_as_primary_fusion_signal": True,
        },
        "fixed_candidate_fusion": {
            "v23_family_weight": 0.80,
            "liver_enriched_signal_weight": 0.20,
            "ecdf_fit_on_outer_training_only": True,
            "threshold_fit_on_outer_training_only": True,
            "weight_tuning_after_results_forbidden": True,
        },
        "acceptance": {
            "loocv_sensitivity_minimum": 0.75,
            "loocv_specificity_minimum": 0.75,
            "technical_failures_count_as_errors": True,
            "inconclusive_counts_as_error": True,
            "maximum_case_seconds": 180.0,
            "must_improve_minimum_sensitivity_specificity_over_v23": True,
            "best_fold_cannot_qualify": True,
        },
        "pilot": {
            "case_count": PILOT_CASE_COUNT,
            "case_ids": pilot_ids,
            "selection": "all_3_predeclared_venous_fallbacks_plus_7_sha256_ranked_registered_cases",
            "human_review_required_before_full_cohort": True,
        },
        "source_hashes": {
            "phase4_evaluation": _sha256(Path(phase4_evaluation_root) / "evaluation.json"),
            "phase3_summary": _sha256(Path(phase3_root) / "summary.json"),
            "development_manifest": _sha256(Path(development_manifest)),
            "holdout_manifest": _sha256(Path(holdout_manifest)),
            "development_mode_manifest": _sha256(Path(development_mode_manifest)),
            "holdout_alignment_summary": _sha256(Path(holdout_alignment_summary)),
            "config": _sha256(Path(config_path)),
        },
        "labels_read": False,
        "lesion_masks_read": 0,
        "inference_executed": False,
        "metrics_calculated": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    protocol = {**body, "protocol_signature": _canonical_sha(body)}
    output = Path(output_path).resolve()
    if output.exists():
        raise PipelineError("Protocolo v24 liver-enriched já existe.")
    _write_json_atomic(output, protocol)
    return protocol


def verify_v24_liver_enriched_protocol(
    *, protocol_path: Path, config_path: Path
) -> dict[str, Any]:
    protocol = _load(protocol_path, "Protocolo v24 liver-enriched")
    unsigned = dict(protocol)
    signature = unsigned.pop("protocol_signature", None)
    if (
        protocol.get("schema") != PROTOCOL_SCHEMA
        or protocol.get("status")
        != "frozen_before_v24_liver_enriched_signal_generation"
        or signature != _canonical_sha(unsigned)
        or protocol.get("case_count") != 132
        or protocol.get("signal_eligible_case_count") != 130
        or protocol.get("technical_failures_carried_forward") != 2
        or protocol.get("source_hashes", {}).get("config") != _sha256(Path(config_path))
        or protocol.get("labels_read") is not False
        or protocol.get("lesion_masks_read") != 0
        or protocol.get("metrics_calculated") is not False
    ):
        raise PipelineError("Protocolo v24 liver-enriched adulterado.")
    return protocol


def _fallback_config(config: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(config)
    result["panel"]["fusion"]["channel_map"] = {
        "red": "pv",
        "green": "pv",
        "blue": "pv",
    }
    result["panel"]["fusion"]["partial_fov_fallback_phase"] = "pv"
    return result


def build_v24_liver_enriched_pilot(
    *,
    protocol_path: Path,
    config_path: Path,
    development_manifest: Path,
    holdout_manifest: Path,
    development_mode_manifest: Path,
    holdout_alignment_summary: Path,
    development_alignment_root: Path,
    holdout_alignment_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    protocol = verify_v24_liver_enriched_protocol(
        protocol_path=protocol_path, config_path=config_path
    )
    eligible = set(protocol["eligible_case_ids"])
    inputs = _inputs(development_manifest, holdout_manifest)
    modes = _modes(
        development_mode_manifest=development_mode_manifest,
        holdout_alignment_summary=holdout_alignment_summary,
        eligible_ids=eligible,
    )
    config = load_screening_config(config_path)
    fallback_config = _fallback_config(config)
    destination = Path(output_root).resolve()
    if destination.exists():
        raise PipelineError("Piloto v24 liver-enriched já existe.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f"._v24_liver_enriched_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    records: list[dict[str, Any]] = []
    try:
        for number, case_id in enumerate(protocol["pilot"]["case_ids"], 1):
            source, mode = inputs[case_id], modes[case_id]
            case_dir = staging / case_id
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
            source_hashes = dict(source["hashes"])
            if mode == "registered_multiphase_rgb":
                alignment_root = (
                    Path(development_alignment_root)
                    if source["split"] == "development"
                    else Path(holdout_alignment_root)
                )
                art, delayed, registered_hashes = _registered_paths(
                    case_id, alignment_root
                )
                phases = {"art": art, "pv": source["venous"], "del": delayed}
                active_config = config
                source_hashes.update(registered_hashes)
            else:
                phases = {"pv": source["venous"]}
                active_config = fallback_config
            result = generate_liver_enriched_panel_set_multiphase(
                phase_paths=phases,
                coarse_liver_mask_path=source["mask"],
                case_manifest_path=case_manifest,
                screening_config=active_config,
                output_dir=case_dir,
                model_trace=model_trace(active_config),
                visible_phi_confirmed=False,
            )
            manifest = _load(result.manifest_path, "Manifesto de painel v24")
            if (
                manifest.get("spatial_policy") != LIVER_ENRICHED_POLICY
                or manifest.get("organ_mask_rendered") is not False
                or manifest.get("lesion_mask_used") is not False
                or manifest.get("ground_truth_used") is not False
                or manifest.get("crop_to_liver") is not False
                or manifest.get("contour_rendered") is not False
                or result.panel_count not in {2, 3}
            ):
                raise PipelineError("Painel piloto v24 violou o contrato visual.")
            panels = [
                {
                    "panel_number": index,
                    "relative_path": f"{case_id}/{path.name}",
                    "sha256": _sha256(path),
                }
                for index, path in enumerate(result.panel_paths, 1)
            ]
            records.append(
                {
                    "number": number,
                    "case_id": case_id,
                    "source_split": source["split"],
                    "input_mode": mode,
                    "panel_count": len(panels),
                    "panels": panels,
                    "manifest": f"{case_id}/{result.manifest_path.name}",
                    "manifest_sha256": _sha256(result.manifest_path),
                    "selection_mode": manifest["localization"]["selection_mode"],
                    "source_hashes": source_hashes,
                }
            )
        body = {
            "schema": PILOT_SCHEMA,
            "status": "complete_pending_human_review",
            "protocol_signature": protocol["protocol_signature"],
            "case_count": len(records),
            "case_ids": [row["case_id"] for row in records],
            "total_panel_count": sum(row["panel_count"] for row in records),
            "cases": records,
            "labels_read": False,
            "lesion_masks_read": 0,
            "inference_executed": False,
            "eligible_for_full_generation": False,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        cohort = {**body, "pilot_signature": _canonical_sha(body)}
        _write_json_atomic(staging / "cohort_manifest.json", cohort)
        _publish_directory(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return cohort


def build_v24_liver_enriched_gallery(
    *, pilot_root: Path, output_root: Path
) -> dict[str, Any]:
    pilot_root = Path(pilot_root).resolve()
    cohort = _load(pilot_root / "cohort_manifest.json", "Coorte piloto v24")
    unsigned = dict(cohort)
    signature = unsigned.pop("pilot_signature", None)
    if (
        cohort.get("schema") != PILOT_SCHEMA
        or signature != _canonical_sha(unsigned)
        or cohort.get("status") != "complete_pending_human_review"
        or cohort.get("labels_read") is not False
        or cohort.get("lesion_masks_read") != 0
    ):
        raise PipelineError("Coorte piloto v24 adulterada.")
    destination = Path(output_root).resolve()
    if destination.exists():
        raise PipelineError("Galeria piloto v24 já existe.")
    staging = destination.parent / f"._v24_gallery_{uuid.uuid4().hex[:8]}"
    images = staging / "images"
    images.mkdir(parents=True)
    cards: list[str] = []
    items: list[dict[str, Any]] = []
    try:
        for record in cohort["cases"]:
            copied = []
            tags = []
            for panel in record["panels"]:
                source = (pilot_root / panel["relative_path"]).resolve()
                if (
                    not source.is_relative_to(pilot_root)
                    or _sha256(source) != panel["sha256"]
                ):
                    raise PipelineError("Painel mudou antes da galeria v24.")
                name = (
                    f"{record['number']:02d}_{record['case_id']}"
                    f"_p{panel['panel_number']:02d}.png"
                )
                target = images / name
                shutil.copyfile(source, target)
                relative = f"images/{name}"
                copied.append({"image": relative, "sha256": _sha256(target)})
                tags.append(
                    f"<img src='{html.escape(relative)}' "
                    f"alt='{html.escape(record['case_id'])} painel {panel['panel_number']}'>"
                )
            cards.append(
                "<section><h2>"
                f"{record['number']}. {html.escape(record['case_id'])}"
                "</h2><p>"
                f"modo: {html.escape(record['input_mode'])} | "
                f"seleção: {html.escape(record['selection_mode'])}"
                "</p><div class='panels'>"
                + "".join(tags)
                + "</div></section>"
            )
            items.append(
                {
                    "number": record["number"],
                    "case_id": record["case_id"],
                    "input_mode": record["input_mode"],
                    "panels": copied,
                }
            )
        css = (
            "body{background:#111827;color:#e5e7eb;font:15px system-ui;margin:20px}"
            "section{background:#1f2937;padding:14px;margin:16px 0;border-radius:8px}"
            ".panels{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:10px}"
            "img{width:100%;height:auto;background:#000}h1,h2{margin:4px 0 10px}"
        )
        (staging / "index.html").write_text(
            "<!doctype html><meta charset='utf-8'><title>ARGOS v24 pilot</title>"
            f"<style>{css}</style><h1>ARGOS v24 — liver-enriched pilot10</h1>"
            "<p>Avaliar: fígado visível em todos os painéis, ausência de crop/contorno, "
            "intercalação útil e ausência de PHI visível. Não avaliar diagnóstico.</p>"
            + "".join(cards),
            encoding="utf-8",
        )
        body = {
            "schema": GALLERY_SCHEMA,
            "status": "pending_human_review",
            "pilot_signature": cohort["pilot_signature"],
            "case_count": len(items),
            "items": items,
            "labels_read": False,
            "lesion_masks_read": 0,
            "inference_authorized": False,
        }
        gallery = {**body, "gallery_signature": _canonical_sha(body)}
        _write_json_atomic(staging / "gallery_manifest.json", gallery)
        _publish_directory(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return gallery


def approve_v24_liver_enriched_gallery(
    *,
    protocol_path: Path,
    config_path: Path,
    gallery_root: Path,
    reviewer: str,
    output_path: Path,
) -> dict[str, Any]:
    """Persist the explicit technical approval needed before full rendering."""

    protocol = verify_v24_liver_enriched_protocol(
        protocol_path=protocol_path, config_path=config_path
    )
    gallery_path = Path(gallery_root).resolve() / "gallery_manifest.json"
    gallery = _load(gallery_path, "Galeria piloto v24")
    unsigned_gallery = dict(gallery)
    gallery_signature = unsigned_gallery.pop("gallery_signature", None)
    clean_reviewer = reviewer.strip()
    if (
        gallery.get("schema") != GALLERY_SCHEMA
        or gallery_signature != _canonical_sha(unsigned_gallery)
        or gallery.get("status") != "pending_human_review"
        or gallery.get("pilot_signature") is None
        or gallery.get("case_count") != PILOT_CASE_COUNT
        or gallery.get("labels_read") is not False
        or gallery.get("lesion_masks_read") != 0
        or gallery.get("inference_authorized") is not False
        or not clean_reviewer
    ):
        raise PipelineError("Galeria v24 não pode ser aprovada.")
    body = {
        "schema": REVIEW_SCHEMA,
        "status": "approved_for_full_label_blind_generation",
        "protocol_signature": protocol["protocol_signature"],
        "gallery_signature": gallery_signature,
        "gallery_manifest_sha256": _sha256(gallery_path),
        "reviewer": clean_reviewer,
        "technical_checks": {
            "liver_visible_in_all_panels": True,
            "no_candidate_revealing_crop_or_contour": True,
            "axial_distribution_adequate": True,
            "no_visible_phi": True,
        },
        "labels_read": False,
        "lesion_masks_read": 0,
        "inference_authorized": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    review = {**body, "review_signature": _canonical_sha(body)}
    output = Path(output_path).resolve()
    if output.exists():
        raise PipelineError("Revisão v24 já existe; sobrescrita recusada.")
    _write_json_atomic(output, review)
    return review


def _verify_review(
    *,
    review_path: Path,
    protocol: dict[str, Any],
    gallery_root: Path,
) -> dict[str, Any]:
    review = _load(review_path, "Revisão v24")
    unsigned = dict(review)
    signature = unsigned.pop("review_signature", None)
    gallery_path = Path(gallery_root).resolve() / "gallery_manifest.json"
    if (
        review.get("schema") != REVIEW_SCHEMA
        or signature != _canonical_sha(unsigned)
        or review.get("status") != "approved_for_full_label_blind_generation"
        or review.get("protocol_signature") != protocol["protocol_signature"]
        or review.get("gallery_manifest_sha256") != _sha256(gallery_path)
        or review.get("labels_read") is not False
        or review.get("lesion_masks_read") != 0
        or review.get("inference_authorized") is not False
        or not all(review.get("technical_checks", {}).values())
    ):
        raise PipelineError("Revisão técnica v24 inválida ou adulterada.")
    return review


def _validate_full_record(root: Path, record: dict[str, Any]) -> None:
    case_id = str(record.get("case_id", ""))
    manifest_path = (root / str(record.get("manifest", ""))).resolve()
    panels = record.get("panels")
    if (
        not case_id
        or not manifest_path.is_relative_to(root)
        or not manifest_path.is_file()
        or _sha256(manifest_path) != record.get("manifest_sha256")
        or not isinstance(panels, list)
        or len(panels) not in {2, 3}
        or record.get("panel_count") != len(panels)
    ):
        raise PipelineError("Registro da coorte v24 está incompleto ou adulterado.")
    manifest = _load(manifest_path, "Manifesto de painel v24")
    if (
        manifest.get("spatial_policy") != LIVER_ENRICHED_POLICY
        or manifest.get("organ_mask_rendered") is not False
        or manifest.get("lesion_mask_used") is not False
        or manifest.get("ground_truth_used") is not False
        or manifest.get("crop_to_liver") is not False
        or manifest.get("contour_rendered") is not False
        or manifest.get("panel_image_count") != len(panels)
    ):
        raise PipelineError("Manifesto da coorte v24 violou o contrato visual.")
    for number, panel in enumerate(panels, 1):
        panel_path = (root / str(panel.get("relative_path", ""))).resolve()
        if (
            panel.get("panel_number") != number
            or not panel_path.is_relative_to(root)
            or not panel_path.is_file()
            or _sha256(panel_path) != panel.get("sha256")
        ):
            raise PipelineError("Painel da coorte v24 ausente ou adulterado.")


def build_v24_liver_enriched_full_cohort(
    *,
    protocol_path: Path,
    review_path: Path,
    gallery_root: Path,
    config_path: Path,
    development_manifest: Path,
    holdout_manifest: Path,
    development_mode_manifest: Path,
    holdout_alignment_summary: Path,
    development_alignment_root: Path,
    holdout_alignment_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Render all 130 eligible cases with a durable per-case checkpoint."""

    protocol = verify_v24_liver_enriched_protocol(
        protocol_path=protocol_path, config_path=config_path
    )
    review = _verify_review(
        review_path=review_path, protocol=protocol, gallery_root=gallery_root
    )
    eligible_ids = list(protocol["eligible_case_ids"])
    eligible = set(eligible_ids)
    inputs = _inputs(development_manifest, holdout_manifest)
    modes = _modes(
        development_mode_manifest=development_mode_manifest,
        holdout_alignment_summary=holdout_alignment_summary,
        eligible_ids=eligible,
    )
    config = load_screening_config(config_path)
    fallback_config = _fallback_config(config)
    destination = Path(output_root).resolve()
    if destination.exists():
        raise PipelineError("Coorte completa v24 já existe; sobrescrita recusada.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(f".{destination.name}.incomplete")
    context = {
        "schema": "argos-openswisshcc-v24-liver-enriched-checkpoint-v1",
        "protocol_signature": protocol["protocol_signature"],
        "review_signature": review["review_signature"],
        "config_sha256": _sha256(Path(config_path)),
        "case_ids": eligible_ids,
        "labels_read": False,
        "lesion_masks_read": 0,
    }
    context["checkpoint_signature"] = _canonical_sha(context)
    checkpoint_path = staging / "checkpoint_cases.jsonl"
    if staging.exists():
        persisted = _load(
            staging / "checkpoint_context.json", "Contexto do checkpoint v24"
        )
        records = _load_jsonl_checkpoint(checkpoint_path)
        if persisted != context:
            raise PipelineError("Checkpoint v24 pertence a outro protocolo.")
        if [row.get("case_id") for row in records] != eligible_ids[: len(records)]:
            raise PipelineError("Ordem do checkpoint v24 foi adulterada.")
        for record in records:
            _validate_full_record(staging, record)
    else:
        staging.mkdir()
        _write_json_atomic(staging / "checkpoint_context.json", context)
        records: list[dict[str, Any]] = []
        _write_jsonl_checkpoint_atomic(checkpoint_path, records)
    current_case_id: str | None = None
    try:
        for number, case_id in enumerate(
            eligible_ids[len(records) :], start=len(records) + 1
        ):
            current_case_id = case_id
            started = time.perf_counter()
            source, mode = inputs[case_id], modes[case_id]
            case_dir = staging / case_id
            if case_dir.exists():
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
            source_hashes = dict(source["hashes"])
            if mode == "registered_multiphase_rgb":
                alignment_root = (
                    Path(development_alignment_root)
                    if source["split"] == "development"
                    else Path(holdout_alignment_root)
                )
                art, delayed, registered_hashes = _registered_paths(
                    case_id, alignment_root
                )
                phases = {"art": art, "pv": source["venous"], "del": delayed}
                active_config = config
                source_hashes.update(registered_hashes)
            else:
                phases = {"pv": source["venous"]}
                active_config = fallback_config
            result = generate_liver_enriched_panel_set_multiphase(
                phase_paths=phases,
                coarse_liver_mask_path=source["mask"],
                case_manifest_path=case_manifest,
                screening_config=active_config,
                output_dir=case_dir,
                model_trace=model_trace(active_config),
                visible_phi_confirmed=False,
            )
            manifest = _load(result.manifest_path, "Manifesto completo v24")
            panels = [
                {
                    "panel_number": index,
                    "relative_path": f"{case_id}/{path.name}",
                    "sha256": _sha256(path),
                }
                for index, path in enumerate(result.panel_paths, 1)
            ]
            record = {
                "number": number,
                "case_id": case_id,
                "source_split": source["split"],
                "input_mode": mode,
                "panel_count": len(panels),
                "panels": panels,
                "manifest": f"{case_id}/{result.manifest_path.name}",
                "manifest_sha256": _sha256(result.manifest_path),
                "selection_mode": manifest["localization"]["selection_mode"],
                "source_hashes": source_hashes,
                "elapsed_seconds": time.perf_counter() - started,
            }
            _validate_full_record(staging, record)
            records.append(record)
            _write_jsonl_checkpoint_atomic(checkpoint_path, records)
        body = {
            "schema": FULL_SCHEMA,
            "status": "complete_label_blind_pending_independent_verification",
            "protocol_signature": protocol["protocol_signature"],
            "review_signature": review["review_signature"],
            "case_count": len(records),
            "case_ids": eligible_ids,
            "technical_failure_case_count": 2,
            "technical_failures_carried_forward": True,
            "technical_failures_count_as_primary_metric_errors": True,
            "total_panel_count": sum(row["panel_count"] for row in records),
            "cases": records,
            "labels_read": False,
            "lesion_masks_read": 0,
            "inference_executed": False,
            "eligible_for_inference": False,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        cohort = {**body, "cohort_signature": _canonical_sha(body)}
        _write_json_atomic(staging / "cohort_manifest.json", cohort)
        (staging / "checkpoint_context.json").unlink(missing_ok=True)
        checkpoint_path.unlink(missing_ok=True)
        (staging / "checkpoint_cases.backup.jsonl").unlink(missing_ok=True)
        (staging / "failure.json").unlink(missing_ok=True)
        _publish_directory(staging, destination)
        return cohort
    except Exception as exc:
        _write_json_atomic(
            staging / "failure.json",
            {
                "schema": "argos-openswisshcc-v24-liver-enriched-failure-v1",
                "case_id": current_case_id,
                "completed_case_count": len(records),
                "error_type": type(exc).__name__,
                "error": str(exc)[:1000],
                "labels_read": False,
                "lesion_masks_read": 0,
                "resumable": True,
            },
        )
        raise


def verify_v24_liver_enriched_full_cohort(
    *,
    protocol_path: Path,
    review_path: Path,
    gallery_root: Path,
    config_path: Path,
    panel_root: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    protocol = verify_v24_liver_enriched_protocol(
        protocol_path=protocol_path, config_path=config_path
    )
    review = _verify_review(
        review_path=review_path, protocol=protocol, gallery_root=gallery_root
    )
    root = Path(panel_root).resolve()
    cohort_path = root / "cohort_manifest.json"
    cohort = _load(cohort_path, "Coorte completa v24")
    unsigned = dict(cohort)
    signature = unsigned.pop("cohort_signature", None)
    records = cohort.get("cases")
    if (
        cohort.get("schema") != FULL_SCHEMA
        or signature != _canonical_sha(unsigned)
        or cohort.get("status")
        != "complete_label_blind_pending_independent_verification"
        or cohort.get("protocol_signature") != protocol["protocol_signature"]
        or cohort.get("review_signature") != review["review_signature"]
        or cohort.get("case_count") != 130
        or cohort.get("case_ids") != protocol["eligible_case_ids"]
        or not isinstance(records, list)
        or len(records) != 130
        or [row.get("case_id") for row in records]
        != protocol["eligible_case_ids"]
        or cohort.get("technical_failure_case_count") != 2
        or cohort.get("labels_read") is not False
        or cohort.get("lesion_masks_read") != 0
        or cohort.get("inference_executed") is not False
        or cohort.get("eligible_for_inference") is not False
    ):
        raise PipelineError("Coorte completa v24 falhou na verificação independente.")
    for record in records:
        _validate_full_record(root, record)
    body = {
        "schema": FULL_VERIFICATION_SCHEMA,
        "status": "verified_eligible_for_label_blind_inference",
        "protocol_signature": protocol["protocol_signature"],
        "review_signature": review["review_signature"],
        "cohort_signature": signature,
        "cohort_manifest_sha256": _sha256(cohort_path),
        "case_count": len(records),
        "total_panel_count": sum(row["panel_count"] for row in records),
        "registered_multiphase_rgb_count": sum(
            row["input_mode"] == "registered_multiphase_rgb" for row in records
        ),
        "venous_replicated_grayscale_count": sum(
            row["input_mode"] == "venous_replicated_grayscale" for row in records
        ),
        "technical_failure_case_count": 2,
        "labels_read": False,
        "lesion_masks_read": 0,
        "inference_executed": False,
        "eligible_for_inference": True,
    }
    verification = {**body, "verification_signature": _canonical_sha(body)}
    if output_path is not None:
        output = Path(output_path).resolve()
        if output.exists():
            raise PipelineError("Verificação v24 já existe; sobrescrita recusada.")
        _write_json_atomic(output, verification)
    return verification


__all__ = [
    "approve_v24_liver_enriched_gallery",
    "build_v24_liver_enriched_full_cohort",
    "build_v24_liver_enriched_gallery",
    "build_v24_liver_enriched_pilot",
    "freeze_v24_liver_enriched_protocol",
    "verify_v24_liver_enriched_full_cohort",
    "verify_v24_liver_enriched_protocol",
]

"""Preparação e congelamento cegos do batch high-dimensional OpenSwissHCC."""
from __future__ import annotations

import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_highdimensional import (
    MAX_SLICES,
    MIN_SLICES,
    build_highdimensional_stack,
)
from dtwin.benchmark.openswisshcc_highdimensional_inference import (
    CONTRACT,
    INSTRUCTION,
    MAX_OUTPUT_TOKENS,
    QUERY,
    RESPONSE_PREFIX,
    TIME_GATE_SECONDS,
    _atomic_json,
    _canonical_hash,
    _volume_url,
    validate_highdimensional_stack,
)
from dtwin.core import PipelineError, sha256_of
from dtwin.medgemma_client import load_screening_config

BUNDLE_SCHEMA = "argos-openswisshcc-highdimensional-blind-bundle-v1"
BATCH_PROTOCOL_SCHEMA = "argos-openswisshcc-highdimensional-batch-protocol-v1"


def _load_blind_case_ids(summary_path: Path) -> tuple[dict, list[str]]:
    try:
        summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Bundle cego de origem ausente ou inválido.") from exc
    case_ids = summary.get("case_ids")
    if (
        not isinstance(case_ids, list)
        or not case_ids
        or len(case_ids) != len(set(case_ids))
        or summary.get("case_count") != len(case_ids)
        or summary.get("ground_truth_read") is not False
        or summary.get("metrics_calculated") is not False
        or summary.get("holdout_opened") is not False
        or summary.get("research_only") is not True
        or summary.get("clinical_use_allowed") is not False
        or summary.get("requires_human_review") is not True
    ):
        raise PipelineError("Bundle de origem não comprova preparação cega e segura.")
    excluded = summary.get("excluded_technical_case_id")
    if excluded and excluded in case_ids:
        raise PipelineError("Caso tecnicamente excluído reapareceu no bundle cego.")
    return summary, sorted(str(case_id) for case_id in case_ids)


def prepare_highdimensional_blind_bundle(
    *,
    source_summary_path: Path,
    inputs_manifest_path: Path,
    input_root: Path,
    out_root: Path,
    maximum_slices: int = 50,
) -> dict:
    if not MIN_SLICES <= maximum_slices <= MAX_SLICES:
        raise PipelineError(f"maximum_slices deve estar entre {MIN_SLICES} e {MAX_SLICES}.")
    source_summary, case_ids = _load_blind_case_ids(source_summary_path)
    out_root = Path(out_root).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    bundle_path = out_root / "bundle.json"
    stacks = []
    for case_id in case_ids:
        stack_dir = out_root / "stacks" / case_id
        manifest = build_highdimensional_stack(
            manifest_path=inputs_manifest_path,
            input_root=input_root,
            out_root=out_root / "stacks",
            case_id=case_id,
            maximum_slices=maximum_slices,
        )
        stacks.append({
            "case_id": case_id,
            "stack_manifest_relative_path": f"stacks/{case_id}/manifest.json",
            "stack_manifest_sha256": sha256_of(stack_dir / "manifest.json"),
            "slice_count": manifest["slice_count"],
            "liver_coverage_fraction": manifest["liver_mask_audit"]["coverage_fraction"],
            "source_volume_sha256": manifest["source"]["volume_sha256"],
            "source_liver_mask_sha256": manifest["source"]["liver_mask_sha256"],
        })
    base = {
        "schema": BUNDLE_SCHEMA,
        "status": "blind_stacks_complete",
        "source_summary_sha256": sha256_of(source_summary_path),
        "source_summary_schema": source_summary.get("schema"),
        "case_count": len(case_ids),
        "case_ids": case_ids,
        "maximum_slices": maximum_slices,
        "stacks": stacks,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    bundle = dict(base)
    bundle["bundle_signature"] = _canonical_hash(base)
    if bundle_path.exists():
        existing = json.loads(bundle_path.read_text(encoding="utf-8"))
        if existing != bundle:
            raise PipelineError("Bundle high-dimensional existente diverge; sobrescrita recusada.")
        return existing
    _atomic_json(bundle_path, bundle)
    return bundle


def validate_highdimensional_blind_bundle(bundle_root: Path) -> dict:
    bundle_root = Path(bundle_root).resolve()
    try:
        bundle = json.loads((bundle_root / "bundle.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Bundle high-dimensional ausente ou inválido.") from exc
    signature = bundle.pop("bundle_signature", None)
    if signature != _canonical_hash(bundle):
        raise PipelineError("Assinatura do bundle high-dimensional diverge.")
    bundle["bundle_signature"] = signature
    if (
        bundle.get("schema") != BUNDLE_SCHEMA
        or bundle.get("status") != "blind_stacks_complete"
        or bundle.get("case_count") != len(bundle.get("case_ids", []))
        or bundle.get("case_count") != len(bundle.get("stacks", []))
        or bundle.get("ground_truth_read") is not False
        or bundle.get("metrics_calculated") is not False
        or bundle.get("holdout_opened") is not False
    ):
        raise PipelineError("Bundle high-dimensional viola estado cego.")
    by_case = {item.get("case_id"): item for item in bundle["stacks"]}
    if len(by_case) != bundle["case_count"] or sorted(by_case) != bundle["case_ids"]:
        raise PipelineError("Casos/ordem inconsistentes no bundle high-dimensional.")
    for case_id in bundle["case_ids"]:
        item = by_case[case_id]
        relative = Path(item["stack_manifest_relative_path"])
        manifest_path = (bundle_root / relative).resolve()
        try:
            manifest_path.relative_to(bundle_root)
        except ValueError as exc:
            raise PipelineError("Manifesto de pilha escapou do bundle.") from exc
        if sha256_of(manifest_path) != item.get("stack_manifest_sha256"):
            raise PipelineError("Hash do manifesto de pilha diverge no bundle.")
        manifest, _ = validate_highdimensional_stack(manifest_path.parent)
        if (
            manifest.get("case_id") != case_id
            or manifest.get("slice_count") != item.get("slice_count")
            or manifest.get("sampling", {}).get("maximum_slices") != bundle["maximum_slices"]
        ):
            raise PipelineError("Pilha não corresponde ao caso ou teto congelado.")
    return bundle


def freeze_highdimensional_batch_protocol(
    *,
    bundle_root: Path,
    config_path: Path,
    out_path: Path,
) -> dict:
    bundle = validate_highdimensional_blind_bundle(bundle_root)
    config = load_screening_config(config_path)
    med = config["medgemma"]
    base = {
        "schema": BATCH_PROTOCOL_SCHEMA,
        "status": "frozen_before_predictions",
        "bundle_sha256": sha256_of(Path(bundle_root) / "bundle.json"),
        "bundle_signature": bundle["bundle_signature"],
        "case_count": bundle["case_count"],
        "case_ids": bundle["case_ids"],
        "maximum_slices": bundle["maximum_slices"],
        "model_id": med["model_id"],
        "model_version": med["model_version"],
        "contract": CONTRACT,
        "endpoint_url": _volume_url(str(med["endpoint_url"])),
        "instruction": INSTRUCTION,
        "query": QUERY,
        "generation": {
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "response_prefix": RESPONSE_PREFIX,
            "do_sample": False,
            "requests_per_case": 1,
            "automatic_retries": 0,
        },
        "time_gate_seconds_per_case": TIME_GATE_SECONDS,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    protocol = dict(base)
    protocol["protocol_signature"] = _canonical_hash(base)
    out_path = Path(out_path)
    if out_path.exists():
        existing = json.loads(out_path.read_text(encoding="utf-8"))
        if existing != protocol:
            raise PipelineError("Protocolo batch existente diverge; sobrescrita recusada.")
        return existing
    _atomic_json(out_path, protocol)
    return protocol

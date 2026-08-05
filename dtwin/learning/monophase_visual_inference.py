"""Strict inference contract for the dedicated single-phase MedSigLIP head."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from dtwin.core import PipelineError
from dtwin.learning.visual_inference import (
    DEFAULT_EMBEDDING_CONFIG,
    ProductionBundle,
    classify_embeddings,
    embed_panels,
    load_production_bundle,
)
from dtwin.learning.protocol import sha256_file


SCENARIO = "monophase_medsiglip"
HIERARCHICAL_SCENARIO = "monophase_medsiglip_hierarchical"
ALLOWED_SCENARIOS = {SCENARIO, HIERARCHICAL_SCENARIO}
PANEL_MODES_BY_PHASE = {
    "t1_arterial": "single_phase_arterial_grayscale_liver_enriched",
    "t1_venous": "single_phase_portal_venous_grayscale_liver_enriched",
    "t1_delayed": "single_phase_delayed_grayscale_liver_enriched",
}
PANEL_INPUT_TYPE = "mri_single_phase_replicated_grayscale_full_fov_liver_enriched"


def _json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def validate_monophase_contract(
    bundle: ProductionBundle,
    *,
    panel_manifest_path: Path,
    panel_paths: Sequence[Path],
    source_phase_key: str | None = None,
) -> dict[str, Any]:
    """Fail closed if a triphasic bundle or synthetic phase reaches this path."""

    contract = bundle.manifest
    expected = contract.get("expected_panels_per_case")
    expected_counts = {int(expected)} if isinstance(expected, int) else {
        int(value) for value in (expected or [])
    }
    if (
        contract.get("analysis_scenario") not in ALLOWED_SCENARIOS
        or contract.get("panel_image_mode")
        != PANEL_MODES_BY_PHASE.get(str(contract.get("source_phase_key") or ""))
        or contract.get("source_phase_contract") != "exactly_one_real_series"
        or contract.get("dynamic_enhancement_information_present") is not False
        or not expected_counts
    ):
        raise PipelineError("Bundle não pertence ao cenário MedSigLIP monofásico.")
    if source_phase_key is not None and contract.get("source_phase_key") != source_phase_key:
        raise PipelineError("Fase monofásica identificada não corresponde ao bundle.")
    manifest = _json(panel_manifest_path, "Manifesto de painel monofásico")
    records = manifest.get("panels")
    channel_map = manifest.get("fusion_channel_map")
    if (
        manifest.get("input_type") != PANEL_INPUT_TYPE
        or manifest.get("single_phase_replicated_across_rgb") is not True
        or manifest.get("dynamic_enhancement_information_present") is not False
        or manifest.get("lesion_mask_used") is not False
        or manifest.get("ground_truth_used") is not False
        or not isinstance(channel_map, dict)
        or set(channel_map.values()) != {"mono"}
        or not isinstance(records, list)
        or len(records) not in expected_counts
        or len(panel_paths) != len(records)
    ):
        raise PipelineError("Representação monofásica incompatível com o bundle.")
    for record, path in zip(records, panel_paths):
        path = Path(path)
        if path.name != record.get("image") or sha256_file(path) != record.get("sha256"):
            raise PipelineError("Hash ou ordem dos painéis monofásicos divergiu.")
    return manifest


def infer_monophase_case_from_panels(
    *,
    bundle_root: Path,
    panel_manifest_path: Path,
    panel_paths: Sequence[Path],
    source_phase_key: str,
    embedding_config_path: Path | str = DEFAULT_EMBEDDING_CONFIG,
) -> dict[str, Any]:
    bundle = load_production_bundle(bundle_root)
    manifest = validate_monophase_contract(
        bundle,
        panel_manifest_path=panel_manifest_path,
        panel_paths=panel_paths,
        source_phase_key=source_phase_key,
    )
    embeddings = embed_panels(embedding_config_path, panel_paths)
    decision = classify_embeddings(bundle, embeddings)
    return {
        **decision,
        "analysis_scenario": str(bundle.manifest["analysis_scenario"]),
        "panel_manifest_sha256": sha256_file(panel_manifest_path),
        "single_phase_replicated_across_rgb": True,
        "dynamic_enhancement_information_present": False,
        "source_phase_contract": bundle.manifest["source_phase_contract"],
        "source_phase_key": bundle.manifest["source_phase_key"],
        "panel_input_type": manifest["input_type"],
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }


__all__ = [
    "PANEL_INPUT_TYPE",
    "PANEL_MODES_BY_PHASE",
    "ALLOWED_SCENARIOS",
    "HIERARCHICAL_SCENARIO",
    "SCENARIO",
    "infer_monophase_case_from_panels",
    "validate_monophase_contract",
]

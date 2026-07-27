"""Per-case visual inference with the frozen Etapa C production bundle.

Panels (from `exam_to_panels.build_exam_panels`) -> MedSigLIP embeddings
(pinned model, same config as training) -> production classifier -> binary
decision. Mirrors exactly the scoring the OOF pipeline used (positive-class
probability mass, then panel aggregation, then threshold), so a case rendered
and embedded the same way is scored the same way the model was validated.

Also exposes the in-sample guard primitive: a benchmark case whose id or patient
group is in the bundle's training set was SEEN during training and must never be
reported as a clean generalization number.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from dtwin.core import PipelineError
from dtwin.learning.medsiglip_classifier import _json  # reuse strict json reader
from dtwin.learning.medsiglip_multiclass_classifier import (
    BUNDLE_SCHEMA,
    _aggregate,
    _positive_probability,
)
from dtwin.learning.protocol import canonical_sha256, sha256_file

DEFAULT_EMBEDDING_CONFIG = "configs/training/medsiglip_frozen_v1.yaml"


@dataclass(frozen=True)
class ProductionBundle:
    root: Path
    manifest: dict[str, Any]
    model: Any  # sklearn Pipeline (scaler + multinomial logistic regression)
    positive_indices: set[int]
    aggregation: str
    threshold: float

    @property
    def training_case_ids(self) -> set[str]:
        return set(self.manifest.get("training_case_ids") or [])

    @property
    def training_patient_group_ids(self) -> set[str]:
        return set(self.manifest.get("training_patient_group_ids") or [])


def load_production_bundle(bundle_root: Path) -> ProductionBundle:
    """Load and verify a frozen production bundle (signature + model hash)."""
    import joblib

    bundle_root = Path(bundle_root)
    manifest = _json(bundle_root / "bundle_manifest.json", "Manifesto do bundle")
    if manifest.get("schema") != BUNDLE_SCHEMA:
        raise PipelineError("Schema de bundle de produção inválido.")
    unsigned = dict(manifest)
    signature = unsigned.pop("bundle_signature", None)
    if signature != canonical_sha256(unsigned):
        raise PipelineError("Assinatura do bundle de produção diverge.")
    model_path = bundle_root / "production_model.joblib"
    if manifest.get("model_sha256") != sha256_file(model_path):
        raise PipelineError("Modelo de produção foi alterado.")
    class_names = list(manifest["class_names"])
    class_index = {name: index for index, name in enumerate(class_names)}
    positive_indices = {class_index[name] for name in manifest["positive_classes"]}
    return ProductionBundle(
        root=bundle_root,
        manifest=manifest,
        model=joblib.load(model_path),
        positive_indices=positive_indices,
        aggregation=str(manifest["selected_aggregation"]),
        threshold=float(manifest["decision_threshold"]),
    )


def classify_embeddings(bundle: ProductionBundle, panel_embeddings: np.ndarray) -> dict[str, Any]:
    """Score one case from its panel embedding matrix (n_panels x dim)."""
    matrix = np.asarray(panel_embeddings, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0:
        raise PipelineError("Embeddings de painel inválidos para inferência.")
    per_panel = _positive_probability(bundle.model, matrix, bundle.positive_indices)
    score = _aggregate(per_panel.tolist(), bundle.aggregation)
    prediction = "POSITIVE" if score >= bundle.threshold else "NEGATIVE"
    return {
        "score": float(score),
        "threshold": bundle.threshold,
        "prediction": prediction,
        "panel_count": int(matrix.shape[0]),
    }


def embed_panels(config_path: Path | str, panel_paths: Sequence[Path]) -> np.ndarray:
    """Embed panel PNGs with the pinned MedSigLIP model, loading and unloading
    the GPU. Uses the SAME embedding config as training so vectors match."""
    from PIL import Image

    from dtwin.learning.medsiglip_embeddings import HuggingFaceMedSigLIPBackend, load_embedding_config

    if not panel_paths:
        raise PipelineError("Nenhum painel para embutir.")
    config = load_embedding_config(Path(config_path))
    backend = HuggingFaceMedSigLIPBackend(config)
    try:
        images = [Image.open(Path(p)).convert("RGB") for p in panel_paths]
        vectors = backend.embed(images)
    finally:
        backend.close()
    return np.asarray(vectors, dtype=np.float64)


def infer_case_from_panels(
    *,
    bundle_root: Path,
    panel_paths: Sequence[Path],
    embedding_config_path: Path | str = DEFAULT_EMBEDDING_CONFIG,
) -> dict[str, Any]:
    """Full per-case inference: panels -> embeddings -> bundle -> decision."""
    bundle = load_production_bundle(bundle_root)
    embeddings = embed_panels(embedding_config_path, panel_paths)
    return classify_embeddings(bundle, embeddings)


def in_sample_status(
    bundle: ProductionBundle, *, case_id: str, patient_group_id: str | None = None
) -> dict[str, Any]:
    """Whether a benchmark case was seen during the bundle's training.

    In-sample cases produce inflated, non-generalization numbers and must be
    labeled as such — never mixed into a clean metric.
    """
    group = str(patient_group_id or case_id)
    by_case = str(case_id) in bundle.training_case_ids
    by_group = group in bundle.training_patient_group_ids
    return {
        "in_sample": bool(by_case or by_group),
        "matched_by_case_id": by_case,
        "matched_by_patient_group_id": by_group,
    }


def partition_in_sample(
    bundle: ProductionBundle, cases: list[dict[str, Any]]
) -> dict[str, Any]:
    """Split a list of case records ({case_id, patient_group_id?}) into in-sample
    vs out-of-sample, so a benchmark report can present them separately."""
    in_sample: list[str] = []
    out_of_sample: list[str] = []
    for case in cases:
        status = in_sample_status(
            bundle,
            case_id=str(case["case_id"]),
            patient_group_id=case.get("patient_group_id"),
        )
        (in_sample if status["in_sample"] else out_of_sample).append(str(case["case_id"]))
    return {
        "in_sample_case_ids": sorted(in_sample),
        "out_of_sample_case_ids": sorted(out_of_sample),
        "in_sample_count": len(in_sample),
        "out_of_sample_count": len(out_of_sample),
        "any_in_sample": bool(in_sample),
    }

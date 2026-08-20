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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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

# Classes de lesão nomeadas. As duas `*_unspecified` existem porque a coorte
# OpenSwissHCC não documenta subtipo; elas NÃO são um subtipo e nunca podem ser
# reportadas como tal.
NAMED_LESION_CLASSES = ("fnh", "hcc", "hemangioma", "hepatic_cyst")

# Massa mínima nas classes nomeadas para que um subtipo possa ser afirmado.
#
# docs/161 mediu que a atribuição de classe é condicionada à coorte de aquisição:
# no LLD real as quatro classes nomeadas recebem 99,32% da massa de probabilidade;
# nas duas coortes OpenSwiss reais, 1,43% e 1,47%; numa coorte sintética com fundo
# anatômico de outra origem, 6,93%. A separação é quase binária, e um limiar em
# 50% fica bem longe de qualquer um dos modos observados.
#
# Sem essa guarda, um exame de origem não vista receberia o argmax entre as quatro
# classes nomeadas mesmo com o modelo colocando ~99% da massa em `unspecified` --
# ou seja, um subtipo inventado sobre 1% de evidência.
NAMED_LESION_MASS_FLOOR = 0.50


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


def class_probabilities(
    bundle: ProductionBundle, panel_embeddings: np.ndarray
) -> dict[str, float]:
    """Mean per-class probability across the case's panels."""
    matrix = np.asarray(panel_embeddings, dtype=np.float64)
    probabilities = bundle.model.predict_proba(matrix).mean(axis=0)
    classes = list(bundle.model.named_steps["classifier"].classes_)
    names = list(bundle.manifest["class_names"])
    return {
        names[int(label)]: float(probabilities[column])
        for column, label in enumerate(classes)
    }


def instance_probability_evidence(
    bundle: ProductionBundle, panel_embeddings: np.ndarray
) -> dict[str, Any]:
    """Expose auditable per-panel evidence without changing the frozen decision.

    This is the inference-side foundation for multiple-instance learning.  It
    records which real panel carried each class signal and provides deterministic
    mean/max/top-2 summaries.  No ground truth, lesion mask or post-hoc class
    selection participates in this computation.
    """

    matrix = np.asarray(panel_embeddings, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0:
        raise PipelineError("Embeddings de painel inválidos para evidência multi-instância.")
    probabilities = np.asarray(bundle.model.predict_proba(matrix), dtype=np.float64)
    classes = list(bundle.model.named_steps["classifier"].classes_)
    names = list(bundle.manifest["class_names"])
    if probabilities.shape != (matrix.shape[0], len(classes)):
        raise PipelineError("Matriz de probabilidades por instância inválida.")

    by_instance: list[dict[str, Any]] = []
    for row_index, row in enumerate(probabilities):
        class_mass = {
            names[int(label)]: float(row[column])
            for column, label in enumerate(classes)
        }
        by_instance.append(
            {
                "instance_index": row_index,
                "class_probabilities": class_mass,
                "positive_probability": float(
                    sum(row[column] for column, label in enumerate(classes) if label in bundle.positive_indices)
                ),
            }
        )

    by_class: dict[str, dict[str, Any]] = {}
    for class_name in names:
        values = [entry["class_probabilities"].get(class_name, 0.0) for entry in by_instance]
        top_indices = sorted(range(len(values)), key=lambda index: (-values[index], index))
        by_class[class_name] = {
            "mean": float(np.mean(values)),
            "max": float(max(values)),
            "top2_mean": float(np.mean(sorted(values, reverse=True)[:2])),
            "top_instance_indices": top_indices[:2],
        }
    return {
        "schema": "oren-visual-instance-evidence-v1",
        "instance_count": int(matrix.shape[0]),
        "instances": by_instance,
        "class_aggregations": by_class,
        "ground_truth_used": False,
        "lesion_mask_used": False,
        "changes_frozen_decision": False,
    }


def resolve_subtype(class_mass: Mapping[str, float]) -> dict[str, Any]:
    """Name the lesion subtype, or refuse to when the evidence is not there.

    The model can place its probability mass on `*_unspecified`, which carries no
    subtype meaning. In that regime the argmax over the four named classes is an
    artefact of renormalizing near-zero numbers, so this returns
    `determined=False` instead of a fabricated label.
    """
    named = {name: float(class_mass.get(name, 0.0)) for name in NAMED_LESION_CLASSES}
    named_mass = sum(named.values())
    unspecified_mass = sum(
        float(value)
        for name, value in class_mass.items()
        if name not in NAMED_LESION_CLASSES
    )
    if named_mass < NAMED_LESION_MASS_FLOOR:
        return {
            "determined": False,
            "subtype": None,
            "subtype_confidence": None,
            "named_lesion_mass": named_mass,
            "unspecified_mass": unspecified_mass,
            "mass_floor": NAMED_LESION_MASS_FLOOR,
            "reason": (
                "O modelo concentrou a probabilidade em classes sem subtipo "
                "documentado, o que ocorre quando o exame vem de uma origem de "
                "aquisição diferente das usadas no treino. Afirmar um subtipo "
                "aqui seria inventá-lo."
            ),
        }
    best = max(named, key=named.get)
    return {
        "determined": True,
        "subtype": best,
        "subtype_confidence": named[best] / named_mass if named_mass else None,
        "named_lesion_mass": named_mass,
        "unspecified_mass": unspecified_mass,
        "mass_floor": NAMED_LESION_MASS_FLOOR,
        "reason": None,
    }


def classify_embeddings(bundle: ProductionBundle, panel_embeddings: np.ndarray) -> dict[str, Any]:
    """Score one case from its panel embedding matrix (n_panels x dim).

    Returns the binary decision exactly as the OOF pipeline computed it, plus the
    per-class mass and a subtype that is only named when the evidence supports it.
    """
    matrix = np.asarray(panel_embeddings, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0:
        raise PipelineError("Embeddings de painel inválidos para inferência.")
    per_panel = _positive_probability(bundle.model, matrix, bundle.positive_indices)
    score = _aggregate(per_panel.tolist(), bundle.aggregation)
    prediction = "POSITIVE" if score >= bundle.threshold else "NEGATIVE"
    mass = class_probabilities(bundle, matrix)
    subtype = resolve_subtype(mass)
    instance_evidence = instance_probability_evidence(bundle, matrix)
    return {
        "score": float(score),
        "threshold": bundle.threshold,
        "prediction": prediction,
        "panel_count": int(matrix.shape[0]),
        "class_probabilities": mass,
        # O subtipo só descreve QUAL alteração, e só faz sentido quando a triagem
        # deu positiva. Num negativo ele fica registrado mas não é a resposta.
        "subtype": subtype,
        "instance_evidence": instance_evidence,
    }


def embed_panels(config_path: Path | str, panel_paths: Sequence[Path]) -> np.ndarray:
    """Embed panel PNGs with the pinned MedSigLIP model, loading and unloading
    the GPU. Uses the SAME embedding config as training so vectors match."""
    from PIL import Image

    from dtwin.learning.medsiglip_embeddings import (
        HuggingFaceMedSigLIPBackend,
        load_embedding_config,
    )

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


IN_SAMPLE_YES = "in_sample"
IN_SAMPLE_NO = "out_of_sample"
IN_SAMPLE_UNKNOWN = "unknown"


def _namespace(identifier: str) -> str:
    """Leading token of an identifier, used as its naming namespace.

    Training ids look like ``anon-lld-…`` / ``anon-openswiss-…`` (namespace
    ``anon``); a blind benchmark id looks like ``ARGOS-BLIND-0001`` (namespace
    ``argos``). Ids from different namespaces are simply not comparable.
    """
    return str(identifier).strip().split("-", 1)[0].lower()


def training_namespaces(bundle: ProductionBundle) -> set[str]:
    return {
        _namespace(value)
        for value in (*bundle.training_case_ids, *bundle.training_patient_group_ids)
        if str(value).strip()
    }


def in_sample_status(
    bundle: ProductionBundle,
    *,
    case_id: str,
    patient_group_id: str | None = None,
    provenance: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Whether a benchmark case was seen during the bundle's training.

    Returns a THREE-state verdict, because "not found in the training set" and
    "cannot be compared to the training set" are different facts and conflating
    them is dangerous: an unmatched identifier from a foreign namespace (e.g. a
    blind benchmark id compared against ``anon-*`` training ids) would otherwise
    be silently reported as out-of-sample, certifying an in-sample — and
    therefore inflated — number as clean. That exact false negative happened on
    the 120-case blind collection, where 86/100 cases were in fact in training
    while every report claimed ``in_sample=False``.

    ``provenance`` maps a benchmark identifier onto the original cohort
    identifier (from an authorized index). When supplied, the comparison becomes
    definitive; without it, a foreign-namespace identifier yields ``unknown``.
    """
    case_id = str(case_id)
    group = str(patient_group_id or case_id)
    resolved_case = str((provenance or {}).get(case_id, case_id))
    resolved_group = str((provenance or {}).get(group, group))

    by_case = resolved_case in bundle.training_case_ids
    by_group = resolved_group in bundle.training_patient_group_ids
    if by_case or by_group:
        verdict = IN_SAMPLE_YES
    else:
        namespaces = training_namespaces(bundle)
        comparable = (
            _namespace(resolved_case) in namespaces
            or _namespace(resolved_group) in namespaces
        )
        verdict = IN_SAMPLE_NO if comparable else IN_SAMPLE_UNKNOWN

    return {
        "verdict": verdict,
        # True only when provably seen in training; never True on `unknown`.
        "in_sample": verdict == IN_SAMPLE_YES,
        # Explicit: callers must not read `not in_sample` as "out-of-sample".
        "provably_out_of_sample": verdict == IN_SAMPLE_NO,
        "matched_by_case_id": by_case,
        "matched_by_patient_group_id": by_group,
        "provenance_resolved": bool(provenance) and resolved_case != case_id,
        "reason": (
            "identificador de namespace estranho ao conjunto de treino; "
            "sem proveniência não é possível decidir"
            if verdict == IN_SAMPLE_UNKNOWN
            else ""
        ),
    }


def partition_in_sample(
    bundle: ProductionBundle,
    cases: list[dict[str, Any]],
    *,
    provenance: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Split case records into in-sample / out-of-sample / unknown.

    ``unknown`` is deliberately NOT folded into out-of-sample: doing so is what
    lets an inflated number pass as a generalization estimate.
    """
    buckets: dict[str, list[str]] = {
        IN_SAMPLE_YES: [], IN_SAMPLE_NO: [], IN_SAMPLE_UNKNOWN: []
    }
    for case in cases:
        status = in_sample_status(
            bundle,
            case_id=str(case["case_id"]),
            patient_group_id=case.get("patient_group_id"),
            provenance=provenance,
        )
        buckets[status["verdict"]].append(str(case["case_id"]))
    return {
        "in_sample_case_ids": sorted(buckets[IN_SAMPLE_YES]),
        "out_of_sample_case_ids": sorted(buckets[IN_SAMPLE_NO]),
        "unknown_case_ids": sorted(buckets[IN_SAMPLE_UNKNOWN]),
        "in_sample_count": len(buckets[IN_SAMPLE_YES]),
        "out_of_sample_count": len(buckets[IN_SAMPLE_NO]),
        "unknown_count": len(buckets[IN_SAMPLE_UNKNOWN]),
        "any_in_sample": bool(buckets[IN_SAMPLE_YES]),
        "any_unknown": bool(buckets[IN_SAMPLE_UNKNOWN]),
    }

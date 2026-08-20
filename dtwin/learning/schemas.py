"""Strict schemas used by the supervised ARGOS research track."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from dtwin.benchmark.models import (
    NEGATIVE_SUBTYPES,
    PHENOTYPE_TAGS,
    POSITIVE_SUBTYPES,
)
from dtwin.core import PipelineError

PROTOCOL_SCHEMA = "argos-hybrid-training-protocol-v1"
SPLIT_SCHEMA = "argos-hybrid-nested-splits-v1"
PROTECTED_LABEL_SCHEMA = "argos-hybrid-protected-training-case-v1"
TARGET_CONDITION = "focal_liver_lesion_suspicion"
LABELS = {"POSITIVE", "NEGATIVE"}

# These keys must never occur in material presented to a feature extractor or
# inference model.  The retrospective evaluator binds them only after features
# and predictions have been persisted.
PROTECTED_INFERENCE_FIELDS = frozenset(
    {
        "label",
        "ground_truth",
        "target",
        "target_condition",
        "negative_subtype",
        "positive_subtype",
        "phenotype_tags",
        "public_category",
        "public_subject_id",
        "lesion_mask",
        "lesion_mask_path",
        "annotation_path",
    }
)


def _token(value: Any, name: str) -> str:
    token = str(value or "").strip()
    if not token:
        raise PipelineError(f"{name} é obrigatório.")
    return token


@dataclass(frozen=True)
class ProtectedTrainingCase:
    """One protected case used only by split generation and evaluation."""

    case_id: str
    patient_group_id: str
    dataset_id: str
    label: str
    target_condition: str = TARGET_CONDITION
    negative_subtype: str | None = None
    positive_subtype: str | None = None
    phenotype_tags: tuple[str, ...] = ()
    technical_failure: bool = False
    schema: str = PROTECTED_LABEL_SCHEMA

    def validate(self) -> None:
        _token(self.case_id, "case_id")
        _token(self.patient_group_id, "patient_group_id")
        _token(self.dataset_id, "dataset_id")
        if self.label not in LABELS:
            raise PipelineError(f"label inválido: {self.label!r}")
        if self.target_condition != TARGET_CONDITION:
            raise PipelineError(
                f"target_condition deve ser {TARGET_CONDITION!r}."
            )
        if self.negative_subtype and self.positive_subtype:
            raise PipelineError(
                "negative_subtype e positive_subtype são mutuamente exclusivos."
            )
        if self.label == "POSITIVE":
            if self.negative_subtype is not None:
                raise PipelineError(
                    "negative_subtype não é permitido em caso POSITIVE."
                )
            if (
                self.positive_subtype is not None
                and self.positive_subtype not in POSITIVE_SUBTYPES
            ):
                raise PipelineError(
                    f"positive_subtype inválido: {self.positive_subtype!r}"
                )
        else:
            if self.positive_subtype is not None:
                raise PipelineError(
                    "positive_subtype não é permitido em caso NEGATIVE."
                )
            if (
                self.negative_subtype is not None
                and self.negative_subtype not in NEGATIVE_SUBTYPES
            ):
                raise PipelineError(
                    f"negative_subtype inválido: {self.negative_subtype!r}"
                )
        invalid = sorted(set(self.phenotype_tags) - set(PHENOTYPE_TAGS))
        if invalid:
            raise PipelineError(f"phenotype_tags inválidas: {invalid}")

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        dataset_id: str | None = None,
    ) -> "ProtectedTrainingCase":
        label = _token(value.get("label"), "label").upper()
        case = cls(
            case_id=_token(value.get("case_id"), "case_id"),
            patient_group_id=_token(
                value.get("patient_group_id") or value.get("case_id"),
                "patient_group_id",
            ),
            dataset_id=_token(
                dataset_id or value.get("dataset_id"), "dataset_id"
            ),
            label=label,
            target_condition=TARGET_CONDITION,
            negative_subtype=(
                str(value["negative_subtype"]).strip()
                if value.get("negative_subtype")
                else None
            ),
            positive_subtype=(
                str(value["positive_subtype"]).strip()
                if value.get("positive_subtype")
                else None
            ),
            phenotype_tags=tuple(
                sorted({str(item).strip() for item in value.get("phenotype_tags", [])})
            ),
            technical_failure=bool(value.get("technical_failure", False)),
        )
        case.validate()
        return case


def assert_label_blind_record(
    value: Mapping[str, Any],
    *,
    context: str = "registro de inferência",
) -> None:
    """Reject protected information recursively before feature extraction."""

    def visit(item: Any, location: str) -> None:
        if isinstance(item, Mapping):
            forbidden = sorted(
                str(key)
                for key in item
                if str(key).lower() in PROTECTED_INFERENCE_FIELDS
            )
            if forbidden:
                raise PipelineError(
                    f"{context} contém campos protegidos em {location}: {forbidden}"
                )
            for key, child in item.items():
                visit(child, f"{location}.{key}")
        elif isinstance(item, (list, tuple)):
            for index, child in enumerate(item):
                visit(child, f"{location}[{index}]")

    visit(value, "$")

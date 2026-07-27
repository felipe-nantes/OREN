"""Build a label-blind global-panel dataset for supervised visual learning.

The builder consumes only already reviewed liver-enriched panels and their
technical manifests. Protected labels and lesion masks are not accepted as
inputs. Labels are attached later by the nested evaluator.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml

from dtwin.core import PipelineError
from dtwin.learning.protocol import canonical_sha256, sha256_file
from dtwin.learning.schemas import assert_label_blind_record
from dtwin.learning.splits import validate_nested_splits


CANDIDATE_DATASET_SCHEMA = "argos-hybrid-label-blind-candidate-dataset-v1"
CANDIDATE_RECORD_SCHEMA = "argos-hybrid-label-blind-candidate-record-v1"


def _json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def _yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PipelineError(f"Config de candidatos inválida: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("Config de candidatos deve ser objeto YAML.")
    return value


def _relative(root: Path, path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError as exc:
        raise PipelineError(f"Artefato fora do workspace: {path}") from exc


def _write_jsonl_fsync(path: Path, rows: list[dict[str, Any]]) -> None:
    with Path(path).open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(
                json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            )
        stream.flush()
        os.fsync(stream.fileno())


def _validate_case_manifest(case_id: str, value: dict[str, Any]) -> None:
    if value.get("case_id") != case_id:
        raise PipelineError(f"case_id divergente no manifesto de {case_id}.")
    forbidden_truth = {
        "label",
        "negative_subtype",
        "positive_subtype",
        "phenotype_tags",
        "public_subject_id",
        "public_category",
    }
    leaked = sorted(forbidden_truth & set(value))
    if leaked:
        raise PipelineError(
            f"Manifesto técnico de {case_id} contém campos protegidos: {leaked}"
        )


def _validate_panel_manifest(case_id: str, value: dict[str, Any]) -> None:
    if value.get("case_id") != case_id:
        raise PipelineError(f"case_id divergente no painel de {case_id}.")
    required_flags = {
        "lesion_mask_used": False,
        "ground_truth_used": False,
        "contour_rendered": False,
        "phi_metadata_removed": True,
        "requires_human_review": True,
    }
    for key, expected in required_flags.items():
        if value.get(key) is not expected:
            raise PipelineError(
                f"Salvaguarda {key} inválida em {case_id}: "
                f"esperado {expected!r}."
            )
    if value.get("organ") != "liver":
        raise PipelineError(f"Painel não hepático em {case_id}.")
    if value.get("regulatory_mode") != "RESEARCH":
        raise PipelineError(f"Painel fora do modo RESEARCH em {case_id}.")
    if not isinstance(value.get("panels"), list) or not value["panels"]:
        raise PipelineError(f"Coleção de painéis vazia em {case_id}.")


def _load_split_universe(splits_path: Path) -> tuple[dict[str, Any], set[str]]:
    splits = _json(splits_path, "Splits")
    validate_nested_splits(splits)
    first = splits["outer_folds"][0]
    universe = set(first["train_case_ids"]) | set(first["test_case_ids"])
    return splits, universe


def _verify_label_blind_binding(
    protocol_path: Path, splits_path: Path
) -> dict[str, Any]:
    protocol = _json(protocol_path, "Protocolo")
    unsigned = dict(protocol)
    signature = unsigned.pop("protocol_signature", None)
    if signature != canonical_sha256(unsigned):
        raise PipelineError("Assinatura do protocolo diverge.")
    if protocol.get("splits_sha256") != sha256_file(splits_path):
        raise PipelineError("Splits não correspondem ao protocolo.")
    if protocol.get("labels_excluded_from_feature_artifacts") is not True:
        raise PipelineError("Protocolo não protege os artefatos de features.")
    return protocol


def build_candidate_dataset(
    *,
    config_path: Path,
    protocol_path: Path,
    splits_path: Path,
    workspace_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Materialize a verified manifest without opening protected labels."""

    root = Path(workspace_root).resolve()
    destination = Path(output_root).resolve()
    if destination.exists():
        raise PipelineError("Dataset de candidatos já existe; saída é imutável.")
    protocol = _verify_label_blind_binding(protocol_path, splits_path)
    splits, expected_case_ids = _load_split_universe(splits_path)
    config = _yaml(config_path)
    sources = config.get("sources")
    if not isinstance(sources, list) or not sources:
        raise PipelineError("Config exige sources.")

    records: list[dict[str, Any]] = []
    observed_case_ids: set[str] = set()
    source_summary: list[dict[str, Any]] = []
    for source_config in sources:
        if not isinstance(source_config, dict):
            raise PipelineError("Fonte de painéis inválida.")
        dataset_id = str(source_config.get("dataset_id") or "").strip()
        source_root = (root / str(source_config.get("root") or "")).resolve()
        _relative(root, source_root)
        cohort_path = source_root / "cohort_manifest.json"
        cohort = _json(cohort_path, "Manifesto de coorte")
        case_ids = cohort.get("case_ids")
        if not isinstance(case_ids, list):
            raise PipelineError(f"case_ids ausentes em {cohort_path}.")
        for case_id_value in case_ids:
            case_id = str(case_id_value)
            if case_id not in expected_case_ids:
                raise PipelineError(
                    f"Caso {case_id} não pertence aos splits congelados."
                )
            if case_id in observed_case_ids:
                raise PipelineError(f"Caso duplicado entre fontes: {case_id}")
            case_root = source_root / case_id
            case_manifest = _json(
                case_root / "case_manifest.json", "Manifesto de caso"
            )
            panel_manifest_path = (
                case_root / "medgemma_liver_screening_manifest.json"
            )
            panel_manifest = _json(
                panel_manifest_path, "Manifesto de painel"
            )
            _validate_case_manifest(case_id, case_manifest)
            _validate_panel_manifest(case_id, panel_manifest)
            panel_total = len(panel_manifest["panels"])
            for panel in panel_manifest["panels"]:
                if not isinstance(panel, dict):
                    raise PipelineError(f"Painel inválido em {case_id}.")
                panel_number = int(panel.get("panel_number", 0))
                image_path = (case_root / str(panel.get("image") or "")).resolve()
                _relative(root, image_path)
                actual_sha = sha256_file(image_path)
                if actual_sha != panel.get("sha256"):
                    raise PipelineError(
                        f"Hash do painel diverge em {case_id}/{panel_number}."
                    )
                record = {
                    "schema": CANDIDATE_RECORD_SCHEMA,
                    "case_id": case_id,
                    "patient_group_id": case_id,
                    "dataset_id": dataset_id,
                    "candidate_id": f"global-panel-{panel_number:03d}",
                    "candidate_kind": "global_liver_panel",
                    "automatic_candidate": False,
                    "phase": "multiphase_rgb_fusion",
                    "panel_number": panel_number,
                    "panel_total": panel_total,
                    "slice_indices": list(
                        panel.get("axial_indices_zyx_absolute") or []
                    ),
                    "image_path": _relative(root, image_path),
                    "image_sha256": actual_sha,
                    "source_manifest_path": _relative(
                        root, panel_manifest_path
                    ),
                    "source_manifest_sha256": sha256_file(
                        panel_manifest_path
                    ),
                    "lesion_mask_used": False,
                    "ground_truth_used": False,
                    "phi_metadata_removed": True,
                    "research_only": True,
                    "clinical_use_allowed": False,
                }
                assert_label_blind_record(
                    {
                        key: value
                        for key, value in record.items()
                        if key
                        not in {
                            # Safety attestations are allowed in the persisted
                            # envelope but are not model inputs.
                            "lesion_mask_used",
                            "ground_truth_used",
                        }
                    },
                    context=f"candidato {case_id}/{panel_number}",
                )
                records.append(record)
            observed_case_ids.add(case_id)
        source_summary.append(
            {
                "dataset_id": dataset_id,
                "root": _relative(root, source_root),
                "cohort_manifest_sha256": sha256_file(cohort_path),
                "case_count": len(case_ids),
            }
        )

    missing = sorted(expected_case_ids - observed_case_ids)
    unexpected = sorted(observed_case_ids - expected_case_ids)
    if unexpected:
        raise PipelineError(f"Casos inesperados: {unexpected[:5]}")
    failure_rows = [
        {
            "schema": "argos-hybrid-label-blind-technical-failure-v1",
            "case_id": case_id,
            "failure_reason": "no_verified_liver_enriched_panel_collection",
            "counts_as_error": True,
            "research_only": True,
        }
        for case_id in missing
    ]
    records.sort(
        key=lambda row: (
            row["case_id"],
            row["panel_number"],
            row["candidate_id"],
        )
    )
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    try:
        records_path = staging / "candidate_records.jsonl"
        failures_path = staging / "technical_failures.jsonl"
        _write_jsonl_fsync(records_path, records)
        _write_jsonl_fsync(failures_path, failure_rows)
        body = {
            "schema": CANDIDATE_DATASET_SCHEMA,
            "status": "complete_label_blind_pending_independent_verification",
            "protocol_signature": protocol["protocol_signature"],
            "splits_sha256": sha256_file(splits_path),
            "config_sha256": sha256_file(config_path),
            "sources": source_summary,
            "expected_case_count": len(expected_case_ids),
            "materialized_case_count": len(observed_case_ids),
            "technical_failure_count": len(missing),
            "candidate_record_count": len(records),
            "candidate_records_sha256": sha256_file(records_path),
            "technical_failures_sha256": sha256_file(failures_path),
            "ground_truth_read": False,
            "lesion_masks_read": 0,
            "lesion_contours_rendered": False,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        manifest = {**body, "dataset_signature": canonical_sha256(body)}
        manifest_path = staging / "dataset_manifest.json"
        manifest_path.write_text(
            json.dumps(
                manifest, ensure_ascii=False, indent=2, sort_keys=True
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return manifest


def verify_candidate_dataset(
    *,
    protocol_path: Path,
    splits_path: Path,
    workspace_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    root = Path(workspace_root).resolve()
    destination = Path(output_root).resolve()
    protocol = _verify_label_blind_binding(protocol_path, splits_path)
    _, expected_case_ids = _load_split_universe(splits_path)
    manifest = _json(destination / "dataset_manifest.json", "Dataset")
    unsigned = dict(manifest)
    signature = unsigned.pop("dataset_signature", None)
    if signature != canonical_sha256(unsigned):
        raise PipelineError("Assinatura do dataset diverge.")
    if manifest.get("protocol_signature") != protocol.get("protocol_signature"):
        raise PipelineError("Dataset não corresponde ao protocolo.")
    records_path = destination / "candidate_records.jsonl"
    failures_path = destination / "technical_failures.jsonl"
    if manifest.get("candidate_records_sha256") != sha256_file(records_path):
        raise PipelineError("Manifesto de candidatos foi alterado.")
    if manifest.get("technical_failures_sha256") != sha256_file(failures_path):
        raise PipelineError("Manifesto de falhas foi alterado.")
    records = [
        json.loads(line)
        for line in records_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    failures = [
        json.loads(line)
        for line in failures_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    cases_with_records = {str(row["case_id"]) for row in records}
    failed_cases = {str(row["case_id"]) for row in failures}
    if cases_with_records & failed_cases:
        raise PipelineError("Caso simultaneamente materializado e falho.")
    if cases_with_records | failed_cases != expected_case_ids:
        raise PipelineError("Dataset não cobre exatamente os splits.")
    if len(records) != int(manifest.get("candidate_record_count", -1)):
        raise PipelineError("candidate_record_count divergente.")
    for record in records:
        image_path = root / str(record["image_path"])
        if sha256_file(image_path) != record.get("image_sha256"):
            raise PipelineError(f"Imagem alterada: {record['image_path']}")
        if record.get("lesion_mask_used") is not False:
            raise PipelineError("Máscara de lesão detectada.")
        if record.get("ground_truth_used") is not False:
            raise PipelineError("Ground truth detectado.")
    if manifest.get("ground_truth_read") is not False:
        raise PipelineError("Dataset não é label-blind.")
    if manifest.get("lesion_masks_read") != 0:
        raise PipelineError("Dataset consumiu máscara de lesão.")
    return manifest

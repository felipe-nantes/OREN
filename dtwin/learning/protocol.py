"""Freeze and verify the hybrid supervised-training protocol."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from dtwin.core import PipelineError
from dtwin.learning.schemas import PROTOCOL_SCHEMA, ProtectedTrainingCase
from dtwin.learning.splits import build_nested_splits, validate_nested_splits


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise PipelineError(f"Artefato ausente: {path}") from exc
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def atomic_write_json(path: Path, value: Any) -> None:
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with Path(path).open("r", encoding="utf-8-sig") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise PipelineError(
                        f"Registro não é objeto em {path}:{line_number}."
                    )
                rows.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSONL protegido inválido: {path}") from exc
    if not rows:
        raise PipelineError(f"JSONL protegido vazio: {path}")
    return rows


def _safe_source(workspace_root: Path, path: Path) -> Path:
    root = Path(workspace_root).resolve()
    source = Path(path)
    if not source.is_absolute():
        source = root / source
    source = source.resolve()
    try:
        relative = source.relative_to(root)
    except ValueError as exc:
        raise PipelineError("Fonte protegida deve permanecer no workspace.") from exc
    lowered = str(relative).lower()
    if "casos/qualification" not in lowered.replace("\\", "/"):
        raise PipelineError("Fonte protegida fora de casos/qualification.")
    if "mask" in source.name.lower() or "lesion" in source.name.lower():
        raise PipelineError("Máscaras de lesão não são fontes de labels.")
    return source


def _read_config(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PipelineError(f"Config de treinamento inválida: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("Config de treinamento deve ser um objeto YAML.")
    return value


def _load_cases(
    config: dict[str, Any], workspace_root: Path
) -> tuple[list[ProtectedTrainingCase], list[dict[str, Any]]]:
    sources = config.get("protected_label_sources")
    if not isinstance(sources, list) or not sources:
        raise PipelineError("protected_label_sources deve ser lista não vazia.")
    cases: list[ProtectedTrainingCase] = []
    source_records: list[dict[str, Any]] = []
    for source_config in sources:
        if not isinstance(source_config, dict):
            raise PipelineError("Fonte protegida inválida.")
        dataset_id = str(source_config.get("dataset_id") or "").strip()
        source = _safe_source(
            workspace_root, Path(str(source_config.get("path") or ""))
        )
        rows = _load_jsonl(source)
        mapped = [
            ProtectedTrainingCase.from_mapping(row, dataset_id=dataset_id)
            for row in rows
        ]
        cases.extend(mapped)
        source_records.append(
            {
                "dataset_id": dataset_id,
                "path": source.relative_to(workspace_root.resolve()).as_posix(),
                "sha256": sha256_file(source),
                "case_count": len(mapped),
            }
        )
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise PipelineError("case_id duplicado entre coortes.")
    return cases, source_records


def load_protected_cases(
    config_path: Path, workspace_root: Path
) -> list[ProtectedTrainingCase]:
    """Load protected labels for training/evaluation after protocol freeze.

    Feature extractors must never call this function.
    """

    cases, _ = _load_cases(
        _read_config(config_path), Path(workspace_root).resolve()
    )
    return cases


def load_protected_label_rows(
    config_path: Path, workspace_root: Path
) -> list[dict[str, Any]]:
    """Load the RAW protected label rows, annotated with their dataset_id.

    ``load_protected_cases`` maps each row onto ``ProtectedTrainingCase``,
    whose subtype fields are restricted to the closed benchmark vocabulary.
    Cohort-specific clinical detail that has no canonical equivalent (for
    example LLD-MMRI's ``subtype``: hcc / hemangioma / hepatic_cyst / fnh) is
    dropped by that mapping. Retrospective evaluators that need the finer
    clinical breakdown read the raw rows through this function instead, going
    through the same authorized sources and the same path guards.

    Like ``load_protected_cases``, feature extractors must never call this.
    """

    config = _read_config(config_path)
    root = Path(workspace_root).resolve()
    sources = config.get("protected_label_sources")
    if not isinstance(sources, list) or not sources:
        raise PipelineError("protected_label_sources deve ser lista não vazia.")
    rows: list[dict[str, Any]] = []
    for source_config in sources:
        if not isinstance(source_config, dict):
            raise PipelineError("Fonte protegida inválida.")
        dataset_id = str(source_config.get("dataset_id") or "").strip()
        source = _safe_source(root, Path(str(source_config.get("path") or "")))
        for row in _load_jsonl(source):
            rows.append({**row, "dataset_id": dataset_id})
    return rows


def freeze_protocol(
    *,
    config_path: Path,
    workspace_root: Path,
    protocol_path: Path,
    splits_path: Path,
) -> dict[str, Any]:
    if Path(protocol_path).exists() or Path(splits_path).exists():
        raise PipelineError("Protocolo ou splits já existem; freeze é imutável.")
    config = _read_config(config_path)
    cases, sources = _load_cases(config, Path(workspace_root).resolve())
    validation = config.get("validation") or {}
    splits = build_nested_splits(
        cases,
        outer_folds=int(validation.get("outer_folds", 5)),
        inner_folds=int(validation.get("inner_folds", 4)),
        seed=int(validation.get("seed", 20260724)),
    )
    atomic_write_json(splits_path, splits)
    splits_sha = sha256_file(splits_path)
    label_counts = Counter(case.label for case in cases)
    dataset_counts = Counter(case.dataset_id for case in cases)
    body = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_before_supervised_feature_extraction",
        "candidate_id": str(config.get("candidate_id")),
        "target_condition": str(config.get("target_condition")),
        "primary_endpoint": {
            "positive": "focal_liver_lesion_or_target_pathology_suspicion",
            "negative": "normal_plus_benign_variant_plus_pseudolesion",
        },
        "acceptance": dict(config.get("acceptance") or {}),
        "validation": dict(validation),
        "failure_policy": dict(config.get("failure_policy") or {}),
        "protected_label_sources": sources,
        "aggregate_case_count": len(cases),
        "aggregate_label_counts": dict(sorted(label_counts.items())),
        "dataset_case_counts": dict(sorted(dataset_counts.items())),
        "splits_path": Path(splits_path)
        .resolve()
        .relative_to(Path(workspace_root).resolve())
        .as_posix(),
        "splits_sha256": splits_sha,
        "config_sha256": sha256_file(config_path),
        "labels_excluded_from_feature_artifacts": True,
        "lesion_masks_read_during_freeze": 0,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    protocol = {**body, "protocol_signature": canonical_sha256(body)}
    atomic_write_json(protocol_path, protocol)
    return protocol


def verify_protocol(
    *,
    config_path: Path,
    workspace_root: Path,
    protocol_path: Path,
    splits_path: Path,
) -> dict[str, Any]:
    try:
        protocol = json.loads(Path(protocol_path).read_text(encoding="utf-8"))
        splits = json.loads(Path(splits_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Protocolo ou splits ausentes/inválidos.") from exc
    if protocol.get("schema") != PROTOCOL_SCHEMA:
        raise PipelineError("Schema do protocolo inválido.")
    unsigned = dict(protocol)
    signature = unsigned.pop("protocol_signature", None)
    if signature != canonical_sha256(unsigned):
        raise PipelineError("Assinatura do protocolo diverge.")
    if protocol.get("config_sha256") != sha256_file(config_path):
        raise PipelineError("Config do protocolo foi alterado.")
    if protocol.get("splits_sha256") != sha256_file(splits_path):
        raise PipelineError("Splits foram alterados.")
    validate_nested_splits(splits)
    _, sources = _load_cases(
        _read_config(config_path), Path(workspace_root).resolve()
    )
    if sources != protocol.get("protected_label_sources"):
        raise PipelineError("Fonte protegida foi alterada.")
    if protocol.get("lesion_masks_read_during_freeze") != 0:
        raise PipelineError("Freeze não pode consumir máscara de lesão.")
    return protocol

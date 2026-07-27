"""Build a label-isolated public MRI cohort for independent ARGOS evaluation.

The builder consumes dataset-registry JSONL files and deliberately emits three
separate artifacts:

* ``inference_manifest.jsonl``: safe case identifiers and immutable input hashes;
* ``operational_source_map.jsonl``: local paths required by the runner;
* ``protected_labels.jsonl``: labels and annotations, for post-inference use only.

No file produced here is sent to MedGemma automatically.  The separation exists
to make accidental ground-truth leakage detectable before a benchmark starts.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import yaml

from dtwin.core import PipelineError
from dtwin.datasets.schema import REGISTRY_SCHEMA


CONFIG_SCHEMA = "argos-public-independent-cohort-config-v1"
INFERENCE_SCHEMA = "argos-public-independent-inference-manifest-v1"
SOURCE_MAP_SCHEMA = "argos-public-independent-source-map-v1"
LABELS_SCHEMA = "argos-public-independent-protected-labels-v1"
PROTOCOL_SCHEMA = "argos-public-independent-cohort-protocol-v1"
AUDIT_SCHEMA = "argos-public-independent-selection-audit-v1"
ROLES = {"positive", "negative"}
FORBIDDEN_INFERENCE_KEYS = {
    "annotation_path",
    "annotations",
    "dataset_id",
    "dataset_name",
    "diagnosis",
    "label",
    "negative_subtype",
    "phenotype_tags",
    "positive_subtype",
    "rag_class",
    "target_condition",
}


@dataclass(frozen=True)
class PublicSource:
    dataset_id: str
    role: str
    registry_path: Path
    root: Path
    root_alias: str
    subject_path_components: int = 1

    def validate(self) -> None:
        if not self.dataset_id:
            raise PipelineError("Fonte pública exige dataset_id.")
        if self.role not in ROLES:
            raise PipelineError(f"Papel inválido para {self.dataset_id}: {self.role!r}")
        if self.subject_path_components < 1:
            raise PipelineError("subject_path_components deve ser >= 1.")
        if not self.registry_path.is_file():
            raise PipelineError(f"Registry não encontrado: {self.registry_path}")
        if not self.root.is_dir():
            raise PipelineError(f"Raiz do dataset não encontrada: {self.root}")
        if not self.root_alias or not self.root_alias.startswith("src-"):
            raise PipelineError("root_alias deve ser opaco e começar com 'src-'.")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tree_fingerprint(paths: Iterable[Path], root: Path) -> tuple[str, int, int]:
    files: dict[str, Path] = {}
    resolved_root = root.resolve()
    for item in paths:
        resolved = item.resolve()
        try:
            resolved.relative_to(resolved_root)
        except ValueError as exc:
            raise PipelineError(f"Entrada fora da raiz autorizada: {item}") from exc
        candidates = [resolved] if resolved.is_file() else sorted(
            child for child in resolved.rglob("*") if child.is_file()
        )
        if not candidates:
            raise PipelineError(f"Entrada vazia ou ausente: {item}")
        for candidate in candidates:
            relative = candidate.relative_to(resolved_root).as_posix()
            files[relative] = candidate

    digest = hashlib.sha256()
    total_bytes = 0
    for relative, candidate in sorted(files.items()):
        size = candidate.stat().st_size
        total_bytes += size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(_file_hash(candidate).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest(), len(files), total_bytes


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise PipelineError(f"Falha ao ler registry {path}: {exc}") from exc
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PipelineError(f"JSON inválido em {path}:{line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise PipelineError(f"Registro deve ser objeto em {path}:{line_number}.")
        rows.append(row)
    if not rows:
        raise PipelineError(f"Registry vazio: {path}")
    return rows


def _safe_relative(value: Any, *, ref: str) -> PurePosixPath:
    token = str(value or "").replace("\\", "/").strip()
    path = PurePosixPath(token)
    if not token or path.is_absolute() or ".." in path.parts:
        raise PipelineError(f"raw_path inseguro em {ref}: {token!r}")
    return path


def _validate_registry_row(row: dict[str, Any], source: PublicSource, ref: str) -> None:
    if row.get("schema") != REGISTRY_SCHEMA:
        raise PipelineError(f"Schema de registry inválido em {ref}.")
    if row.get("dataset_id") != source.dataset_id:
        raise PipelineError(f"dataset_id divergente em {ref}.")
    if str(row.get("rag_class") or "").lower() != source.role:
        raise PipelineError(f"rag_class divergente do papel congelado em {ref}.")
    if str(row.get("modality") or "").upper() != "MR":
        raise PipelineError(f"Somente MR é permitido em {ref}.")
    if row.get("research_only") is not True or row.get("clinical_use_allowed") is not False:
        raise PipelineError(f"Salvaguardas de pesquisa ausentes em {ref}.")
    if str(row.get("source_format") or "").lower() not in {"dicom", "nifti"}:
        raise PipelineError(f"source_format inválido em {ref}.")
    if source.role == "negative" and row.get("positive_subtype") is not None:
        raise PipelineError(f"Subtipo positivo em fonte negativa: {ref}.")
    if source.role == "positive" and row.get("negative_subtype") is not None:
        raise PipelineError(f"Subtipo negativo em fonte positiva: {ref}.")


def _subject_relative(raw_path: PurePosixPath, components: int, ref: str) -> PurePosixPath:
    if len(raw_path.parts) < components:
        raise PipelineError(
            f"raw_path não possui {components} componentes para identificar sujeito em {ref}."
        )
    return PurePosixPath(*raw_path.parts[:components])


def anonymous_public_case_id(cohort_id: str, dataset_id: str, subject_relative: str) -> str:
    digest = hashlib.sha256(
        f"{cohort_id}\0{dataset_id}\0{subject_relative}".encode("utf-8")
    ).hexdigest()[:20]
    return f"anon-public-{digest}"


def _forbidden_paths(value: Any, prefix: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_INFERENCE_KEYS:
                found.append(f"{prefix}.{key}")
            found.extend(_forbidden_paths(child, f"{prefix}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_forbidden_paths(child, f"{prefix}[{index}]"))
    return found


def _jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(_canonical_bytes(row) + b"\n" for row in rows)


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def build_public_independent_cohort(
    *,
    cohort_id: str,
    sources: list[PublicSource],
    output_dir: Path,
    minimum_subjects_per_role: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Build a deterministic, hash-bound and label-isolated cohort bundle."""
    if not cohort_id or not sources:
        raise PipelineError("cohort_id e ao menos uma fonte são obrigatórios.")
    minimums = {"positive": 1, "negative": 1, **(minimum_subjects_per_role or {})}
    if set(minimums) != ROLES or any(int(value) < 1 for value in minimums.values()):
        raise PipelineError("minimum_subjects_per_role deve definir positive/negative >= 1.")

    seen_datasets: set[str] = set()
    seen_aliases: set[str] = set()
    grouped: dict[tuple[str, str], list[tuple[dict[str, Any], PurePosixPath]]] = {}
    source_by_dataset: dict[str, PublicSource] = {}
    registry_hashes: dict[str, str] = {}
    for source in sources:
        source.validate()
        if source.dataset_id in seen_datasets or source.root_alias in seen_aliases:
            raise PipelineError("dataset_id e root_alias devem ser únicos na coorte.")
        seen_datasets.add(source.dataset_id)
        seen_aliases.add(source.root_alias)
        source_by_dataset[source.dataset_id] = source
        registry_hashes[source.dataset_id] = _file_hash(source.registry_path)
        for index, row in enumerate(_read_jsonl(source.registry_path), 1):
            ref = f"{source.registry_path}:{index}"
            _validate_registry_row(row, source, ref)
            raw_path = _safe_relative(row.get("raw_path"), ref=ref)
            subject = _subject_relative(raw_path, source.subject_path_components, ref)
            grouped.setdefault((source.dataset_id, subject.as_posix()), []).append((row, raw_path))

    inference_rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    protected_rows: list[dict[str, Any]] = []
    role_counts = {"positive": 0, "negative": 0}
    dataset_counts: dict[str, int] = {}
    all_case_ids: set[str] = set()

    for (dataset_id, subject_relative), records in sorted(grouped.items()):
        source = source_by_dataset[dataset_id]
        role_counts[source.role] += 1
        dataset_counts[dataset_id] = dataset_counts.get(dataset_id, 0) + 1
        case_id = anonymous_public_case_id(cohort_id, dataset_id, subject_relative)
        if case_id in all_case_ids:
            raise PipelineError(f"Colisão de case_id: {case_id}")
        all_case_ids.add(case_id)

        raw_paths = sorted({path.as_posix() for _row, path in records})
        absolute_paths = [(source.root / PurePosixPath(path)).resolve() for path in raw_paths]
        fingerprint, file_count, total_bytes = _tree_fingerprint(absolute_paths, source.root)
        formats = {str(row.get("source_format")).lower() for row, _path in records}
        if len(formats) != 1:
            raise PipelineError(f"Formatos mistos no sujeito protegido {case_id}.")
        source_format = formats.pop()

        inference_row = {
            "schema": INFERENCE_SCHEMA,
            "case_id": case_id,
            "input_format": source_format.upper(),
            "series_or_volume_count": len(raw_paths),
            "source_file_count": file_count,
            "source_total_bytes": total_bytes,
            "source_sha256": fingerprint,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
            "ground_truth_read_during_inference": False,
            "lesion_mask_available_to_inference": False,
        }
        forbidden = _forbidden_paths(inference_row)
        if forbidden:
            raise PipelineError(f"Campo protegido vazou para inferência: {forbidden}")
        inference_rows.append(inference_row)
        source_rows.append({
            "schema": SOURCE_MAP_SCHEMA,
            "case_id": case_id,
            "root_alias": source.root_alias,
            "subject_relative_path": subject_relative,
            "raw_paths": raw_paths,
            "source_sha256": fingerprint,
            "never_send_to_model": True,
        })

        annotation_paths = sorted({
            str(row["annotation_path"])
            for row, _path in records
            if row.get("annotation_path")
        })
        first = records[0][0]
        protected_rows.append({
            "schema": LABELS_SCHEMA,
            "case_id": case_id,
            "label": source.role,
            "target_condition": "focal_liver_lesion_suspicion",
            "negative_subtype": first.get("negative_subtype") if source.role == "negative" else None,
            "positive_subtype": first.get("positive_subtype") if source.role == "positive" else None,
            "phenotype_tags": sorted(set(first.get("phenotype_tags") or [])),
            "dataset_id": dataset_id,
            "source_registry_case_ids": sorted(str(row.get("case_id")) for row, _path in records),
            "annotation_paths": annotation_paths,
            "label_basis": "public_dataset_documentation",
            "review_status": str(first.get("review_status") or "pending_review"),
            "research_only": True,
            "clinical_use_allowed": False,
        })

    for role, minimum in minimums.items():
        if role_counts[role] < int(minimum):
            raise PipelineError(
                f"Coorte insuficiente para {role}: {role_counts[role]} < {int(minimum)}."
            )

    inference_rows.sort(key=lambda row: row["case_id"])
    source_rows.sort(key=lambda row: row["case_id"])
    protected_rows.sort(key=lambda row: row["case_id"])
    if [row["case_id"] for row in inference_rows] != [row["case_id"] for row in protected_rows]:
        raise PipelineError("Manifestos cego e protegido não possuem os mesmos casos.")

    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError(f"Saída já existe; recuso sobrescrever freeze: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    try:
        inference_bytes = _jsonl_bytes(inference_rows)
        source_bytes = _jsonl_bytes(source_rows)
        labels_bytes = _jsonl_bytes(protected_rows)
        _write_bytes_atomic(temporary / "inference_manifest.jsonl", inference_bytes)
        _write_bytes_atomic(temporary / "operational_source_map.jsonl", source_bytes)
        protected_dir = temporary / "protected_ground_truth"
        _write_bytes_atomic(protected_dir / "protected_labels.jsonl", labels_bytes)

        inference_hash = hashlib.sha256(inference_bytes).hexdigest()
        source_map_hash = hashlib.sha256(source_bytes).hexdigest()
        labels_hash = hashlib.sha256(labels_bytes).hexdigest()
        positive_datasets = {source.dataset_id for source in sources if source.role == "positive"}
        negative_datasets = {source.dataset_id for source in sources if source.role == "negative"}
        domain_confounding = positive_datasets.isdisjoint(negative_datasets)
        protocol = {
            "schema": PROTOCOL_SCHEMA,
            "cohort_id": cohort_id,
            "case_count": len(inference_rows),
            "inference_manifest_sha256": inference_hash,
            "operational_source_map_sha256": source_map_hash,
            "protected_labels_sha256": labels_hash,
            "registry_sha256": dict(sorted(registry_hashes.items())),
            "selection_policy": "all_subjects_grouped_before_inference",
            "ground_truth_read_during_inference": False,
            "holdout_opened": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        protocol["protocol_signature"] = _canonical_hash(protocol)
        _write_bytes_atomic(
            temporary / "cohort_protocol.json",
            json.dumps(protocol, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n",
        )
        audit = {
            "schema": AUDIT_SCHEMA,
            "cohort_id": cohort_id,
            "case_count": len(inference_rows),
            "role_counts": role_counts,
            "dataset_counts": dict(sorted(dataset_counts.items())),
            "minimum_subjects_per_role": {key: int(value) for key, value in sorted(minimums.items())},
            "dataset_class_confounding": domain_confounding,
            "limitations": [
                "Classes originadas de datasets distintos podem ser separadas por domínio de aquisição.",
                "Este piloto mede generalização técnica e não substitui validação clínica balanceada no mesmo domínio.",
                "Labels e máscaras permanecem protegidos até a inferência completa e congelada.",
            ],
            "qualified_as_final_publication_evidence": False,
        }
        _write_bytes_atomic(
            protected_dir / "selection_audit.json",
            json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n",
        )
        temporary.replace(output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {**protocol, "role_counts": role_counts, "dataset_counts": dataset_counts, "domain_confounding": domain_confounding}


def load_public_cohort_config(path: Path) -> tuple[str, list[PublicSource], dict[str, int]]:
    """Load a versioned config; dataset roots are supplied only through env vars."""
    path = Path(path).resolve()
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise PipelineError(f"Config de coorte inválida ({path}): {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != CONFIG_SCHEMA:
        raise PipelineError(f"Config deve usar schema {CONFIG_SCHEMA}.")
    cohort_id = str(payload.get("cohort_id") or "").strip()
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise PipelineError("Config exige lista não vazia em sources.")
    sources: list[PublicSource] = []
    for index, item in enumerate(raw_sources, 1):
        if not isinstance(item, dict):
            raise PipelineError(f"Fonte inválida em sources[{index}].")
        root_env = str(item.get("root_env") or "").strip()
        root_value = os.environ.get(root_env) if root_env else None
        if not root_value:
            raise PipelineError(f"Variável de ambiente obrigatória ausente: {root_env or '<vazia>'}")
        registry_value = Path(str(item.get("registry") or ""))
        registry = registry_value if registry_value.is_absolute() else Path.cwd() / registry_value
        dataset_id = str(item.get("dataset_id") or "").strip()
        alias = "src-" + hashlib.sha256(dataset_id.encode("utf-8")).hexdigest()[:12]
        sources.append(PublicSource(
            dataset_id=dataset_id,
            role=str(item.get("role") or "").strip().lower(),
            registry_path=registry.resolve(),
            root=Path(root_value).resolve(),
            root_alias=alias,
            subject_path_components=int(item.get("subject_path_components", 1)),
        ))
    minimums = payload.get("minimum_subjects_per_role") or {"positive": 1, "negative": 1}
    if not isinstance(minimums, dict):
        raise PipelineError("minimum_subjects_per_role deve ser objeto.")
    return cohort_id, sources, {str(key): int(value) for key, value in minimums.items()}


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{label} inválido ({path}): {exc}") from exc
    if not isinstance(payload, dict):
        raise PipelineError(f"{label} deve ser objeto: {path}")
    return payload


def verify_public_independent_cohort(
    *,
    bundle_dir: Path,
    sources: list[PublicSource],
    expected_protocol_signature: str | None = None,
    recompute_source_hashes: bool = True,
) -> dict[str, Any]:
    """Fail-closed preflight that does not parse protected label contents."""
    bundle_dir = Path(bundle_dir).resolve()
    protocol_path = bundle_dir / "cohort_protocol.json"
    inference_path = bundle_dir / "inference_manifest.jsonl"
    source_map_path = bundle_dir / "operational_source_map.jsonl"
    protected_labels_path = bundle_dir / "protected_ground_truth" / "protected_labels.jsonl"
    for required in (protocol_path, inference_path, source_map_path, protected_labels_path):
        if not required.is_file():
            raise PipelineError(f"Artefato obrigatório ausente no preflight: {required}")

    protocol = _read_json_object(protocol_path, "Protocolo da coorte")
    if protocol.get("schema") != PROTOCOL_SCHEMA:
        raise PipelineError("Schema do protocolo da coorte é inválido.")
    signature = str(protocol.get("protocol_signature") or "")
    unsigned = dict(protocol)
    unsigned.pop("protocol_signature", None)
    if signature != _canonical_hash(unsigned):
        raise PipelineError("Assinatura do protocolo da coorte é inconsistente.")
    if expected_protocol_signature and signature != expected_protocol_signature:
        raise PipelineError("Assinatura do protocolo difere da assinatura esperada.")
    if protocol.get("holdout_opened") is not False:
        raise PipelineError("Protocolo não comprova holdout fechado.")
    if protocol.get("research_only") is not True or protocol.get("clinical_use_allowed") is not False:
        raise PipelineError("Salvaguardas de pesquisa inválidas no protocolo.")

    exact_hashes = {
        "inference_manifest_sha256": _file_hash(inference_path),
        "operational_source_map_sha256": _file_hash(source_map_path),
        # Hashing bytes is allowed; protected semantic fields are deliberately not parsed.
        "protected_labels_sha256": _file_hash(protected_labels_path),
    }
    for key, observed in exact_hashes.items():
        if protocol.get(key) != observed:
            raise PipelineError(f"Hash inconsistente no preflight: {key}.")

    inference_rows = _read_jsonl(inference_path)
    source_rows = _read_jsonl(source_map_path)
    inference_ids = [str(row.get("case_id") or "") for row in inference_rows]
    source_ids = [str(row.get("case_id") or "") for row in source_rows]
    if not inference_ids or len(inference_ids) != len(set(inference_ids)):
        raise PipelineError("case_id ausente ou duplicado no manifesto de inferência.")
    if inference_ids != sorted(inference_ids) or inference_ids != source_ids:
        raise PipelineError("Ordem/conjunto de casos divergente entre manifesto e source map.")
    if int(protocol.get("case_count", -1)) != len(inference_rows):
        raise PipelineError("case_count divergente no protocolo.")
    for row in inference_rows:
        if row.get("schema") != INFERENCE_SCHEMA:
            raise PipelineError("Schema inválido no manifesto de inferência.")
        forbidden = _forbidden_paths(row)
        if forbidden:
            raise PipelineError(f"Campo protegido vazou para inferência: {forbidden}")
        if row.get("ground_truth_read_during_inference") is not False:
            raise PipelineError("Manifesto não comprova cegueira de ground truth.")
        if row.get("lesion_mask_available_to_inference") is not False:
            raise PipelineError("Máscara de lesão foi disponibilizada à inferência.")

    roots: dict[str, Path] = {}
    for source in sources:
        source.validate()
        if source.root_alias in roots:
            raise PipelineError(f"root_alias duplicado no preflight: {source.root_alias}")
        roots[source.root_alias] = source.root.resolve()

    inference_by_id = {row["case_id"]: row for row in inference_rows}
    for row in source_rows:
        if row.get("schema") != SOURCE_MAP_SCHEMA or row.get("never_send_to_model") is not True:
            raise PipelineError("Source map não possui salvaguarda obrigatória.")
        alias = str(row.get("root_alias") or "")
        if alias not in roots:
            raise PipelineError(f"root_alias não autorizado no preflight: {alias!r}")
        raw_values = row.get("raw_paths")
        if not isinstance(raw_values, list) or not raw_values:
            raise PipelineError("Source map exige lista não vazia em raw_paths.")
        raw_paths = [_safe_relative(value, ref=str(row.get("case_id"))) for value in raw_values]
        absolute = [(roots[alias] / value).resolve() for value in raw_paths]
        if recompute_source_hashes:
            fingerprint, file_count, total_bytes = _tree_fingerprint(absolute, roots[alias])
            inference = inference_by_id[row["case_id"]]
            if fingerprint != row.get("source_sha256") or fingerprint != inference.get("source_sha256"):
                raise PipelineError(f"Fonte alterada após freeze: {row['case_id']}")
            if file_count != int(inference.get("source_file_count", -1)):
                raise PipelineError(f"Contagem de arquivos alterada após freeze: {row['case_id']}")
            if total_bytes != int(inference.get("source_total_bytes", -1)):
                raise PipelineError(f"Quantidade de bytes alterada após freeze: {row['case_id']}")

    return {
        "schema": "argos-public-independent-preflight-v1",
        "status": "ready_for_blind_inference",
        "cohort_id": protocol["cohort_id"],
        "case_count": len(inference_rows),
        "protocol_signature": signature,
        "artifact_integrity_passed": True,
        "source_integrity_passed": bool(recompute_source_hashes),
        "protected_labels_parsed": False,
        "ground_truth_read": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }

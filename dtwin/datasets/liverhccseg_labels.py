"""Fail-closed LiverHccSeg subject filtering from the official reading sheet."""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET

from dtwin.core import PipelineError
from dtwin.datasets.schema import REGISTRY_SCHEMA

OFFICIAL_V11_METADATA_MD5 = "37806f09955aa198ab8e50e0e2929da7"
AUDIT_SCHEMA = "argos-liverhccseg-protected-selection-audit-v1"
_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _digest(path: Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _column_index(reference: str) -> int:
    match = re.match(r"([A-Z]+)", reference.upper())
    if not match:
        raise PipelineError(f"Referência de célula XLSX inválida: {reference!r}")
    value = 0
    for character in match.group(1):
        value = value * 26 + ord(character) - ord("A") + 1
    return value - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        payload = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(payload)
    return [
        "".join(node.text or "" for node in item.findall(f".//{{{_MAIN_NS}}}t"))
        for item in root.findall(f"{{{_MAIN_NS}}}si")
    ]


def _xlsx_rows(path: Path) -> list[list[str]]:
    try:
        with zipfile.ZipFile(path) as archive:
            strings = _shared_strings(archive)
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise PipelineError(f"Planilha LiverHccSeg inválida ({path}): {exc}") from exc
    rows: list[list[str]] = []
    for row_node in sheet.findall(f".//{{{_MAIN_NS}}}row"):
        values: dict[int, str] = {}
        for cell in row_node.findall(f"{{{_MAIN_NS}}}c"):
            index = _column_index(str(cell.get("r") or ""))
            cell_type = cell.get("t")
            if cell_type == "inlineStr":
                value = "".join(
                    node.text or "" for node in cell.findall(f".//{{{_MAIN_NS}}}t")
                )
            else:
                node = cell.find(f"{{{_MAIN_NS}}}v")
                value = node.text if node is not None and node.text is not None else ""
                if cell_type == "s" and value:
                    try:
                        value = strings[int(value)]
                    except (ValueError, IndexError) as exc:
                        raise PipelineError("Índice sharedStrings inválido na planilha.") from exc
            values[index] = str(value).strip()
        if values:
            width = max(values) + 1
            rows.append([values.get(index, "") for index in range(width)])
    if not rows:
        raise PipelineError("Planilha LiverHccSeg não contém linhas.")
    return rows


def read_liverhccseg_subject_labels(
    metadata_path: Path,
    *,
    expected_md5: str = OFFICIAL_V11_METADATA_MD5,
    expected_subjects: int = 17,
    expected_tumor_subjects: int = 14,
) -> dict[str, Any]:
    """Read subject-level tumor availability without exposing labels to inference."""
    metadata_path = Path(metadata_path).resolve()
    if not metadata_path.is_file():
        raise PipelineError(f"Planilha LiverHccSeg não encontrada: {metadata_path}")
    observed_md5 = _digest(metadata_path, "md5")
    if expected_md5 and observed_md5.lower() != expected_md5.lower():
        raise PipelineError("MD5 da planilha LiverHccSeg diverge da versão oficial congelada.")
    rows = _xlsx_rows(metadata_path)
    header = [value.replace("\n", " ").strip() for value in rows[0]]
    try:
        patient_column = header.index("PatientID")
        index_column = header.index("Index")
    except ValueError as exc:
        raise PipelineError("Planilha LiverHccSeg não possui PatientID/Index esperados.") from exc
    by_subject: dict[str, list[str]] = defaultdict(list)
    for row in rows[1:]:
        patient_id = row[patient_column].strip() if patient_column < len(row) else ""
        if not patient_id.startswith("TCGA-"):
            continue
        lesion_index = row[index_column].strip() if index_column < len(row) else ""
        by_subject[patient_id].append(lesion_index)
    tumor_subjects = {
        patient_id
        for patient_id, indexes in by_subject.items()
        if any(value.lower().startswith("tumor") for value in indexes)
    }
    non_tumor_subjects = set(by_subject) - tumor_subjects
    if len(by_subject) != expected_subjects:
        raise PipelineError(
            f"Contagem de sujeitos LiverHccSeg inesperada: {len(by_subject)} != {expected_subjects}."
        )
    if len(tumor_subjects) != expected_tumor_subjects:
        raise PipelineError(
            "Contagem de sujeitos com tumor segmentado inesperada: "
            f"{len(tumor_subjects)} != {expected_tumor_subjects}."
        )
    return {
        "metadata_md5": observed_md5,
        "metadata_sha256": _digest(metadata_path),
        "subject_count": len(by_subject),
        "tumor_subject_count": len(tumor_subjects),
        "non_tumor_subject_count": len(non_tumor_subjects),
        "tumor_subjects": tumor_subjects,
        "non_tumor_subjects": non_tumor_subjects,
    }


def _registry_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise PipelineError(f"Falha ao ler registry LiverHccSeg: {exc}") from exc
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PipelineError(f"Registry inválido em {path}:{line_number}: {exc}") from exc
        if not isinstance(row, dict) or row.get("schema") != REGISTRY_SCHEMA:
            raise PipelineError(f"Schema de registry inválido em {path}:{line_number}.")
        if row.get("dataset_id") != "liverhccseg" or row.get("rag_class") != "positive":
            raise PipelineError(f"Registro não pertence ao registry positivo LiverHccSeg: linha {line_number}.")
        rows.append(row)
    if not rows:
        raise PipelineError("Registry LiverHccSeg está vazio.")
    return rows


def _atomic_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(path)


def filter_liverhccseg_tumor_positive_registry(
    *,
    registry_path: Path,
    metadata_path: Path,
    output_registry_path: Path,
    protected_audit_path: Path,
    expected_md5: str = OFFICIAL_V11_METADATA_MD5,
    expected_subjects: int = 17,
    expected_tumor_subjects: int = 14,
) -> dict[str, Any]:
    """Keep only scientifically read subjects with a segmented tumor."""
    output_registry_path = Path(output_registry_path).resolve()
    protected_audit_path = Path(protected_audit_path).resolve()
    if output_registry_path.exists() or protected_audit_path.exists():
        raise PipelineError("Recuso sobrescrever registry/auditoria LiverHccSeg congelados.")
    labels = read_liverhccseg_subject_labels(
        metadata_path,
        expected_md5=expected_md5,
        expected_subjects=expected_subjects,
        expected_tumor_subjects=expected_tumor_subjects,
    )
    rows = _registry_rows(Path(registry_path).resolve())
    selected: list[dict[str, Any]] = []
    observed_subjects: set[str] = set()
    for row in rows:
        raw = str(row.get("raw_path") or "").replace("\\", "/")
        path = PurePosixPath(raw)
        if path.is_absolute() or not path.parts or ".." in path.parts:
            raise PipelineError(f"raw_path inseguro no registry LiverHccSeg: {raw!r}")
        subject_id = path.parts[0]
        if subject_id not in labels["tumor_subjects"] and subject_id not in labels["non_tumor_subjects"]:
            raise PipelineError(
                "Sujeito do registry não foi encontrado na leitura científica; "
                "confirme que --root aponta para o nível Patient-ID."
            )
        observed_subjects.add(subject_id)
        if subject_id in labels["tumor_subjects"]:
            selected.append(row)
    missing = (labels["tumor_subjects"] | labels["non_tumor_subjects"]) - observed_subjects
    if missing:
        raise PipelineError(f"Registry não contém todos os {expected_subjects} sujeitos documentados.")
    selected_subjects = {PurePosixPath(str(row["raw_path"]).replace("\\", "/")).parts[0] for row in selected}
    if len(selected_subjects) != expected_tumor_subjects:
        raise PipelineError("Filtro não preservou exatamente os sujeitos tumor-positivos esperados.")
    selected.sort(key=lambda row: (str(row.get("raw_path")), str(row.get("case_id"))))
    _atomic_jsonl(output_registry_path, selected)
    audit = {
        "schema": AUDIT_SCHEMA,
        "status": "tumor_positive_registry_filtered",
        "source_registry_sha256": _digest(Path(registry_path).resolve()),
        "filtered_registry_sha256": _digest(output_registry_path),
        "metadata_md5": labels["metadata_md5"],
        "metadata_sha256": labels["metadata_sha256"],
        "documented_subject_count": labels["subject_count"],
        "included_tumor_subject_count": len(selected_subjects),
        "excluded_non_tumor_subject_count": labels["non_tumor_subject_count"],
        "included_subject_hashes": sorted(hashlib.sha256(value.encode()).hexdigest() for value in selected_subjects),
        "excluded_subject_hashes": sorted(
            hashlib.sha256(value.encode()).hexdigest() for value in labels["non_tumor_subjects"]
        ),
        "excluded_subjects_not_assumed_negative": True,
        "ground_truth_available_to_inference": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    protected_audit_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = protected_audit_path.with_name(f".{protected_audit_path.name}.tmp")
    temporary.write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(protected_audit_path)
    return audit


import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from dtwin.core import PipelineError
from dtwin.datasets.liverhccseg_labels import (
    filter_liverhccseg_tumor_positive_registry,
    read_liverhccseg_subject_labels,
)
from dtwin.datasets.schema import REGISTRY_SCHEMA


def _xlsx(path: Path, rows: list[list[str]]) -> str:
    def cell(column, row_number, value):
        letters = ""
        number = column + 1
        while number:
            number, remainder = divmod(number - 1, 26)
            letters = chr(65 + remainder) + letters
        escaped = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f'<c r="{letters}{row_number}" t="inlineStr"><is><t>{escaped}</t></is></c>'
    xml_rows = []
    for row_number, values in enumerate(rows, 1):
        xml_rows.append(f'<row r="{row_number}">' + "".join(
            cell(index, row_number, value) for index, value in enumerate(values)
        ) + "</row>")
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData>' + "".join(xml_rows) + '</sheetData></worksheet>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return hashlib.md5(path.read_bytes()).hexdigest()


def _metadata(tmp_path):
    path = tmp_path / "metadata.xlsx"
    md5 = _xlsx(path, [
        ["PatientID", "StudyDate", "Index"],
        ["TCGA-A", "1", "tumor1"],
        ["TCGA-A", "1", "tumor2"],
        ["TCGA-B", "2", ""],
        ["TCGA-C", "3", "tumor1"],
    ])
    return path, md5


def _registry(tmp_path):
    rows = []
    for patient in ("TCGA-A", "TCGA-B", "TCGA-C"):
        for sequence in ("ART", "PV"):
            rows.append({
                "schema": REGISTRY_SCHEMA,
                "case_id": f"{patient}-{sequence}",
                "dataset_id": "liverhccseg",
                "rag_class": "positive",
                "raw_path": f"{patient}/DATE/{sequence}",
            })
    path = tmp_path / "registry.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def test_reads_subject_level_tumor_status_without_openpyxl(tmp_path):
    metadata, md5 = _metadata(tmp_path)
    result = read_liverhccseg_subject_labels(
        metadata, expected_md5=md5, expected_subjects=3, expected_tumor_subjects=2,
    )
    assert result["subject_count"] == 3
    assert result["tumor_subjects"] == {"TCGA-A", "TCGA-C"}
    assert result["non_tumor_subjects"] == {"TCGA-B"}


def test_filter_excludes_non_tumor_without_calling_it_negative(tmp_path):
    metadata, md5 = _metadata(tmp_path)
    out = tmp_path / "positive.jsonl"
    audit_path = tmp_path / "protected" / "audit.json"
    audit = filter_liverhccseg_tumor_positive_registry(
        registry_path=_registry(tmp_path), metadata_path=metadata,
        output_registry_path=out, protected_audit_path=audit_path,
        expected_md5=md5, expected_subjects=3, expected_tumor_subjects=2,
    )
    rows = [json.loads(line) for line in out.read_text("utf-8").splitlines()]
    assert len(rows) == 4
    assert all("TCGA-B" not in row["raw_path"] for row in rows)
    assert audit["included_tumor_subject_count"] == 2
    assert audit["excluded_non_tumor_subject_count"] == 1
    assert audit["excluded_subjects_not_assumed_negative"] is True
    assert "TCGA-B" not in audit_path.read_text("utf-8")


def test_metadata_hash_and_counts_fail_closed(tmp_path):
    metadata, md5 = _metadata(tmp_path)
    with pytest.raises(PipelineError, match="MD5"):
        read_liverhccseg_subject_labels(
            metadata, expected_md5="0" * 32, expected_subjects=3, expected_tumor_subjects=2,
        )
    with pytest.raises(PipelineError, match="Contagem de sujeitos"):
        read_liverhccseg_subject_labels(
            metadata, expected_md5=md5, expected_subjects=4, expected_tumor_subjects=2,
        )


def test_registry_unknown_subject_fails_and_outputs_are_atomic(tmp_path):
    metadata, md5 = _metadata(tmp_path)
    registry = _registry(tmp_path)
    rows = [json.loads(line) for line in registry.read_text("utf-8").splitlines()]
    rows.append({
        "schema": REGISTRY_SCHEMA, "case_id": "unknown", "dataset_id": "liverhccseg",
        "rag_class": "positive", "raw_path": "TCGA-UNKNOWN/DATE/ART",
    })
    registry.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    out = tmp_path / "positive.jsonl"
    audit = tmp_path / "audit.json"
    with pytest.raises(PipelineError, match="não foi encontrado"):
        filter_liverhccseg_tumor_positive_registry(
            registry_path=registry, metadata_path=metadata, output_registry_path=out,
            protected_audit_path=audit, expected_md5=md5,
            expected_subjects=3, expected_tumor_subjects=2,
        )
    assert not out.exists() and not audit.exists()


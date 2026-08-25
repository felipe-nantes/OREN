"""Smoke do braço de apresentação S5 (REF-05/W-019): render_markdown_report.

A PHASE_07 justificou deixar a renderização sem teste; este smoke fecha a
lacuna sem tocar produção: monta o report com as MESMAS funções componentes
que evaluate_robustness usa (fiel ao schema real) e verifica invariantes
estruturais do markdown — não números científicos.
"""
from __future__ import annotations

import pytest

from dtwin.core import PipelineError
from dtwin.learning.robustness import (
    _metrics_for,
    bootstrap_confidence_interval,
    clinical_subtype_metrics,
    leave_one_dataset_out,
    render_markdown_report,
    subgroup_metrics,
)
from dtwin.learning.schemas import ProtectedTrainingCase


def _case(case_id, label, dataset_id, negative_subtype=None, positive_subtype=None):
    return ProtectedTrainingCase(
        case_id=case_id,
        patient_group_id=case_id,
        dataset_id=dataset_id,
        label=label,
        negative_subtype=negative_subtype,
        positive_subtype=positive_subtype,
        phenotype_tags=(),
    )


def _report():
    protected = {
        "a1": _case("a1", "POSITIVE", "ds_a", positive_subtype="hcc"),
        "a2": _case("a2", "NEGATIVE", "ds_a", negative_subtype="cyst"),
        "a3": _case("a3", "POSITIVE", "ds_a", positive_subtype="hcc"),
        "b1": _case("b1", "POSITIVE", "ds_b"),
        "b2": _case("b2", "NEGATIVE", "ds_b", negative_subtype="hemangioma"),
    }
    rows = [
        {"case_id": "a1", "prediction": "POSITIVE", "technical_failure": False, "score": 0.9},
        {"case_id": "a2", "prediction": "NEGATIVE", "technical_failure": False, "score": 0.2},
        # Falha técnica em caso POSITIVO: conta como FN no denominador (SCI-004).
        {"case_id": "a3", "prediction": None, "technical_failure": True, "score": None},
        {"case_id": "b1", "prediction": "POSITIVE", "technical_failure": False, "score": 0.8},
        {"case_id": "b2", "prediction": "NEGATIVE", "technical_failure": False, "score": 0.1},
    ]
    lodo = leave_one_dataset_out(rows, protected)
    subtipos = {"a1": "hcc", "a2": "cyst", "a3": "hcc"}
    return {
        "candidate_id": "smoke-candidate",
        "overall": _metrics_for(rows, protected),
        "leave_one_dataset_out": lodo,
        "bootstrap": bootstrap_confidence_interval(rows, protected, n_resamples=50, seed=7),
        "subgroups": subgroup_metrics(rows, protected),
        "clinical_subtypes": clinical_subtype_metrics(rows, protected, subtipos),
        "stability": {
            "worst_dataset_sensitivity": min(m["sensitivity"] for m in lodo.values()),
            "worst_dataset_specificity": min(m["specificity"] for m in lodo.values()),
            "all_datasets_pass_75_75": all(m["passed_75_75"] for m in lodo.values()),
        },
    }


def test_render_markdown_report_estrutura_completa():
    texto = render_markdown_report(_report())
    assert texto.startswith("# Robustez — smoke-candidate")
    for ancora in (
        "## Geral",
        "## Bootstrap por paciente (IC95%)",
        "## Leave-one-dataset-out",
        "## Cobertura de subtipo canônico (vocabulário fechado)",
        "## Desempenho por subtipo clínico (mimetizador)",
        "### Negativos por subtipo",
        "### Positivos por subtipo",
    ):
        assert ancora in texto, f"seção ausente: {ancora}"
    # Ambos os datasets aparecem na tabela LODO.
    assert "| ds_a |" in texto and "| ds_b |" in texto
    # O veredito do gate é um dos dois literais — nunca interpolação quebrada.
    assert ("APROVADO" in texto) or ("REPROVADO" in texto)
    assert "None%" not in texto
    assert texto.endswith("\n")


def test_render_markdown_report_deterministico():
    assert render_markdown_report(_report()) == render_markdown_report(_report())


def test_render_sem_subtipos_omite_secoes_opcionais():
    report = _report()
    report["clinical_subtypes"] = {"by_clinical_subtype": {}, "coverage": {}}
    report["subgroups"]["by_negative_subtype"] = {}
    report["subgroups"]["by_positive_subtype"] = {}
    texto = render_markdown_report(report)
    assert "## Desempenho por subtipo clínico" not in texto
    assert "### Negativos por subtipo" not in texto
    assert "### Positivos por subtipo" not in texto


def test_bootstrap_sem_grupos_falha_fechado():
    with pytest.raises(PipelineError, match="ao menos um grupo"):
        bootstrap_confidence_interval([], {}, n_resamples=10, seed=1)

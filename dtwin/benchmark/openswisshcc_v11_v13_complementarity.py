"""Diagnóstico exploratório de complementaridade entre v11 LOOCV e v13."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_v11_fusion import (
    _loocv_fusion,
    verify_fusion_protocol,
)
from dtwin.core import PipelineError, sha256_of


def compare_predictions(
    *,
    case_ids: list[str],
    truth: list[bool],
    v11_predictions: list[bool],
    v13_predictions: list[str],
) -> dict[str, Any]:
    size = len(case_ids)
    if (
        size == 0
        or len(set(case_ids)) != size
        or len(truth) != size
        or len(v11_predictions) != size
        or len(v13_predictions) != size
        or any(value not in {"POSITIVA", "NEGATIVA", "INCONCLUSIVA"} for value in v13_predictions)
    ):
        raise PipelineError("Vetores de complementaridade são inválidos ou desalinhados.")
    pair = {
        "both_correct": 0,
        "only_v11_correct": 0,
        "only_v13_correct": 0,
        "both_wrong_or_v13_inconclusive": 0,
    }
    v11_errors_corrected = {"positive": 0, "negative": 0}
    v13_errors_corrected = {"positive": 0, "negative": 0}
    oracle_tp = oracle_tn = 0
    rows = []
    for case_id, expected, first, second in zip(
        case_ids, truth, v11_predictions, v13_predictions, strict=True
    ):
        first_correct = first == expected
        second_correct = (
            ((second == "POSITIVA") == expected)
            if second != "INCONCLUSIVA"
            else False
        )
        if first_correct and second_correct:
            pair["both_correct"] += 1
        elif first_correct:
            pair["only_v11_correct"] += 1
        elif second_correct:
            pair["only_v13_correct"] += 1
        else:
            pair["both_wrong_or_v13_inconclusive"] += 1
        group = "positive" if expected else "negative"
        v11_errors_corrected[group] += int(not first_correct and second_correct)
        v13_errors_corrected[group] += int(not second_correct and first_correct)
        oracle_tp += int(expected and (first_correct or second_correct))
        oracle_tn += int(not expected and (first_correct or second_correct))
        rows.append({
            "case_id": case_id,
            "truth": "POSITIVE" if expected else "NEGATIVE",
            "v11_loocv_prediction": "POSITIVA" if first else "NEGATIVA",
            "v13_prediction": second,
            "v11_correct": first_correct,
            "v13_correct_primary": second_correct,
        })
    positives = sum(truth)
    negatives = size - positives
    v11_errors_corrected["total"] = sum(v11_errors_corrected.values())
    v13_errors_corrected["total"] = sum(v13_errors_corrected.values())
    return {
        "schema": "argos-openswisshcc-v11-v13-complementarity-v1",
        "status": "development_exploratory_only",
        "case_count": size,
        "positive_count": positives,
        "negative_count": negatives,
        "pair_correctness": pair,
        "v11_errors_corrected_by_v13": v11_errors_corrected,
        "v13_errors_corrected_by_v11": v13_errors_corrected,
        "oracle_any_correct": {
            "tp": oracle_tp,
            "tn": oracle_tn,
            "sensitivity": oracle_tp / positives if positives else None,
            "specificity": oracle_tn / negatives if negatives else None,
            "not_a_model_metric": True,
        },
        "case_rows": rows,
        "rule_selected": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }


def analyze_v11_v13_complementarity(
    *,
    v11_bundle_root: Path,
    v11_protocol_path: Path,
    v13_cases_path: Path,
    expected_case_count: int = 87,
) -> dict[str, Any]:
    paths = [
        Path(v11_bundle_root).resolve(),
        Path(v11_protocol_path).resolve(),
        Path(v13_cases_path).resolve(),
    ]
    if any("holdout" in str(path).lower() for path in paths):
        raise PipelineError("Análise de complementaridade não aceita caminhos de holdout.")
    protocol, rows = verify_fusion_protocol(
        bundle_root=paths[0],
        protocol_path=paths[1],
        expected_case_count=expected_case_count,
    )
    try:
        cases = [
            json.loads(line)
            for line in paths[2].read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Artefato de casos v13 ausente ou inválido.") from exc
    by_id: dict[str, dict[str, Any]] = {}
    for item in cases:
        case_id = str(item.get("case_id", "")) if isinstance(item, dict) else ""
        if (
            not case_id.startswith("anon-")
            or case_id in by_id
            or item.get("truth") not in {"positive", "negative"}
            or item.get("prediction") not in {"POSITIVA", "NEGATIVA", "INCONCLUSIVA"}
        ):
            raise PipelineError("Registro v13 inválido para análise de complementaridade.")
        by_id[case_id] = item
    case_ids = [str(row["case_id"]) for row in rows]
    if len(by_id) != expected_case_count or sorted(by_id) != sorted(case_ids):
        raise PipelineError("v11 e v13 não cobrem exatamente a mesma coorte.")
    truth = [by_id[case_id]["truth"] == "positive" for case_id in case_ids]
    loocv = _loocv_fusion(rows, truth)
    v11_predictions = [
        score >= threshold
        for score, threshold in zip(
            loocv["scores"], loocv["thresholds"], strict=True
        )
    ]
    result = compare_predictions(
        case_ids=case_ids,
        truth=truth,
        v11_predictions=v11_predictions,
        v13_predictions=[by_id[case_id]["prediction"] for case_id in case_ids],
    )
    result["v11_loocv_metrics"] = {
        key: loocv[key]
        for key in ("tp", "fn", "tn", "fp", "sensitivity", "specificity")
    }
    result["v11_protocol_signature"] = protocol["protocol_signature"]
    result["v13_cases_sha256"] = sha256_of(paths[2])
    return result


"""Subsistema de benchmark do webapp (REF-03 seam 2, extraído de server.py).

Byte-idêntico em comportamento. REGRA R2 do design: config, estado e todo
símbolo monkeypatchado (incl. write_run_outputs, que no server chega por
import) resolvem via `server.<nome>` EM TEMPO DE CHAMADA — nunca cópia
local — para que `monkeypatch.setattr(server, ...)` siga eficaz. Chamadas
internas a patch-targets (_run_benchmark_case etc.) também passam por
server. Import circular seguro: só o objeto módulo é capturado.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import platform
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import SimpleITK as sitk
from fastapi import HTTPException, Request
from starlette.datastructures import FormData

from dtwin.benchmark.hashing import git_state
from dtwin.benchmark.metrics import compute_benchmark_metrics
from dtwin.benchmark.runner import classify_screening_failure
from dtwin.benchmark.subtype_metrics import (
    SUBTYPE_CLASSES,
    binary_label_for_subtype,
    compute_subtype_metrics,
)
from dtwin.core import PipelineError, sha256_of
from dtwin.medgemma_client import (
    OPTIONAL_REPORT_V2_FIELDS,
    effective_config_sha256,
)
from dtwin.medgemma_volumetric import effective_screening_timeout
from webapp import server

log = logging.getLogger("dtwin.webapp")


def calculate_benchmark_metrics(results: list[dict]) -> dict:
    """Adaptador retrocompatível para o núcleo compartilhado do benchmark."""
    metrics = compute_benchmark_metrics(results)
    metrics["scoring_policy"] = "inconclusive_and_failed_count_as_errors"
    return metrics


def _benchmark_config(scenario: str) -> str:
    if scenario not in server.BENCHMARK_SCENARIOS:
        raise PipelineError(f"Cenário de benchmark não autorizado: {scenario!r}")
    configured = server.BENCHMARK_SCENARIOS[scenario]
    resolved = (server.REPO / configured).resolve()
    configs_root = (server.REPO / "configs").resolve()
    if resolved.parent != configs_root or not resolved.is_file():
        raise PipelineError(f"Configuração autorizada não encontrada: {configured}")
    return configured


def _individual_screening_config(scenario: str) -> str:
    """Resolve um modo autorizado da tela de exame individual."""
    if scenario not in server.INDIVIDUAL_SCREENING_SCENARIOS:
        raise PipelineError(f"Modo de exame individual não autorizado: {scenario!r}")
    configured = server.INDIVIDUAL_SCREENING_SCENARIOS[scenario]
    resolved = (server.REPO / configured).resolve()
    configs_root = (server.REPO / "configs").resolve()
    if resolved.parent != configs_root or not resolved.is_file():
        raise PipelineError(f"Configuração autorizada não encontrada: {configured}")
    return configured


def _benchmark_model_info(config_path: str | None = None) -> dict:
    config_path = config_path or server.MEDGEMMA_CONFIG
    try:
        screening = server.load_screening_config(server.REPO / config_path)
        model = screening.get("medgemma", {})
        return {
            "model_id": model.get("model_id"),
            "model_version": model.get("model_version"),
            "model_parameter_scale": model.get("model_parameter_scale"),
            "runtime": model.get("runtime", "transformers"),
            "experimental_strategy": str(
                screening.get("panel", {}).get("strategy", "uniform_9")
            ),
            "config": config_path,
        }
    except Exception:
        return {"model_id": None, "model_version": None, "config": config_path}


def _is_visual_scenario(scenario: str) -> bool:
    return scenario in server.VISUAL_BENCHMARK_SCENARIOS


def _visual_bundle_root(scenario: str) -> Path:
    """Resolve o bundle do classificador visual, sem aceitar caminho do navegador."""
    if scenario not in server.VISUAL_BENCHMARK_SCENARIOS:
        raise PipelineError(f"Cenário visual não autorizado: {scenario!r}")
    root = (server.REPO / server.VISUAL_BENCHMARK_SCENARIOS[scenario]).resolve()
    if not (root / "bundle_manifest.json").is_file():
        raise PipelineError(
            "Bundle do classificador visual não encontrado. Gere-o com: "
            "python -m tools.train_medsiglip_multiclass train-production"
        )
    return root


def _provenance_summary(results: list[dict]) -> dict:
    """Resume a procedência dos casos e diz se as métricas são interpretáveis.

    Sem isto, a tela apresenta acurácia/sensibilidade com o mesmo destaque de um
    resultado limpo mesmo quando todos os casos podem ter sido vistos no treino
    — que é exatamente como um número inflado vira conclusão. O veredito por
    caso vem do guard de três estados (`in_sample_verdict`).
    """
    counts = {"in_sample": 0, "out_of_sample": 0, "unknown": 0}
    for row in results:
        verdict = str(row.get("in_sample_verdict") or "unknown")
        counts[verdict if verdict in counts else "unknown"] += 1
    total = sum(counts.values())
    messages = []
    if counts["in_sample"]:
        messages.append(
            f"{counts['in_sample']} de {total} caso(s) foram vistos no treino do modelo: "
            "as métricas incluem desempenho in-sample, que é inflado."
        )
    if counts["unknown"]:
        messages.append(
            f"{counts['unknown']} de {total} caso(s) têm procedência NÃO verificável "
            "contra o conjunto de treino (identificadores de nomenclatura distinta). "
            "Eles podem ser in-sample."
        )
    clean = counts["out_of_sample"] == total and total > 0
    if not clean:
        messages.append(
            "Portanto estas métricas NÃO são estimativa de generalização. "
            "A estimativa honesta do modelo é o nested-OOF da Etapa C "
            "(75,91% sens. / 76,11% esp., docs/121)."
        )
    return {
        "counts": counts,
        "metrics_are_generalization_estimate": clean,
        "warning": " ".join(messages) or None,
    }


def _visual_model_info(scenario: str) -> dict:
    """Identidade do classificador visual, com o enquadramento honesto embutido."""
    try:
        manifest = json.loads((server._visual_bundle_root(scenario) / "bundle_manifest.json").read_text("utf-8"))
    except (PipelineError, OSError, json.JSONDecodeError):
        return {"model_id": "medsiglip_multiclass", "model_version": "indisponível"}
    return {
        "model_id": "medsiglip_multiclass_production_bundle",
        "model_version": str(manifest.get("candidate_id") or "hybrid_v1"),
        "bundle_signature": manifest.get("bundle_signature"),
        "decision_threshold": manifest.get("decision_threshold"),
        "generalization_estimate_source": manifest.get("generalization_estimate_source"),
        "oof_reference": "Etapa C nested-OOF 75,91%/76,11% (docs/121)",
        "gate_75_75_stable_by_dataset": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }


def _authorized_visual_phase_resolution(case_id: str, raw_case_dir: Path):
    """Resolve séries opacas apenas para IDs do benchmark cego autorizado.

    Casos comuns continuam usando as subpastas arterial/venous/delayed. O
    caminho do índice vem exclusivamente da configuração do servidor.
    """
    from dtwin.learning.internal_blind_phase_adapter import (
        BLIND_CASE_PATTERN,
        resolve_authorized_blind_phase_folders,
    )

    if not BLIND_CASE_PATTERN.fullmatch(str(case_id)):
        return None
    configured = Path(server.VISUAL_AUTHORIZED_PHASE_AUDIT)
    audit_path = configured if configured.is_absolute() else server.REPO / configured
    return resolve_authorized_blind_phase_folders(
        case_id=str(case_id),
        case_dir=Path(raw_case_dir),
        audit_path=audit_path.resolve(),
    )


def _subtype_fields(subtype: dict, positiva: bool) -> dict:
    """Campos de subtipo para a resposta, sem afirmar o que não se sabe.

    Duas coisas distintas que a interface não pode confundir:

    * **Triagem negativa não significa fígado sem lesão.** Só o CHC é positivo
      neste endpoint; HNF, hemangioma e cisto são negativos e continuam sendo
      alterações. Dizer "não há alteração" num negativo seria falso, e descartaria
      uma identificação que o modelo fez com confiança alta.
    * **Nomear exige base.** Se a massa de probabilidade foi para as classes sem
      subtipo documentado (docs/161), o subtipo fica indeterminado -- escolher o
      maior de quatro números quase nulos seria inventá-lo.
    """
    determinado = bool(subtype.get("determined"))
    campos = {
        "subtype_determined": determinado,
        "subtype": None,
        "subtype_label": None,
        "subtype_confidence": None,
        "subtype_named_lesion_mass": subtype.get("named_lesion_mass"),
        "subtype_is_screening_target": None,
        "subtype_unavailable_reason": None,
    }
    if not determinado:
        campos["subtype_unavailable_reason"] = subtype.get("reason")
        return campos
    nome = str(subtype["subtype"])
    campos.update(
        subtype=nome,
        subtype_label=server.SUBTYPE_LABELS_PT.get(nome, nome),
        subtype_confidence=subtype.get("subtype_confidence"),
        subtype_is_screening_target=(nome == server.SCREENING_TARGET_SUBTYPE),
    )
    if not positiva and nome == server.SCREENING_TARGET_SUBTYPE:
        # Triagem negativa mas a classe mais provável é o próprio alvo: as duas
        # leituras discordam e nenhuma deve ser apresentada como conclusão.
        campos["subtype_unavailable_reason"] = (
            "A triagem ficou abaixo do limiar, mas a classe mais provável é o "
            "próprio alvo. As duas leituras discordam e o caso exige revisão."
        )
    return campos


def _run_visual_benchmark_case(
    benchmark_id: str, index: int, item: dict, raw_case_dir: Path, scenario: str
) -> dict:
    """Executa o fluxo visual da Etapa C para UM exame multifásico.

    fases (subpastas) -> harmonização na grade venosa + segmentação hepática ->
    painéis liver-enriched -> embeddings MedSigLIP -> bundle de produção.
    Qualquer falha vira falha técnica (conta como erro), nunca decisão fabricada.
    """
    from dtwin.learning.exam_to_panels import build_exam_panels
    from dtwin.learning.multiphase_ingest import build_multiphase_case
    from dtwin.learning.visual_inference import (
        classify_embeddings,
        embed_panels,
        in_sample_status,
        load_production_bundle,
    )

    benchmark_root = server.WORKSPACE / "benchmarks" / benchmark_id
    case_dir = (benchmark_root / "cases" / f"{index:04d}").resolve()
    started = time.monotonic()
    base = {
        "case_id": item["id"],
        "dataset": item.get("dataset", "web_upload"),
        "input_format": "DICOM_MULTIPHASE",
        "prediction": None,
        "confidence": None,
        "status": "failed",
        "error": None,
        "input_hashes": {},
        "durations_seconds": {},
    }
    try:
        bundle = load_production_bundle(server._visual_bundle_root(scenario))
        authorized_resolution = _authorized_visual_phase_resolution(
            str(item["id"]), Path(raw_case_dir)
        )
        if authorized_resolution is not None:
            base["input_format"] = "DICOM_MULTIPHASE_AUTHORIZED_INDEX"
            base["phase_resolution"] = authorized_resolution.safe_manifest()

        def segment_venous(venous_dir: Path, work_dir: Path) -> Path:
            # Mesmo gate anatômico do exame individual. Sem ele, o benchmark
            # contava como acerto exames que a página individual recusava.
            work_dir = Path(work_dir).resolve()
            base["liver_mask_quality"] = server._segmentar_figado_com_gate(
                venous_dir, work_dir, f"Benchmark visual {benchmark_id}/{item['id']}"
            )
            return work_dir

        ingest_started = time.monotonic()
        multiphase = build_multiphase_case(
            case_id=str(item["id"]),
            case_upload_dir=Path(raw_case_dir),
            output_dir=case_dir / "multiphase",
            segment_venous=segment_venous,
            phase_dirs=(
                authorized_resolution.phase_dirs
                if authorized_resolution is not None
                else None
            ),
        )
        base["durations_seconds"]["multiphase_ingest_and_segmentation"] = round(
            time.monotonic() - ingest_started, 4
        )
        base["phase_coverage"] = multiphase.coverage

        panel_started = time.monotonic()
        panels = build_exam_panels(
            case_id=str(item["id"]),
            phase_paths=multiphase.phase_paths,
            coarse_liver_mask_path=multiphase.coarse_liver_mask_path,
            output_dir=case_dir / "panels",
            panel_config_path=server.REPO / server.VISUAL_PANEL_CONFIG,
        )
        base["durations_seconds"]["panel_generation"] = round(time.monotonic() - panel_started, 4)

        inference_started = time.monotonic()
        embeddings = embed_panels(server.REPO / server.VISUAL_EMBEDDING_CONFIG, panels.panel_paths)
        decision = classify_embeddings(bundle, embeddings)
        base["durations_seconds"]["visual_inference"] = round(time.monotonic() - inference_started, 4)

        # Sem mapa de proveniência, um identificador de coorte com nomenclatura
        # própria (ex.: benchmark cego) cai em 'unknown' — que NÃO é o mesmo que
        # out-of-sample e não deve ser lido como tal.
        status = in_sample_status(bundle, case_id=str(item["id"]))
        positiva = decision["prediction"] == "POSITIVE"
        base.update(
            prediction="POSITIVA" if positiva else "NEGATIVA",
            confidence=None,
            status="decisive",
            visual_score=decision["score"],
            visual_threshold=decision["threshold"],
            panel_count=decision["panel_count"],
            in_sample=status["in_sample"],
            in_sample_verdict=status["verdict"],
            class_probabilities=decision["class_probabilities"],
        )
        base.update(server._subtype_fields(decision["subtype"], positiva))
        return base
    except subprocess.TimeoutExpired:
        base["error"] = "O processamento excedeu o tempo limite."
        base["status"] = "timeout"
        return base
    except PipelineError as exc:
        base["error"] = str(exc)
        return base
    except Exception as exc:
        log.exception("Benchmark visual %s/%s: falha inesperada", benchmark_id, item["id"])
        base["error"] = f"Falha inesperada: {type(exc).__name__}"
        return base
    finally:
        base["duration_seconds"] = round(time.monotonic() - started, 2)
        base["durations_seconds"]["total"] = round(time.monotonic() - started, 4)


def _run_benchmark_case(
    benchmark_id: str,
    index: int,
    item: dict,
    raw_case_dir: Path,
    medgemma_config: str | None = None,
) -> dict:
    """Executa segmentação + triagem para um exame, sem gerar a malha 3D."""
    benchmark_root = server.WORKSPACE / "benchmarks" / benchmark_id
    # case_dir PRECISA ser absoluto: a segmentação roda por um launcher com
    # cwd=%TEMP% (workaround do nnU-Net no Windows). Se for relativo, a saída cai
    # sob %TEMP% e server._seg_done() — avaliado a partir da raiz do repo — nunca a
    # encontra, marcando TODO exame como falha (e forçando o fallback lento p/ CPU).
    # O fluxo de exame individual (process_job) já resolve por isso; espelhamos aqui.
    case_dir = (benchmark_root / "cases" / f"{index:04d}").resolve()
    series_dir = benchmark_root / "_series" / f"{index:04d}"
    started = time.monotonic()
    base = {
        "case_id": item["id"],
        "dataset": item.get("dataset", "web_upload"),
        "input_format": "DICOM",
        "prediction": None,
        "confidence": None,
        "status": "failed",
        "error": None,
        "input_hashes": {},
        "durations_seconds": {},
    }
    medgemma_config = medgemma_config or server.MEDGEMMA_CONFIG
    try:
        import_started = time.monotonic()
        best_files, n = server.find_best_series(raw_case_dir)
        if not best_files or n < server.MIN_SLICES:
            base["error"] = "Nenhuma série DICOM de RM válida foi encontrada."
            return base

        series_dir.mkdir(parents=True, exist_ok=True)
        for file_index, source in enumerate(best_files):
            shutil.copyfile(source, series_dir / f"{file_index:05d}_{os.path.basename(source)}")
        base["durations_seconds"]["import"] = round(time.monotonic() - import_started, 4)

        preparation_started = time.monotonic()
        prep = server._segment(str(series_dir.resolve()), case_dir, "gpu", server.PREP_TIMEOUT_GPU, fast=True)
        if not server._seg_done(case_dir):
            reason = server._cli_reason(prep)
            log.warning("Benchmark %s/%s: GPU falhou (%s); tentando CPU", benchmark_id, item["id"], reason[:100])
            shutil.rmtree(case_dir, ignore_errors=True)
            prep = server._segment(str(series_dir.resolve()), case_dir, "cpu", server.PREP_TIMEOUT_CPU, fast=True)
            if not server._seg_done(case_dir):
                base["error"] = server._friendly_text(server._cli_reason(prep))
                return base
        server._persist_series_selection(case_dir, best_files)
        base["durations_seconds"]["preparation_and_segmentation"] = round(
            time.monotonic() - preparation_started, 4
        )

        screening_started = time.monotonic()
        screening_config = server.load_screening_config(server.REPO / medgemma_config)
        effective_timeout, expected_panel_count = effective_screening_timeout(
            sitk.GetArrayFromImage(sitk.ReadImage(str(case_dir / "mask_organ.nii.gz"))) > 0,
            screening_config,
            server.SCREEN_TIMEOUT,
        )
        with server._medgemma_screening_lock:
            screening = server._run(
                [
                    server.PY,
                    "-m",
                    "dtwin.medgemma_screening",
                    "--case-dir",
                    str(case_dir),
                    "--medgemma-config",
                    medgemma_config,
                    "--confirm-no-visible-phi",
                ],
                timeout=effective_timeout,
            )
        envelope = server._load_report(case_dir / "outputs" / "medgemma" / "medgemma_report.json")
        if envelope is None:
            reason = server._cli_reason(screening)
            base["error"] = server._friendly_text(reason)
            base["status"] = classify_screening_failure(reason).value
            base["screening_diagnostics"] = server._persist_screening_diagnostics(case_dir, screening)
            failure_path = case_dir / "outputs" / "medgemma" / "medgemma_failure.json"
            if failure_path.is_file():
                base["failure_artifact"] = str(failure_path.relative_to(case_dir))
            return base

        report = envelope["report"]
        base["durations_seconds"].update(envelope.get("durations_seconds") or {})
        base["durations_seconds"]["screening_subprocess"] = round(
            time.monotonic() - screening_started, 4
        )
        base["input_hashes"] = {
            "volume": envelope.get("input_volume_sha256"),
            "mask_organ": envelope.get("input_liver_mask_sha256"),
            "panel": envelope.get("input_panel_sha256"),
            "screening_config": envelope.get("screening_config_sha256"),
            "panels": {
                item["image"]: item["sha256"] for item in envelope.get("input_panels", [])
            },
        }
        prediction = str(report.get("resultado_hipotese", "")).upper()
        if prediction not in {"POSITIVA", "NEGATIVA", "INCONCLUSIVA"}:
            base["error"] = "O relatório retornou uma classificação inválida."
            base["status"] = "invalid_response"
            return base
        base.update(
            prediction=prediction,
            confidence=report.get("confianca"),
            status="inconclusive" if prediction == "INCONCLUSIVA" else "decisive",
            report_summary=report.get("resumo_do_achado"),
            # Campos v2 (schema pathology-target) só existem quando o modelo os
            # emite; preservados aqui para estratificar o benchmark e o CSV.
            report_v2={
                key: report[key] for key in OPTIONAL_REPORT_V2_FIELDS if key in report
            },
            report_path=str(
                Path("cases") / f"{index:04d}" / "outputs" / "medgemma" / "medgemma_report.json"
            ),
            panel_path=str(
                Path("cases") / f"{index:04d}" / "outputs" / "medgemma" / str(envelope.get("input_panel") or "")
            ),
            panel_paths=[
                str(Path("cases") / f"{index:04d}" / "outputs" / "medgemma" / item["image"])
                for item in envelope.get("input_panels", [])
            ],
            panel_strategy=screening_config.get("panel", {}).get("strategy", "uniform_9"),
            expected_panel_count=expected_panel_count,
            effective_screening_timeout_seconds=effective_timeout,
        )
        return base
    except subprocess.TimeoutExpired:
        base["error"] = "O processamento excedeu o tempo limite."
        base["status"] = "timeout"
        return base
    except Exception as exc:
        log.exception("Benchmark %s/%s: falha inesperada", benchmark_id, item["id"])
        base["error"] = f"Falha inesperada: {type(exc).__name__}"
        return base
    finally:
        base["duration_seconds"] = round(time.monotonic() - started, 2)
        base["durations_seconds"]["total"] = round(time.monotonic() - started, 4)
        shutil.rmtree(series_dir, ignore_errors=True)


def _evaluate_benchmark_result(
    inference_result: dict,
    label: str,
    truth_subtype: str | None = None,
) -> dict:
    """Anexa ground truths binário e multiclasse somente após a inferência."""
    started = time.monotonic()
    result = dict(inference_result)
    expected = "POSITIVA" if label == "positive" else "NEGATIVA"
    prediction = result.get("prediction")
    result.update(
        truth=label,
        truth_subtype=truth_subtype,
        correct=(prediction == expected) if prediction in {"POSITIVA", "NEGATIVA"} else None,
        protected_ground_truth_hashes={"lesion_mask": None, "annotation_manifest": None},
    )
    durations = dict(result.get("durations_seconds") or {})
    durations["evaluation"] = round(time.monotonic() - started, 4)
    result["durations_seconds"] = durations
    return result


def process_benchmark(benchmark_id: str, manifest: dict, raw_dir: Path) -> None:
    benchmark_root = server.WORKSPACE / "benchmarks" / benchmark_id
    cases = manifest["cases"]
    started_at = datetime.now(timezone.utc).isoformat()
    results: list[dict] = []
    try:
        scenario = manifest.get("scenario", "baseline")
        visual = server._is_visual_scenario(scenario)
        medgemma_config = None if visual else _benchmark_config(scenario)
        server._set_benchmark(benchmark_id, state="processing", started_at=started_at)
        for index, item in enumerate(cases, start=1):
            progress = 5 + int(((index - 1) / max(len(cases), 1)) * 90)
            server._set_benchmark(
                benchmark_id,
                current_case=item["id"],
                processed=index - 1,
                progress=progress,
            )
            case_item = {"id": item["id"], "dataset": manifest["dataset_name"]}
            if visual:
                inference_result = server._run_visual_benchmark_case(
                    benchmark_id, index, case_item, raw_dir / f"{index:04d}", scenario
                )
            else:
                inference_result = server._run_benchmark_case(
                    benchmark_id, index, case_item, raw_dir / f"{index:04d}", medgemma_config
                )
            results.append(
                _evaluate_benchmark_result(
                    inference_result,
                    item["label"],
                    item.get("truth_subtype"),
                )
            )
            server._set_benchmark(benchmark_id, processed=index, progress=5 + int(index / len(cases) * 90))

        completed_at = datetime.now(timezone.utc).isoformat()
        model_info = (
            server._visual_model_info(scenario) if visual else server._benchmark_model_info(medgemma_config)
        )
        metrics = calculate_benchmark_metrics(results)
        subtype_metrics = (
            compute_subtype_metrics(results)
            if manifest.get("evaluation_mode") == "pathology_and_subtype"
            else None
        )
        combined_target = {
            "requires_binary_and_subtype_targets": bool(subtype_metrics),
            "binary_met": metrics["target"]["met"],
            "subtype_met": subtype_metrics["target"]["met"] if subtype_metrics else None,
            "met": bool(
                metrics["target"]["met"]
                and (subtype_metrics is None or subtype_metrics["target"]["met"])
            ),
        }
        report = {
            "schema_version": 1,
            "benchmark_id": benchmark_id,
            "dataset_name": manifest["dataset_name"],
            "dataset_kind": manifest["dataset_kind"],
            "evaluation_mode": manifest.get("evaluation_mode", "binary"),
            "scenario": manifest.get("scenario", "baseline"),
            "started_at": started_at,
            "completed_at": completed_at,
            "model": model_info,
            "metrics": metrics,
            "subtype_metrics": subtype_metrics,
            "combined_target": combined_target,
            "provenance": _provenance_summary(results) if visual else None,
            "cases": results,
            "disclaimer": server.DISCLAIMER,
        }
        benchmark_root.mkdir(parents=True, exist_ok=True)
        report_path = benchmark_root / "benchmark_report.json"
        temp = benchmark_root / ".benchmark_report.json.tmp"
        temp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(report_path)
        config_path = (
            None
            if visual
            else (server.REPO / str(medgemma_config)).resolve()
        )
        run_manifest = {
            "schema_version": 1,
            "run_id": benchmark_id,
            "created_at": started_at,
            **git_state(server.REPO),
            "model_family": "MedSigLIP" if visual else "MedGemma",
            **model_info,
            "medgemma_config_path": medgemma_config,
            "medgemma_config_hash": (
                effective_config_sha256(server.load_screening_config(config_path))
                if config_path is not None and config_path.is_file()
                else None
            ),
            "visual_panel_config_path": server.VISUAL_PANEL_CONFIG if visual else None,
            "visual_embedding_config_path": server.VISUAL_EMBEDDING_CONFIG if visual else None,
            "visual_panel_config_sha256": (
                sha256_of((server.REPO / server.VISUAL_PANEL_CONFIG).resolve())
                if visual and (server.REPO / server.VISUAL_PANEL_CONFIG).is_file()
                else None
            ),
            "visual_embedding_config_sha256": (
                sha256_of((server.REPO / server.VISUAL_EMBEDDING_CONFIG).resolve())
                if visual and (server.REPO / server.VISUAL_EMBEDDING_CONFIG).is_file()
                else None
            ),
            "dataset_names": [manifest["dataset_name"]],
            "num_cases_total": len(cases),
            "num_cases_positive": sum(item["label"] == "positive" for item in cases),
            "num_cases_negative": sum(item["label"] == "negative" for item in cases),
            "started_at": started_at,
            "finished_at": completed_at,
            "duration_seconds_total": round(
                sum(float(item.get("duration_seconds") or 0) for item in results), 4
            ),
            "environment": {
                "python_version": platform.python_version(),
                "platform": platform.platform(),
            },
            "research_only": True,
            "evaluation_mode": manifest.get("evaluation_mode", "binary"),
            "subtype_reference_vocabulary": (
                list(SUBTYPE_CLASSES)
                if manifest.get("evaluation_mode") == "pathology_and_subtype"
                else None
            ),
        }
        server.write_run_outputs(benchmark_root, run_manifest, results, metrics)
        if subtype_metrics is not None:
            subtype_path = benchmark_root / "metrics_subtype.json"
            subtype_temp = benchmark_root / ".metrics_subtype.json.tmp"
            subtype_temp.write_text(
                json.dumps(subtype_metrics, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            subtype_temp.replace(subtype_path)
        server._set_benchmark(
            benchmark_id,
            state="done",
            current_case=None,
            processed=len(cases),
            progress=100,
            report=report,
        )
    except Exception as exc:
        log.exception("Benchmark %s: falha inesperada", benchmark_id)
        server._set_benchmark(
            benchmark_id,
            state="failed",
            progress=100,
            error=f"Não foi possível concluir o benchmark: {type(exc).__name__}",
        )
    finally:
        shutil.rmtree(raw_dir, ignore_errors=True)


def _parse_benchmark_manifest(raw: str, file_count: int) -> dict:
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Manifesto do benchmark inválido.") from exc
    if not isinstance(manifest, dict):
        raise HTTPException(status_code=400, detail="Manifesto do benchmark inválido.")
    dataset_name = str(manifest.get("dataset_name") or "").strip()[:120]
    dataset_kind = manifest.get("dataset_kind")
    evaluation_mode = str(manifest.get("evaluation_mode") or "binary")
    scenario = str(manifest.get("scenario") or "baseline")
    cases = manifest.get("cases")
    if not dataset_name:
        raise HTTPException(status_code=400, detail="Informe o nome do dataset.")
    if dataset_kind not in {"positive", "negative", "mixed"}:
        raise HTTPException(status_code=400, detail="Tipo de dataset inválido.")
    if evaluation_mode not in {"binary", "pathology_and_subtype"}:
        raise HTTPException(status_code=400, detail="Modo de avaliação inválido.")
    if evaluation_mode == "pathology_and_subtype" and dataset_kind != "mixed":
        raise HTTPException(
            status_code=400,
            detail="O benchmark de patologia e variação exige dataset misto.",
        )
    if scenario not in server.BENCHMARK_SCENARIOS and scenario not in server.VISUAL_BENCHMARK_SCENARIOS:
        raise HTTPException(status_code=400, detail="Cenário de benchmark inválido.")
    if not isinstance(cases, list) or not cases:
        raise HTTPException(status_code=400, detail="Nenhum exame foi identificado no dataset.")

    seen_ids: set[str] = set()
    seen_files: set[int] = set()
    normalized = []
    for case in cases:
        if not isinstance(case, dict):
            raise HTTPException(status_code=400, detail="Definição de exame inválida.")
        case_id = str(case.get("id") or "").strip()[:120]
        label = case.get("label")
        truth_subtype = case.get("truth_subtype")
        if truth_subtype is not None:
            truth_subtype = str(truth_subtype).strip()
        if evaluation_mode == "pathology_and_subtype":
            if truth_subtype not in SUBTYPE_CLASSES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Subtipo de referência inválido no exame {case_id}.",
                )
            expected_label = binary_label_for_subtype(truth_subtype)
            if label != expected_label:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Rótulo binário incompatível com o subtipo no exame {case_id}."
                    ),
                )
        elif truth_subtype:
            raise HTTPException(
                status_code=400,
                detail="Subtipo protegido só é aceito no modo patologia e variação.",
            )
        indices = case.get("file_indices")
        if not case_id or case_id in seen_ids:
            raise HTTPException(status_code=400, detail="Os exames precisam de identificadores únicos.")
        if label not in {"positive", "negative"}:
            raise HTTPException(status_code=400, detail=f"Rótulo inválido no exame {case_id}.")
        if dataset_kind in {"positive", "negative"} and label != dataset_kind:
            raise HTTPException(
                status_code=400,
                detail=f"O rótulo do exame {case_id} não corresponde ao tipo do dataset.",
            )
        if not isinstance(indices, list) or not indices:
            raise HTTPException(status_code=400, detail=f"O exame {case_id} não contém arquivos.")
        clean_indices = []
        for value in indices:
            if not isinstance(value, int) or value < 0 or value >= file_count or value in seen_files:
                raise HTTPException(status_code=400, detail="Mapeamento de arquivos do benchmark inválido.")
            seen_files.add(value)
            clean_indices.append(value)
        seen_ids.add(case_id)
        normalized.append({
            "id": case_id,
            "label": label,
            "truth_subtype": truth_subtype if evaluation_mode == "pathology_and_subtype" else None,
            "file_indices": clean_indices,
        })
    if seen_files != set(range(file_count)):
        raise HTTPException(status_code=400, detail="Todos os arquivos devem pertencer a um exame.")
    return {
        "dataset_name": dataset_name, "dataset_kind": dataset_kind,
        "evaluation_mode": evaluation_mode,
        "scenario": scenario, "cases": normalized,
    }


def _csv_cell(value: Any) -> Any:
    """Serializa valores compostos/booleanos de forma estável para o CSV."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ";".join(str(v) for v in value)
    return value


def _benchmark_csv(report: dict) -> str:
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow([
        "case_id", "truth", "prediction", "status", "correct", "confidence",
        "duration_seconds", "error",
        "truth_subtype", "predicted_subtype_for_scoring", "subtype_correct",
        # Identificação da alteração (modo visual). `subtype_determined` falso num
        # caso POSITIVA não é dado faltante: é o modelo declarando que não tem base
        # para nomear o subtipo neste exame (docs/161).
        "subtype_determined", "subtype", "subtype_confidence",
        "subtype_named_lesion_mass", "subtype_unavailable_reason",
        # Taxonomia protegida (preenchida quando o manifesto a declara).
        "target_condition", "negative_subtype", "positive_subtype", "phenotype_tags",
        # Schema v2 do relatório MedGemma (cenário pathology-target).
        "ha_lesao_focal_suspeita", "ha_variante_anatomica_benigna",
        "ha_pseudolesao_ou_artefato", "tipo_alteracao_nao_alvo",
    ])
    for item in report.get("cases", []):
        v2 = item.get("report_v2") or {}
        writer.writerow([
            item.get("case_id"), item.get("truth"), item.get("prediction"),
            item.get("status"), item.get("correct"), item.get("confidence"),
            item.get("duration_seconds"), _csv_cell(item.get("error")),
            _csv_cell(item.get("truth_subtype")),
            _csv_cell(item.get("predicted_subtype_for_scoring")),
            _csv_cell(item.get("subtype_correct")),
            _csv_cell(item.get("subtype_determined")),
            _csv_cell(item.get("subtype")),
            _csv_cell(item.get("subtype_confidence")),
            _csv_cell(item.get("subtype_named_lesion_mass")),
            _csv_cell(item.get("subtype_unavailable_reason")),
            _csv_cell(item.get("target_condition")),
            _csv_cell(item.get("negative_subtype")),
            _csv_cell(item.get("positive_subtype")),
            _csv_cell(item.get("phenotype_tags")),
            _csv_cell(v2.get("ha_lesao_focal_suspeita")),
            _csv_cell(v2.get("ha_variante_anatomica_benigna")),
            _csv_cell(v2.get("ha_pseudolesao_ou_artefato")),
            _csv_cell(v2.get("tipo_alteracao_nao_alvo")),
        ])
    return stream.getvalue()


async def _upload_form(request: Request) -> FormData:
    """Analisa o multipart com o teto de arquivos elevado (server.MAX_UPLOAD_FILES).

    FastAPI não expõe max_files/max_fields do parser do Starlette através de
    File(...)/Form(...); por isso o form é lido manualmente aqui, nos dois
    endpoints que recebem upload de exames. Sem `async with`: os UploadFile
    precisam continuar abertos até serem lidos no corpo do endpoint; o
    encerramento/limpeza é feito pelo próprio Starlette ao fim da requisição."""
    return await request.form(max_files=server.MAX_UPLOAD_FILES, max_fields=server.MAX_UPLOAD_FILES)



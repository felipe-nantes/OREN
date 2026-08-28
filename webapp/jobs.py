"""Workers de análise do webapp (REF-03 seam 3, extraído de server.py).

process_job, process_visual_job, process_monophase_medsiglip_job e o
advisory tardio. Byte-idêntico em comportamento. REGRA R2 do design:
config, estado (_jobs/_set/locks) e TODO patch-target (26 inventariados,
incl. _subtype_fields/_visual_bundle_root/load_screening_config que chegam
por import no server) resolvem via `server.<nome>` EM TEMPO DE CHAMADA.
Import circular seguro: só o objeto módulo é capturado.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import SimpleITK as sitk

from dtwin.benchmark.dataset_audit import select_monophase_evidence_series
from dtwin.benchmark.operational_timing import (
    DEFAULT_REPORT_BUDGET_SECONDS,
    build_operational_timing,
    persist_operational_timing,
)
from dtwin.core import PipelineError, sha256_of
from dtwin.learning.monophase_protocol import (
    build_hierarchical_screening_result,
    resolve_monophase_sequence_contract,
)
from dtwin.medgemma_volumetric import effective_screening_timeout
from webapp import server

log = logging.getLogger("dtwin.webapp")


def process_monophase_medsiglip_job(
    job_id: str,
    raw_dir: Path,
    *,
    input_assessment: dict[str, Any],
) -> None:
    """Classify an explicitly identified delayed single phase with MedSigLIP.

    The LLD nested-OOF gate applies only to the delayed representation.  A
    generic/arterial/venous series must never enter this worker.
    """
    from dtwin.learning.exam_to_panels import build_monophase_exam_panels
    from dtwin.learning.monophase_visual_inference import (
        infer_monophase_case_from_panels,
    )
    from dtwin.learning.visual_inference import in_sample_status, load_production_bundle

    case_dir = (server.WORKSPACE / job_id / "case").resolve()
    started = time.monotonic()
    durations: dict[str, float] = {}
    try:
        server._set(job_id, state="processing", step="ingestao_monofasica", progress=18)
        selection_started = time.monotonic()
        best_files, frames, selection = server.select_best_mr_series(raw_dir, min_slices=server.MIN_SLICES)
        selected = (selection or {}).get("selected") or {}
        sequence_contract = resolve_monophase_sequence_contract(selected)
        if not best_files or frames < server.MIN_SLICES:
            raise PipelineError("Nenhuma série DICOM de RM válida foi encontrada.")
        if selected.get("sequence_class") != "T1_DELAYED":
            raise PipelineError("O bundle MedSigLIP monofásico exige uma fase tardia identificada.")
        series_dir = server.WORKSPACE / job_id / "_series"
        series_dir.mkdir(parents=True, exist_ok=True)
        for index, source in enumerate(best_files):
            shutil.copyfile(source, series_dir / f"{index:05d}_{Path(source).name}")
        durations["series_selection_and_copy"] = round(time.monotonic() - selection_started, 4)

        server._set(job_id, step="segmentacao", progress=45)
        segment_started = time.monotonic()
        mask_quality = server._segmentar_figado_com_gate(
            series_dir, case_dir, f"Job MedSigLIP monofásico {job_id}"
        )
        durations["preparation_and_segmentation"] = round(
            time.monotonic() - segment_started, 4
        )
        server._persist_series_selection(case_dir, best_files)

        server._set(job_id, step="paineis", progress=65)
        panel_started = time.monotonic()
        panels = build_monophase_exam_panels(
            case_id=job_id,
            volume_path=case_dir / "volume.nii.gz",
            coarse_liver_mask_path=case_dir / "mask_organ.nii.gz",
            output_dir=case_dir / "monophase_medsiglip_panels",
            panel_config_path=server.REPO / "configs/medsiglip_monophase_liver_enriched_v1.yaml",
        )
        durations["panels"] = round(time.monotonic() - panel_started, 4)

        server._set(job_id, step="classificacao", progress=82)
        inference_started = time.monotonic()
        bundle_root = (server.REPO / server.MONOPHASE_DELAYED_VISUAL_BUNDLE).resolve()
        decision = infer_monophase_case_from_panels(
            bundle_root=bundle_root,
            panel_manifest_path=panels.manifest_path,
            panel_paths=panels.panel_paths,
            source_phase_key="t1_delayed",
            embedding_config_path=server.REPO / server.VISUAL_EMBEDDING_CONFIG,
        )
        durations["classification"] = round(time.monotonic() - inference_started, 4)

        server._set(job_id, step="localizacao_candidata", progress=88)
        localization_started = time.monotonic()
        try:
            candidate_localization = server._localize_candidate(case_dir, decision)
        except Exception as exc:  # localization never changes the frozen decision
            candidate_localization = {
                "status": "localization_unavailable",
                "candidate_present": False,
                "used_by_screening_inference": False,
                "requires_human_review": True,
                "reason": type(exc).__name__,
            }
        durations["candidate_localization_after_inference"] = round(
            time.monotonic() - localization_started, 4
        )

        server._set(job_id, step="modelo_3d", progress=94)
        model_started = time.monotonic()
        try:
            viewer_ready, viewer_error = server._build_model(case_dir)
        except Exception as exc:
            viewer_ready, viewer_error = False, type(exc).__name__
        durations["model_3d"] = round(time.monotonic() - model_started, 4)
        durations["total"] = round(time.monotonic() - started, 4)

        bundle = load_production_bundle(bundle_root)
        status = in_sample_status(bundle, case_id=job_id)
        positive = decision["prediction"] == "POSITIVE"
        result = {
            "status": "concluido",
            "analysis_scenario": "monophase_medsiglip_delayed",
            "prediction": "POSITIVA" if positive else "NEGATIVA",
            "visual_score": decision["score"],
            "visual_threshold": decision["threshold"],
            "panel_count": decision["panel_count"],
            "panel_manifest_sha256": decision["panel_manifest_sha256"],
            "class_probabilities": decision["class_probabilities"],
            "source_phase_key": "t1_delayed",
            "selected_sequence_class": "T1_DELAYED",
            "monophase_sequence_contract": sequence_contract,
            "dynamic_enhancement_information_present": False,
            "validated_triphase_metrics_applicable": False,
            "monophase_reference_metrics": {
                "cohort": "LLD-MMRI nested patient-grouped OOF",
                "sensitivity": 0.7770700636942676,
                "specificity": 0.7584269662921348,
                "technical_failures_count_as_errors": True,
                "external_validation": False,
            },
            "input_assessment": input_assessment,
            "in_sample": status["in_sample"],
            "in_sample_verdict": status["verdict"],
            "durations_seconds": durations,
            "liver_mask_quality": mask_quality,
            "liver_volume_warning": server._aviso_volume_figado(mask_quality),
            "liver_fragmentation_warning": server._aviso_fragmentacao_figado(mask_quality),
            "candidate_localization": candidate_localization,
            "viewer_ready": bool(viewer_ready),
            "viewer_url": (
                f"/viewer/index.html?case=/api/jobs/{job_id}/model&job={job_id}"
                if viewer_ready else None
            ),
            "viewer_error": viewer_error or None,
            "approval": {"status": "pending"} if viewer_ready else None,
            "requires_human_review": True,
            "research_only": True,
            "clinical_use_allowed": False,
            "disclaimer": server.DISCLAIMER,
        }
        result["hierarchical_assessment"] = build_hierarchical_screening_result(
            prediction=decision["prediction"],
            subtype=decision.get("subtype"),
            sequence_contract=sequence_contract,
        )
        result.update(server._subtype_fields(decision["subtype"], positive))
        server._set(job_id, state="done", step="concluido", progress=100, result=result)
    except subprocess.TimeoutExpired:
        server._set(job_id, state="done", step="concluido", progress=100, result=server._graceful(
            "O processamento excedeu o tempo limite.", "timeout"))
    except PipelineError as exc:
        server._set(job_id, state="done", step="concluido", progress=100, result=server._graceful(str(exc)))
    except Exception as exc:
        log.exception("Job MedSigLIP monofásico %s: falha inesperada", job_id)
        server._set(job_id, state="done", step="concluido", progress=100, result=server._graceful(
            "Não foi possível concluir a análise monofásica.", type(exc).__name__))


def process_visual_job(job_id: str, raw_dir: Path) -> None:
    """Exame individual pelo classificador visual da Etapa C.

    É o mesmo caminho do benchmark visual, caso a caso: fases em subpastas ->
    harmonização na grade venosa + segmentação hepática -> painéis
    liver-enriched -> embeddings MedSigLIP -> bundle congelado. Qualquer falha
    vira "não concluído"; nunca uma decisão fabricada.

    Exige as três fases dinâmicas em subpastas nomeadas, porque identificar a
    fase a partir de DICOM bruto é problema não resolvido (docs/123). Adivinhar
    aqui produziria um recorte na fase errada e uma resposta sem valor.
    """
    from dtwin.learning.exam_to_panels import build_exam_panels
    from dtwin.learning.multiphase_ingest import build_multiphase_case
    from dtwin.learning.raw_dicom_phase_resolver import RawPhaseResolutionError
    from dtwin.learning.visual_inference import (
        classify_embeddings,
        embed_panels,
        in_sample_status,
        load_production_bundle,
    )

    case_dir = (server.WORKSPACE / job_id / "case").resolve()
    with server._lock:
        enhanced_3d_requested = bool((server._jobs.get(job_id) or {}).get("enhanced_3d"))
    started = time.monotonic()
    duracoes: dict[str, float] = {}
    qualidade_mascara: dict | None = None
    try:
        server._set(job_id, state="processing", step="ingestao_multifasica", progress=15)
        def segment_venous(venous_dir: Path, _work_dir: Path) -> Path:
            # Segmenta no PRÓPRIO diretório do job, e não numa subpasta: é de lá
            # que a rota /api/jobs/{id}/model serve a malha, então isso preserva o
            # modelo 3D de revisão que o fluxo anterior gerava.
            nonlocal qualidade_mascara
            qualidade_mascara = server._segmentar_figado_com_gate(
                venous_dir, case_dir, f"Job visual {job_id}"
            )
            return case_dir

        t0 = time.monotonic()
        try:
            multiphase = build_multiphase_case(
                case_id=job_id,
                case_upload_dir=Path(raw_dir),
                output_dir=case_dir / "multiphase",
                segment_venous=segment_venous,
            )
        except RawPhaseResolutionError as exc:
            if exc.code != "insufficient_dynamic_phases":
                raise
            # Never make fake RGB phases. Use the best real series through a
            # dedicated single-phase reader and carry its limitations forward.
            _files, _frames, selection = server.select_best_mr_series(
                Path(raw_dir), min_slices=server.MIN_SLICES
            )
            _evidence_paths, evidence_selection = select_monophase_evidence_series(
                Path(raw_dir), min_slices=server.MIN_SLICES
            )
            selected_sequence_class = str(
                ((selection or {}).get("selected") or {}).get("sequence_class") or "UNKNOWN"
            )
            sequence_contract = resolve_monophase_sequence_contract(
                ((selection or {}).get("selected") or {})
            )
            delayed_medsiglip = (
                server.MONOPHASE_DELAYED_VISUAL_AUTO_PROMOTED
                and
                selected_sequence_class == "T1_DELAYED"
                and (server.REPO / server.MONOPHASE_DELAYED_VISUAL_BUNDLE / "bundle_manifest.json").is_file()
            )
            scenario = (
                "monophase_medsiglip_delayed" if delayed_medsiglip else "monophase_rag"
            )
            assessment = {
                "schema": "oren-input-assessment-v1",
                "mode": "single_phase",
                "dynamic_enhancement_information_present": False,
                "synthetic_phases_created": False,
                "validated_triphase_metrics_applicable": False,
                "fallback_reason_code": exc.code,
                "selected_sequence_class": selected_sequence_class,
                "monophase_sequence_contract": sequence_contract,
                "available_real_sequence_classes": (
                    list(evidence_selection.get("selected_sequence_classes") or [])
                    if evidence_selection else [selected_sequence_class]
                ),
                "complementary_real_sequence_classes": (
                    list(evidence_selection.get("complementary_sequence_classes") or [])
                    if evidence_selection else []
                ),
                "complementary_sequences_used_by_current_reader": False,
                "single_phase_reader": (
                    "MedSigLIP delayed frozen classifier"
                    if delayed_medsiglip
                    else (
                        "MedGemma 4B + RAG (primário) + MedSigLIP tardio (segundo leitor)"
                        if selected_sequence_class == "T1_DELAYED"
                        and server.MONOPHASE_DELAYED_ADVISORY_ENABLED
                        else "MedGemma 4B + RAG"
                    )
                ),
                "limitations": [
                    "Apenas uma série de RM foi usada.",
                    "O painel contém nove cortes sistematicamente amostrados e não representa cobertura axial integral.",
                    "Não é possível avaliar realce arterial, washout ou persistência entre fases.",
                    "Este resultado não deve ser comparado diretamente às métricas do protocolo trifásico.",
                ],
            }
            server._set(
                job_id,
                analysis_scenario=scenario,
                input_assessment=assessment,
                step="ingestao_monofasica",
                progress=18,
            )
            if delayed_medsiglip:
                server.process_monophase_medsiglip_job(
                    job_id,
                    raw_dir,
                    input_assessment=assessment,
                )
                return
            with server._lock:
                escolhido = (server._jobs.get(job_id) or {}).get("monophase_medgemma_config")
            server.process_job(
                job_id,
                raw_dir,
                medgemma_config=escolhido or server.MONOPHASE_MEDGEMMA_CONFIG,
                analysis_scenario=scenario,
                input_assessment=assessment,
            )
            return
        duracoes["ingestao_e_segmentacao"] = round(time.monotonic() - t0, 4)

        # A single-phase fallback must not depend on the visual bundle.
        bundle = load_production_bundle(server._visual_bundle_root("hybrid_supervised"))

        server._set(job_id, state="processing", step="paineis", progress=55)
        t0 = time.monotonic()
        panels = build_exam_panels(
            case_id=job_id,
            phase_paths=multiphase.phase_paths,
            coarse_liver_mask_path=multiphase.coarse_liver_mask_path,
            output_dir=case_dir / "panels",
            panel_config_path=server.REPO / server.VISUAL_PANEL_CONFIG,
        )
        duracoes["paineis"] = round(time.monotonic() - t0, 4)

        server._set(job_id, state="processing", step="classificacao", progress=80)
        t0 = time.monotonic()
        embeddings = embed_panels(server.REPO / server.VISUAL_EMBEDDING_CONFIG, panels.panel_paths)
        decision = classify_embeddings(bundle, embeddings)
        duracoes["classificacao"] = round(time.monotonic() - t0, 4)

        # A decisão já está congelada. Só agora a região candidata pode ser
        # localizada para o visualizador; ela jamais retorna ao classificador.
        server._set(job_id, state="processing", step="localizacao_candidata", progress=88)
        t0 = time.monotonic()
        try:
            candidate_localization = server._localize_candidate(case_dir, decision)
        except subprocess.TimeoutExpired:
            for name in (
                "mask_candidate.nii.gz", "mask_candidate_clean.nii.gz",
                "mesh_candidate.vtp", "candidate_region.json",
            ):
                (case_dir / name).unlink(missing_ok=True)
            candidate_localization = {
                "status": "localization_timeout",
                "candidate_present": False,
                "used_by_screening_inference": False,
                "requires_human_review": True,
            }
        except Exception as exc:
            candidate_localization = {
                "status": "localization_unavailable",
                "candidate_present": False,
                "used_by_screening_inference": False,
                "requires_human_review": True,
                "reason": type(exc).__name__,
            }
        duracoes["localizacao_candidata_pos_inferencia"] = round(
            time.monotonic() - t0, 4
        )

        # Máscara de visualização pela união das três fases (docs/188 §9,
        # docs/189). A decisão já está congelada e os painéis já vieram só da
        # venosa -- isto só melhora o que o modelo 3D mostra, nunca o que foi
        # classificado. Roda antes de server._build_model para que o estágio de malha
        # já encontre mask_organ_union.nii.gz, se ela existir.
        # A decisão e os painéis já estão congelados. Esta etapa escreve somente
        # os artefatos v2 de visualização e jamais altera mask_organ.nii.gz.
        visualizacao_shadow: dict[str, Any] = {"status": "not_requested"}
        if enhanced_3d_requested:
            server._set(job_id, state="processing", step="segmentacao_3d_aprimorada", progress=91)
            t0 = time.monotonic()
            try:
                visualizacao_shadow = server._build_enhanced_visualization_shadow(
                    case_dir, multiphase.phase_paths
                )
            except Exception as exc:
                visualizacao_shadow = {
                    "status": "failed",
                    "reason": type(exc).__name__,
                    "fallback": "existing_union_or_venous",
                    "production_files_written": False,
                }
                log.warning("Job visual %s: 3-D aprimorado indisponível (%s)", job_id, exc)
            duracoes["segmentacao_3d_aprimorada"] = round(time.monotonic() - t0, 4)

        shadow_approved = visualizacao_shadow.get("status") in {
            "APPROVED", "APPROVED_WITH_WARNING"
        }
        uniao_mascara: dict[str, Any] = {
            "status": "replaced_by_phase_aware_shadow" if shadow_approved else "union_disabled"
        }
        if server.UNION_MASK_ENABLED and not shadow_approved:
            server._set(job_id, state="processing", step="mascara_uniao", progress=91)
            t0 = time.monotonic()
            try:
                uniao_mascara = server._build_union_liver_mask(case_dir, multiphase.phase_paths)
            except Exception as exc:
                uniao_mascara = {
                    "status": "union_failed", "reason": type(exc).__name__,
                    "phases_included": ["venous"], "phase_failures": {},
                }
                log.warning("Job visual %s: união de fases falhou (%s)", job_id, exc)
            duracoes["mascara_uniao"] = round(time.monotonic() - t0, 4)

        # Modelo 3D do fígado para revisão. É acessório à decisão: se falhar, o
        # resultado sai do mesmo jeito, apenas sem o visualizador.
        server._set(job_id, state="processing", step="modelo_3d", progress=94)
        t0 = time.monotonic()
        try:
            viewer_ready, motivo_modelo = server._build_model(case_dir)
        except Exception as exc:
            viewer_ready, motivo_modelo = False, f"{type(exc).__name__}"
        duracoes["modelo_3d"] = round(time.monotonic() - t0, 4)
        if not viewer_ready:
            log.warning("Job visual %s: modelo 3D indisponível (%s)", job_id, motivo_modelo)

        positiva = decision["prediction"] == "POSITIVE"
        status = in_sample_status(bundle, case_id=job_id)
        resultado = {
            "status": "concluido",
            "analysis_scenario": "hybrid_supervised",
            "prediction": "POSITIVA" if positiva else "NEGATIVA",
            "visual_score": decision["score"],
            "visual_threshold": decision["threshold"],
            "panel_count": decision["panel_count"],
            "class_probabilities": decision["class_probabilities"],
            "phase_coverage": multiphase.coverage,
            "phase_resolution": multiphase.phase_resolution,
            "in_sample": status["in_sample"],
            "in_sample_verdict": status["verdict"],
            "durations_seconds": duracoes,
            "liver_mask_quality": qualidade_mascara,
            "liver_mask_union": uniao_mascara,
            "liver_visualization_shadow": visualizacao_shadow,
            "liver_volume_warning": server._aviso_volume_figado(
                qualidade_mascara,
                (
                    ((visualizacao_shadow.get("mask") or {}).get("volume_ml"))
                    if shadow_approved
                    else (
                        uniao_mascara.get("union_volume_ml")
                        if uniao_mascara.get("status") == "union_built" else None
                    )
                ),
            ),
            "liver_fragmentation_warning": server._aviso_fragmentacao_figado(qualidade_mascara),
            "candidate_localization": candidate_localization,
            "viewer_ready": bool(viewer_ready),
            "viewer_url": (
                f"/viewer/index.html?case=/api/jobs/{job_id}/model&job={job_id}"
                if viewer_ready
                else None
            ),
            "approval": {"status": "pending"} if viewer_ready else None,
            "requires_human_review": True,
            "research_only": True,
            "clinical_use_allowed": False,
            "disclaimer": server.DISCLAIMER,
        }
        resultado.update(server._subtype_fields(decision["subtype"], positiva))
        resultado["durations_seconds"]["total"] = round(time.monotonic() - started, 4)
        server._set(job_id, state="done", step="concluido", progress=100, result=resultado)
    except subprocess.TimeoutExpired:
        server._set(job_id, state="done", step="concluido", progress=100, result=server._graceful(
            "O processamento excedeu o tempo limite.",
            "Exames muito grandes podem não caber no orçamento de tempo."))
    except PipelineError as exc:
        server._set(job_id, state="done", step="concluido", progress=100,
             result=server._graceful(str(exc)))
    except Exception as exc:
        log.exception("Job visual %s: falha inesperada", job_id)
        server._set(job_id, state="done", step="concluido", progress=100, result=server._graceful(
            "Não foi possível concluir a análise deste exame.",
            f"Falha inesperada: {type(exc).__name__}"))



def _run_delayed_medsiglip_advisory(
    *,
    case_dir: Path,
    case_id: str,
    input_assessment: dict[str, Any],
    primary_prediction: str,
) -> dict[str, Any]:
    """Run the delayed MedSigLIP head strictly as a non-decisional reader.

    The head passed its internal LLD gate but did not generalize to OpenSwissHCC.
    Consequently this function deliberately has no way to change the primary
    MedGemma prediction.  Its signed, auditable output is useful to the human
    reviewer and to future paired validation, while remaining honest for an
    arbitrary DICOM upload whose source domain is unknown.
    """
    from dtwin.learning.exam_to_panels import build_monophase_exam_panels
    from dtwin.learning.monophase_visual_inference import (
        infer_monophase_case_from_panels,
    )
    from dtwin.medgemma_screening import _write_json_atomic

    started = time.monotonic()
    contract = dict(input_assessment.get("monophase_sequence_contract") or {})
    output_path = case_dir / "outputs" / "second_reader" / "medsiglip_advisory.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    base: dict[str, Any] = {
        "schema": "oren-monophase-second-reader-v1",
        "role": "advisory_second_reader",
        "affects_primary_decision": False,
        "primary_reader": "MedGemma 4B + RAG",
        "primary_prediction": str(primary_prediction).upper(),
        "source_phase_key": contract.get("source_phase_key"),
        "external_gate_passed": False,
        "auto_promotion_allowed": False,
        "requires_human_review": True,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    if not server.MONOPHASE_DELAYED_ADVISORY_ENABLED:
        result = {**base, "status": "disabled", "reason": "advisory_disabled_by_configuration"}
        _write_json_atomic(output_path, result)
        return result
    # Restauração do laudo com % por tipo (2026-08-28, ordem do operador):
    # o segundo leitor roda em QUALQUER sequência monofásica. Fora da fase
    # validada (T1 tardia) as probabilidades são sinal de pesquisa FORA DE
    # DOMÍNIO — o payload declara isso e a UI exibe o aviso; o papel segue
    # estritamente advisory (nunca altera o laudo MedGemma).
    fora_do_dominio = (
        contract.get("source_phase_key") != "t1_delayed"
        or contract.get("sequence_specific_medsiglip_bundle_allowed") is not True
    )
    base["sequence_out_of_validated_domain"] = fora_do_dominio

    bundle_root = (server.REPO / server.MONOPHASE_DELAYED_VISUAL_BUNDLE).resolve()
    if not (bundle_root / "bundle_manifest.json").is_file():
        result = {**base, "status": "unavailable", "reason": "signed_bundle_not_found"}
        _write_json_atomic(output_path, result)
        return result

    panels = build_monophase_exam_panels(
        case_id=case_id,
        volume_path=case_dir / "volume.nii.gz",
        coarse_liver_mask_path=case_dir / "mask_organ.nii.gz",
        output_dir=case_dir / "monophase_medsiglip_advisory_panels",
        panel_config_path=server.REPO / "configs/medsiglip_monophase_liver_enriched_v1.yaml",
    )
    decision = infer_monophase_case_from_panels(
        bundle_root=bundle_root,
        panel_manifest_path=panels.manifest_path,
        panel_paths=panels.panel_paths,
        source_phase_key="t1_delayed",
        embedding_config_path=server.REPO / server.VISUAL_EMBEDDING_CONFIG,
    )
    advisory_prediction = "POSITIVA" if decision["prediction"] == "POSITIVE" else "NEGATIVA"
    primary = str(primary_prediction).upper()
    comparable = primary in {"POSITIVA", "NEGATIVA"}
    result = {
        **base,
        "status": "completed",
        "prediction": advisory_prediction,
        "score": decision["score"],
        "threshold": decision["threshold"],
        "panel_count": decision["panel_count"],
        "panel_manifest_sha256": decision["panel_manifest_sha256"],
        "class_probabilities": decision["class_probabilities"],
        "agreement_with_primary": (
            advisory_prediction == primary if comparable else None
        ),
        "review_priority": (
            "standard" if comparable and advisory_prediction == primary else "elevated"
        ),
        "interpretation": (
            "Os dois leitores concordaram; a decisão continua sendo do MedGemma e exige revisão humana."
            if comparable and advisory_prediction == primary
            else "Os leitores discordaram ou o leitor principal foi inconclusivo; priorize a revisão humana."
        ),
        "known_limitations": (
            ([
                f"A série analisada ({contract.get('source_phase_key') or 'desconhecida'}) "
                "está FORA da fase validada (T1 tardia): as probabilidades são "
                "sinal de pesquisa fora de domínio."
            ] if fora_do_dominio else [])
            + [
                "O classificador foi desenvolvido no LLD-MMRI.",
                "A validação externa OpenSwissHCC não atingiu o gate de sensibilidade.",
                "O resultado não substitui nem altera o relatório MedGemma.",
            ]
        ),
        "latency_seconds": round(time.monotonic() - started, 4),
    }
    _write_json_atomic(output_path, result)
    return result


def process_job(
    job_id: str,
    raw_dir: Path,
    medgemma_config: str = server.VOLUMETRIC_RAG_MEDGEMMA_CONFIG,
    analysis_scenario: str = "volumetric_rag",
    input_assessment: dict[str, Any] | None = None,
) -> None:
    # case_dir e raw_dir (_upload) são IRMÃOS sob server.WORKSPACE/job_id; nunca aninhados,
    # senão limpar o case_dir apagaria o DICOM enviado (necessário no fallback CPU).
    case_dir = (server.WORKSPACE / job_id / "case").resolve()
    worker_started = time.monotonic()
    started_at_utc = datetime.now(timezone.utc).isoformat()
    durations_seconds: dict[str, float] = {}
    outcome = "failed"
    failure_stage: str | None = "series_selection_and_copy"
    segmentation_device: str | None = None
    report_available = False
    viewer_ready = False
    secondary_reader: dict[str, Any] | None = None
    try:
        server._set(job_id, state="processing", step="ingestao", progress=15)
        series_started = time.monotonic()
        best_files, n = server.find_best_series(raw_dir)
        if not best_files or n < server.MIN_SLICES:
            durations_seconds["series_selection_and_copy"] = round(
                time.monotonic() - series_started, 4
            )
            outcome = "not_completed"
            server._set(job_id, state="done", result=server._graceful(
                "Não encontramos uma série DICOM de RM válida no envio.",
                "Envie a pasta de um exame de RM (DICOM) com múltiplos cortes — "
                "ou um único arquivo DICOM multi-frame."))
            return

        # Copia a série escolhida para um diretório limpo: isola de estruturas
        # bagunçadas / múltiplas séries e garante que o prepare veja só esta série.
        series_dir_path = server.WORKSPACE / job_id / "_series"
        series_dir_path.mkdir(parents=True, exist_ok=True)
        for i, source in enumerate(best_files):
            shutil.copyfile(source, series_dir_path / f"{i:05d}_{os.path.basename(source)}")
        series_dir = str(series_dir_path.resolve())
        durations_seconds["series_selection_and_copy"] = round(
            time.monotonic() - series_started, 4
        )

        # Fase 1: ingestão + des-identificação + segmentação (launcher isolado).
        failure_stage = "preparation_and_segmentation"
        segmentation_started = time.monotonic()
        try:
            server._set(job_id, step="segmentacao", progress=45)
            segmentation_device = "gpu"
            prep = server._segment(series_dir, case_dir, "gpu", server.PREP_TIMEOUT_GPU, fast=False)
            if not server._seg_done(case_dir):
                reason = server._cli_reason(prep)
                log.warning("Segmentação na GPU falhou (%s); tentando CPU...", reason[:100])
                shutil.rmtree(case_dir, ignore_errors=True)
                server._set(job_id, step="segmentacao", progress=55)
                segmentation_device = "cpu_fallback"
                prep = server._segment(series_dir, case_dir, "cpu", server.PREP_TIMEOUT_CPU, fast=False)
                if not server._seg_done(case_dir):
                    reason = server._cli_reason(prep)
                    outcome = "not_completed"
                    server._set(job_id, state="done", result=server._graceful(server._friendly_text(reason), reason))
                    return
        finally:
            durations_seconds["preparation_and_segmentation"] = round(
                time.monotonic() - segmentation_started, 4
            )

        # Fase 2: montagem 2D + MedGemma (subprocesso isolado).
        server._persist_series_selection(case_dir, best_files)
        failure_stage = "medgemma_screening"
        server._set(job_id, step="medgemma", progress=80)
        screening_started = time.monotonic()
        try:
            screening_config = server.load_screening_config(server.REPO / medgemma_config)
            screening_timeout, _panel_count = effective_screening_timeout(
                sitk.GetArrayFromImage(
                    sitk.ReadImage(str(case_dir / "mask_organ.nii.gz"))
                ) > 0,
                screening_config,
                server.SCREEN_TIMEOUT,
            )
            with server._medgemma_screening_lock:
                scr = server._run(
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
                    timeout=screening_timeout,
                )
        finally:
            durations_seconds["screening_subprocess"] = round(
                time.monotonic() - screening_started, 4
            )

        report = server._load_report(case_dir / "outputs" / "medgemma" / "medgemma_report.json")
        if report is None:
            reason = server._cli_reason(scr)
            outcome = "not_completed"
            server._set(job_id, state="done", result=server._graceful(server._friendly_text(reason), reason))
            return

        report_available = True
        outcome = "report_completed"
        durations_seconds.update({
            str(key): float(value)
            for key, value in (report.get("durations_seconds") or {}).items()
            if isinstance(value, (int, float)) and float(value) >= 0
        })
        durations_seconds["time_to_report"] = round(time.monotonic() - worker_started, 4)

        # A delayed MedSigLIP head is useful as a second opinion, but its failed
        # external gate forbids automatic promotion.  Run it only after a valid
        # primary report exists and never let an advisory failure invalidate the
        # MedGemma result.
        if input_assessment and input_assessment.get("mode") == "single_phase":
            advisory_started = time.monotonic()
            server._set(job_id, step="segundo_leitor", progress=88)
            try:
                secondary_reader = server._run_delayed_medsiglip_advisory(
                    case_dir=case_dir,
                    case_id=job_id,
                    input_assessment=input_assessment,
                    primary_prediction=str(
                        (report.get("report") or {}).get("resultado_hipotese") or "INCONCLUSIVA"
                    ),
                )
            except Exception as exc:  # advisory evidence must not erase a valid report
                log.exception("Job %s: segundo leitor MedSigLIP indisponível", job_id)
                secondary_reader = {
                    "schema": "oren-monophase-second-reader-v1",
                    "role": "advisory_second_reader",
                    "status": "unavailable",
                    "reason": type(exc).__name__,
                    "affects_primary_decision": False,
                    "external_gate_passed": False,
                    "requires_human_review": True,
                    "research_only": True,
                    "clinical_use_allowed": False,
                }
            durations_seconds["medsiglip_advisory"] = round(
                time.monotonic() - advisory_started, 4
            )

        # Fase 3: máscara hepática -> malha/STL para revisão humana.
        failure_stage = "model_3d"
        server._set(job_id, step="modelo_3d", progress=92)
        model_started = time.monotonic()
        try:
            viewer_ready, viewer_error = server._build_model(case_dir)
        finally:
            durations_seconds["model_3d"] = round(time.monotonic() - model_started, 4)

        if not viewer_ready:
            log.warning(
                "Job %s: relatório concluído, mas modelo 3D falhou: %s",
                job_id,
                viewer_error,
            )
            outcome = "report_completed_viewer_failed"
        else:
            outcome = "completed"
            failure_stage = None

        server._set(
            job_id,
            state="done",
            step="concluido",
            progress=100,
            viewer_error=viewer_error or None,
            approval={"status": "pending"} if viewer_ready else None,
            result=server._viewer_result(
                report,
                job_id,
                viewer_ready,
                analysis_scenario=analysis_scenario,
                input_assessment=input_assessment,
                secondary_reader=secondary_reader,
            ),
        )
    except subprocess.TimeoutExpired:
        outcome = "timeout"
        server._set(job_id, state="done", result=server._graceful(
            "O processamento excedeu o tempo limite.", "timeout"))
    except Exception as exc:
        outcome = "failed"
        log.exception("Job %s: falha inesperada", job_id)
        server._set(job_id, state="done", result=server._graceful(
            "Ocorreu um erro inesperado no processamento.", type(exc).__name__))
    finally:
        durations_seconds["total_with_3d"] = round(time.monotonic() - worker_started, 4)
        try:
            config_path = server.REPO / medgemma_config
            config_sha256 = sha256_of(config_path) if config_path.is_file() else "unavailable"
            timing = build_operational_timing(
                job_id=job_id,
                analysis_scenario=analysis_scenario,
                medgemma_config=medgemma_config,
                medgemma_config_sha256=config_sha256,
                started_at_utc=started_at_utc,
                finished_at_utc=datetime.now(timezone.utc).isoformat(),
                durations_seconds=durations_seconds,
                outcome=outcome,
                report_available=report_available,
                viewer_ready=viewer_ready,
                failure_stage=failure_stage,
                segmentation_device=segmentation_device,
                report_budget_seconds=DEFAULT_REPORT_BUDGET_SECONDS,
            )
            timing_path = persist_operational_timing(case_dir, timing)
            server._set(
                job_id,
                operational_timing=timing,
                operational_timing_artifact=str(
                    timing_path.relative_to((server.WORKSPACE / job_id).resolve())
                ),
            )
        except Exception:
            log.exception("Job %s: não foi possível persistir a auditoria de tempo", job_id)
        shutil.rmtree(raw_dir, ignore_errors=True)
        shutil.rmtree(server.WORKSPACE / job_id / "_series", ignore_errors=True)

def _select_ct_series(raw_dir: Path) -> tuple[list[str], int]:
    """Seleciona a série de TC com mais cortes no envio (CT-01, D3).

    Caminho deliberadamente SIMPLES, espelhando a decisão validada no
    Volyrics: TC entra por série única (o caso comum de TC de abdome), sem a
    heurística de sequências que é específica de RM. Agrupa por
    SeriesInstanceUID, aceita apenas Modality == CT e devolve a maior série.
    Labels e ground truth nunca participam.
    """
    import pydicom

    series: dict[str, list[str]] = {}
    for path in sorted(Path(raw_dir).rglob("*")):
        if not path.is_file():
            continue
        try:
            ds = pydicom.dcmread(str(path), stop_before_pixels=True, force=True)
        except Exception:
            continue
        modality = str(getattr(ds, "Modality", "") or "").upper()
        if modality != "CT":
            continue
        uid = str(getattr(ds, "SeriesInstanceUID", "") or "sem_uid")
        series.setdefault(uid, []).append(str(path))
    if not series:
        return [], 0
    melhores = max(series.values(), key=len)
    return melhores, len(melhores)


def process_ct_job(job_id: str, raw_dir: Path) -> None:
    """Exame de TC: segmentação → malha 3D → volumetria → revisão humana.

    CT-01 (D4): SEM triagem visual — os classificadores MedSigLIP/MedGemma
    foram treinados e congelados sobre RM; rodá-los em TC seria claim sem
    lastro. O payload declara a ausência explicitamente. Perfil, avisos e
    fluxo seguem o plano CT-01 (perfil figado_ct.yaml por job; multifásico
    nunca é tentado — a validação de origem cobre apenas série única).
    """
    case_dir = (server.WORKSPACE / job_id / "case").resolve()
    worker_started = time.monotonic()
    started_at_utc = datetime.now(timezone.utc).isoformat()
    durations_seconds: dict[str, float] = {}
    outcome = "failed"
    failure_stage: str | None = "series_selection_and_copy"
    segmentation_device: str | None = None
    viewer_ready = False
    viewer_error = ""
    perfil_ct = server.MODALITY_PROFILES["CT"]
    try:
        server._set(job_id, state="processing", step="ingestao", progress=15)
        series_started = time.monotonic()
        best_files, n = _select_ct_series(raw_dir)
        if not best_files or n < server.MIN_SLICES:
            durations_seconds["series_selection_and_copy"] = round(
                time.monotonic() - series_started, 4
            )
            outcome = "not_completed"
            server._set(job_id, state="done", result=server._graceful(
                "Não encontramos uma série DICOM de TC válida no envio.",
                "Você selecionou TC, mas o envio não contém uma série de TC com "
                "múltiplos cortes — confira a modalidade do exame e a seleção."))
            return

        series_dir_path = server.WORKSPACE / job_id / "_series"
        series_dir_path.mkdir(parents=True, exist_ok=True)
        for i, source in enumerate(best_files):
            shutil.copyfile(source, series_dir_path / f"{i:05d}_{os.path.basename(source)}")
        series_dir = str(series_dir_path.resolve())
        durations_seconds["series_selection_and_copy"] = round(
            time.monotonic() - series_started, 4
        )

        failure_stage = "preparation_and_segmentation"
        segmentation_started = time.monotonic()
        try:
            server._set(job_id, step="segmentacao", progress=45)
            segmentation_device = "gpu"
            prep = server._segment(
                series_dir, case_dir, "gpu", server.PREP_TIMEOUT_GPU,
                fast=False, profile_rel=perfil_ct,
            )
            if not server._seg_done(case_dir):
                reason = server._cli_reason(prep)
                log.warning("Job CT %s: GPU falhou (%s); tentando CPU...", job_id, reason[:100])
                shutil.rmtree(case_dir, ignore_errors=True)
                server._set(job_id, step="segmentacao", progress=55)
                segmentation_device = "cpu_fallback"
                prep = server._segment(
                    series_dir, case_dir, "cpu", server.PREP_TIMEOUT_CPU,
                    fast=False, profile_rel=perfil_ct,
                )
                if not server._seg_done(case_dir):
                    reason = server._cli_reason(prep)
                    outcome = "not_completed"
                    server._set(job_id, state="done", result=server._graceful(
                        server._friendly_text(reason), reason))
                    return
        finally:
            durations_seconds["preparation_and_segmentation"] = round(
                time.monotonic() - segmentation_started, 4
            )

        server._persist_series_selection(case_dir, best_files)

        # CT-LAUDO (2026-08-28, ordem do operador — revoga o D4 do CT-01):
        # laudo MedGemma zero-shot em TC com a config do benchmark CT-01-F.
        # A acurácia MEDIDA acompanha o payload (CT_SCREENING_VALIDATION).
        # Falha do laudo NÃO derruba o job: volumetria e 3D permanecem, com
        # a ausência declarada — nunca omissão silenciosa.
        failure_stage = "medgemma_screening"
        server._set(job_id, step="medgemma", progress=70)
        screening_started = time.monotonic()
        ct_report = None
        ct_screening_error: str | None = None
        try:
            ct_config = server.CT_MEDGEMMA_CONFIG
            screening_config = server.load_screening_config(server.REPO / ct_config)
            screening_timeout, _panel_count = effective_screening_timeout(
                sitk.GetArrayFromImage(
                    sitk.ReadImage(str(case_dir / "mask_organ.nii.gz"))
                ) > 0,
                screening_config,
                server.SCREEN_TIMEOUT,
            )
            with server._medgemma_screening_lock:
                scr = server._run(
                    [
                        server.PY, "-m", "dtwin.medgemma_screening",
                        "--case-dir", str(case_dir),
                        "--medgemma-config", ct_config,
                        "--confirm-no-visible-phi",
                    ],
                    timeout=screening_timeout,
                )
            ct_report = server._load_report(
                case_dir / "outputs" / "medgemma" / "medgemma_report.json"
            )
            if ct_report is None:
                ct_screening_error = server._cli_reason(scr)
        except Exception as exc:
            log.exception("Job CT %s: laudo MedGemma indisponível", job_id)
            ct_screening_error = type(exc).__name__
        finally:
            durations_seconds["screening_subprocess"] = round(
                time.monotonic() - screening_started, 4
            )

        failure_stage = "model_3d"
        server._set(job_id, step="modelo_3d", progress=80)
        model_started = time.monotonic()
        try:
            viewer_ready, viewer_error = server._build_model(
                case_dir, profile_rel=perfil_ct
            )
        finally:
            durations_seconds["model_3d"] = round(time.monotonic() - model_started, 4)

        if not viewer_ready:
            outcome = "not_completed"
            server._set(job_id, state="done", result=server._graceful(
                server._friendly_text(viewer_error), viewer_error))
            return

        outcome = "completed"
        failure_stage = None
        # Volume para o card de resultado: leitura defensiva do manifesto que o
        # finalize acabou de escrever (a volumetria completa fica no viewer).
        liver_volume_ml = None
        try:
            manifest = json.loads(
                (case_dir / "outputs" / "viewer_manifest.json").read_text(encoding="utf-8")
            )
            liver_volume_ml = (
                (manifest.get("volumetry") or {}).get("whole_liver_summary") or {}
            ).get("volume_ml")
        except Exception:
            liver_volume_ml = None
        result = {
            "status": "concluido",
            "analysis_scenario": "ct_volumetric",
            "modality": "CT",
            "profile": "figado_ct",
            # CT-LAUDO: laudo MedGemma presente quando o backend respondeu;
            # ausência sempre declarada com motivo, nunca silenciosa.
            "screening_available": ct_report is not None,
            "screening_unavailable_reason": (
                None if ct_report is not None else (
                    "O laudo MedGemma de TC não pôde ser gerado nesta "
                    f"execução ({ct_screening_error or 'backend indisponível'}); "
                    "volumetria e revisão 3D seguem normalmente."
                )
            ),
            "report": (ct_report or {}).get("report"),
            "screening_validation": (
                dict(server.CT_SCREENING_VALIDATION) if ct_report is not None else None
            ),
            "prediction": None,
            "viewer_ready": True,
            "viewer_url": f"/viewer/index.html?case=/api/jobs/{job_id}/model&job={job_id}",
            "liver_volume_ml": liver_volume_ml,
            "volumetry_note": server._aviso_volumetria_ct(),
            "requires_human_review": True,
            "research_only": True,
            "clinical_use_allowed": False,
            "disclaimer": server.DISCLAIMER,
        }
        server._set(
            job_id,
            state="done",
            step="concluido",
            progress=100,
            approval={"status": "pending"},
            result=result,
        )
    except subprocess.TimeoutExpired:
        outcome = "timeout"
        server._set(job_id, state="done", result=server._graceful(
            "O processamento excedeu o tempo limite.", "timeout"))
    except Exception as exc:
        outcome = "failed"
        log.exception("Job CT %s: falha inesperada", job_id)
        server._set(job_id, state="done", result=server._graceful(
            "Ocorreu um erro inesperado no processamento.", type(exc).__name__))
    finally:
        durations_seconds["total_with_3d"] = round(time.monotonic() - worker_started, 4)
        try:
            timing = build_operational_timing(
                job_id=job_id,
                analysis_scenario="ct_volumetric",
                medgemma_config=server.CT_MEDGEMMA_CONFIG,
                medgemma_config_sha256="not_applicable",
                started_at_utc=started_at_utc,
                finished_at_utc=datetime.now(timezone.utc).isoformat(),
                durations_seconds=durations_seconds,
                outcome=outcome,
                report_available=False,
                viewer_ready=viewer_ready,
                failure_stage=failure_stage,
                segmentation_device=segmentation_device,
                report_budget_seconds=DEFAULT_REPORT_BUDGET_SECONDS,
            )
            timing_path = persist_operational_timing(case_dir, timing)
            server._set(
                job_id,
                operational_timing=timing,
                operational_timing_artifact=str(
                    timing_path.relative_to((server.WORKSPACE / job_id).resolve())
                ),
            )
        except Exception:
            log.exception("Job CT %s: não foi possível persistir a auditoria de tempo", job_id)
        shutil.rmtree(raw_dir, ignore_errors=True)
        shutil.rmtree(server.WORKSPACE / job_id / "_series", ignore_errors=True)

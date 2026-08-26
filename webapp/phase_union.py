"""União de fases e construção do modelo 3D (REF-03 seam 4).

DOWNSTREAM CIENTÍFICO (decisão 13: specs de geometria dos comparadores).
Extraído de server.py byte-idêntico em comportamento. REGRA R2: config e
patch-targets via `server.<nome>` em tempo de chamada.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk

from dtwin.candidate_subprocess import candidate_error, run_candidate_subprocess
from dtwin.core import PipelineError, sha256_of
from webapp import server

log = logging.getLogger("dtwin.webapp")


def _model_done(case_dir: Path) -> bool:
    """Modelo publicável = manifesto válido, artefatos presentes e hashes íntegros."""
    manifest_path = case_dir / "outputs" / "viewer_manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text("utf-8"))
        assets = server._viewer_assets(manifest)
        mesh_names = {
            item.get("stl") for item in manifest.get("meshes", []) if isinstance(item, dict)
        }
        if not mesh_names or not mesh_names <= set(assets):
            return False
        volumetry = manifest.get("volumetry")
        if isinstance(volumetry, dict):
            artifacts = volumetry.get("artifacts") or {}
            json_name = artifacts.get("json")
            csv_name = artifacts.get("csv")
            if not all(
                isinstance(name, str) and Path(name).name == name
                for name in (json_name, csv_name)
            ):
                return False
            persisted_volumetry = json.loads(
                (manifest_path.parent / json_name).read_text(encoding="utf-8")
            )
            if persisted_volumetry != volumetry:
                return False
        for filename, spec in assets.items():
            path = manifest_path.parent / filename
            if not path.is_file():
                return False
            expected_hash = spec.get("sha256")
            if expected_hash and sha256_of(path) != expected_hash:
                return False
        return True
    except (OSError, json.JSONDecodeError, TypeError, KeyError):
        return False


def _build_model(case_dir: Path, profile_rel: str | None = None) -> tuple[bool, str]:
    """Gera a malha do figado em subprocesso, sem inventar uma lesao.

    `profile_rel` (CT-01) escolhe o perfil por job; None preserva o default
    MR — nenhum caller de RM mudou."""
    proc = server._run(
        [
            server.PY,
            "digital_twin.py",
            "finalize",
            str(case_dir),
            "--profile",
            profile_rel or server.PROFILE,
            "--no-lesion",
        ],
        timeout=server.MODEL_TIMEOUT,
    )
    if _model_done(case_dir):
        return True, ""
    return False, server._cli_reason(proc)


def _mesma_geometria_sitk(a: sitk.Image, b: sitk.Image) -> bool:
    # direction incluida por decisao HG-03 (HUMAN_DECISIONS item 13): sem ela,
    # uma mascara flipada entrava na uniao em array space fora do lugar fisico.
    return (
        a.GetSize() == b.GetSize()
        and a.GetSpacing() == b.GetSpacing()
        and a.GetOrigin() == b.GetOrigin()
        and bool(np.allclose(a.GetDirection(), b.GetDirection(), rtol=0.0, atol=1e-6))
    )


def _build_enhanced_visualization_shadow(
    case_dir: Path, phase_paths: dict[str, Path]
) -> dict[str, Any]:
    """Run the authorized visualization-only adapter; browser paths are never accepted."""

    from dtwin.segmentation_shadow import run_phase_aware_shadow

    return run_phase_aware_shadow(
        case_root=case_dir,
        phase_paths=phase_paths,
        reference_volume=case_dir / "volume.nii.gz",
        mrsegmentator_exe=server.MRSEGMENTATOR_EXE,
        timeout_seconds=server.ENHANCED_3D_TIMEOUT,
    )


def _build_union_liver_mask(case_dir: Path, phase_paths: dict[str, Path]) -> dict[str, Any]:
    """Segmenta arterial e tardia e funde com a venosa para o MODELO 3D.

    Roda só DEPOIS da decisão de triagem congelada: os painéis de classificação
    já foram construídos a partir de mask_organ.nii.gz (venosa) antes deste
    ponto, e permanecem exatamente como estavam -- esta função nunca escreve
    nele. O resultado vai para mask_organ_union.nii.gz, um arquivo NOVO que o
    estágio de malha (dtwin.stages._fonte_da_malha_do_orgao) prefere quando
    presente.

    Uma falha aqui NUNCA falha o exame: o pior caso é o modelo 3D continuar
    vindo só da venosa, como sempre foi. Cada fase extra tem seu próprio
    timeout e é simplesmente excluída da união se estourar, travar ou sair com
    geometria divergente.

    Por que isto é seguro fazer: validado contra referência humana (docs/189,
    CHAOS, n=20) que 82% dos voxels que a união ACRESCENTA sobre uma fase
    isolada são confirmados como fígado -- ela recupera órgão real, não invade
    tecido vizinho. E medido com as três fases de produção no LLD (n=19,
    experiments/three_phase_union_v1): recupera 23% de volume a mais que a
    venosa sozinha, na mediana.
    """
    from dtwin.benchmark.lld_mmri_v23_preparation import (
        isolated_total_mr_liver_segmenter,
    )
    from dtwin.learning.multiphase_ingest import ARTERIAL, DELAYED

    venous_mask_path = case_dir / "mask_organ.nii.gz"
    if not venous_mask_path.is_file():
        return {"status": "venous_mask_missing", "phases_included": [], "phase_failures": {}}
    venous_image = sitk.ReadImage(str(venous_mask_path))
    venous = sitk.GetArrayFromImage(venous_image) > 0

    uniao = venous.copy()
    fases_incluidas = ["venous"]
    fases_falhas: dict[str, str] = {}
    # phase_paths vem de multiphase.phase_paths, cujas chaves são as constantes
    # de dtwin.learning.multiphase_ingest ("t1_arterial"/"t1_delayed"), não os
    # nomes curtos que este módulo usa para relatar fases -- importar em vez de
    # supor a string evita a mesma divergência silenciosa se o nome mudar lá.
    for fase, chave_real in (("arterial", ARTERIAL), ("delayed", DELAYED)):
        fonte = phase_paths.get(chave_real)
        if fonte is None or not Path(fonte).is_file():
            fases_falhas[fase] = "fase_ausente"
            continue
        destino = case_dir / f"mask_organ_{fase}.nii.gz"
        try:
            isolated_total_mr_liver_segmenter(
                Path(fonte), destino, device="gpu", fast=False,
                timeout_seconds=server.UNION_PHASE_TIMEOUT, python_executable=server.PY,
            )
        except Exception as exc:
            fases_falhas[fase] = type(exc).__name__
            continue
        try:
            imagem_fase = sitk.ReadImage(str(destino))
        except Exception:
            fases_falhas[fase] = "leitura_falhou"
            continue
        if not _mesma_geometria_sitk(imagem_fase, venous_image):
            fases_falhas[fase] = "geometria_divergente"
            continue
        uniao = uniao | (sitk.GetArrayFromImage(imagem_fase) > 0)
        fases_incluidas.append(fase)

    if len(fases_incluidas) == 1:
        # Nenhuma fase extra contribuiu -- não escreve um arquivo idêntico ao
        # venoso. dtwin.stages já cai para mask_organ.nii.gz sozinho.
        return {
            "status": "union_unavailable_venous_only",
            "phases_included": fases_incluidas,
            "phase_failures": fases_falhas,
        }

    saida = sitk.GetImageFromArray(uniao.astype(np.uint8))
    saida.CopyInformation(venous_image)
    destino_uniao = case_dir / "mask_organ_union.nii.gz"
    # O nome precisa terminar em ".nii.gz": o SimpleITK escolhe o formato de
    # escrita pela extensão, e ".tmp" sozinho não é reconhecido.
    temporario = case_dir / f".{destino_uniao.stem.removesuffix('.nii')}.partial.nii.gz"
    sitk.WriteImage(saida, str(temporario))
    temporario.replace(destino_uniao)

    espacamento = venous_image.GetSpacing()
    volume_venosa_ml = float(int(venous.sum()) * float(np.prod(espacamento)) / 1000.0)
    volume_uniao_ml = float(int(uniao.sum()) * float(np.prod(espacamento)) / 1000.0)
    return {
        "status": "union_built",
        "phases_included": fases_incluidas,
        "phase_failures": fases_falhas,
        "venous_volume_ml": round(volume_venosa_ml, 1),
        "union_volume_ml": round(volume_uniao_ml, 1),
        "classification_region_fraction_of_union": (
            round(volume_venosa_ml / volume_uniao_ml, 4) if volume_uniao_ml > 0 else None
        ),
    }


def _localize_candidate(case_dir: Path, decision: dict[str, Any]) -> dict[str, Any]:
    """Run the viewer-only localizer after the screening decision is frozen.

    A localization failure never changes the already computed prediction and
    never prevents publication of the liver model. It is reported explicitly.
    """
    subtype = decision.get("subtype") if isinstance(decision.get("subtype"), dict) else {}
    requested = decision.get("prediction") == "POSITIVE" or bool(subtype.get("determined"))
    if not requested:
        for name in (
            "mask_candidate.nii.gz", "mask_candidate_clean.nii.gz",
            "mesh_candidate.vtp", "candidate_region.json", "candidate_request.json",
        ):
            (case_dir / name).unlink(missing_ok=True)
        return {
            "status": "not_requested_no_focal_finding",
            "candidate_present": False,
            "used_by_screening_inference": False,
            "requires_human_review": False,
        }
    request = {
        "schema": "argos-candidate-request-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "screening_decision_frozen": True,
        "prediction": str(decision.get("prediction")),
        "visual_score": float(decision.get("score", 0.0)),
        "visual_threshold": float(decision.get("threshold", 0.0)),
        "subtype_determined": bool(subtype.get("determined")),
        "subtype": str(subtype.get("subtype")) if subtype.get("determined") else None,
        "subtype_label": (
            server.SUBTYPE_LABELS_PT.get(str(subtype.get("subtype")), str(subtype.get("subtype")))
            if subtype.get("determined") else None
        ),
        "used_by_screening_inference": False,
        "ground_truth_included": False,
        "research_only": True,
    }
    request_path = case_dir / "candidate_request.json"
    temp = request_path.with_name(".candidate_request.json.tmp")
    temp.write_text(json.dumps(request, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(request_path)
    process = run_candidate_subprocess(
        case_dir=case_dir,
        request_path=request_path,
        device="gpu",
        timeout_seconds=server.CANDIDATE_TIMEOUT,
        python_executable=server.PY,
    )
    manifest_path = case_dir / "candidate_region.json"
    if process.returncode == 0 and manifest_path.is_file():
        try:
            result = json.loads(manifest_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError("Manifesto do candidato automático inválido.") from exc
        if result.get("schema") != "argos-candidate-region-v1":
            raise PipelineError("Schema do candidato automático inválido.")
        return result
    # Remove any incomplete/stale candidate so finalize cannot publish it.
    for name in (
        "mask_candidate.nii.gz", "mask_candidate_clean.nii.gz",
        "mesh_candidate.vtp", "candidate_region.json",
    ):
        (case_dir / name).unlink(missing_ok=True)
    return {
        "status": "localization_unavailable",
        "candidate_present": False,
        "used_by_screening_inference": False,
        "requires_human_review": True,
        "reason": candidate_error(process),
    }



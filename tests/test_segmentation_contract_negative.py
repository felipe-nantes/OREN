"""Testes negativos do contrato de segmentacao visual (PHASE_07 S2-S4).

Braços fail-closed de ``image_geometry``, dos manifestos e do gate de
exibição ``approved_visualization_mask``, disparados com artefatos sintéticos.
Estados inválidos que o próprio SimpleITK recusa construir (spacing <= 0,
direção toda-zero) ficam justificados no ledger da wave, não aqui.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.core import PipelineError
from dtwin.segmentation_contract import (
    INPUT_SCHEMA,
    QUALITY_SCHEMA,
    approved_visualization_mask,
    build_native_input_manifest,
    build_quality_manifest,
    experimental_paths,
    image_geometry,
    validate_visualization_mask,
)


def _image(array: np.ndarray | None = None) -> sitk.Image:
    image = sitk.GetImageFromArray(
        np.ones((4, 4, 4), dtype=np.uint8) if array is None else array
    )
    image.SetSpacing((1.0, 1.0, 2.0))
    image.SetOrigin((0.0, 0.0, 0.0))
    return image


def _write_image(path: Path, array: np.ndarray | None = None) -> Path:
    sitk.WriteImage(_image(array), str(path), useCompression=True)
    return path


# --- S2: image_geometry ------------------------------------------------------


def test_image_geometry_rejeita_origem_nao_finita():
    image = _image()
    image.SetOrigin((float("nan"), 0.0, 0.0))
    with pytest.raises(PipelineError, match="nao finito"):
        image_geometry(image)


def test_image_geometry_rejeita_direcao_quase_singular():
    image = _image()
    image.SetDirection((1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1e-9))
    with pytest.raises(PipelineError, match="singular"):
        image_geometry(image)


# --- S3: manifesto de entrada nativo ----------------------------------------


def test_manifesto_nativo_rejeita_volume_ausente(tmp_path):
    with pytest.raises(PipelineError, match="ausente"):
        build_native_input_manifest(
            source_volume=tmp_path / "nao_existe.nii.gz",
            reference_volume=tmp_path / "tambem_nao.nii.gz",
            source_role="volume_nativo",
        )


@pytest.mark.parametrize("role", ["", "papel invalido!"])
def test_manifesto_nativo_rejeita_papel_invalido(tmp_path, role):
    source = _write_image(tmp_path / "vol.nii.gz")
    with pytest.raises(PipelineError, match="[Pp]apel"):
        build_native_input_manifest(
            source_volume=source, reference_volume=source, source_role=role
        )


def test_manifesto_nativo_rejeita_volume_ilegivel(tmp_path):
    falso = tmp_path / "vol.nii.gz"
    falso.write_bytes(b"isto nao e um nifti")
    with pytest.raises(PipelineError, match="Falha ao ler entrada"):
        build_native_input_manifest(
            source_volume=falso, reference_volume=falso,
            source_role="volume_nativo",
        )


# --- S3: validate_visualization_mask ----------------------------------------


def test_mascara_visual_rejeita_arquivo_ausente(tmp_path):
    referencia = _write_image(tmp_path / "ref.nii.gz")
    with pytest.raises(PipelineError, match="ausente"):
        validate_visualization_mask(tmp_path / "mask.nii.gz", referencia)


def test_mascara_visual_rejeita_arquivo_ilegivel(tmp_path):
    referencia = _write_image(tmp_path / "ref.nii.gz")
    falsa = tmp_path / "mask.nii.gz"
    falsa.write_bytes(b"isto nao e um nifti")
    with pytest.raises(PipelineError, match="Falha ao ler mascara"):
        validate_visualization_mask(falsa, referencia)


def test_mascara_visual_rejeita_valor_nao_finito(tmp_path):
    # OBSERVED: o writer NIfTI do ITK sanitiza NaN->0 no round-trip; o braço
    # não-finito protege contra arquivos de outros writers. MetaImage (.mha)
    # preserva NaN e permite exercitar o braço de verdade.
    referencia = _write_image(tmp_path / "ref.mha")
    valores = np.ones((4, 4, 4), dtype=np.float32)
    valores[0, 0, 0] = math.nan
    mascara = _write_image(tmp_path / "mask.mha", valores)
    with pytest.raises(PipelineError, match="nao finito"):
        validate_visualization_mask(mascara, referencia)


# --- S3: build_quality_manifest ---------------------------------------------


def _input_manifest_valido() -> dict:
    return {"schema": INPUT_SCHEMA}


def test_manifesto_de_qualidade_rejeita_schema_de_entrada_incompativel(tmp_path):
    with pytest.raises(PipelineError, match="incompativel"):
        build_quality_manifest(
            backend_id="b", backend_version="1",
            input_manifest={"schema": "outro"},
            visualization_mask=tmp_path / "m.nii.gz",
            reference_volume=tmp_path / "r.nii.gz",
            elapsed_seconds=1.0,
        )


def test_manifesto_de_qualidade_exige_backend_identificado(tmp_path):
    with pytest.raises(PipelineError, match="identificador e versao"):
        build_quality_manifest(
            backend_id="", backend_version="1",
            input_manifest=_input_manifest_valido(),
            visualization_mask=tmp_path / "m.nii.gz",
            reference_volume=tmp_path / "r.nii.gz",
            elapsed_seconds=1.0,
        )


@pytest.mark.parametrize("elapsed", [-1.0, math.nan])
def test_manifesto_de_qualidade_rejeita_tempo_invalido(tmp_path, elapsed):
    with pytest.raises(PipelineError, match="Tempo de segmentacao"):
        build_quality_manifest(
            backend_id="b", backend_version="1",
            input_manifest=_input_manifest_valido(),
            visualization_mask=tmp_path / "m.nii.gz",
            reference_volume=tmp_path / "r.nii.gz",
            elapsed_seconds=elapsed,
        )


# --- S4: approved_visualization_mask (gate de exibição; degrada para None) ---


def _recibo_valido(mask_bytes: bytes) -> dict:
    return {
        "schema": QUALITY_SCHEMA,
        "status": "APPROVED",
        "purpose": "visualization_only",
        "classification_input_immutable": True,
        "ground_truth_read": False,
        "lesion_masks_read": 0,
        "production_files_written": False,
        "mask": {"sha256": hashlib.sha256(mask_bytes).hexdigest()},
    }


def _montar_caso(case_root: Path, recibo: dict | str,
                 mask_bytes: bytes = b"mascara") -> Path:
    case_root.mkdir(parents=True, exist_ok=True)
    paths = experimental_paths(case_root)
    paths.visualization_mask.write_bytes(mask_bytes)
    texto = recibo if isinstance(recibo, str) else json.dumps(recibo)
    paths.quality_manifest.write_text(texto, encoding="utf-8")
    return case_root


def test_gate_aprova_somente_recibo_completo_e_integro(tmp_path):
    caso = _montar_caso(tmp_path / "caso", _recibo_valido(b"mascara"))
    aprovado = approved_visualization_mask(caso)
    assert aprovado == experimental_paths(caso).visualization_mask


def test_gate_degrada_para_none_com_recibo_ilegivel(tmp_path):
    caso = _montar_caso(tmp_path / "caso", "{quebrado")
    assert approved_visualization_mask(caso) is None


def test_gate_degrada_para_none_com_schema_estranho(tmp_path):
    recibo = _recibo_valido(b"mascara")
    recibo["schema"] = "outro-schema"
    caso = _montar_caso(tmp_path / "caso", recibo)
    assert approved_visualization_mask(caso) is None


def test_gate_degrada_para_none_com_status_reprovado(tmp_path):
    recibo = _recibo_valido(b"mascara")
    recibo["status"] = "REJECTED"
    caso = _montar_caso(tmp_path / "caso", recibo)
    assert approved_visualization_mask(caso) is None


@pytest.mark.parametrize("chave, valor", [
    ("ground_truth_read", True),
    ("lesion_masks_read", 1),
    ("production_files_written", True),
])
def test_gate_degrada_para_none_se_recibo_confessa_violacao(tmp_path, chave, valor):
    recibo = _recibo_valido(b"mascara")
    recibo[chave] = valor
    caso = _montar_caso(tmp_path / "caso", recibo)
    assert approved_visualization_mask(caso) is None


def test_gate_degrada_para_none_com_hash_divergente(tmp_path):
    # Recibo íntegro, mas a máscara em disco foi trocada depois do carimbo.
    caso = _montar_caso(
        tmp_path / "caso", _recibo_valido(b"mascara"), mask_bytes=b"trocada"
    )
    assert approved_visualization_mask(caso) is None


def test_gate_degrada_para_none_sem_hash_registrado(tmp_path):
    recibo = _recibo_valido(b"mascara")
    del recibo["mask"]
    caso = _montar_caso(tmp_path / "caso", recibo)
    assert approved_visualization_mask(caso) is None

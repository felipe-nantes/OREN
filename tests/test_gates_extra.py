# tests/test_gates_extra.py
"""Characterization tests for the pipeline's abort gates and branches that the
core suite did not yet exercise. These cover stage 3 (segmentation, via an
injected fake TotalSegmentator — no GPU/torch), normalization variants, the
lesion-import gates, refino safety gates, and the privacy-policy gate.

If any of these FAIL, an existing safety behavior regressed — investigate the
code, not the test.
"""
import sys
import types
from pathlib import Path

import numpy as np
import pytest

from dtwin import stages
from dtwin.core import (
    Case,
    PipelineError,
    array_from,
    array_to_image,
    read_image,
    save_image,
)
from dtwin.stages import _make_case_id, stage2_normalize, stage3_segment_organ

from .conftest import make_geo_image, make_sphere_mask

ORGAN_PROFILE = {"segmentacao_orgao": {"rotulo_alvo": "liver", "motor_task": "total_mr"}}
ANATOMY_PROFILE = {
    "segmentacao_orgao": {"rotulo_alvo": "liver", "motor_task": "total_mr"},
    "segmentacao_anatomia": {
        "habilitada": True,
        "tarefas": [
            {
                "motor_task": "total_mr",
                "estruturas": [{"papel": "vesicula_biliar", "rotulo": "gallbladder"}],
            },
            {
                "motor_task": "liver_segments_mr",
                "fast": False,
                "require_complete": True,
                "estruturas": [
                    {"papel": "couinaud_i", "rotulo": "liver_segment_1"},
                    {"papel": "couinaud_ii", "rotulo": "liver_segment_2"},
                ],
            },
        ],
    },
}


# --------------------------------------------------------------------------- #
# Stage 3 — segmentação automática (fake TotalSegmentator, sem GPU/torch)
# --------------------------------------------------------------------------- #
def _install_fake_totalseg(monkeypatch, writer):
    pkg = types.ModuleType("totalsegmentator")
    api = types.ModuleType("totalsegmentator.python_api")
    api.totalsegmentator = writer
    pkg.python_api = api
    monkeypatch.setitem(sys.modules, "totalsegmentator", pkg)
    monkeypatch.setitem(sys.modules, "totalsegmentator.python_api", api)


def test_stage3_missing_package_aborts(synthetic_case, monkeypatch):
    # ensure no fake is present: stage3 must abort, never fabricate a mask
    monkeypatch.setitem(sys.modules, "totalsegmentator", None)
    with pytest.raises(PipelineError, match="TotalSegmentator"):
        stage3_segment_organ(synthetic_case, ORGAN_PROFILE, device="cpu", fast=True)


def test_stage3_success_writes_organ_mask(synthetic_case, monkeypatch):
    def writer(**kw):
        out = Path(kw["output"])
        vol = read_image(Path(kw["input"]))
        arr = array_from(vol)
        organ = make_sphere_mask(arr.shape, tuple(s // 2 for s in arr.shape), max(arr.shape) // 4)
        save_image(array_to_image(organ, vol, np.uint8), out / (kw["roi_subset"][0] + ".nii.gz"))

    _install_fake_totalseg(monkeypatch, writer)
    synthetic_case.mask_organ.unlink()  # prove stage3 (re)creates it
    stage3_segment_organ(synthetic_case, ORGAN_PROFILE, device="cpu", fast=True)
    assert synthetic_case.mask_organ.exists()
    assert int(array_from(read_image(synthetic_case.mask_organ)).sum()) > 0


# RIM-01 (2026-08-28, plano aprovado): rotulo_alvo aceita lista (órgão par —
# mask_organ = UNIÃO lógica dos rótulos); string permanece byte-idêntica.
PAIRED_ORGAN_PROFILE = {
    "segmentacao_orgao": {"rotulo_alvo": ["kidney_left", "kidney_right"], "motor_task": "total_mr"}
}


def test_stage3_multi_label_union_writes_organ_mask_from_two_disjoint_rois(
    synthetic_case, monkeypatch
):
    def writer(**kw):
        out = Path(kw["output"])
        vol = read_image(Path(kw["input"]))
        arr = array_from(vol)
        shape = arr.shape
        left = make_sphere_mask(shape, tuple(s // 4 for s in shape), max(shape) // 8)
        right = make_sphere_mask(
            shape, tuple(3 * s // 4 for s in shape), max(shape) // 8
        )
        by_role = {"kidney_left": left, "kidney_right": right}
        for role in kw["roi_subset"]:
            save_image(array_to_image(by_role[role], vol, np.uint8), out / f"{role}.nii.gz")

    _install_fake_totalseg(monkeypatch, writer)
    synthetic_case.mask_organ.unlink()
    stage3_segment_organ(synthetic_case, PAIRED_ORGAN_PROFILE, device="cpu", fast=True)
    assert synthetic_case.mask_organ.exists()
    union = array_from(read_image(synthetic_case.mask_organ)) > 0
    left = array_from(read_image(synthetic_case.seg_dir / "kidney_left.nii.gz")) > 0
    right = array_from(read_image(synthetic_case.seg_dir / "kidney_right.nii.gz")) > 0
    assert int(union.sum()) == int((left | right).sum())
    assert int((left & right).sum()) == 0  # spheres não se sobrepõem — prova a união real
    assert int(union.sum()) > int(left.sum())  # ambos os lados contribuem


def test_stage3_multi_label_missing_one_side_aborts(synthetic_case, monkeypatch):
    """Se um dos rótulos do par não sai da task, aborta — nunca publica meio órgão."""
    def writer(**kw):
        out = Path(kw["output"])
        vol = read_image(Path(kw["input"]))
        arr = array_from(vol)
        left = make_sphere_mask(arr.shape, tuple(s // 2 for s in arr.shape), max(arr.shape) // 4)
        save_image(array_to_image(left, vol, np.uint8), out / "kidney_left.nii.gz")
        # kidney_right.nii.gz deliberadamente não escrito

    _install_fake_totalseg(monkeypatch, writer)
    with pytest.raises(PipelineError, match="kidney_right"):
        stage3_segment_organ(synthetic_case, PAIRED_ORGAN_PROFILE, device="cpu", fast=True)


def test_stage3_rotulo_alvo_invalido_aborta(synthetic_case, monkeypatch):
    perfil_lista_vazia = {"segmentacao_orgao": {"rotulo_alvo": [], "motor_task": "total_mr"}}
    with pytest.raises(PipelineError, match="string ou lista"):
        stage3_segment_organ(synthetic_case, perfil_lista_vazia, device="cpu", fast=True)

    perfil_tipo_errado = {"segmentacao_orgao": {"rotulo_alvo": 42, "motor_task": "total_mr"}}
    with pytest.raises(PipelineError, match="string ou lista"):
        stage3_segment_organ(synthetic_case, perfil_tipo_errado, device="cpu", fast=True)


def test_stage3_perfil_real_rins_rm_produz_uniao_e_estruturas_por_lado(
    synthetic_case, monkeypatch
):
    """Prova que profiles/rins.yaml (arquivo real, não dict sintético) é
    consumido corretamente: mask_organ = união L+R; seg_raw/ preserva os
    dois rótulos individualmente p/ a anatomia (rim_esquerdo/rim_direito)."""
    from dtwin.core import load_profile

    perfil = load_profile("profiles/rins.yaml")

    def writer(**kw):
        out = Path(kw["output"])
        vol = read_image(Path(kw["input"]))
        arr = array_from(vol)
        shape = arr.shape
        left = make_sphere_mask(shape, tuple(s // 4 for s in shape), max(shape) // 8)
        right = make_sphere_mask(
            shape, tuple(3 * s // 4 for s in shape), max(shape) // 8
        )
        by_role = {"kidney_left": left, "kidney_right": right}
        for role in kw["roi_subset"]:
            save_image(array_to_image(by_role[role], vol, np.uint8), out / f"{role}.nii.gz")

    _install_fake_totalseg(monkeypatch, writer)
    synthetic_case.mask_organ.unlink()
    stage3_segment_organ(synthetic_case, perfil, device="cpu", fast=True)
    assert synthetic_case.mask_organ.exists()
    left = array_from(read_image(synthetic_case.seg_dir / "kidney_left.nii.gz")) > 0
    right = array_from(read_image(synthetic_case.seg_dir / "kidney_right.nii.gz")) > 0
    union = array_from(read_image(synthetic_case.mask_organ)) > 0
    assert int(union.sum()) == int((left | right).sum())
    assert int(left.sum()) > 0 and int(right.sum()) > 0  # ambos os lados saíram


def test_stage3_exports_supported_internal_anatomy_without_affecting_liver_gate(
    synthetic_case, monkeypatch
):
    calls = []

    def writer(**kw):
        roi_subset = kw.get("roi_subset")
        calls.append((kw["task"], tuple(roi_subset) if roi_subset else None, kw["fast"]))
        out = Path(kw["output"])
        vol = read_image(Path(kw["input"]))
        arr = array_from(vol)
        labels = roi_subset or ["liver_segment_1", "liver_segment_2"]
        for index, label in enumerate(labels):
            mask = make_sphere_mask(
                arr.shape, tuple(s // 2 + index for s in arr.shape), max(arr.shape) // 6
            )
            save_image(array_to_image(mask, vol, np.uint8), out / f"{label}.nii.gz")

    _install_fake_totalseg(monkeypatch, writer)
    stage3_segment_organ(synthetic_case, ANATOMY_PROFILE, device="cpu", fast=True)

    assert ("total_mr", ("gallbladder", "liver"), True) in calls
    assert ("liver_segments_mr", None, False) in calls
    assert synthetic_case.mask_organ.exists()
    assert synthetic_case.anatomy_mask("vesicula_biliar").exists()
    assert synthetic_case.anatomy_mask("couinaud_i").exists()
    assert synthetic_case.anatomy_mask("couinaud_ii").exists()


def test_stage3_never_publishes_partial_required_anatomy(synthetic_case, monkeypatch):
    def writer(**kw):
        out = Path(kw["output"])
        vol = read_image(Path(kw["input"]))
        arr = array_from(vol)
        labels = kw.get("roi_subset") or ["liver_segment_1"]
        for label in labels:
            mask = make_sphere_mask(
                arr.shape, tuple(s // 2 for s in arr.shape), max(arr.shape) // 6
            )
            save_image(array_to_image(mask, vol, np.uint8), out / f"{label}.nii.gz")

    _install_fake_totalseg(monkeypatch, writer)
    stage3_segment_organ(synthetic_case, ANATOMY_PROFILE, device="cpu", fast=True)

    assert not synthetic_case.anatomy_mask("couinaud_i").exists()
    assert not synthetic_case.anatomy_mask("couinaud_ii").exists()


def test_stage3_missing_output_aborts(synthetic_case, monkeypatch):
    _install_fake_totalseg(monkeypatch, lambda **kw: None)  # writes nothing
    with pytest.raises(PipelineError, match="não encontrada"):
        stage3_segment_organ(synthetic_case, ORGAN_PROFILE, device="cpu", fast=True)


def test_stage3_empty_segmentation_aborts(synthetic_case, monkeypatch):
    def writer(**kw):
        out = Path(kw["output"])
        vol = read_image(Path(kw["input"]))
        zeros = np.zeros(array_from(vol).shape, dtype=np.uint8)
        save_image(array_to_image(zeros, vol, np.uint8), out / (kw["roi_subset"][0] + ".nii.gz"))

    _install_fake_totalseg(monkeypatch, writer)
    with pytest.raises(PipelineError, match="não encontrou"):
        stage3_segment_organ(synthetic_case, ORGAN_PROFILE, device="cpu", fast=True)


def test_stage3_segmentator_raises_aborts(synthetic_case, monkeypatch):
    def writer(**kw):
        raise RuntimeError("CUDA out of memory")

    _install_fake_totalseg(monkeypatch, writer)
    with pytest.raises(PipelineError, match="Falha na segmentação"):
        stage3_segment_organ(synthetic_case, ORGAN_PROFILE, device="cpu", fast=True)


# --------------------------------------------------------------------------- #
# Stage 2 — normalização minmax (o sucesso só era testado p/ zscore)
# --------------------------------------------------------------------------- #
def test_minmax_normalization_maps_to_unit_range(tmp_path):
    arr = np.random.default_rng(2).normal(40, 12, size=(16, 16, 16)).astype(np.float32)
    case = Case(tmp_path)
    save_image(make_geo_image(arr), case.volume)
    stage2_normalize(case, {"normalizacao": "minmax"})
    out = array_from(read_image(case.volume_zscore))
    assert abs(float(out.min())) < 1e-6
    assert abs(float(out.max()) - 1.0) < 1e-6


def test_minmax_no_contrast_aborts(tmp_path):
    arr = np.full((8, 8, 8), 3.0, np.float32)
    case = Case(tmp_path)
    save_image(make_geo_image(arr), case.volume)
    with pytest.raises(PipelineError):
        stage2_normalize(case, {"normalizacao": "minmax"})


# --------------------------------------------------------------------------- #
# Stage 4b — gates de importação da lesão
# --------------------------------------------------------------------------- #
def test_lesion_size_mismatch_aborts(synthetic_case):
    # overwrite lesion with a differently-sized mask
    small = make_sphere_mask((30, 30, 30), (15, 15, 15), 4)
    save_image(make_geo_image(small), synthetic_case.mask_lesion)
    with pytest.raises(PipelineError, match="tamanho diferente"):
        stages.stage4b_import_lesion(synthetic_case, ORGAN_PROFILE, no_lesion=False)


def test_lesion_outside_organ_warns_but_completes(synthetic_case, tmp_path, caplog):
    # lesion fully disjoint from organ: warning, not abort
    shape = (40, 40, 40)
    lesion = make_sphere_mask(shape, (4, 4, 4), 2)
    ref = read_image(synthetic_case.mask_organ)
    save_image(array_to_image(lesion, ref, np.uint8), synthetic_case.mask_lesion)
    profile = {**ORGAN_PROFILE, "id": "figado", "flywheel": {"dir": str(tmp_path / "fly")}}
    import logging
    with caplog.at_level(logging.WARNING, logger="dtwin"):
        stages.stage4b_import_lesion(synthetic_case, profile, no_lesion=False)
    assert any("não sobrepõe" in r.message for r in caplog.records)


def test_lesion_missing_without_flag_aborts(synthetic_case):
    synthetic_case.mask_lesion.unlink()
    with pytest.raises(PipelineError, match="ausente"):
        stages.stage4b_import_lesion(synthetic_case, ORGAN_PROFILE, no_lesion=False)


def test_organ_missing_aborts(tmp_path):
    case = Case(tmp_path)  # nothing on disk
    with pytest.raises(PipelineError, match="órgão ausente"):
        stages.stage4b_import_lesion(case, ORGAN_PROFILE, no_lesion=True)


# --------------------------------------------------------------------------- #
# Stage 5 — refino nunca pode zerar uma máscara que tinha conteúdo
# --------------------------------------------------------------------------- #
def _case_with_masks(tmp_path):
    shape = (40, 40, 40)
    ref = make_geo_image(np.zeros(shape, np.float32))
    case = Case(tmp_path)
    save_image(ref, case.volume)
    save_image(array_to_image(make_sphere_mask(shape, (20, 20, 20), 12), ref, np.uint8), case.mask_organ)
    save_image(array_to_image(make_sphere_mask(shape, (20, 20, 20), 4), ref, np.uint8), case.mask_lesion)
    return case


def test_refino_zeroing_organ_aborts(tmp_path):
    case = _case_with_masks(tmp_path)
    profile = {"refino": {"orgao": {"min_volume_voxels": 10**9}}}
    with pytest.raises(PipelineError, match="zerou a máscara do órgão"):
        stages.stage5_refine(case, profile)


def test_refino_descarta_uniao_com_direction_divergente(tmp_path, caplog):
    """HG-03 item 13 (2026-08-20): união com direction flipada (mesmos
    size/spacing/origin) é descartada com warning e o refino usa a venosa."""
    import SimpleITK as sitk

    case = _case_with_masks(tmp_path)
    uniao = sitk.ReadImage(str(case.mask_organ))
    uniao.SetDirection((1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, -1.0))
    sitk.WriteImage(uniao, str(case.mask_organ_union), useCompression=True)

    with caplog.at_level("WARNING"):
        stages.stage5_refine(case, {"refino": {}})
    assert "geometria divergente" in caplog.text
    assert case.mask_organ_clean.is_file()


def test_refino_zeroing_lesion_aborts(tmp_path):
    case = _case_with_masks(tmp_path)
    profile = {"refino": {"lesao": {"min_volume_voxels": 10**9}}}
    with pytest.raises(PipelineError, match="zerou a máscara da lesão"):
        stages.stage5_refine(case, profile)


# --------------------------------------------------------------------------- #
# Stage 6 — malha de órgão vazia aborta
# --------------------------------------------------------------------------- #
def test_empty_organ_mesh_aborts(tmp_path):
    shape = (10, 10, 10)
    ref = make_geo_image(np.zeros(shape, np.float32))
    case = Case(tmp_path)
    save_image(array_to_image(np.zeros(shape, np.uint8), ref, np.uint8), case.mask_organ_clean)
    with pytest.raises(PipelineError, match="Malha do órgão vazia"):
        stages.stage6_mesh(case, {})


# --------------------------------------------------------------------------- #
# Política de privacidade — pseudonimização é gate reservado, não simulação
# --------------------------------------------------------------------------- #
def test_pseudonymize_policy_aborts():
    with pytest.raises(PipelineError, match="Pseudonimização"):
        _make_case_id("pseudonymize", None)


def test_unknown_policy_aborts():
    with pytest.raises(PipelineError, match="desconhecida"):
        _make_case_id("bogus", None)


def test_anonymize_policy_returns_anon_id():
    cid = _make_case_id("anonymize", None)
    assert cid.startswith("anon-") and len(cid) > 5


# --------------------------------------------------------------------------- #
# Stage 1 / 4a — gates de ingestão e de handoff
# --------------------------------------------------------------------------- #
def test_stage1_missing_dicom_dir_aborts(tmp_path):
    case = Case(tmp_path)
    with pytest.raises(PipelineError, match="DICOM inexistente"):
        stages.stage1_ingest(case, {"modalidade": ["MR"]}, tmp_path / "ghost", "anonymize")


def test_stage1_no_readable_dicom_aborts(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "notdicom.txt").write_text("garbage", encoding="utf-8")
    case = Case(tmp_path / "case")
    # pydicom(force=True) lê o lixo como dataset vazio; o gate real dispara
    # adiante, quando o GDCM não encontra nenhuma série montável.
    with pytest.raises(PipelineError, match="Nenhuma série DICOM"):
        stages.stage1_ingest(case, {"modalidade": ["MR"]}, src, "anonymize")


def test_stage4a_incomplete_aborts(tmp_path):
    case = Case(tmp_path)  # no volume / no organ mask
    with pytest.raises(PipelineError, match="incompletos"):
        stages.stage4a_prepare_lesion(case, {})

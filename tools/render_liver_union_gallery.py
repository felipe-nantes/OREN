#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Galeria com a máscara de VISUALIZAÇÃO nova (união de fases), mesmos casos.

Usa os MESMOS 10 casos e a MESMA lista de docs/188 (`experiments/_galeria_casos.txt`)
para que a comparação com a galeria anterior (venosa isolada) seja honesta --
mesmo paciente, mesma câmera por caso, só a fonte da malha muda.

Reaproveita o código de PRODUÇÃO, não uma reimplementação: constrói a união com
`webapp.server._build_union_liver_mask` e monta a malha com
`dtwin.stages._fonte_da_malha_do_orgao` + `_refine_mask` +
`_isolar_orgao_para_visualizacao` + `_mesh_from_mask`, exatamente o caminho que
o webapp executa.

Uso:
    .venv-win/Scripts/python.exe tools/render_liver_union_gallery.py
"""
from __future__ import annotations

import argparse
import shutil
import sys
import warnings
from pathlib import Path

import numpy as np
import SimpleITK as sitk

warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pyvista as pv  # noqa: E402

pv.OFF_SCREEN = True

from dtwin.stages import (  # noqa: E402
    _fonte_da_malha_do_orgao,
    _isolar_orgao_para_visualizacao,
    _mesh_from_mask,
    _refine_mask,
)
from dtwin.core import Case  # noqa: E402
from webapp.server import _build_union_liver_mask  # noqa: E402

VENOSA = REPO / "casos/qualification/lld_mmri_v23/prepared/external_segmentation_audit335_fullres_v1"
ENTRADAS = REPO / "casos/qualification/lld_mmri_v23/prepared/external_inputs_v1/inputs"
SAIDA = REPO / "experiments/liver_union_gallery_v1"
FAIXA_ADULTO_ML = (900.0, 2400.0)

MESH = dict(level=0.5, smooth_iter=30, feature_angle=60.0, pass_band=0.1,
            isotropic_mm=0.8, gaussian_sigma_mm=2.0, max_triangles=160000)
COR_ORGAO = "#C8A27D"
VISTAS = (("anterior", 0, 0), ("posterior", 180, 0), ("superior", 0, 88))
LADO = 620


def renderiza(malha, destino: Path, azimute: float, elevacao: float) -> None:
    plotter = pv.Plotter(off_screen=True, window_size=(LADO, LADO))
    plotter.set_background("#0e1216")
    plotter.add_mesh(
        malha, color=COR_ORGAO, smooth_shading=True, pbr=True,
        metallic=0.03, roughness=0.40, diffuse=1.0, specular=0.30,
    )
    plotter.reset_camera(bounds=malha.bounds)
    plotter.camera.azimuth = azimute
    plotter.camera.elevation = elevacao
    plotter.camera.zoom(1.25)
    plotter.enable_anti_aliasing("ssaa")
    plotter.screenshot(str(destino))
    plotter.close()


def mesh_do_caso(case_dir: Path) -> tuple[object, dict]:
    profile = {
        "refino": {"orgao": {"opening": True, "opening_radius": 2, "min_volume_voxels": 300}},
    }
    oc = profile["refino"]["orgao"]
    fonte = _fonte_da_malha_do_orgao(Case(root=case_dir))
    imagem = sitk.ReadImage(str(fonte))
    bruta = sitk.GetArrayFromImage(imagem) > 0
    limpo = _refine_mask(bruta, oc["opening"], oc["opening_radius"], oc["min_volume_voxels"]).astype(bool)
    limpo, diagnostico = _isolar_orgao_para_visualizacao(limpo)
    saida_mask = sitk.GetImageFromArray(limpo.astype(np.uint8))
    saida_mask.CopyInformation(imagem)
    temporario = case_dir / "_tmp_mesh_source.nii.gz"
    sitk.WriteImage(saida_mask, str(temporario))
    malha = _mesh_from_mask(
        temporario, MESH["level"], MESH["smooth_iter"], MESH["feature_angle"],
        pass_band=MESH["pass_band"], isotropic_mm=MESH["isotropic_mm"],
        gaussian_sigma_mm=MESH["gaussian_sigma_mm"], max_triangles=MESH["max_triangles"],
    )
    temporario.unlink(missing_ok=True)
    return malha, diagnostico


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--casos", type=Path, default=REPO / "experiments/_galeria_casos.txt")
    args = parser.parse_args()
    casos = [c.strip() for c in args.casos.read_text().splitlines() if c.strip()]
    SAIDA.mkdir(parents=True, exist_ok=True)

    from PIL import Image, ImageDraw

    baixo, alto = FAIXA_ADULTO_ML
    print(f"renderizando {len(casos)} casos com a uniao de fases, 3 vistas cada\n")
    gerados = []
    for indice, case_id in enumerate(casos, 1):
        venosa_mask_path = VENOSA / case_id / "liver_mask_venous.nii.gz"
        arterial_src = ENTRADAS / case_id / "t1_arterial.nii.gz"
        delayed_src = ENTRADAS / case_id / "t1_delayed.nii.gz"
        if not all(p.is_file() for p in (venosa_mask_path, arterial_src, delayed_src)):
            print(f"  [{indice}] {case_id}: entrada ausente, pulado")
            continue
        print(f"[{indice}/{len(casos)}] {case_id}", flush=True)

        case_dir = SAIDA / "_work" / case_id
        if case_dir.exists():
            shutil.rmtree(case_dir)
        case_dir.mkdir(parents=True)
        shutil.copyfile(venosa_mask_path, case_dir / "mask_organ.nii.gz")

        uniao_info = _build_union_liver_mask(
            case_dir, {"arterial": arterial_src, "delayed": delayed_src}
        )
        print(f"    uniao: {uniao_info.get('status')}  "
              f"fases={uniao_info.get('phases_included')}", flush=True)

        malha, diagnostico = mesh_do_caso(case_dir)
        if malha is None:
            print(f"    malha vazia, pulado")
            shutil.rmtree(case_dir, ignore_errors=True)
            continue

        volume = abs(float(malha.volume)) / 1000.0
        parciais = []
        for nome, azimute, elevacao in VISTAS:
            alvo = SAIDA / f"_{case_id}_{nome}.png"
            renderiza(malha, alvo, azimute, elevacao)
            parciais.append(alvo)

        rodape = 68
        tela = Image.new("RGB", (LADO * 3 + 12, LADO + rodape), "#0e1216")
        for posicao, parcial in enumerate(parciais):
            with Image.open(parcial) as figura:
                tela.paste(figura, (posicao * (LADO + 6), 0))
            parcial.unlink(missing_ok=True)
        desenho = ImageDraw.Draw(tela)
        dentro = baixo <= volume <= alto
        marca = "dentro da faixa adulta" if dentro else "ABAIXO da faixa adulta (900-2400 mL)"
        venosa_volume = uniao_info.get("venous_volume_ml")
        ganho_txt = (
            f"venosa {venosa_volume:.0f} mL -> uniao {volume:.0f} mL "
            f"({volume/venosa_volume:.2f}x)"
            if uniao_info.get("status") == "union_built" and venosa_volume
            else f"{volume:.0f} mL (uniao indisponivel, so venosa)"
        )
        desenho.text(
            (14, LADO + 8),
            f"{indice:02d}  {case_id}   {ganho_txt}   —   {marca}",
            fill="#e6eef5" if dentro else "#e8a33d",
        )
        desenho.text(
            (14, LADO + 28),
            f"fases na uniao: {','.join(uniao_info.get('phases_included', []))}   "
            f"componentes: {diagnostico['componentes']}   "
            f"fracao do principal: {diagnostico['fracao_componente_principal']:.3f}",
            fill="#8fa3b4",
        )
        desenho.text(
            (14, LADO + 46),
            "vistas: anterior · posterior · superior   |   mesma reconstrucao de producao",
            fill="#5f7887",
        )
        composto = SAIDA / f"{indice:02d}_{int(volume):05d}mL_{case_id[:14]}.png"
        tela.save(composto)
        gerados.append(composto)
        shutil.rmtree(case_dir, ignore_errors=True)
        print(f"    -> {volume:.0f} mL  ({'ok' if dentro else 'abaixo da faixa'})", flush=True)

    print(f"\n{len(gerados)} imagens em {SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

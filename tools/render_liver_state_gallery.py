#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Galeria do estado atual da malha hepática, cobrindo a faixa REAL de qualidade.

Renderiza offscreen com a reconstrução e o material de produção, para que a
imagem seja o que o usuário veria na tela.

A amostra é escolhida ao longo da distribuição de volume (p5 a p95), não pelos
melhores casos. Uma galeria curada mostraria um produto que não existe: 76% da
coorte tem volume abaixo do piso adulto (docs/188), e esconder isso numa seleção
de fígados bonitos seria propaganda, não avaliação.

Cada caso sai em três vistas (anterior, posterior e superior) para que a forma
seja avaliável, e com o volume anotado.

Uso:
    .venv-win/Scripts/python.exe tools/render_liver_state_gallery.py
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import SimpleITK as sitk

warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pyvista as pv

pv.OFF_SCREEN = True

from dtwin.stages import (
    _isolar_orgao_para_visualizacao,
    _mesh_from_mask,
    _refine_mask,
)

VENOSA = REPO / "casos/qualification/lld_mmri_v23/prepared/external_segmentation_audit335_fullres_v1"
SAIDA = REPO / "experiments/liver_state_gallery_v1"
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--casos", type=Path,
                        default=REPO / "experiments/_galeria_casos.txt")
    args = parser.parse_args()
    if not args.casos.is_file():
        print(f"ERRO: lista de casos ausente: {args.casos}", file=sys.stderr)
        return 2
    casos = [c.strip() for c in args.casos.read_text().splitlines() if c.strip()]
    SAIDA.mkdir(parents=True, exist_ok=True)
    temporario = SAIDA / "_tmp.nii.gz"

    from PIL import Image, ImageDraw

    baixo, alto = FAIXA_ADULTO_ML
    print(f"renderizando {len(casos)} casos, 3 vistas cada\n")
    gerados = []
    for indice, case_id in enumerate(casos, 1):
        caminho = VENOSA / case_id / "liver_mask_venous.nii.gz"
        if not caminho.is_file():
            continue
        imagem = sitk.ReadImage(str(caminho))
        bruta = sitk.GetArrayFromImage(imagem) > 0
        limpo = _refine_mask(bruta, True, 2, 300).astype(bool)
        limpo, diagnostico = _isolar_orgao_para_visualizacao(limpo)
        saida_mask = sitk.GetImageFromArray(limpo.astype(np.uint8))
        saida_mask.CopyInformation(imagem)
        sitk.WriteImage(saida_mask, str(temporario))
        malha = _mesh_from_mask(
            temporario, MESH["level"], MESH["smooth_iter"], MESH["feature_angle"],
            pass_band=MESH["pass_band"], isotropic_mm=MESH["isotropic_mm"],
            gaussian_sigma_mm=MESH["gaussian_sigma_mm"], max_triangles=MESH["max_triangles"],
        )
        if malha is None:
            print(f"  [{indice}] {case_id}: malha vazia")
            continue

        volume = abs(float(malha.volume)) / 1000.0
        parciais = []
        for nome, azimute, elevacao in VISTAS:
            alvo = SAIDA / f"_{case_id}_{nome}.png"
            renderiza(malha, alvo, azimute, elevacao)
            parciais.append(alvo)

        rodape = 54
        tela = Image.new("RGB", (LADO * 3 + 12, LADO + rodape), "#0e1216")
        for posicao, parcial in enumerate(parciais):
            with Image.open(parcial) as figura:
                tela.paste(figura, (posicao * (LADO + 6), 0))
            parcial.unlink(missing_ok=True)
        desenho = ImageDraw.Draw(tela)
        dentro = baixo <= volume <= alto
        marca = "dentro da faixa adulta" if dentro else "ABAIXO da faixa adulta (900-2400 mL)"
        desenho.text(
            (14, LADO + 10),
            f"{indice:02d}  {case_id}   volume {volume:.0f} mL  —  {marca}",
            fill="#e6eef5" if dentro else "#e8a33d",
        )
        desenho.text(
            (14, LADO + 30),
            f"componentes na mascara: {diagnostico['componentes']}   "
            f"fracao do principal: {diagnostico['fracao_componente_principal']:.3f}   "
            f"corpo isolado: {'sim' if diagnostico['isolado'] else 'nao'}   "
            f"|   vistas: anterior · posterior · superior",
            fill="#8fa3b4",
        )
        composto = SAIDA / f"{indice:02d}_{int(volume):05d}mL_{case_id[:14]}.png"
        tela.save(composto)
        gerados.append(composto)
        print(f"  [{indice}] {case_id}: {volume:.0f} mL  "
              f"({'ok' if dentro else 'abaixo da faixa'})", flush=True)

    temporario.unlink(missing_ok=True)
    print(f"\n{len(gerados)} imagens em {SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

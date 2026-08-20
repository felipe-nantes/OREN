#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Renderiza figado + veias (porta/esplenica, cava inferior) + aorta para os
20 casos de casos/qualification/lld_mmri_v23/analise_10_melhores_10_piores_v1,
e monta um unico contact-sheet (10 melhores em cima, 10 piores embaixo).

VERSAO 2 (Fase 4 do plano de fragmentacao, docs/19X): o figado agora vem de
mask_organ_clean_producao.nii.gz -- a mascara que passou pela SEQUENCIA REAL
de producao (uniao de fases + _refine_mask + _isolar_orgao_para_visualizacao,
gerada por tools/build_production_liver_masks_for_selection.py), nao mais
direto da venosa crua. A primeira versao pulava essas tres mitigacoes ja
existentes e superestimava a fragmentacao. Os vasos ganharam a mesma remocao
de specks que ja roda em producao (_refine_mask, min_volume_voxels=20); o
fechamento morfologico para reconectar vasos foi testado e REPROVADO no gate
(tools/test_vessel_closing_gate.py) -- fragmentacao vascular residual e' real,
nao artefato de renderizacao.

Nota honesta sobre a "arteria": total_mr (TotalSegmentator MRI, 50 classes)
NAO tem rotulo de arteria hepatica. A unica estrutura arterial disponivel e'
a aorta -- usada aqui como representante da arvore arterial, nao como a
arteria hepatica propriamente dita. Isso fica escrito na legenda da imagem.

Reaproveita _mesh_from_mask (mesmo mesher de producao); usa parametros mais
leves de suavizacao para as estruturas finas (vasos) para nao apagar o lume.

Uso:
    .venv-win/Scripts/python.exe tools/render_best_worst_gallery.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import numpy as np
import pyvista as pv

pv.OFF_SCREEN = True

from dtwin.core import array_from, array_to_image, read_image, save_image
from dtwin.stages import _mesh_from_mask, _refine_mask

SELECAO = REPO / "casos/qualification/lld_mmri_v23/analise_10_melhores_10_piores_v1"
SAIDA = REPO / "experiments/best_worst_gallery_v1"
TMP = SAIDA / "_tmp_vaso_refinado"

ORGAO_MESH = dict(level=0.5, smooth_iter=30, feature_angle=60.0, pass_band=0.1,
                   isotropic_mm=0.8, gaussian_sigma_mm=2.0, max_triangles=160000)
VASO_MESH = dict(level=0.5, smooth_iter=15, feature_angle=60.0, pass_band=0.1,
                  isotropic_mm=0.5, gaussian_sigma_mm=0.6, max_triangles=80000)
VASO_MESH_PLANO = dict(level=0.5, smooth_iter=15, feature_angle=60.0, pass_band=0.1)

COR_ORGAO = "#C8A27D"
COR_PORTA = "#2E7FD9"   # veia porta/esplenica
COR_CAVA = "#8E5FE0"    # veia cava inferior
COR_AORTA = "#E23B3B"   # aorta (representante arterial -- ver nota na legenda)

LADO = 300


def malha_segura(mask_path: Path, cfg: dict):
    if not mask_path.is_file():
        return None
    malha = _mesh_from_mask(mask_path, **cfg)
    if malha is None and cfg.get("isotropic_mm"):
        malha = _mesh_from_mask(mask_path, **VASO_MESH_PLANO)
    return malha


def malha_vaso_refinado(mask_path: Path, case_id: str, papel: str):
    """Mesma remocao de specks que roda em producao (stage5_refine, bloco de
    anatomia) antes de gerar a malha -- a galeria original meshava a mascara
    de vaso crua direto."""
    if not mask_path.is_file():
        return None
    imagem = read_image(mask_path)
    bruta = array_from(imagem) > 0
    if bruta.sum() == 0:
        return None
    refinada = _refine_mask(bruta, False, 1, 20)
    if refinada.sum() == 0:
        return None
    TMP.mkdir(parents=True, exist_ok=True)
    tmp_path = TMP / f"{case_id}_{papel}.nii.gz"
    save_image(array_to_image(refinada.astype(np.uint8), imagem, np.uint8), tmp_path)
    return malha_segura(tmp_path, VASO_MESH)


def renderiza_caso(pasta_caso: Path, destino: Path) -> bool:
    case_id = pasta_caso.name
    figado_producao = pasta_caso / "mask_organ_clean_producao.nii.gz"
    if figado_producao.is_file():
        figado = malha_segura(figado_producao, ORGAO_MESH)
    else:
        # sem Fase 1 rodada para este caso: recai na venosa crua (comportamento antigo)
        figado = malha_segura(pasta_caso / "mask_organ_venosa.nii.gz", ORGAO_MESH)
    porta = malha_vaso_refinado(pasta_caso / "mask_vessel_portal_esplenica.nii.gz", case_id, "porta")
    cava = malha_vaso_refinado(pasta_caso / "mask_vessel_cava_inferior.nii.gz", case_id, "cava")
    aorta = malha_vaso_refinado(pasta_caso / "mask_vessel_aorta.nii.gz", case_id, "aorta")
    if figado is None:
        return False

    plotter = pv.Plotter(off_screen=True, window_size=(LADO, LADO))
    plotter.set_background("#0e1216")
    plotter.add_mesh(figado, color=COR_ORGAO, opacity=0.32, smooth_shading=True,
                      pbr=True, metallic=0.02, roughness=0.45, specular=0.20)
    for malha, cor in ((porta, COR_PORTA), (cava, COR_CAVA), (aorta, COR_AORTA)):
        if malha is not None:
            plotter.add_mesh(malha, color=cor, smooth_shading=True, pbr=True,
                              metallic=0.05, roughness=0.30, specular=0.40)

    bounds = figado.bounds
    plotter.reset_camera(bounds=bounds)
    plotter.camera.azimuth = 20
    plotter.camera.elevation = 15
    plotter.camera.zoom(1.15)
    plotter.enable_anti_aliasing("ssaa")
    plotter.screenshot(str(destino))
    plotter.close()
    return True


def monta_bloco(titulo: str, casos: list[tuple[str, dict]], imagens_dir: Path):
    from PIL import Image, ImageDraw

    colunas, linhas = 5, 2
    header_h, footer_h = 34, 46
    bloco = Image.new("RGB", (LADO * colunas, header_h + LADO * linhas + footer_h * linhas), "#0e1216")
    desenho = ImageDraw.Draw(bloco)
    desenho.text((10, 8), titulo, fill="#e6eef5")

    for i, (case_id, scorecard) in enumerate(casos):
        col, lin = i % colunas, i // colunas
        img_path = imagens_dir / f"{case_id}.png"
        x = col * LADO
        y = header_h + lin * (LADO + footer_h)
        if img_path.is_file():
            with Image.open(img_path) as im:
                bloco.paste(im, (x, y))
        rotulo = f"{i+1:02d}  {case_id[9:19]}  final={scorecard.get('score_final', 0):.2f}"
        desenho.text((x + 6, y + LADO + 4), rotulo, fill="#c7d3dc")
        desenho.text((x + 6, y + LADO + 20),
                      f"figado pct {scorecard.get('percentil_figado', 0):.2f}  "
                      f"vasos pct {scorecard.get('percentil_vasos', 0):.2f}",
                      fill="#8fa3b4")
    return bloco


def main() -> int:
    import json

    from PIL import Image, ImageDraw

    SAIDA.mkdir(parents=True, exist_ok=True)
    imagens_dir = SAIDA / "_casos"
    imagens_dir.mkdir(exist_ok=True)

    blocos = []
    for nome, titulo in (("10_melhores", "10 MELHORES - integridade hepatica + continuidade vascular"),
                          ("10_piores", "10 PIORES - integridade hepatica + continuidade vascular")):
        pasta_grupo = SELECAO / nome
        casos = []
        for pasta_caso in sorted(pasta_grupo.iterdir()):
            if not pasta_caso.is_dir():
                continue
            scorecard = json.loads((pasta_caso / "scorecard.json").read_text("utf-8"))
            destino_png = imagens_dir / f"{pasta_caso.name}.png"
            print(f"[{nome}] {pasta_caso.name}", flush=True)
            ok = renderiza_caso(pasta_caso, destino_png)
            if not ok:
                print("    malha do figado vazia, pulado")
            casos.append((pasta_caso.name, scorecard))
        blocos.append(monta_bloco(titulo, casos, imagens_dir))

    largura = max(b.width for b in blocos)
    altura_total = sum(b.height for b in blocos) + 90
    final = Image.new("RGB", (largura, altura_total), "#0e1216")
    y = 0
    for b in blocos:
        final.paste(b, (0, y))
        y += b.height

    desenho = ImageDraw.Draw(final)
    desenho.text(
        (10, y + 10),
        "figado = translucido | azul = veia porta/esplenica | roxo = veia cava inferior | "
        "vermelho = aorta",
        fill="#c7d3dc",
    )
    desenho.text(
        (10, y + 30),
        "figado: uniao de fases + refino + guarda de isolamento (caminho real de producao, "
        "docs/19X). vasos: com remocao de specks; fechamento morfologico testado e reprovado.",
        fill="#e8a33d",
    )
    desenho.text(
        (10, y + 50),
        "nota: total_mr nao tem rotulo de arteria hepatica -- aorta representa a arvore "
        "arterial visivel, nao a arteria hepatica em si. research_only=True.",
        fill="#5f7887",
    )

    caminho_final = SAIDA / "10_melhores_10_piores_producao.png"
    final.save(caminho_final)
    print(f"\nimagem final: {caminho_final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

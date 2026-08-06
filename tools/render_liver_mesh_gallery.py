#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Galeria de malhas hepáticas — compara fases lado a lado, no MESMO enquadramento.

Renderiza offscreen com a mesma reconstrução de produção (campo contínuo em
0,8 mm, sigma 2,0 mm, Taubin 30x, decimação para 160k) e o mesmo material do
visualizador, para que o que se vê aqui seja o que o usuário veria na tela.

As duas variantes de um caso são renderizadas com a MESMA câmera, escolhida pelo
maior dos dois volumes. Sem isso o menor pareceria maior por estar mais perto, e
a comparação de fidelidade viraria ilusão de ótica.

Uso:
    .venv-win/Scripts/python.exe tools/render_liver_mesh_gallery.py --limit 10
"""
from __future__ import annotations

import argparse
import json
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
    _isolar_orgao_para_visualizacao,
    _mesh_from_mask,
    _refine_mask,
)

VENOSA = REPO / "casos/qualification/lld_mmri_v23/prepared/external_segmentation_audit335_fullres_v1"
PRE = REPO / "experiments/precontrast_segmentation_v1"
SAIDA = REPO / "experiments/liver_mesh_gallery_v1"

MESH = dict(level=0.5, smooth_iter=30, feature_angle=60.0, pass_band=0.1,
            isotropic_mm=0.8, gaussian_sigma_mm=2.0, max_triangles=160000)
COR_ORGAO = "#C8A27D"      # mesma do profiles/figado.yaml
TAMANHO = (760, 760)


def malha_de(mask_array: np.ndarray, referencia: sitk.Image, temporario: Path):
    """Aplica o refino de produção e reconstrói como o pipeline reconstrói."""
    limpo = _refine_mask(mask_array, True, 2, 300).astype(bool)
    limpo, diagnostico = _isolar_orgao_para_visualizacao(limpo)
    if not limpo.any():
        return None, diagnostico
    imagem = sitk.GetImageFromArray(limpo.astype(np.uint8))
    imagem.CopyInformation(referencia)
    sitk.WriteImage(imagem, str(temporario))
    malha = _mesh_from_mask(
        temporario, MESH["level"], MESH["smooth_iter"], MESH["feature_angle"],
        pass_band=MESH["pass_band"], isotropic_mm=MESH["isotropic_mm"],
        gaussian_sigma_mm=MESH["gaussian_sigma_mm"], max_triangles=MESH["max_triangles"],
    )
    return malha, diagnostico


def renderiza(malha, destino: Path, camera_bounds, titulo: str) -> None:
    """Render com o material do visualizador e luz presa à câmera."""
    plotter = pv.Plotter(off_screen=True, window_size=TAMANHO)
    plotter.set_background("#0f1418")
    plotter.add_mesh(
        malha, color=COR_ORGAO, smooth_shading=True, pbr=True,
        metallic=0.03, roughness=0.42, diffuse=1.0, specular=0.25,
    )
    # Enquadramento comum: a caixa vem do maior dos dois volumes do caso.
    plotter.reset_camera(bounds=camera_bounds)
    plotter.camera.azimuth = 35
    plotter.camera.elevation = 18
    plotter.camera.zoom(1.15)
    plotter.enable_anti_aliasing("ssaa")
    plotter.add_text(titulo, position="upper_left", font_size=11, color="#dbe5ec")
    plotter.screenshot(str(destino))
    plotter.close()


def compoe(esquerda: Path, direita: Path, destino: Path, rodape: str) -> None:
    from PIL import Image, ImageDraw

    a, b = Image.open(esquerda), Image.open(direita)
    altura_rodape = 46
    tela = Image.new("RGB", (a.width + b.width + 6, a.height + altura_rodape), "#0f1418")
    tela.paste(a, (0, 0))
    tela.paste(b, (a.width + 6, 0))
    desenho = ImageDraw.Draw(tela)
    desenho.text((12, a.height + 14), rodape, fill="#9fb3c4")
    tela.save(destino)
    a.close(); b.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    resultados_path = PRE / "results.json"
    if not resultados_path.is_file():
        print(f"ERRO: rode antes o piloto de pré-contraste ({resultados_path})", file=sys.stderr)
        return 2
    resultados = json.loads(resultados_path.read_text("utf-8"))
    casos = [c for c, v in resultados.items() if "erro" not in v][: args.limit]
    if not casos:
        print("ERRO: nenhum caso válido no piloto.", file=sys.stderr)
        return 2

    SAIDA.mkdir(parents=True, exist_ok=True)
    temporario = SAIDA / "_tmp.nii.gz"
    entradas = REPO / "casos/qualification/lld_mmri_v23/prepared/external_inputs_v1/inputs"

    print(f"renderizando {len(casos)} casos\n")
    gerados = []
    for i, case_id in enumerate(casos, 1):
        mascara_venosa = VENOSA / case_id / "liver_mask_venous.nii.gz"
        mascara_pre = PRE / "masks" / f"{case_id}.nii.gz"
        if not (mascara_venosa.is_file() and mascara_pre.is_file()):
            continue
        img_ven = sitk.ReadImage(str(mascara_venosa))
        img_pre = sitk.ReadImage(str(entradas / case_id / "t1_native.nii.gz"))

        malha_ven, _ = malha_de(sitk.GetArrayFromImage(img_ven) > 0, img_ven, temporario)
        malha_pre, _ = malha_de(
            sitk.GetArrayFromImage(sitk.ReadImage(str(mascara_pre))) > 0, img_pre, temporario
        )
        if malha_ven is None or malha_pre is None:
            print(f"  {case_id}: malha vazia, pulado")
            continue

        # Câmera comum, derivada da união das caixas -- comparação honesta.
        caixas = np.array([malha_ven.bounds, malha_pre.bounds])
        comum = (
            min(caixas[:, 0]), max(caixas[:, 1]),
            min(caixas[:, 2]), max(caixas[:, 3]),
            min(caixas[:, 4]), max(caixas[:, 5]),
        )
        vol_ven = abs(malha_ven.volume) / 1000.0
        vol_pre = abs(malha_pre.volume) / 1000.0
        esquerda = SAIDA / f"{case_id}_venosa.png"
        direita = SAIDA / f"{case_id}_precontraste.png"
        renderiza(malha_ven, esquerda, comum, f"VENOSA (em producao)   {vol_ven:.0f} mL")
        renderiza(malha_pre, direita, comum, f"PRE-CONTRASTE          {vol_pre:.0f} mL")
        composto = SAIDA / f"comparacao_{i:02d}_{case_id[:16]}.png"
        compoe(esquerda, direita, composto,
               f"{case_id}   |   venosa {vol_ven:.0f} mL  ->  pre-contraste {vol_pre:.0f} mL"
               f"   ({vol_pre/vol_ven:.2f}x)   |   mesma camera nos dois")
        esquerda.unlink(missing_ok=True); direita.unlink(missing_ok=True)
        gerados.append(composto)
        print(f"  [{i}] {case_id}: {vol_ven:.0f} -> {vol_pre:.0f} mL  ({vol_pre/vol_ven:.2f}x)", flush=True)

    temporario.unlink(missing_ok=True)
    print(f"\n{len(gerados)} comparacoes em {SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

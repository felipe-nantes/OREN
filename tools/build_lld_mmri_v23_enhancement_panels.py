#!/usr/bin/env python3
"""Paineis de REALCE RELATIVO para o LLD-MMRI (Etapa 1 de docs/135).

Motivacao. Os paineis atuais fundem tres fases POS-contraste nos canais R/G/B.
Nesse espaco a pergunta clinica que separa as classes fracas -- "esta lesao
realca?" -- e' inrespondivel, porque realce e' pos MENOS pre e o pre-contraste
nunca entrou. Um cisto (que nao realca) e uma FNH (que virou isointensa) ficam
igualmente planos quando so' se comparam fases pos entre si.

O que este builder faz. Substitui o conteudo dos canais por realce relativo

    RE_fase = (fase - pre) / (pre + eps)

calculado voxel a voxel na grade venosa, onde as quatro fases dinamicas JA estao
harmonizadas (`external_dynamic_harmonized_v1`, referencia `t1_venous`).

Duas propriedades importantes de desenho:

1. RE e' uma RAZAO contra referencia interna a propria aquisicao. docs/131 mediu
   que features fisicas absolutas -- momentos, entropia, gradiente de figado
   inteiro -- deixam a coorte previsivel a 98,75%, porque carregam assinatura de
   scanner. Uma razao dentro da mesma imagem cancela o ganho do aparelho por
   construcao. Toda feature nova do plano obedece essa exigencia.

2. A janela de exibicao e' FIXA em unidades fisicas de realce, nao por
   percentil. Percentil por caso tornaria a cor incomparavel entre exames: o
   mesmo tom significaria realces diferentes. Com janela fixa, "vermelho forte"
   quer dizer a mesma coisa em todos os casos.

Ablacao controlada. Os cortes axiais NAO sao reselecionados: sao lidos dos
manifestos dos paineis existentes (`all_axial_indices_zyx_absolute` e os indices
por painel). Assim os paineis novos cobrem exatamente a mesma anatomia dos
antigos e a unica variavel que muda e' o conteudo dos canais. Isso tambem
dispensa re-rodar o TotalSegmentator, porque a selecao de cortes ja foi feita.

Nenhum rotulo, nenhuma mascara de lesao e nenhum ground truth e' lido.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_gradient_magnitude

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from dtwin.core import PipelineError, array_from, now_utc, read_image, sha256_of  # noqa: E402
from dtwin.medgemma_panel_multiphase import _render_color_tile  # noqa: E402

PANEL_SCHEMA = "argos-lld-mmri-v23-relative-enhancement-panel-manifest-v1"
BUILD_SCHEMA = "argos-lld-mmri-v23-relative-enhancement-build-v1"
ALGORITHM_VERSION = "relative-enhancement-confidence-weighted-v2"

# Realce relativo mapeado para [0,1] por uma janela FIXA, igual em todos os casos.
# -0,15 deixa margem para ruido negativo; 1,60 (160% de ganho sobre o pre) cobre
# realce arterial intenso sem saturar o parenquima normal, que fica em torno de
# 0,4-0,8 na fase venosa.
RE_WINDOW_LOW = -0.15
RE_WINDOW_HIGH = 1.60

# Voxels cujo pre-contraste esta no ruido nao permitem razao estavel: dividir por
# um denominador quase nulo explode. Sao marcados como sem-suporte e recebem o
# valor neutro de realce zero.
PRE_NOISE_PERCENTILE = 60.0
PRE_NOISE_FRACTION = 0.08

# Ponderacao de confianca (v2). As fases sao harmonizadas na grade mas SEM
# correcao de movimento, entao bordas de orgao viram aneis de realce falso na
# subtracao, e regioes de baixo sinal amplificam a razao. Duas atenuacoes, ambas
# derivadas da propria imagem (referencia interna, exigencia de docs/131):
#   - borda: cai onde o gradiente espacial do pre e' alto (onde a subtracao e'
#     dominada por desalinhamento, nao por realce real);
#   - tecido: cai onde o sinal venoso e' baixo (ruido/ar residual), preservando
#     parenquima e lesao, que tem sinal substancial.
# O produto das duas multiplica o realce antes da janela fixa.
EDGE_GRADIENT_SIGMA = 1.0
EDGE_GRADIENT_PERCENTILE = 80.0

CHANNEL_ROLES = (("red", "t1_arterial"), ("green", "t1_venous"), ("blue", "t1_delayed"))
NATIVE_ROLE = "t1_native"
TILE_SIZE = 320


def _load_axial_groups(panel_manifest_path: Path) -> tuple[tuple[int, ...], ...]:
    """Le os grupos de cortes do painel EXISTENTE, para ablacao controlada."""
    manifest = json.loads(panel_manifest_path.read_text(encoding="utf-8"))
    panels = manifest.get("panels")
    if not isinstance(panels, list) or not panels:
        raise PipelineError(f"Manifesto sem paineis: {panel_manifest_path}")
    groups: list[tuple[int, ...]] = []
    for panel in panels:
        indices = panel.get("axial_indices_zyx_absolute") or panel.get("axial_indices")
        if not isinstance(indices, list) or not indices:
            raise PipelineError(
                f"Painel sem indices axiais em {panel_manifest_path}: chaves={sorted(panel)}"
            )
        groups.append(tuple(int(v) for v in indices))
    return tuple(groups)


def _relative_enhancement(
    post: np.ndarray, pre: np.ndarray, support: np.ndarray
) -> np.ndarray:
    """(post - pre) / (pre + eps), zerado fora do suporte de pre-contraste."""
    eps = np.float32(1e-3)
    denominator = np.maximum(pre, eps)
    out = (post - pre) / denominator
    out[~support] = 0.0
    return out.astype(np.float32)


def build_case(
    *,
    case_id: str,
    harmonized_case_dir: Path,
    panel_manifest_path: Path,
    output_dir: Path,
    tissue_weighting: bool = True,
) -> dict[str, Any]:
    roles = [NATIVE_ROLE, *(role for _, role in CHANNEL_ROLES)]
    paths = {role: harmonized_case_dir / f"{role}.nii.gz" for role in roles}
    for role, path in paths.items():
        if not path.is_file():
            raise PipelineError(f"Fase harmonizada ausente: {role} em {harmonized_case_dir}")

    images = {role: read_image(path) for role, path in paths.items()}
    reference = images["t1_venous"]
    for role, image in images.items():
        if image.GetSize() != reference.GetSize() or image.GetDimension() != 3:
            raise PipelineError(f"Fase {role} nao esta na grade venosa de {case_id}.")
    arrays = {role: array_from(image).astype(np.float32) for role, image in images.items()}

    pre = arrays[NATIVE_ROLE]
    # Suporte: pre-contraste acima de uma fracao do seu proprio percentil alto.
    # E' uma referencia interna, nao um limiar absoluto de intensidade.
    positive = pre[pre > 0]
    if positive.size == 0:
        raise PipelineError(f"Pre-contraste vazio em {case_id}.")
    floor = float(np.percentile(positive, PRE_NOISE_PERCENTILE)) * PRE_NOISE_FRACTION
    support = pre > floor

    # Confianca (v2): atenua aneis de desalinhamento e ruido de baixo sinal.
    # O tissue_weight suprime realce onde o sinal venoso e' baixo -- mas cisto E'
    # conteudo fluido de sinal T1 baixo, entao esse peso APAGA a classe que a
    # hipotese queria destacar (docs/137). A flag edge_only o desliga para isolar
    # o efeito.
    eps = 1e-3
    gradient = gaussian_gradient_magnitude(pre, sigma=EDGE_GRADIENT_SIGMA)
    grad_ref = max(float(np.percentile(gradient[support], EDGE_GRADIENT_PERCENTILE)), eps)
    edge_weight = 1.0 / (1.0 + (gradient / grad_ref) ** 2)
    if tissue_weighting:
        venous = arrays["t1_venous"]
        tissue_ref = max(float(np.median(venous[support])), eps)
        tissue_weight = np.clip(venous / tissue_ref, 0.0, 1.0)
        confidence = (edge_weight * tissue_weight).astype(np.float32)
    else:
        confidence = edge_weight.astype(np.float32)
    confidence[~support] = 0.0

    enhancement = {
        channel: _relative_enhancement(arrays[role], pre, support) * confidence
        for channel, role in CHANNEL_ROLES
    }
    span = RE_WINDOW_HIGH - RE_WINDOW_LOW
    normalized = {
        channel: np.clip((values - RE_WINDOW_LOW) / span, 0.0, 1.0)
        for channel, values in enhancement.items()
    }

    groups = _load_axial_groups(panel_manifest_path)
    depth = arrays[NATIVE_ROLE].shape[0]
    flat = [z for group in groups for z in group]
    if any(z < 0 or z >= depth for z in flat):
        raise PipelineError(f"Indice axial fora do volume em {case_id}.")

    sx, sy, sz = (float(value) for value in reference.GetSpacing())
    coordinates = np.argwhere(support)
    _z, yc, xc = np.rint(coordinates.mean(axis=0)).astype(int)

    def fuse(selection) -> np.ndarray:
        return np.stack(
            [normalized["red"][selection], normalized["green"][selection],
             normalized["blue"][selection]],
            axis=-1,
        )

    def render(rgb: np.ndarray, label: str, row_spacing: float, col_spacing: float) -> Image.Image:
        return _render_color_tile(
            rgb, np.zeros(rgb.shape[:2], dtype=bool), label, TILE_SIZE,
            row_spacing, col_spacing, 1, (255, 255, 255), 1.0,
        )

    coronal = render(fuse(np.s_[:, yc, :]), "CORONAL (REALCE RELATIVO)", sz, sx)
    sagittal = render(fuse(np.s_[:, :, xc]), "SAGITAL (REALCE RELATIVO)", sz, sy)

    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(groups)
    panel_records: list[dict[str, Any]] = []
    panel_paths: list[Path] = []
    for panel_number, indices in enumerate(groups, start=1):
        canvas = Image.new("RGB", (TILE_SIZE * 4, TILE_SIZE * 3), (10, 14, 20))
        for tile_number, z in enumerate(indices, start=1):
            tile = render(
                fuse(np.s_[z]),
                f"AXIAL {tile_number}/{len(indices)} | PAINEL {panel_number}/{total} | Z={z}",
                sy, sx,
            )
            canvas.paste(
                tile,
                (((tile_number - 1) % 3) * TILE_SIZE, ((tile_number - 1) // 3) * TILE_SIZE),
            )
        canvas.paste(coronal, (3 * TILE_SIZE, 0))
        canvas.paste(sagittal, (3 * TILE_SIZE, TILE_SIZE))
        notice = Image.new("RGB", (TILE_SIZE, TILE_SIZE), (18, 24, 32))
        ImageDraw.Draw(notice).multiline_text(
            (14, 18),
            "MODO PESQUISA\n\nREALCE RELATIVO\n(pos - pre) / pre\n\n"
            f"PAINEL {panel_number}/{total}\nCORTES DO PAINEL\nORIGINAL (ABLACAO)\n\n"
            "R=arterial\nG=venosa\nB=tardia\n\n"
            f"JANELA FIXA\n[{RE_WINDOW_LOW:+.2f}, {RE_WINDOW_HIGH:+.2f}]\n\n"
            "SEM CONTORNO\nSEM CROP\nSEM ROTULO",
            fill=(150, 170, 190), spacing=4,
        )
        canvas.paste(notice, (3 * TILE_SIZE, 2 * TILE_SIZE))
        name = f"enhancement_panel_{panel_number:03d}_of_{total:03d}.png"
        destination = output_dir / name
        canvas.save(destination, format="PNG", optimize=True)
        panel_paths.append(destination)
        panel_records.append({
            "panel_number": panel_number,
            "panel_total": total,
            "image": name,
            "sha256": sha256_of(destination),
            "axial_indices_zyx_absolute": [int(z) for z in indices],
        })

    manifest = {
        "schema": PANEL_SCHEMA,
        "case_id": case_id,
        "organ": "liver",
        "modality": "MRI",
        "regulatory_mode": "RESEARCH",
        "input_type": "mri_relative_enhancement_rgb_fusion",
        "algorithm_version": ALGORITHM_VERSION,
        "reference_role": "t1_venous",
        "native_role": NATIVE_ROLE,
        "fusion_channel_map": {channel: role for channel, role in CHANNEL_ROLES},
        "enhancement_formula": "((post - pre) / max(pre, 1e-3)) * edge_weight * tissue_weight",
        "confidence_weighting": {
            "edge_weight": "1 / (1 + (|grad(pre)| / p80)^2)",
            "tissue_weight": "clip(venous / median(venous), 0, 1)",
            "edge_gradient_sigma": EDGE_GRADIENT_SIGMA,
            "edge_gradient_percentile": EDGE_GRADIENT_PERCENTILE,
        },
        "display_window": [RE_WINDOW_LOW, RE_WINDOW_HIGH],
        "display_window_is_fixed_across_cases": True,
        "pre_support_percentile": PRE_NOISE_PERCENTILE,
        "pre_support_fraction": PRE_NOISE_FRACTION,
        "axial_indices_source": "reused_from_existing_liver_enriched_panel_manifest",
        "axial_indices_zyx_absolute": [int(z) for z in flat],
        "panel_image_count": total,
        "panels": panel_records,
        "organ_mask_used": False,
        "organ_mask_rendered": False,
        "lesion_mask_used": False,
        "ground_truth_used": False,
        "crop_to_liver": False,
        "contour_rendered": False,
        "phi_metadata_removed": True,
        "created_at": now_utc(),
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    (output_dir / "enhancement_panel_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"case_id": case_id, "panel_count": total,
            "panel_paths": [str(p) for p in panel_paths]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--harmonized-root",
        default="casos/qualification/lld_mmri_v23/prepared/external_dynamic_harmonized_v1",
    )
    parser.add_argument(
        "--panels-root",
        default="casos/qualification/lld_mmri_v23/prepared/external_liver_enriched_full321_v3",
    )
    parser.add_argument(
        "--output-root",
        default="casos/qualification/lld_mmri_v23/prepared/external_relative_enhancement_v1",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--no-tissue-weight", action="store_true",
        help="diagnostico (docs/137): so' atenuacao de borda, sem suprimir baixo sinal",
    )
    args = parser.parse_args(argv)
    tissue_weighting = not args.no_tissue_weight

    harmonized_root = (_REPO / args.harmonized_root).resolve() / "cases"
    panels_root = (_REPO / args.panels_root).resolve()
    output_root = (_REPO / args.output_root).resolve()
    if output_root.exists():
        raise SystemExit(f"Saida ja existe, sobrescrita recusada: {output_root}")

    case_ids = sorted(
        d.name for d in panels_root.iterdir()
        if d.is_dir() and (harmonized_root / d.name).is_dir()
    )
    if args.limit:
        case_ids = case_ids[: args.limit]
    print(f"casos a construir: {len(case_ids)}", flush=True)

    staging = output_root.parent / f"._reenh_{uuid.uuid4().hex[:8]}"
    staging.mkdir(parents=True)
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    started = time.perf_counter()
    try:
        for index, case_id in enumerate(case_ids, start=1):
            try:
                row = build_case(
                    case_id=case_id,
                    harmonized_case_dir=harmonized_root / case_id,
                    panel_manifest_path=panels_root / case_id / "medgemma_liver_screening_manifest.json",
                    output_dir=staging / "cases" / case_id,
                    tissue_weighting=tissue_weighting,
                )
                rows.append(row)
            except Exception as exc:  # noqa: BLE001
                failures.append({"case_id": case_id, "error": f"{type(exc).__name__}: {exc}"})
            if index % 25 == 0 or index == len(case_ids):
                elapsed = time.perf_counter() - started
                print(f"  {index}/{len(case_ids)}  {elapsed/60:.1f}min  falhas={len(failures)}",
                      flush=True)
        summary = {
            "schema": BUILD_SCHEMA,
            "algorithm_version": ALGORITHM_VERSION,
            "case_count": len(rows),
            "failure_count": len(failures),
            "display_window": [RE_WINDOW_LOW, RE_WINDOW_HIGH],
            "axial_indices_source": "reused_from_existing_liver_enriched_panel_manifest",
            "elapsed_seconds": time.perf_counter() - started,
            "ground_truth_read": False,
            "labels_read": False,
            "lesion_masks_read": 0,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        (staging / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        with (staging / "cases.jsonl").open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        with (staging / "failures.jsonl").open("w", encoding="utf-8") as fh:
            for row in failures:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        staging.replace(output_root)
    except BaseException:
        raise
    print(f"\nconstruidos: {len(rows)}  falhas: {len(failures)}")
    print(f"salvo em {output_root}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())

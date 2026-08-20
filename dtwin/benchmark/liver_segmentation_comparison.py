"""Reference-based, offline comparison of liver segmentation masks.

The module never runs a segmenter and never writes into a case directory. It
only evaluates already frozen predictions and builds an audit gallery after
prediction, keeping ground truth out of every inference process.
"""
from __future__ import annotations

import html
import json
import math
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk
import yaml
from PIL import Image, ImageDraw
from scipy import ndimage

from dtwin.core import PipelineError, now_utc, sha256_of
from dtwin.segmentation_contract import image_geometry, same_geometry

CONFIG_SCHEMA = "argos-liver-segmentation-benchmark-config-v2"
RESULT_SCHEMA = "argos-liver-segmentation-comparison-v2"
CASE_SCHEMA = "argos-liver-segmentation-case-comparison-v2"


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    display_name: str
    color: str
    required: bool
    mask_template: str
    label_value: int | None


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_binary(
    path: Path, reference: sitk.Image, *, label_value: int | None = None
) -> tuple[np.ndarray, bool, str]:
    try:
        image = sitk.ReadImage(str(path))
    except Exception as exc:
        raise PipelineError(f"Falha ao ler mascara {path.name}: {exc}") from exc
    if label_value is not None:
        image = sitk.Cast(image == int(label_value), sitk.sitkUInt8)
    else:
        image = sitk.Cast(image > 0, sitk.sitkUInt8)
    resampled = not same_geometry(image, reference)
    if resampled:
        image = sitk.Resample(
            image,
            reference,
            sitk.Transform(),
            sitk.sitkNearestNeighbor,
            0,
            sitk.sitkUInt8,
        )
    values = sitk.GetArrayFromImage(image)
    if not np.isfinite(values).all():
        raise PipelineError(f"Mascara {path.name} contem valor nao finito.")
    binary = values > 0
    if not binary.any():
        raise PipelineError(f"Mascara {path.name} esta vazia.")
    return binary, resampled, sha256_of(path)


def _surface_distances(
    prediction: np.ndarray, reference: np.ndarray, spacing_xyz: tuple[float, float, float]
) -> tuple[float, float]:
    structure = ndimage.generate_binary_structure(3, 1)
    pred_surface = prediction ^ ndimage.binary_erosion(prediction, structure=structure)
    ref_surface = reference ^ ndimage.binary_erosion(reference, structure=structure)
    if not pred_surface.any() or not ref_surface.any():
        return math.inf, math.inf
    sampling_zyx = tuple(float(value) for value in spacing_xyz[::-1])
    to_reference = ndimage.distance_transform_edt(~ref_surface, sampling=sampling_zyx)
    to_prediction = ndimage.distance_transform_edt(~pred_surface, sampling=sampling_zyx)
    pred_to_ref = to_reference[pred_surface]
    ref_to_pred = to_prediction[ref_surface]
    hd95 = max(float(np.percentile(pred_to_ref, 95)), float(np.percentile(ref_to_pred, 95)))
    assd = float((pred_to_ref.sum() + ref_to_pred.sum()) / (pred_to_ref.size + ref_to_pred.size))
    return hd95, assd


def segmentation_metrics(
    prediction: np.ndarray,
    reference: np.ndarray,
    spacing_xyz: tuple[float, float, float],
) -> dict[str, Any]:
    prediction = np.asarray(prediction, dtype=bool)
    reference = np.asarray(reference, dtype=bool)
    if prediction.shape != reference.shape or prediction.ndim != 3:
        raise PipelineError("Metricas exigem mascaras 3-D na mesma grade.")
    pred_count = int(prediction.sum())
    ref_count = int(reference.sum())
    if pred_count == 0 or ref_count == 0:
        raise PipelineError("Metricas exigem mascaras nao vazias.")
    intersection = int(np.logical_and(prediction, reference).sum())
    union = int(np.logical_or(prediction, reference).sum())
    false_positive = int(np.logical_and(prediction, ~reference).sum())
    false_negative = int(np.logical_and(~prediction, reference).sum())
    labels, components = ndimage.label(prediction)
    sizes = np.bincount(labels.ravel())[1:]
    largest_fraction = float(sizes.max() / sizes.sum()) if sizes.size else 0.0
    hd95, assd = _surface_distances(prediction, reference, spacing_xyz)
    voxel_ml = float(np.prod(np.asarray(spacing_xyz, dtype=np.float64)) / 1000.0)
    return {
        "dice": 2.0 * intersection / (pred_count + ref_count),
        "jaccard": intersection / union,
        "precision": intersection / pred_count,
        "recall": intersection / ref_count,
        "false_positive_voxels": false_positive,
        "false_negative_voxels": false_negative,
        "prediction_volume_ml": pred_count * voxel_ml,
        "reference_volume_ml": ref_count * voxel_ml,
        "volume_ratio": pred_count / ref_count,
        "absolute_volume_error_percent": abs(pred_count - ref_count) * 100.0 / ref_count,
        "hd95_mm": hd95,
        "assd_mm": assd,
        "component_count": int(components),
        "largest_component_fraction": largest_fraction,
    }


def _model_specs(raw: Any) -> tuple[ModelSpec, ...]:
    if not isinstance(raw, list) or not raw:
        raise PipelineError("Benchmark de segmentacao exige ao menos um modelo.")
    specs: list[ModelSpec] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise PipelineError("Modelo do benchmark invalido.")
        model_id = str(item.get("id") or "").strip()
        template = str(item.get("mask_template") or "").strip()
        if not model_id or model_id in seen or "{case_id}" not in template:
            raise PipelineError("ID duplicado ou template de mascara invalido.")
        seen.add(model_id)
        specs.append(
            ModelSpec(
                model_id=model_id,
                display_name=str(item.get("display_name") or model_id),
                color=str(item.get("color") or "#FFFFFF"),
                required=bool(item.get("required", False)),
                mask_template=template,
                label_value=(
                    int(item["label_value"])
                    if item.get("label_value") is not None
                    else None
                ),
            )
        )
        if specs[-1].label_value is not None and specs[-1].label_value < 1:
            raise PipelineError("Valor de rotulo do modelo deve ser positivo.")
    return tuple(specs)


def _resolve_inside_repo(repo: Path, value: str) -> Path:
    candidate = (repo / value).resolve()
    try:
        candidate.relative_to(repo)
    except ValueError as exc:
        raise PipelineError("Config do benchmark aponta para fora do repositorio.") from exc
    return candidate


def load_config(config_path: Path | str, repo: Path | str) -> dict[str, Any]:
    repo_path = Path(repo).resolve()
    try:
        config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PipelineError(f"Config de benchmark invalida: {exc}") from exc
    if not isinstance(config, dict) or config.get("schema") != CONFIG_SCHEMA:
        raise PipelineError("Schema do benchmark de segmentacao incompativel.")
    if config.get("research_only") is not True:
        raise PipelineError("Benchmark de segmentacao deve ser research_only.")
    cohort = config.get("cohort")
    output = config.get("output")
    if not isinstance(cohort, dict) or not isinstance(output, dict):
        raise PipelineError("Config de coorte/saida incompleta.")
    if cohort.get("ground_truth_used_only_after_prediction") is not True:
        raise PipelineError("Ground truth deve permanecer fora da inferencia.")
    return {
        "raw": config,
        "repo": repo_path,
        "cohort_root": _resolve_inside_repo(repo_path, str(cohort.get("root") or "")),
        "source_name": str(cohort.get("source_name") or ""),
        "reference_name": str(cohort.get("reference_name") or ""),
        "cohort_id": str(cohort.get("id") or ""),
        "models": _model_specs(config.get("models")),
        "output_root": _resolve_inside_repo(repo_path, str(output.get("root") or "")),
        "generate_gallery": bool(output.get("generate_gallery", True)),
    }


def _round_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        key: (round(float(value), 6) if isinstance(value, (float, np.floating)) else value)
        for key, value in metrics.items()
    }


def _summary(rows: list[dict[str, Any]], specs: tuple[ModelSpec, ...]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for spec in specs:
        values = [row["models"][spec.model_id] for row in rows if row["models"].get(spec.model_id, {}).get("status") == "evaluated"]
        if not values:
            output[spec.model_id] = {"evaluated_cases": 0}
            continue
        metrics = [item["metrics"] for item in values]
        output[spec.model_id] = {
            "display_name": spec.display_name,
            "evaluated_cases": len(metrics),
            "missing_cases": len(rows) - len(metrics),
            "median_dice": round(float(np.median([item["dice"] for item in metrics])), 6),
            "minimum_dice": round(float(np.min([item["dice"] for item in metrics])), 6),
            "median_recall": round(float(np.median([item["recall"] for item in metrics])), 6),
            "median_precision": round(float(np.median([item["precision"] for item in metrics])), 6),
            "median_volume_ratio": round(float(np.median([item["volume_ratio"] for item in metrics])), 6),
            "median_hd95_mm": round(float(np.median([item["hd95_mm"] for item in metrics])), 6),
            "median_assd_mm": round(float(np.median([item["assd_mm"] for item in metrics])), 6),
        }
    return output


def evaluate(config_path: Path | str, *, repo: Path | str) -> dict[str, Any]:
    config = load_config(config_path, repo)
    cohort_root: Path = config["cohort_root"]
    output_root: Path = config["output_root"]
    if not cohort_root.is_dir():
        raise PipelineError(f"Coorte ausente: {cohort_root}")
    if output_root.exists():
        raise PipelineError("Saida do benchmark ja existe; sobrescrita recusada.")
    cases = sorted(path for path in cohort_root.iterdir() if path.is_dir())
    if not cases:
        raise PipelineError("Coorte de segmentacao vazia.")
    output_root.mkdir(parents=True)
    rows: list[dict[str, Any]] = []
    for case in cases:
        source_path = case / config["source_name"]
        reference_path = case / config["reference_name"]
        if not source_path.is_file() or not reference_path.is_file():
            raise PipelineError(f"Caso incompleto: {case.name}")
        source_image = sitk.ReadImage(str(source_path))
        reference_image = sitk.ReadImage(str(reference_path))
        reference, _, reference_sha = _load_binary(reference_path, source_image)
        row: dict[str, Any] = {
            "schema": CASE_SCHEMA,
            "case_id": case.name,
            "source_sha256": sha256_of(source_path),
            "reference_sha256": reference_sha,
            "source_geometry": image_geometry(source_image),
            "ground_truth_read_after_prediction": True,
            "models": {},
        }
        for spec in config["models"]:
            mask_path = _resolve_inside_repo(
                config["repo"], spec.mask_template.format(case_id=case.name)
            )
            if not mask_path.is_file():
                if spec.required:
                    raise PipelineError(
                        f"Mascara obrigatoria {spec.model_id} ausente no caso {case.name}."
                    )
                row["models"][spec.model_id] = {"status": "not_available"}
                continue
            prediction, resampled, mask_sha = _load_binary(
                mask_path, source_image, label_value=spec.label_value
            )
            row["models"][spec.model_id] = {
                "status": "evaluated",
                "mask_sha256": mask_sha,
                "resampled_to_source_grid": resampled,
                "metrics": _round_metrics(
                    segmentation_metrics(prediction, reference, source_image.GetSpacing())
                ),
            }
        rows.append(row)
    cases_path = output_root / "cases.jsonl"
    cases_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    result = {
        "schema": RESULT_SCHEMA,
        "created_utc": now_utc(),
        "cohort_id": config["cohort_id"],
        "case_count": len(rows),
        "ground_truth_read": True,
        "ground_truth_used_during_inference": False,
        "inference_executed_by_this_tool": False,
        "models": _summary(rows, config["models"]),
        "cases_sha256": sha256_of(cases_path),
    }
    _atomic_json(output_root / "evaluation.json", result)
    if config["generate_gallery"]:
        build_gallery(config, rows)
        result["gallery"] = "gallery/index.html"
        _atomic_json(output_root / "evaluation.json", result)
    return result


def _normalize_plane(plane: np.ndarray) -> np.ndarray:
    values = np.asarray(plane, dtype=np.float32)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.zeros(values.shape, dtype=np.uint8)
    low, high = np.percentile(finite, [1.0, 99.0])
    if high <= low:
        high = low + 1.0
    return np.clip((values - low) * (255.0 / (high - low)), 0, 255).astype(np.uint8)


def _plane(array: np.ndarray, orientation: str, index: int) -> np.ndarray:
    if orientation == "axial":
        return array[index, :, :]
    if orientation == "coronal":
        return array[:, index, :]
    if orientation == "sagittal":
        return array[:, :, index]
    raise AssertionError(orientation)


def _contour(mask: np.ndarray) -> np.ndarray:
    return mask ^ ndimage.binary_erosion(mask, structure=np.ones((3, 3), dtype=bool))


def _render_cell(
    base: np.ndarray,
    overlays: list[tuple[np.ndarray, str]],
    title: str,
    *,
    pixel_spacing_rc: tuple[float, float],
) -> Image.Image:
    gray = _normalize_plane(base)
    rgb = np.repeat(gray[:, :, None], 3, axis=2)
    for mask, color in overlays:
        edge = _contour(np.asarray(mask, dtype=bool))
        value = tuple(int(color[index : index + 2], 16) for index in (1, 3, 5))
        rgb[edge] = value
    image = Image.fromarray(rgb, mode="RGB")
    physical_width = float(image.width) * float(pixel_spacing_rc[1])
    physical_height = float(image.height) * float(pixel_spacing_rc[0])
    scale = min(300.0 / physical_width, 260.0 / physical_height)
    display_size = (
        max(1, int(round(physical_width * scale))),
        max(1, int(round(physical_height * scale))),
    )
    image = image.resize(display_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (320, 300), "#0D1520")
    canvas.paste(image, ((320 - image.width) // 2, 32 + (260 - image.height) // 2))
    ImageDraw.Draw(canvas).text((8, 8), title, fill="white")
    return canvas


def _case_gallery_image(
    *,
    source: np.ndarray,
    reference: np.ndarray,
    masks: dict[str, np.ndarray],
    specs: tuple[ModelSpec, ...],
    spacing_xyz: tuple[float, float, float],
) -> Image.Image:
    coords = np.argwhere(reference)
    center = np.rint(coords.mean(axis=0)).astype(int)
    sx, sy, sz = (float(value) for value in spacing_xyz)
    orientations = (
        ("axial", int(center[0]), (sy, sx)),
        ("coronal", int(center[1]), (sz, sx)),
        ("sagittal", int(center[2]), (sz, sy)),
    )
    available = [spec for spec in specs if spec.model_id in masks]
    columns = 2 + len(available)
    output = Image.new("RGB", (columns * 320, 3 * 300), "#111827")
    for row, (orientation, index, pixel_spacing) in enumerate(orientations):
        base = _plane(source, orientation, index)
        ref_plane = _plane(reference, orientation, index)
        cells = [
            _render_cell(
                base, [], f"{orientation.upper()} | RM", pixel_spacing_rc=pixel_spacing
            ),
            _render_cell(
                base,
                [(ref_plane, "#FFD400")],
                "Referencia humana",
                pixel_spacing_rc=pixel_spacing,
            ),
        ]
        for spec in available:
            prediction = _plane(masks[spec.model_id], orientation, index)
            cells.append(
                _render_cell(
                    base,
                    [(ref_plane, "#FFD400"), (prediction, spec.color)],
                    spec.display_name,
                    pixel_spacing_rc=pixel_spacing,
                )
            )
        for column, cell in enumerate(cells):
            output.paste(cell, (column * 320, row * 300))
    return output


def build_gallery(config: dict[str, Any], rows: list[dict[str, Any]]) -> Path:
    output_root: Path = config["output_root"]
    gallery = output_root / "gallery"
    images_dir = gallery / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    cards: list[str] = []
    row_by_case = {row["case_id"]: row for row in rows}
    for case in sorted(path for path in config["cohort_root"].iterdir() if path.is_dir()):
        source_image = sitk.ReadImage(str(case / config["source_name"]))
        source = sitk.GetArrayFromImage(source_image)
        reference, _, _ = _load_binary(case / config["reference_name"], source_image)
        masks: dict[str, np.ndarray] = {}
        metric_lines: list[str] = []
        for spec in config["models"]:
            item = row_by_case[case.name]["models"].get(spec.model_id, {})
            if item.get("status") != "evaluated":
                continue
            path = _resolve_inside_repo(
                config["repo"], spec.mask_template.format(case_id=case.name)
            )
            masks[spec.model_id], _, _ = _load_binary(
                path, source_image, label_value=spec.label_value
            )
            metrics = item["metrics"]
            metric_lines.append(
                f"<li><b>{html.escape(spec.display_name)}</b>: Dice {metrics['dice']:.3f}, "
                f"recall {metrics['recall']:.3f}, volume {metrics['volume_ratio']:.3f}x</li>"
            )
        image = _case_gallery_image(
            source=source,
            reference=reference,
            masks=masks,
            specs=config["models"],
            spacing_xyz=source_image.GetSpacing(),
        )
        image_name = f"{case.name}.png"
        image.save(images_dir / image_name, optimize=True)
        cards.append(
            f"<section><h2>{html.escape(case.name)}</h2><img src='images/{image_name}' "
            f"alt='Comparacao {html.escape(case.name)}'><ul>{''.join(metric_lines)}</ul></section>"
        )
    page = """<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>
<title>ARGOS — comparação de segmentação hepática</title><style>
body{margin:0;background:#0b1120;color:#e5e7eb;font:15px system-ui;padding:24px}
h1{margin-top:0}section{background:#182235;border:1px solid #334155;border-radius:12px;padding:16px;margin:18px 0}
img{width:100%;height:auto;background:#111827;border-radius:8px}li{margin:5px 0}
.legend span{margin-right:20px}.yellow{color:#FFD400}.cyan{color:#00D8FF}.pink{color:#FF3FD2}
</style></head><body><h1>ARGOS — benchmark isolado de segmentação</h1>
<p>Referência humana em <span class='yellow'>amarelo</span>; TotalSegmentator em
<span class='cyan'>ciano</span>; MRSegmentator em <span class='pink'>magenta</span>.
Ground truth foi aberto somente após as predições já existirem.</p>""" + "".join(cards) + "</body></html>"
    (gallery / "index.html").write_text(page, encoding="utf-8")
    return gallery / "index.html"


__all__ = [
    "CONFIG_SCHEMA",
    "RESULT_SCHEMA",
    "CASE_SCHEMA",
    "ModelSpec",
    "load_config",
    "segmentation_metrics",
    "evaluate",
    "build_gallery",
]

"""Build a label-blind, technically ranked DICOM MRI showcase.

The tool compares local MR studies without reading diagnosis, benchmark labels or
lesion masks.  It combines DICOM geometry with pixel-level display metrics,
selects technically strong but acquisition-diverse studies, and materializes the
result with NTFS hardlinks when possible.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pydicom
from PIL import Image, ImageDraw, ImageFont

from dtwin.benchmark.dataset_audit import select_monophase_evidence_series


SCHEMA = "argos-dicom-quality-showcase-v1"
EXCLUDED_NAME_TOKENS = ("mask", "seg", "label", "lesion", "tumor", "ground_truth")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_pixels(path: Path) -> np.ndarray:
    dataset = pydicom.dcmread(str(path), force=True)
    array = np.asarray(dataset.pixel_array, dtype=np.float32)
    if array.ndim > 2:
        array = np.asarray(array[array.shape[0] // 2], dtype=np.float32)
    slope = float(getattr(dataset, "RescaleSlope", 1.0) or 1.0)
    intercept = float(getattr(dataset, "RescaleIntercept", 0.0) or 0.0)
    return array * slope + intercept


def _normalize(array: np.ndarray) -> np.ndarray:
    finite = array[np.isfinite(array)]
    if finite.size < 16:
        raise ValueError("insufficient finite pixels")
    low, high = (float(value) for value in np.percentile(finite, [1.0, 99.0]))
    if not high > low:
        raise ValueError("constant image")
    return np.clip((array - low) / (high - low), 0.0, 1.0)


def _entropy(normalized: np.ndarray) -> float:
    histogram, _ = np.histogram(normalized[np.isfinite(normalized)], bins=64, range=(0, 1))
    probabilities = histogram[histogram > 0] / max(int(histogram.sum()), 1)
    return float(-(probabilities * np.log2(probabilities)).sum())


def _pixel_metrics(files: list[Path], sample_count: int = 7) -> tuple[dict[str, float], list[np.ndarray]]:
    if not files:
        raise ValueError("empty series")
    indices = sorted(set(int(value) for value in np.linspace(0, len(files) - 1, min(sample_count, len(files)))))
    normalized_images: list[np.ndarray] = []
    sharpness: list[float] = []
    entropies: list[float] = []
    foreground: list[float] = []
    clipping: list[float] = []
    for index in indices:
        normalized = _normalize(_read_pixels(files[index]))
        normalized_images.append(normalized)
        height, width = normalized.shape[-2:]
        crop = normalized[max(0, height // 20): max(1, height - height // 20), max(0, width // 20): max(1, width - width // 20)]
        gx = np.diff(crop, axis=1)
        gy = np.diff(crop, axis=0)
        sharpness.append(float((np.mean(np.abs(gx)) + np.mean(np.abs(gy))) / 2.0))
        entropies.append(_entropy(crop))
        foreground.append(float(np.mean(crop > 0.06)))
        clipping.append(float(np.mean((crop <= 0.001) | (crop >= 0.999))))
    correlations: list[float] = []
    for left, right in zip(normalized_images, normalized_images[1:]):
        if left.shape != right.shape:
            continue
        a = left.ravel()[::16]
        b = right.ravel()[::16]
        if float(np.std(a)) > 1e-6 and float(np.std(b)) > 1e-6:
            correlations.append(float(np.corrcoef(a, b)[0, 1]))
    return {
        "sample_count": float(len(normalized_images)),
        "sharpness": float(np.median(sharpness)),
        "entropy_bits": float(np.median(entropies)),
        "foreground_fraction": float(np.median(foreground)),
        "clipping_fraction": float(np.median(clipping)),
        "inter_slice_consistency": float(np.median(correlations)) if correlations else 0.0,
    }, normalized_images


def _technical_header(path: Path) -> dict[str, Any]:
    dataset = pydicom.dcmread(
        str(path),
        stop_before_pixels=True,
        force=True,
        specific_tags=["Manufacturer", "MagneticFieldStrength", "Modality"],
    )
    manufacturer = str(getattr(dataset, "Manufacturer", "unknown")).strip().upper()
    if "SIEMENS" in manufacturer:
        manufacturer = "SIEMENS"
    elif "GE" in manufacturer:
        manufacturer = "GE"
    elif "PHILIPS" in manufacturer:
        manufacturer = "PHILIPS"
    else:
        manufacturer = "OTHER_OR_UNKNOWN"
    try:
        field_strength = round(float(getattr(dataset, "MagneticFieldStrength")), 1)
    except (TypeError, ValueError, AttributeError):
        field_strength = None
    return {"manufacturer": manufacturer, "field_strength_t": field_strength}


def _find_cases(roots: Iterable[Path]) -> list[Path]:
    discovered: dict[str, Path] = {}
    for root in roots:
        if root.name.upper().startswith("TCGA-"):
            discovered[root.name] = root
            continue
        for path in root.rglob("TCGA-*"):
            if path.is_dir():
                discovered.setdefault(path.name, path)
    return [discovered[key] for key in sorted(discovered)]


def _safe_series_files(paths: Iterable[str]) -> list[Path]:
    safe: list[Path] = []
    for value in paths:
        path = Path(value)
        lowered = " ".join(part.lower() for part in path.parts)
        if not any(token in lowered for token in EXCLUDED_NAME_TOKENS):
            safe.append(path)
    return sorted(safe)


def _case_record(case_dir: Path) -> tuple[dict[str, Any], list[np.ndarray]]:
    paths_by_sequence, selection = select_monophase_evidence_series(case_dir, min_slices=16)
    if not selection or not paths_by_sequence:
        raise RuntimeError("no eligible MR series")
    primary = str(selection["primary_sequence_class"])
    files = _safe_series_files(paths_by_sequence[primary])
    if not files:
        raise RuntimeError("primary series removed by safety filter")
    pixels, preview = _pixel_metrics(files)
    payload = selection["selected_by_sequence"][primary]
    spacing = payload.get("pixel_spacing_mm") or [None, None]
    spacing_values = [float(value) for value in spacing if value is not None]
    in_plane = float(max(spacing_values)) if spacing_values else None
    rows = int(payload.get("rows") or 0)
    columns = int(payload.get("columns") or 0)
    frames = int(payload.get("frame_count") or 0)
    header = _technical_header(files[0])
    source_bytes = sum(path.stat().st_size for path in case_dir.rglob("*") if path.is_file())
    return {
        "case_id": case_dir.name,
        "source_path": str(case_dir),
        "source_file_count": sum(1 for path in case_dir.rglob("*") if path.is_file()),
        "source_bytes": source_bytes,
        "primary_sequence_class": primary,
        "available_sequence_classes": sorted(paths_by_sequence),
        "dynamic_phase_count": int(selection.get("dynamic_phase_count", 0)),
        "eligible_series_count": int(selection.get("selected_series_count", 0)),
        "matrix": [rows, columns],
        "pixel_spacing_mm": spacing,
        "slice_thickness_mm": payload.get("slice_thickness_mm"),
        "frame_count": frames,
        "metadata_quality_score": int(payload.get("quality_score", 0)),
        "pixel_metrics": pixels,
        **header,
    }, preview


def _percentile_rank(values: list[float], value: float, *, higher_is_better: bool = True) -> float:
    ordered = np.asarray(values, dtype=np.float64)
    if ordered.size <= 1 or float(np.max(ordered) - np.min(ordered)) < 1e-12:
        return 1.0
    rank = float(np.mean(ordered <= value))
    return rank if higher_is_better else 1.0 - float(np.mean(ordered < value))


def _score(records: list[dict[str, Any]]) -> None:
    sharpness = [row["pixel_metrics"]["sharpness"] for row in records]
    entropy = [row["pixel_metrics"]["entropy_bits"] for row in records]
    consistency = [row["pixel_metrics"]["inter_slice_consistency"] for row in records]
    clipping = [row["pixel_metrics"]["clipping_fraction"] for row in records]
    for row in records:
        spacing = row["pixel_spacing_mm"]
        valid_spacing = [float(value) for value in spacing if value is not None]
        in_plane = max(valid_spacing) if valid_spacing else 2.5
        matrix_score = min(1.0, math.sqrt(max(row["matrix"][0] * row["matrix"][1], 1)) / 512.0)
        spatial_score = max(0.0, min(1.0, (1.8 - in_plane) / 1.1))
        coverage_score = min(1.0, row["frame_count"] / 60.0)
        breadth_score = min(1.0, row["eligible_series_count"] / 5.0)
        pixels = row["pixel_metrics"]
        components = {
            "metadata_geometry": min(1.0, row["metadata_quality_score"] / 100.0),
            "spatial_resolution": 0.6 * spatial_score + 0.4 * matrix_score,
            "slice_coverage": coverage_score,
            "sequence_breadth": breadth_score,
            "sharpness_rank": _percentile_rank(sharpness, pixels["sharpness"]),
            "entropy_rank": _percentile_rank(entropy, pixels["entropy_bits"]),
            "consistency_rank": _percentile_rank(consistency, pixels["inter_slice_consistency"]),
            "low_clipping_rank": _percentile_rank(clipping, pixels["clipping_fraction"], higher_is_better=False),
        }
        score = (
            0.16 * components["metadata_geometry"]
            + 0.18 * components["spatial_resolution"]
            + 0.14 * components["slice_coverage"]
            + 0.12 * components["sequence_breadth"]
            + 0.16 * components["sharpness_rank"]
            + 0.10 * components["entropy_rank"]
            + 0.09 * components["consistency_rank"]
            + 0.05 * components["low_clipping_rank"]
        )
        row["quality_components"] = {key: round(value, 6) for key, value in components.items()}
        row["technical_quality_score"] = round(100.0 * score, 2)


def _select_diverse(records: list[dict[str, Any]], reference: str, count: int) -> list[dict[str, Any]]:
    by_id = {row["case_id"]: row for row in records}
    if reference not in by_id:
        raise RuntimeError(f"reference case not found: {reference}")
    reference_row = by_id[reference]
    threshold = max(65.0, reference_row["technical_quality_score"] - 12.0)
    candidates = [row for row in records if row["technical_quality_score"] >= threshold]
    if len(candidates) < min(count, len(records)):
        candidates = sorted(records, key=lambda row: (-row["technical_quality_score"], row["case_id"]))[: max(count, len(candidates))]
    selected = [reference_row]
    remaining = [row for row in candidates if row["case_id"] != reference]
    while remaining and len(selected) < count:
        def utility(row: dict[str, Any]) -> tuple[float, float, str]:
            diversity = 0.0
            if all(row["manufacturer"] != item["manufacturer"] for item in selected):
                diversity += 7.0
            if all(row["field_strength_t"] != item["field_strength_t"] for item in selected):
                diversity += 4.0
            if all(row["primary_sequence_class"] != item["primary_sequence_class"] for item in selected):
                diversity += 3.0
            prefix = "-".join(row["case_id"].split("-")[:2])
            if all(prefix != "-".join(item["case_id"].split("-")[:2]) for item in selected):
                diversity += 3.0
            return row["technical_quality_score"] + diversity, row["technical_quality_score"], row["case_id"]
        chosen = max(remaining, key=utility)
        selected.append(chosen)
        remaining.remove(chosen)
    return selected


def _preview_image(images: list[np.ndarray], title: str, score: float) -> Image.Image:
    chosen = images[:6]
    tile_size = 320
    canvas = Image.new("RGB", (tile_size * 3, tile_size * 2 + 52), "#101722")
    draw = ImageDraw.Draw(canvas)
    draw.text((14, 14), f"{title}  |  qualidade tecnica {score:.2f}/100", fill="white", font=ImageFont.load_default())
    for index, array in enumerate(chosen):
        image = Image.fromarray(np.uint8(np.clip(array, 0, 1) * 255), mode="L").convert("RGB")
        image.thumbnail((tile_size - 8, tile_size - 8), Image.Resampling.LANCZOS)
        x = (index % 3) * tile_size + (tile_size - image.width) // 2
        y = 52 + (index // 3) * tile_size + (tile_size - image.height) // 2
        canvas.paste(image, (x, y))
    return canvas


def _link_case(source: Path, destination: Path) -> tuple[int, int, int]:
    linked = copied = bytes_total = 0
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        lowered = " ".join(part.lower() for part in path.parts)
        if any(token in lowered for token in EXCLUDED_NAME_TOKENS):
            continue
        try:
            header = pydicom.dcmread(str(path), stop_before_pixels=True, force=True, specific_tags=["Modality"])
        except Exception:
            continue
        if str(getattr(header, "Modality", "")).upper() != "MR":
            continue
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(path, target)
            linked += 1
        except OSError:
            shutil.copy2(path, target)
            copied += 1
        bytes_total += path.stat().st_size
    return linked, copied, bytes_total


def _write_gallery(output: Path, selected: list[dict[str, Any]], previews: dict[str, list[np.ndarray]]) -> None:
    gallery = output / "galeria"
    gallery.mkdir(parents=True, exist_ok=True)
    cards: list[str] = []
    for index, row in enumerate(selected, 1):
        filename = f"{index:02d}_{row['case_id']}.png"
        _preview_image(previews[row["case_id"]], row["case_id"], row["technical_quality_score"]).save(gallery / filename)
        cards.append(
            f"<article><h2>{index}. {html.escape(row['case_id'])}</h2><img src='{html.escape(filename)}' "
            f"alt='{html.escape(row['case_id'])}'><p>Score {row['technical_quality_score']:.2f} · "
            f"{html.escape(row['manufacturer'])} · {html.escape(str(row['field_strength_t']))} T · "
            f"{html.escape(row['primary_sequence_class'])}</p></article>"
        )
    document = """<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><title>Mostruário DICOM ARGOS</title>
<style>body{margin:0;background:#0b111b;color:#edf2f7;font:16px system-ui;padding:28px}main{max-width:1200px;margin:auto}article{background:#182231;border:1px solid #334155;border-radius:12px;padding:18px;margin:22px 0}img{width:100%;height:auto;border-radius:6px}p{color:#b8c4d6}</style></head><body><main><h1>Mostruário DICOM de alta qualidade técnica</h1><p>Seleção label-blind. A pontuação mede apresentação técnica e não qualidade diagnóstica.</p>""" + "".join(cards) + "</main></body></html>"
    (gallery / "index.html").write_text(document, encoding="utf-8")


def build(
    roots: list[Path],
    output: Path,
    reference: str,
    count: int,
    requested_case_ids: list[str] | None = None,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    cases = _find_cases(roots)
    if not cases:
        raise RuntimeError("no TCGA cases found")
    records: list[dict[str, Any]] = []
    previews: dict[str, list[np.ndarray]] = {}
    rejected: list[dict[str, str]] = []
    for case in cases:
        try:
            record, preview = _case_record(case)
        except Exception as exc:  # noqa: BLE001 - recorded without PHI/UIDs
            rejected.append({"case_id": case.name, "reason": f"technical_audit_failure:{type(exc).__name__}"})
            continue
        records.append(record)
        previews[case.name] = preview
    _score(records)
    if requested_case_ids:
        requested = list(dict.fromkeys(requested_case_ids))
        missing = sorted(set(requested) - {row["case_id"] for row in records})
        if missing:
            raise RuntimeError(f"requested cases failed or were not found: {missing}")
        by_id = {row["case_id"]: row for row in records}
        selected = [by_id[case_id] for case_id in requested]
    else:
        selected = _select_diverse(records, reference, min(count, len(records)))
    output.mkdir(parents=True)
    link_totals = {"hardlinked_files": 0, "copied_files": 0, "logical_bytes": 0}
    for index, row in enumerate(selected, 1):
        destination = output / "casos" / f"{index:02d}_{row['case_id']}"
        linked, copied, bytes_total = _link_case(Path(row["source_path"]), destination)
        row["showcase_relative_path"] = str(destination.relative_to(output))
        row["materialization"] = {"hardlinked_files": linked, "copied_files": copied, "logical_bytes": bytes_total}
        for key, value in row["materialization"].items():
            link_totals[key] += value
    ranked = sorted(records, key=lambda row: (-row["technical_quality_score"], row["case_id"]))
    selected_ids = {row["case_id"] for row in selected}
    manifest = {
        "schema": SCHEMA,
        "selection_mode": (
            "label_blind_technical_quality_plus_human_image_quality_review"
            if requested_case_ids
            else "label_blind_technical_quality_and_diversity"
        ),
        "reference_case": reference,
        "clinical_labels_read": False,
        "lesion_masks_read": False,
        "diagnostic_quality_claimed": False,
        "source_case_count": len(cases),
        "audited_case_count": len(records),
        "selected_case_count": len(selected),
        "selected_cases": [{key: value for key, value in row.items() if key != "source_path"} for row in selected],
        "complete_ranking": [
            {"rank": index, "case_id": row["case_id"], "technical_quality_score": row["technical_quality_score"], "selected": row["case_id"] in selected_ids}
            for index, row in enumerate(ranked, 1)
        ],
        "rejected_cases": rejected,
        "materialization_totals": link_totals,
    }
    (output / "manifesto_qualidade.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_gallery(output, selected, previews)
    readme = f"""# Mostruário DICOM ARGOS — alta qualidade técnica

Esta coleção contém {len(selected)} exames públicos TCGA-LIHC escolhidos em modo **label-blind**, usando o `{reference}` como referência visual. Diagnósticos, labels e máscaras de lesão não participaram da seleção.

## Como usar

- Exame individual: selecione uma pasta dentro de `casos/` no webapp.
- Benchmark: use `casos/` como raiz; cada subpasta é um caso independente.
- Revisão visual: abra `galeria/index.html`.

Os DICOMs foram materializados preferencialmente como **hardlinks NTFS**. Portanto, não ocupam uma segunda cópia física enquanto permanecerem no mesmo disco. Não apague os arquivos-fonte pensando que os hardlinks dependem do caminho original: cada hardlink continua válido de forma independente, mas o espaço só é liberado quando todos os links daquele arquivo forem removidos.

## Limite metodológico

O score é de qualidade técnica para processamento/apresentação (geometria, resolução, cobertura, nitidez, contraste e consistência). Ele não certifica qualidade diagnóstica nem presença/ausência de doença. Uso exclusivo em pesquisa com revisão humana.
"""
    (output / "LEIA-ME.md").write_text(readme, encoding="utf-8")
    checksums = []
    for path in sorted((output / "casos").rglob("*")):
        if path.is_file():
            checksums.append(f"{_sha256_file(path)}  {path.relative_to(output).as_posix()}")
    (output / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference", default="TCGA-G3-AAV1")
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="Caso previamente aprovado por revisão técnica label-blind; repetível.",
    )
    args = parser.parse_args()
    manifest = build(args.root, args.output, args.reference, args.count, args.case_ids)
    print(json.dumps({
        "output": str(args.output.resolve()),
        "selected": [row["case_id"] for row in manifest["selected_cases"]],
        "materialization": manifest["materialization_totals"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

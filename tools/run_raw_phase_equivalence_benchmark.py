"""Run a resumable, label-blind raw-vs-explicit DICOM phase equivalence arm."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import SimpleITK as sitk
import yaml

from dtwin.benchmark.lld_mmri_v23_mask_quality import evaluate_liver_mask_quality
from dtwin.core import PipelineError, sha256_of
from dtwin.learning.exam_to_panels import build_exam_panels
from dtwin.learning.raw_phase_equivalence import (
    SCHEMA, panel_hashes, positive_arm_metrics, selection_key, verified_review,
)
from dtwin.learning.raw_dicom_phase_resolver import REQUIRED_PHASES, resolve_raw_dicom_phases
from dtwin.learning.multiphase_ingest import build_multiphase_case
from dtwin.learning.visual_inference import classify_embeddings, embed_panels, load_production_bundle
from dtwin.segmentation_subprocess import run_segmentation_subprocess, segmentation_error


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _discover_sources(source_roots: list[Path], work: Path) -> dict[str, tuple[Path, dict[str, Path]]]:
    """Match public folders to approved series hashes without reading labels."""
    candidates = sorted({child.resolve() for root in source_roots for child in Path(root).iterdir() if child.is_dir()})
    matches: dict[str, tuple[Path, dict[str, Path]]] = {}
    approved = json.loads((work.parent / "review.json").read_text("utf-8"))["entries"]
    by_key = {selection_key(list(entry["series_hashes"])): str(entry["case_id"]) for entry in approved}
    index_root = work / "source_index"
    for index, source in enumerate(candidates):
        try:
            resolution = resolve_raw_dicom_phases(source, index_root / f"source-{index:03d}")
            manifest = json.loads(resolution.manifest_path.read_text("utf-8"))
            key = selection_key([manifest["selected"][phase]["series_hash"] for phase in REQUIRED_PHASES])
            case_id = by_key.get(key)
            if case_id:
                if case_id in matches:
                    raise PipelineError(f"Mais de uma fonte corresponde a {case_id}.")
                matches[case_id] = (source, resolution.phase_dirs)
        except PipelineError:
            continue
    return matches


def _copy_segmentation(source_dir: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("volume.nii.gz", "mask_organ.nii.gz"):
        shutil.copyfile(source_dir / name, destination / name)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--source-root", action="append", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, default=Path("casos/qualification/hybrid_v1/medsiglip_multiclass_production_bundle_v1"))
    parser.add_argument("--panel-config", type=Path, default=Path("configs/medgemma_local_4b_lld_v23_liver_enriched_pilot.yaml"))
    parser.add_argument("--embedding-config", type=Path, default=Path("configs/training/medsiglip_frozen_v1.yaml"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--device", default="gpu")
    args = parser.parse_args()

    review = verified_review(args.review.resolve())
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    # Freeze an internal copy so resumed runs cannot silently switch gallery.
    review_copy = out / "review.json"
    if review_copy.exists() and sha256_of(review_copy) != sha256_of(args.review):
        raise PipelineError("A galeria difere da usada no início deste run.")
    if not review_copy.exists(): shutil.copyfile(args.review, review_copy)
    approval = {
        "schema": "argos-raw-phase-review-approval-v1",
        "protocol_signature": review["protocol_signature"],
        "approved": True,
        "approval_source": "explicit_user_approval_in_codex_task",
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    approval_path = out / "review_approval.json"
    if not approval_path.exists(): _atomic_json(approval_path, approval)

    work = out / "_work"; work.mkdir(exist_ok=True)
    sources = _discover_sources([path.resolve() for path in args.source_root], work)
    entries = list(review["entries"])
    if args.limit: entries = entries[:args.limit]
    bundle = load_production_bundle(args.bundle)
    records: list[dict[str, Any]] = []
    for position, entry in enumerate(entries, 1):
        case_id = str(entry["case_id"]); case_dir = work / case_id; result_path = case_dir / "prediction.json"
        if result_path.is_file():
            records.append(json.loads(result_path.read_text("utf-8"))); continue
        started = time.monotonic()
        record: dict[str, Any] = {"case_id": case_id, "status": "technical_failure", "prediction": None}
        try:
            if case_id not in sources: raise PipelineError("Fonte aprovada não encontrada sem usar labels.")
            raw_source, approved_phase_dirs = sources[case_id]
            automatic_dir = case_dir / "automatic"

            checkpoint_auto = sorted((case_dir / "automatic_panels").glob("medgemma_liver_screening_panel_*.png"))
            checkpoint_explicit = sorted((case_dir / "explicit_panels").glob("medgemma_liver_screening_panel_*.png"))
            checkpoint_ready = (
                bool(checkpoint_auto)
                and len(checkpoint_auto) == len(checkpoint_explicit)
                and (automatic_dir / "segmentation" / "mask_organ.nii.gz").is_file()
                and (automatic_dir / "segmentation" / "volume.nii.gz").is_file()
            )

            def segment(venous: Path, destination: Path, *, record=record) -> Path:
                t0 = time.monotonic()
                process = run_segmentation_subprocess(
                    dicom_dir=venous, case_dir=destination, profile_path=Path("profiles/figado.yaml"),
                    device=args.device, fast=False, timeout_seconds=900,
                )
                record["segmentation_seconds"] = round(time.monotonic() - t0, 4)
                if not (destination / "volume.nii.gz").is_file() or not (destination / "mask_organ.nii.gz").is_file():
                    raise PipelineError("Segmentação falhou: " + segmentation_error(process))
                quality = evaluate_liver_mask_quality(destination / "mask_organ.nii.gz", sitk.ReadImage(str(destination / "volume.nii.gz")))
                record["mask_quality"] = quality
                if not quality["gate_passed"]: raise PipelineError("Máscara reprovada: " + ", ".join(quality["failure_reasons"]))
                return destination

            if checkpoint_ready:
                auto_panel_paths, explicit_panel_paths = checkpoint_auto, checkpoint_explicit
                record["resumed_from_panel_checkpoint"] = True
                record["mask_quality"] = evaluate_liver_mask_quality(
                    automatic_dir / "segmentation" / "mask_organ.nii.gz",
                    sitk.ReadImage(str(automatic_dir / "segmentation" / "volume.nii.gz")),
                )
                record["phase_coverage"] = {phase: 1.0 for phase in REQUIRED_PHASES}
                record["phase_resolution"] = {"method": str(entry["method"]), "confidence": entry["confidence"]}
            else:
                t0 = time.monotonic()
                automatic = build_multiphase_case(
                    case_id=case_id, case_upload_dir=raw_source, output_dir=automatic_dir,
                    segment_venous=segment,
                )
                record["automatic_ingest_and_segmentation_seconds"] = round(time.monotonic() - t0, 4)
                auto_resolved = json.loads((automatic_dir / "resolved_raw_phases" / "phase_resolution_manifest.json").read_text("utf-8"))
                actual_hashes = [auto_resolved["selected"][phase]["series_hash"] for phase in REQUIRED_PHASES]
                if actual_hashes != list(entry["series_hashes"]): raise PipelineError("Seleção automática divergiu da galeria aprovada.")

                t0 = time.monotonic()
                explicit = build_multiphase_case(
                    case_id=case_id, case_upload_dir=raw_source, output_dir=case_dir / "explicit",
                    phase_dirs=approved_phase_dirs,
                    segment_venous=lambda _venous, destination, automatic_dir=automatic_dir: _copy_segmentation(automatic_dir / "segmentation", destination),
                )
                record["explicit_ingest_seconds"] = round(time.monotonic() - t0, 4)
                auto_panels = build_exam_panels(
                    case_id=case_id, phase_paths=automatic.phase_paths,
                    coarse_liver_mask_path=automatic.coarse_liver_mask_path,
                    output_dir=case_dir / "automatic_panels", panel_config_path=args.panel_config,
                )
                explicit_panels = build_exam_panels(
                    case_id=case_id, phase_paths=explicit.phase_paths,
                    coarse_liver_mask_path=explicit.coarse_liver_mask_path,
                    output_dir=case_dir / "explicit_panels", panel_config_path=args.panel_config,
                )
                auto_panel_paths, explicit_panel_paths = auto_panels.panel_paths, explicit_panels.panel_paths
                record["phase_coverage"] = automatic.coverage
                record["phase_resolution"] = automatic.phase_resolution
            auto_hashes, explicit_hashes = panel_hashes(auto_panel_paths), panel_hashes(explicit_panel_paths)
            record.update(
                automatic_panel_hashes=auto_hashes, explicit_panel_hashes=explicit_hashes,
                panel_byte_equivalent=(auto_hashes == explicit_hashes), panel_count=len(auto_hashes),
            )
            if auto_hashes != explicit_hashes: raise PipelineError("Painéis automático e explícito não são byte-idênticos.")
            infer_started = time.monotonic()
            embeddings = embed_panels(args.embedding_config, auto_panel_paths)
            decision = classify_embeddings(bundle, embeddings)
            record.update(
                status="complete", prediction=decision["prediction"], score=decision["score"],
                threshold=decision["threshold"], class_probabilities=decision["class_probabilities"],
                inference_reused_for_explicit=True,
                inference_reuse_reason="byte_identical_panel_set",
                embedding_and_classification_seconds=round(time.monotonic() - infer_started, 4),
            )
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
        record["automatic_total_seconds"] = round(time.monotonic() - started, 4)
        _atomic_json(result_path, record); records.append(record)
        print(f"[{position}/{len(entries)}] {case_id}: {record['status']} {record.get('prediction')} {record['automatic_total_seconds']}s", flush=True)

    # Protected public labels are opened only after every requested prediction exists.
    predictions_complete = len(records) == len(entries) and all((work / str(e["case_id"]) / "prediction.json").is_file() for e in entries)
    if not predictions_complete: raise PipelineError("Predições incompletas; labels permaneceram fechados.")
    labels_payload = yaml.safe_load(args.labels.read_text("utf-8")) or {}
    labels = {str(item["case_id"]): str(item["label"]).upper() for item in labels_payload.get("cases", [])}
    evaluated = [{**row, "ground_truth": labels.get(row["case_id"])} for row in records]
    if any(row["ground_truth"] != "POSITIVE" for row in evaluated): raise PipelineError("Braço contém label diferente de POSITIVE.")
    report = {
        "schema": SCHEMA, "review_protocol_signature": review["protocol_signature"],
        "ground_truth_opened_after_predictions": True, "lesion_masks_read": False,
        "research_only": True, "clinical_use_allowed": False,
        "metrics": positive_arm_metrics(evaluated), "cases": evaluated,
    }
    _atomic_json(out / "benchmark_report.json", report)
    print(json.dumps(report["metrics"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

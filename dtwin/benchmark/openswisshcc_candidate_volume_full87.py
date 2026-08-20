"""Build the v16 full87 reviewed-input bundle after the signed timing gate."""
from __future__ import annotations

import html
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_candidate_volume import (
    COHORT_SCHEMA,
    CONTRACT,
    MAX_CANDIDATES,
    MIN_BASE_CANDIDATES,
    OUTPUT_SIDE,
    ROI_MM,
    TARGET_CANDIDATE_COVERAGE,
    _canonical,
    _input_index,
    _load,
    _original_dynamic_inputs,
    _registered_or_none,
    _valid_localizer_run_schema,
    build_candidate_volume_case,
    preview_frame_indices,
)
from dtwin.benchmark.openswisshcc_candidate_volume_fallback import _validate_timing_plan
from dtwin.benchmark.openswisshcc_candidate_volume_score import (
    validate_candidate_volume_bundle,
    validate_candidate_volume_review,
)
from dtwin.benchmark.openswisshcc_candidate_volume_timing_run import (
    RUN_SCHEMA as TIMING_RUN_SCHEMA,
)
from dtwin.benchmark.openswisshcc_candidate_volume_timing_run import (
    _load_static_context,
)
from dtwin.benchmark.openswisshcc_lesion_localizer_chunks import MERGED_RUN_SCHEMA
from dtwin.core import PipelineError, sha256_of
from dtwin.medgemma_screening import _write_json_atomic

FULL87_SCHEMA = "argos-openswisshcc-candidate-volume-full87-v16"
CONTACT_SHEET_SCHEMA = "argos-openswisshcc-candidate-volume-contact-sheet-v16"


def validate_timing_authorization(
    *,
    timing_bundle_root: Path,
    timing_review_path: Path,
    timing_protocol_path: Path,
    config_path: Path,
    timing_report_path: Path,
) -> dict[str, Any]:
    bundle, review, protocol = _load_static_context(
        timing_bundle_root,
        timing_review_path,
        timing_protocol_path,
        config_path,
    )
    report_path = Path(timing_report_path).resolve()
    report = _load(report_path)
    cases = report.get("cases")
    if (
        report.get("schema") != TIMING_RUN_SCHEMA
        or report.get("status") != "timing_gate_passed"
        or report.get("protocol_signature") != protocol["protocol_signature"]
        or report.get("review_signature") != review["review_signature"]
        or report.get("bundle_cohort_sha256") != bundle["cohort_sha256"]
        or report.get("model_id") != protocol["model_id"]
        or report.get("case_count") != 4
        or report.get("candidate_request_count") != 10
        or report.get("full87_authorized_by_timing") is not True
        or report.get("inference_executed") is not True
        or report.get("ground_truth_read") is not False
        or report.get("metrics_calculated") is not False
        or report.get("holdout_opened") is not False
        or report.get("accuracy_claimed") is not False
        or report.get("timing_interpretation", {}).get("projected_pipeline_180_seconds_passed") is not True
        or report.get("timing_interpretation", {}).get("full_pipeline_180_seconds_proven") is not False
        or not isinstance(cases, list)
        or len(cases) != 4
    ):
        raise PipelineError("Relatorio temporal v16 nao autoriza o full87.")
    prediction_root = report_path.parent / "predictions"
    seen = set()
    for item in cases:
        case_id = str(item.get("case_id", ""))
        prediction_path = prediction_root / f"{case_id}.json"
        if (
            not case_id.startswith("anon-")
            or case_id in seen
            or item.get("fresh_hash_match") is not True
            or item.get("projected_time_gate_passed") is not True
            or item.get("prediction_published") is not True
            or not prediction_path.is_file()
            or sha256_of(prediction_path) != item.get("prediction_sha256")
        ):
            raise PipelineError("Predicao/tempo do piloto v16 divergiu do relatorio.")
        prediction = _load(prediction_path)
        if (
            prediction.get("case_id") != case_id
            or prediction.get("protocol_signature") != protocol["protocol_signature"]
            or prediction.get("status") != "technical_passed"
            or prediction.get("time_gate_passed") is not True
            or prediction.get("ground_truth_read") is not False
            or prediction.get("metrics_calculated") is not False
            or prediction.get("holdout_opened") is not False
        ):
            raise PipelineError("Predicao do piloto temporal v16 invalida.")
        seen.add(case_id)
    return {
        "report": report,
        "report_sha256": sha256_of(report_path),
        "protocol_signature": protocol["protocol_signature"],
        "review_signature": review["review_signature"],
        "timing_bundle_sha256": bundle["cohort_sha256"],
    }


def _contact_sheet(candidate_dir: Path, candidate_manifest: dict[str, Any], out_path: Path) -> dict[str, Any]:
    tile_side = 128
    label_height = 30
    row_height = tile_side + label_height
    groups = candidate_manifest["groups"]
    canvas = Image.new("RGB", (tile_side * 3, 46 + row_height * len(groups)), (8, 13, 20))
    draw = ImageDraw.Draw(canvas)
    draw.text((8, 7), f'Caso {candidate_manifest["case_id"]} | candidato {candidate_manifest["candidate_number"]}/{candidate_manifest["candidate_total"]}', fill=(236, 240, 245))
    draw.text((8, 25), "AUDITORIA HUMANA - NAO E ENTRADA DO MODELO", fill=(255, 190, 80))
    for row, group in enumerate(groups):
        positions = preview_frame_indices(len(group["frames"]))
        labels = {positions[0]: "inicio", positions[-1]: "fim"}
        labels[positions[len(positions) // 2]] = "centro"
        for column, position in enumerate(positions):
            frame = group["frames"][position]
            image_path = candidate_dir / frame["filename"]
            with Image.open(image_path) as image:
                tile = image.convert("RGB").resize((tile_side, tile_side), Image.Resampling.LANCZOS)
            x = column * tile_side
            y = 46 + row * row_height
            canvas.paste(tile, (x, y))
            label = f'{group["role"]} {labels[position]} z={frame["source_index_z"]}'
            draw.text((x + 3, y + tile_side + 3), label[:30], fill=(218, 225, 233))
    canvas.save(out_path, format="PNG", optimize=False)
    return {
        "schema": CONTACT_SHEET_SCHEMA,
        "filename": out_path.name,
        "sha256": _sha256(out_path),
        "bytes": out_path.stat().st_size,
        "width": canvas.width,
        "height": canvas.height,
        "candidate_number": candidate_manifest["candidate_number"],
        "candidate_total": candidate_manifest["candidate_total"],
        "source_frame_count": candidate_manifest["frame_count"],
        "preview_frame_count": sum(len(preview_frame_indices(len(group["frames"]))) for group in groups),
        "audit_only_not_model_input": True,
    }


def _gallery_pages(root: Path, records: list[dict[str, Any]], page_size: int = 10) -> list[dict[str, Any]]:
    pages = []
    chunks = [records[index:index + page_size] for index in range(0, len(records), page_size)]
    for page_number, chunk in enumerate(chunks, 1):
        filename = f"page_{page_number:03d}.html"
        sections = []
        for record in chunk:
            figures = "".join(
                f'<figure><img loading="lazy" src="{html.escape(item["relative_path"])}">'
                f'<figcaption>Candidato {item["candidate_number"]}/{record["candidate_stack_count"]} — '
                f'{html.escape(item["description"])}</figcaption></figure>'
                for item in record["audit_contact_sheets"]
            )
            sections.append(
                f'<section><h2>{html.escape(record["case_id"])}</h2>'
                f'<p>Modo: {html.escape(record["dynamic_alignment_mode"])} | stacks: {record["candidate_stack_count"]}</p>'
                f'<div class="grid">{figures}</div></section>'
            )
        navigation = " ".join(f'<a href="page_{number:03d}.html">{number}</a>' for number in range(1, len(chunks) + 1))
        page = (
            '<!doctype html><html><head><meta charset="utf-8"><title>ARGOS v16 full87</title>'
            '<style>body{background:#08111b;color:#e8edf2;font:15px system-ui;margin:24px}a{color:#72b7ff;margin-right:8px}'
            'section{border-top:1px solid #334155;padding:18px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(390px,1fr));gap:14px}'
            'figure{margin:0;background:#111827;padding:8px}img{width:100%;height:auto}figcaption{margin-top:5px;color:#b8c3cf}</style></head><body>'
            f'<h1>ARGOS v16 full87 — página {page_number}/{len(chunks)}</h1><p>{navigation}</p>'
            '<p>Revisar somente qualidade técnica, continuidade e correspondência. Não inferir diagnóstico/ground truth.</p>'
            + "".join(sections) + f'<p>{navigation}</p></body></html>'
        )
        (root / filename).write_text(page, encoding="utf-8")
        pages.append({"page_number": page_number, "filename": filename, "case_count": len(chunk), "sha256": _sha256(root / filename)})
    index_links = "".join(f'<li><a href="{item["filename"]}">Página {item["page_number"]}</a> — {item["case_count"]} casos</li>' for item in pages)
    (root / "index.html").write_text(
        '<!doctype html><html><head><meta charset="utf-8"><title>ARGOS v16 full87</title>'
        '<style>body{background:#08111b;color:#e8edf2;font:16px system-ui;margin:32px}a{color:#72b7ff}</style></head><body>'
        '<h1>ARGOS v16 full87 — auditoria humana paginada</h1>'
        '<p>87 casos. Contact sheets são apenas para auditoria e nunca entram no modelo.</p>'
        '<p>Avaliar todos os candidatos de todas as páginas; não avaliar diagnóstico.</p>'
        f'<ol>{index_links}</ol></body></html>',
        encoding="utf-8",
    )
    return pages


def _validate_contact_sheet_file(root: Path, case_id: str, item: dict[str, Any]) -> Path:
    expected_name = f'audit_candidate_{int(item.get("candidate_number", 0)):03d}.png'
    relative = str(item.get("relative_path", ""))
    path = (root / relative).resolve()
    if (
        item.get("schema") != CONTACT_SHEET_SCHEMA
        or item.get("filename") != expected_name
        or relative != f"{case_id}/{expected_name}"
        or not path.is_relative_to(root)
        or not path.is_file()
        or path.stat().st_size != int(item.get("bytes", -1))
        or _sha256(path) != item.get("sha256")
        or item.get("audit_only_not_model_input") is not True
        or int(item.get("preview_frame_count", 0)) < 3
        or int(item.get("source_frame_count", 0)) < 5
    ):
        raise PipelineError("Contact sheet full87 ausente, adulterada ou insegura.")
    with Image.open(path) as image:
        if (
            image.format != "PNG"
            or image.mode != "RGB"
            or image.width != int(item.get("width", -1))
            or image.height != int(item.get("height", -1))
        ):
            raise PipelineError("Contact sheet full87 viola formato ou dimensoes.")
        image.load()
    return path


def validate_full87_audit_gallery(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    bundle = validate_candidate_volume_bundle(root)
    cohort = bundle["cohort"]
    if (
        cohort.get("full87_schema") != FULL87_SCHEMA
        or cohort.get("case_count") != 87
        or cohort.get("registered_case_count") != 84
        or cohort.get("unregistered_approved_fallback_case_count") != 3
        or cohort.get("technical_review_status") != "pending"
        or cohort.get("protocol", {}).get("contact_sheets_are_model_inputs") is not False
        or cohort.get("inference_executed") is not False
        or cohort.get("ground_truth_read") is not False
        or cohort.get("holdout_opened") is not False
    ):
        raise PipelineError("Coorte de auditoria full87 viola contrato ou salvaguardas.")
    sheet_count = 0
    model_input_frame_count = 0
    longest_path_chars = 0
    seen_sheets = set()
    for record in cohort["cases"]:
        case_id = record["case_id"]
        sheets = record.get("audit_contact_sheets")
        if not isinstance(sheets, list) or len(sheets) != record["candidate_stack_count"]:
            raise PipelineError("Contact sheets full87 nao correspondem aos stacks.")
        case_manifest_path = root / case_id / "case_manifest.json"
        case_manifest = _load(case_manifest_path)
        if "audit_candidate_" in json.dumps(case_manifest, sort_keys=True):
            raise PipelineError("Contact sheet full87 vazou para manifesto do modelo.")
        model_input_frame_count += sum(int(item["frame_count"]) for item in case_manifest["candidate_stacks"])
        for expected_number, item in enumerate(sheets, 1):
            if item.get("candidate_number") != expected_number:
                raise PipelineError("Ordem das contact sheets full87 divergiu.")
            path = _validate_contact_sheet_file(root, case_id, item)
            if path in seen_sheets:
                raise PipelineError("Contact sheet full87 duplicada.")
            seen_sheets.add(path)
            longest_path_chars = max(longest_path_chars, len(str(path)))
            sheet_count += 1
    pages = cohort.get("gallery_pages")
    if not isinstance(pages, list) or len(pages) != 9 or sum(int(item["case_count"]) for item in pages) != 87:
        raise PipelineError("Paginacao da galeria full87 invalida.")
    for expected_number, item in enumerate(pages, 1):
        page = (root / str(item.get("filename", ""))).resolve()
        if (
            item.get("page_number") != expected_number
            or item.get("filename") != f"page_{expected_number:03d}.html"
            or not page.is_relative_to(root)
            or not page.is_file()
            or _sha256(page) != item.get("sha256")
        ):
            raise PipelineError("Pagina da galeria full87 ausente ou adulterada.")
    index_path = root / "index.html"
    if not index_path.is_file() or _sha256(index_path) != cohort.get("gallery_index_sha256"):
        raise PipelineError("Indice da galeria full87 ausente ou adulterado.")
    return {
        "case_count": bundle["case_count"],
        "candidate_stack_count": bundle["candidate_stack_count"],
        "model_input_frame_count": model_input_frame_count,
        "contact_sheet_count": sheet_count,
        "gallery_page_count": len(pages),
        "longest_contact_sheet_path_chars": longest_path_chars,
        "cohort_sha256": bundle["cohort_sha256"],
        "gallery_signature": cohort["gallery_signature"],
        "ground_truth_read": False,
        "holdout_opened": False,
    }
def build_candidate_volume_full87_gallery(
    *,
    timing_bundle_root: Path,
    timing_review_path: Path,
    timing_protocol_path: Path,
    config_path: Path,
    timing_report_path: Path,
    timing_plan_path: Path,
    fallback_bundle_root: Path,
    fallback_review_path: Path,
    localizer_run: Path,
    input_manifest: Path,
    input_root: Path,
    registration_root: Path,
    output_root: Path,
    expected_source_case_count: int = 88,
    expected_case_count: int = 87,
) -> dict[str, Any]:
    authorization = validate_timing_authorization(
        timing_bundle_root=timing_bundle_root,
        timing_review_path=timing_review_path,
        timing_protocol_path=timing_protocol_path,
        config_path=config_path,
        timing_report_path=timing_report_path,
    )
    plan_path = Path(timing_plan_path).resolve()
    plan = _validate_timing_plan(plan_path)
    if authorization["report"]["timing_plan_signature"] != plan["plan_signature"]:
        raise PipelineError("Plano temporal full87 divergiu do piloto aprovado.")
    fallback_bundle = validate_candidate_volume_bundle(fallback_bundle_root)
    fallback_review = validate_candidate_volume_review(fallback_review_path, fallback_bundle)
    unavailable_ids = sorted(item["case_id"] for item in plan["alignment_unavailable_cases"])
    if sorted(fallback_bundle["case_ids"]) != unavailable_ids:
        raise PipelineError("Bundle fallback aprovado divergiu dos casos sem alinhamento.")
    approved_fallback = {item["case_id"]: item for item in fallback_bundle["cases"]}

    localizer_run = Path(localizer_run).resolve()
    localizer_summary_path = localizer_run / "summary.json"
    localizer_summary = _load(localizer_summary_path)
    if (
        localizer_summary.get("schema") != MERGED_RUN_SCHEMA
        or not _valid_localizer_run_schema(localizer_summary)
        or localizer_summary.get("status") != "complete_scores_only_no_decision"
        or localizer_summary.get("case_count") != expected_case_count
        or len(localizer_summary.get("case_ids", [])) != expected_case_count
        or localizer_summary.get("ground_truth_read") is not False
        or localizer_summary.get("ground_truth_lesion_mask_used") is not False
        or localizer_summary.get("final_decision") is not None
        or plan.get("source_localizer_summary_sha256") != _sha256(localizer_summary_path)
    ):
        raise PipelineError("Resumo do localizador invalido para full87 v16.")
    morphology = _input_index(input_manifest, input_root)
    dynamic = _original_dynamic_inputs(input_manifest, input_root)
    if len(morphology) != expected_source_case_count or set(morphology) != set(dynamic):
        raise PipelineError("Coorte fonte full87 v16 inesperada.")

    destination = Path(output_root).resolve()
    if destination.exists():
        raise PipelineError("Destino full87 v16 ja existe; sobrescrita recusada.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f"._v16full87_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    records = []
    registered_count = 0
    fallback_count = 0
    try:
        for case_id in localizer_summary["case_ids"]:
            registered = _registered_or_none(case_id, registration_root)
            if registered is None:
                if case_id not in approved_fallback:
                    raise PipelineError("Caso full87 sem registro nao possui fallback humano aprovado.")
                fallback_count += 1
            else:
                if case_id in approved_fallback:
                    raise PipelineError("Caso aprovado como fallback agora possui registro inesperado.")
                registered_count += 1
            case_dir = staging / case_id
            case_manifest = build_candidate_volume_case(
                case_id=case_id,
                morphology_source=morphology[case_id],
                dynamic_source=dynamic[case_id],
                registered_source=registered,
                localizer_dir=localizer_run / case_id,
                destination=case_dir,
            )
            case_manifest_path = case_dir / "case_manifest.json"
            if registered is None and sha256_of(case_manifest_path) != approved_fallback[case_id]["case_manifest_sha256"]:
                raise PipelineError("Fallback full87 regenerado divergiu do bundle humano aprovado.")
            sheets = []
            for stack in case_manifest["candidate_stacks"]:
                candidate_dir = case_dir / stack["relative_directory"]
                candidate_manifest = _load(candidate_dir / "manifest.json")
                sheet_path = case_dir / f'audit_candidate_{stack["candidate_number"]:03d}.png'
                sheet = _contact_sheet(candidate_dir, candidate_manifest, sheet_path)
                sheets.append(
                    {
                        **sheet,
                        "relative_path": f'{case_id}/{sheet_path.name}',
                        "description": (
                            "fallback no centro hepatico"
                            if stack["fallback_no_candidate"]
                            else f'rank {stack["component_rank"]}, {stack["component_voxels"]} voxels'
                        ),
                    }
                )
            records.append(
                {
                    "case_id": case_id,
                    "candidate_stack_count": case_manifest["candidate_stack_count"],
                    "case_manifest_sha256": sha256_of(case_manifest_path),
                    "dynamic_alignment_mode": case_manifest["dynamic_alignment_mode"],
                    "audit_contact_sheets": sheets,
                }
            )
        if registered_count != 84 or fallback_count != 3:
            raise PipelineError("Distribuicao registrada/fallback do full87 v16 divergiu de 84/3.")
        pages = _gallery_pages(staging, records)
        cohort = {
            "schema": COHORT_SCHEMA,
            "full87_schema": FULL87_SCHEMA,
            "contract": CONTRACT,
            "case_count": len(records),
            "candidate_stack_count": sum(item["candidate_stack_count"] for item in records),
            "cases": records,
            "registered_case_count": registered_count,
            "unregistered_approved_fallback_case_count": fallback_count,
            "source_timing_report_sha256": authorization["report_sha256"],
            "source_timing_protocol_signature": authorization["protocol_signature"],
            "source_timing_review_signature": authorization["review_signature"],
            "source_timing_bundle_sha256": authorization["timing_bundle_sha256"],
            "source_timing_plan_sha256": _sha256(plan_path),
            "source_timing_plan_signature": plan["plan_signature"],
            "source_fallback_bundle_sha256": fallback_bundle["cohort_sha256"],
            "source_fallback_review_signature": fallback_review["review_signature"],
            "source_localizer_summary_sha256": _sha256(localizer_summary_path),
            "input_manifest_sha256": _sha256(Path(input_manifest).resolve()),
            "protocol": {
                "roi_mm": ROI_MM,
                "output_side": OUTPUT_SIDE,
                "candidate_target_fraction": TARGET_CANDIDATE_COVERAGE,
                "minimum_base_candidates": MIN_BASE_CANDIDATES,
                "maximum_candidates": MAX_CANDIDATES,
                "gallery_page_size": 10,
                "contact_sheets_are_model_inputs": False,
            },
            "gallery_pages": pages,
            "gallery_index_sha256": _sha256(staging / "index.html"),
            "gallery_signature": _canonical(records),
            "technical_review_status": "pending",
            "inference_executed": False,
            "ground_truth_read": False,
            "dataset_lesion_mask_used": False,
            "holdout_opened": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        _write_json_atomic(staging / "cohort_manifest.json", cohort)
        _publish_directory(staging, destination)
        return cohort
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

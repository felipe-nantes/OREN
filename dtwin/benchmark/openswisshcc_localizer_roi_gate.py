"""Signed human review for paired OpenSwissHCC v10 localizer ROI galleries."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_localizer_enhancement_roi import CASE_SCHEMA as ENHANCEMENT_CASE_SCHEMA, COHORT_SCHEMA as ENHANCEMENT_COHORT_SCHEMA
from dtwin.benchmark.openswisshcc_localizer_roi import CASE_SCHEMA as MORPHOLOGY_CASE_SCHEMA, COHORT_SCHEMA as MORPHOLOGY_COHORT_SCHEMA
from dtwin.core import PipelineError

REVIEW_SCHEMA = "argos-openswisshcc-localizer-roi-paired-review-v1"
REQUIRED_CONFIRMATIONS = (
    "no_visible_phi",
    "morphology_roi_acceptable",
    "enhancement_roi_acceptable",
    "same_candidate_pairing_acceptable",
    "fallback_behavior_understood",
)
SIGNED_REVIEW_FIELDS = (
    "schema",
    "review_status",
    "reviewer",
    "reviewed_at_utc",
    "confirmations",
    "morphology_gallery",
    "enhancement_gallery",
    "case_count",
    "panel_pairs",
    "cases",
    "research_only",
    "clinical_use_allowed",
    "ground_truth_read",
    "lesion_mask_used",
    "inference_executed",
)


def _canonical(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON do gate ROI v10 invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("JSON do gate ROI v10 deve ser objeto.")
    return value


def _review_signature(payload: dict[str, Any]) -> str:
    return _canonical({key: payload.get(key) for key in SIGNED_REVIEW_FIELDS})


def _safe_image(case_dir: Path, panel: dict[str, Any]) -> dict[str, Any]:
    relative = PurePosixPath(str(panel.get("image", "")))
    if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 1:
        raise PipelineError("Caminho de painel ROI v10 inseguro.")
    image_path = (case_dir / relative.name).resolve()
    if not image_path.is_relative_to(case_dir) or not image_path.is_file():
        raise PipelineError("Painel ROI v10 ausente ou fora do caso.")
    digest = _sha256(image_path)
    size = image_path.stat().st_size
    if digest != panel.get("sha256") or size != panel.get("bytes"):
        raise PipelineError("Hash ou bytes do painel ROI v10 divergiram.")
    if size > 8_000_000:
        raise PipelineError("Painel ROI v10 excede limite de bytes.")
    try:
        with Image.open(image_path) as source:
            if source.format != "PNG" or source.width * source.height > 4_000_000:
                raise PipelineError("Formato ou pixels do painel ROI v10 invalidos.")
            source.verify()
    except OSError as exc:
        raise PipelineError("PNG ROI v10 corrompido.") from exc
    return {"image": relative.name, "sha256": digest, "bytes": size}


def _validate_tiles(kind: str, panel: dict[str, Any]) -> None:
    tiles = panel.get("tiles")
    if not isinstance(tiles, list) or len(tiles) != 4:
        raise PipelineError("Painel ROI v10 deve conter quatro tiles.")
    roles = [str(tile.get("role", "")) for tile in tiles]
    if kind == "morphology":
        if roles[0] != "t1_venous" or roles[1] not in {"t2_blade", "t2_haste"} or not roles[2].startswith("dwi_trace_run_") or roles[3] != "dwi_adc":
            raise PipelineError("Ordem de modalidades morfologicas v10 invalida.")
    elif roles != ["t1_native", "t1_arterial_registered", "t1_venous", "t1_delayed_registered"]:
        raise PipelineError("Ordem de fases dinamicas v10 invalida.")
    fallback = panel.get("fallback_no_candidate") is True
    contour_tiles = [tile for tile in tiles if tile.get("candidate_contour_shown") is True]
    if fallback:
        if panel.get("fallback_reason") != "no_model_derived_candidate" or contour_tiles:
            raise PipelineError("Fallback ROI v10 ambiguo ou com contorno indevido.")
    else:
        expected_role = "t1_venous"
        if len(contour_tiles) != 1 or contour_tiles[0].get("role") != expected_role:
            raise PipelineError("Candidato ROI v10 deve ter um contorno apenas no T1 venoso.")
    if kind == "morphology":
        if any(tile.get("available_in_fov") is not True for tile in tiles):
            raise PipelineError("Galeria morfologica aprovada contem tile indisponivel.")
    else:
        usable = sum(tile.get("available_in_fov") is True for tile in tiles)
        venous = next(tile for tile in tiles if tile.get("role") == "t1_venous")
        if usable < 2 or venous.get("available_in_fov") is not True or panel.get("usable_phase_count") != usable:
            raise PipelineError("Painel dinamico v10 nao preserva evidencia minima.")
        for tile in tiles:
            available = tile.get("available_in_fov") is True
            reason = tile.get("unavailable_reason")
            if available and reason is not None:
                raise PipelineError("Tile dinamico disponivel possui motivo de indisponibilidade.")
            if not available and reason not in {"sem_contraste_no_roi", "fora_do_fov"}:
                raise PipelineError("Motivo de tile dinamico indisponivel nao autorizado.")


def _validate_gallery(root: Path, kind: str, expected_case_count: int) -> dict[str, Any]:
    root = Path(root).resolve()
    if not root.is_dir():
        raise PipelineError("Galeria ROI v10 ausente.")
    cohort = _load(root / "cohort_manifest.json")
    cohort_schema = MORPHOLOGY_COHORT_SCHEMA if kind == "morphology" else ENHANCEMENT_COHORT_SCHEMA
    case_schema = MORPHOLOGY_CASE_SCHEMA if kind == "morphology" else ENHANCEMENT_CASE_SCHEMA
    manifest_name = "roi_manifest.json" if kind == "morphology" else "enhancement_roi_manifest.json"
    if cohort.get("schema") != cohort_schema or cohort.get("case_count") != expected_case_count:
        raise PipelineError("Schema ou contagem da galeria ROI v10 divergiu.")
    if any(cohort.get(key) is not expected for key, expected in {"ground_truth_lesion_mask_used": False, "ground_truth_read": False, "inference_executed": False, "research_only": True, "clinical_use_allowed": False, "requires_human_review": True}.items()):
        raise PipelineError("Galeria ROI v10 perdeu salvaguardas.")
    cohort_cases = cohort.get("cases")
    if not isinstance(cohort_cases, list) or len(cohort_cases) != expected_case_count:
        raise PipelineError("Casos da galeria ROI v10 incompletos.")
    records = []
    panel_total = 0
    seen = set()
    for cohort_case in cohort_cases:
        case_id = str(cohort_case.get("case_id", ""))
        if not case_id.startswith("anon-") or case_id in seen or any(char in case_id for char in "/\\"):
            raise PipelineError("case_id ROI v10 invalido ou duplicado.")
        seen.add(case_id)
        case_dir = (root / case_id).resolve()
        if not case_dir.is_relative_to(root) or not case_dir.is_dir():
            raise PipelineError("Diretorio de caso ROI v10 inseguro.")
        manifest_path = case_dir / manifest_name
        manifest = _load(manifest_path)
        manifest_sha = _sha256(manifest_path)
        if manifest.get("schema") != case_schema or manifest.get("case_id") != case_id or manifest_sha != cohort_case.get("manifest_sha256"):
            raise PipelineError("Manifesto de caso ROI v10 divergiu do cohort.")
        if any(manifest.get(key) is not expected for key, expected in {"candidate_mask_is_model_derived": True, "ground_truth_lesion_mask_used": False, "ground_truth_read": False, "inference_executed": False, "research_only": True, "clinical_use_allowed": False, "requires_human_review": True}.items()):
            raise PipelineError("Manifesto de caso ROI v10 perdeu salvaguardas.")
        panels = manifest.get("panels")
        if not isinstance(panels, list) or not panels or manifest.get("panel_count") != len(panels) or cohort_case.get("panel_count") != len(panels):
            raise PipelineError("Contagem de paineis ROI v10 invalida.")
        cohort_panels = cohort_case.get("panels")
        if not isinstance(cohort_panels, list) or len(cohort_panels) != len(panels):
            raise PipelineError("Lista de paineis do cohort ROI v10 invalida.")
        image_records = []
        pair_records = []
        for number, (panel, cohort_panel) in enumerate(zip(panels, cohort_panels, strict=True), 1):
            if panel.get("panel_number") != number or panel.get("panel_total") != len(panels):
                raise PipelineError("Ordem de paineis ROI v10 invalida.")
            image_record = _safe_image(case_dir, panel)
            if cohort_panel != {"image": image_record["image"], "sha256": image_record["sha256"]}:
                raise PipelineError("Painel do cohort ROI v10 divergiu do caso.")
            _validate_tiles(kind, panel)
            image_records.append(image_record)
            pair_records.append({
                "panel_number": number,
                "component_rank": panel.get("component_rank"),
                "component_voxels": panel.get("component_voxels"),
                "physical_center_lps_xyz": panel.get("physical_center_lps_xyz"),
                "fallback_no_candidate": panel.get("fallback_no_candidate"),
            })
        panel_total += len(panels)
        records.append({"case_id": case_id, "manifest_sha256": manifest_sha, "panel_set_sha256": _canonical(image_records), "panel_count": len(panels), "pair_records": pair_records})
    if cohort.get("panel_count") != panel_total:
        raise PipelineError("Total de paineis ROI v10 divergiu.")
    return {"root": root, "cohort": cohort, "cohort_sha256": _sha256(root / "cohort_manifest.json"), "records": records}


def validate_paired_galleries(*, morphology_root: Path, enhancement_root: Path, expected_case_count: int = 10) -> dict[str, Any]:
    if expected_case_count < 1:
        raise PipelineError("expected_case_count ROI v10 invalido.")
    morphology = _validate_gallery(morphology_root, "morphology", expected_case_count)
    enhancement = _validate_gallery(enhancement_root, "enhancement", expected_case_count)
    if [r["case_id"] for r in morphology["records"]] != [r["case_id"] for r in enhancement["records"]]:
        raise PipelineError("Galerias ROI v10 nao possuem a mesma ordem de casos.")
    cases = []
    for left, right in zip(morphology["records"], enhancement["records"], strict=True):
        if left["panel_count"] != right["panel_count"] or left["pair_records"] != right["pair_records"]:
            raise PipelineError("Galerias ROI v10 nao representam exatamente os mesmos candidatos.")
        cases.append({
            "case_id": left["case_id"],
            "panel_count": left["panel_count"],
            "fallback_no_candidate": bool(left["pair_records"][0]["fallback_no_candidate"]),
            "morphology_manifest_sha256": left["manifest_sha256"],
            "morphology_panel_set_sha256": left["panel_set_sha256"],
            "enhancement_manifest_sha256": right["manifest_sha256"],
            "enhancement_panel_set_sha256": right["panel_set_sha256"],
            "pairing_sha256": _canonical(left["pair_records"]),
        })
    return {
        "morphology_gallery": {"schema": morphology["cohort"]["schema"], "gallery_signature": morphology["cohort"]["gallery_signature"], "cohort_sha256": morphology["cohort_sha256"], "panel_count": morphology["cohort"]["panel_count"]},
        "enhancement_gallery": {"schema": enhancement["cohort"]["schema"], "gallery_signature": enhancement["cohort"]["gallery_signature"], "cohort_sha256": enhancement["cohort_sha256"], "panel_count": enhancement["cohort"]["panel_count"]},
        "case_count": len(cases),
        "panel_pairs": sum(case["panel_count"] for case in cases),
        "cases": cases,
    }


def create_paired_review(*, morphology_root: Path, enhancement_root: Path, output_path: Path, reviewer: str, confirmations: dict[str, bool], expected_case_count: int = 10) -> dict[str, Any]:
    reviewer = str(reviewer).strip()
    if not reviewer or len(reviewer) > 120:
        raise PipelineError("Revisor ROI v10 obrigatorio.")
    if set(confirmations) != set(REQUIRED_CONFIRMATIONS) or any(confirmations[key] is not True for key in REQUIRED_CONFIRMATIONS):
        raise PipelineError("Todas as confirmacoes ROI v10 devem ser explicitas.")
    validated = validate_paired_galleries(morphology_root=morphology_root, enhancement_root=enhancement_root, expected_case_count=expected_case_count)
    payload = {
        "schema": REVIEW_SCHEMA,
        "review_status": "approved_for_research_scores_only",
        "reviewer": reviewer,
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "confirmations": {key: True for key in REQUIRED_CONFIRMATIONS},
        **validated,
        "research_only": True,
        "clinical_use_allowed": False,
        "ground_truth_read": False,
        "lesion_mask_used": False,
        "inference_executed": False,
    }
    payload["review_signature"] = _review_signature(payload)
    output = Path(output_path).resolve()
    if output.exists():
        raise PipelineError("Revisao ROI v10 ja existe e nao sera sobrescrita.")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return payload


def verify_paired_review(*, morphology_root: Path, enhancement_root: Path, review_path: Path, expected_case_count: int = 10) -> dict[str, Any]:
    review = _load(Path(review_path).resolve())
    if set(review) != set(SIGNED_REVIEW_FIELDS) | {"review_signature"} or review.get("schema") != REVIEW_SCHEMA or review.get("review_status") != "approved_for_research_scores_only":
        raise PipelineError("Campos ou status da revisao ROI v10 invalidos.")
    if review.get("review_signature") != _review_signature(review):
        raise PipelineError("Assinatura da revisao ROI v10 invalida.")
    if set(review.get("confirmations", {})) != set(REQUIRED_CONFIRMATIONS) or any(review["confirmations"].get(key) is not True for key in REQUIRED_CONFIRMATIONS):
        raise PipelineError("Confirmacoes da revisao ROI v10 invalidas.")
    if any(review.get(key) is not expected for key, expected in {"research_only": True, "clinical_use_allowed": False, "ground_truth_read": False, "lesion_mask_used": False, "inference_executed": False}.items()):
        raise PipelineError("Revisao ROI v10 violou isolamento metodologico.")
    current = validate_paired_galleries(morphology_root=morphology_root, enhancement_root=enhancement_root, expected_case_count=expected_case_count)
    for key in ("morphology_gallery", "enhancement_gallery", "case_count", "panel_pairs", "cases"):
        if review.get(key) != current[key]:
            raise PipelineError("Galerias ROI v10 mudaram apos a revisao humana.")
    return review

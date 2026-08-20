"""Scorer cego MedGemma 4B para o atlas axial OpenSwissHCC v17."""
from __future__ import annotations

import base64
import json
import math
import re
import statistics
import time
from collections.abc import Mapping
from pathlib import Path
from urllib.request import Request

from PIL import Image

from dtwin.benchmark.openswisshcc_axial_atlas import (
    CASE_SCHEMA,
    COHORT_SCHEMA,
    GALLERY_SCHEMA,
    REQUIRED_REVIEW_CONFIRMATIONS,
    REVIEW_SCHEMA,
)
from dtwin.benchmark.openswisshcc_axial_atlas import (
    PROTOCOL_SIGNATURE as ATLAS_PROTOCOL_SIGNATURE,
)
from dtwin.benchmark.openswisshcc_highdimensional_inference import (
    RESPONSE_PREFIX,
    _atomic_json,
    _canonical_hash,
    _request_json,
)
from dtwin.benchmark.openswisshcc_volume_score import (
    CHOICES,
    CONTRACT,
    PROBABILITY_TOLERANCE,
    SCORING_METHOD,
    _score_url,
    _validate_score_response,
)
from dtwin.core import PipelineError, sha256_of
from dtwin.medgemma_client import load_screening_config

PROTOCOL_SCHEMA = "argos-openswisshcc-v17-atlas-score-protocol-v1"
PREDICTION_SCHEMA = "argos-openswisshcc-v17-atlas-score-prediction-v1"
RUN_CONTEXT_SCHEMA = "argos-openswisshcc-v17-atlas-score-run-context-v1"
PROGRESS_SCHEMA = "argos-openswisshcc-v17-atlas-score-progress-v1"
SUMMARY_SCHEMA = "argos-openswisshcc-v17-atlas-score-summary-v1"
TIMING_PLAN_SCHEMA = "argos-openswisshcc-v17-atlas-timing-plan-v1"
TIMING_RESULT_SCHEMA = "argos-openswisshcc-v17-atlas-timing-result-v1"
CASE_TIME_GATE_SECONDS = 180.0
MAX_IMAGE_EDGE = 768
_FRAME_NAME = re.compile(r"^axial_atlas_frame_[0-9]{3}_of_[0-9]{3}\.png$")

INSTRUCTION = (
    "Analise um atlas axial completo de RM hepatica para pesquisa. Cada imagem recebida e um "
    "FRAME 2x2: quadrantes superior esquerdo, superior direito, inferior esquerdo e inferior "
    "direito representam cortes axiais consecutivos nessa ordem. Quadrantes totalmente pretos "
    "no ultimo frame sao preenchimento e devem ser ignorados. Inspecione sistematicamente todos "
    "os quadrantes e confirme continuidade em frames vizinhos. Em frames coloridos, vermelho "
    "representa arterial, verde portal/venoso e azul tardio; cor isolada nao prova doenca. Frames "
    "em escala de cinza sao fallback venoso valido. O alvo exclusivo e lesao focal hepatica "
    "suspeita. Vaso tubular continuo, veia calibrosa, variante anatomica, perfusao sem massa, "
    "volume parcial, cisto simples e artefato nao devem ser classificados como patologia alvo. "
    "Nao emita diagnostico definitivo nem recomendacao clinica."
)
QUERY_TEMPLATE = (
    "Foram recebidos {frame_count} frames contendo {tile_count} cortes reais, do indice axial "
    "{first_index} ao {last_index}. Representacao: {representation}. Classifique POSITIVA somente "
    "se houver lesao focal hepatica suspeita sustentada por morfologia focal e persistencia entre "
    "cortes; NEGATIVA quando nao houver lesao focal suspeita, inclusive variantes e mimetizadores; "
    "INCONCLUSIVA apenas quando a qualidade impedir a separacao. Complete somente o valor e feche "
    "o JSON iniciado."
)


def _load_json(path: Path, description: str) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def _safe_child(root: Path, relative: str) -> Path:
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise PipelineError("Caminho v17 escapou da raiz autorizada.")
    return path


def _validate_case_frames(case_dir: Path, manifest: dict) -> list[bytes]:
    frames = manifest.get("frames")
    atlas = manifest.get("atlas", {})
    if (
        not isinstance(frames, list)
        or len(frames) != atlas.get("frame_count")
        or not 5 <= len(frames) <= 32
    ):
        raise PipelineError("Quantidade de frames v17 inválida.")
    payloads: list[bytes] = []
    seen: set[str] = set()
    for number, frame in enumerate(frames, 1):
        filename = str(frame.get("image", ""))
        if (
            frame.get("frame_number") != number
            or frame.get("frame_total") != len(frames)
            or not _FRAME_NAME.fullmatch(filename)
            or filename in seen
        ):
            raise PipelineError("Nome ou ordem de frame v17 inválido.")
        seen.add(filename)
        path = _safe_child(case_dir, filename)
        if (
            not path.is_file()
            or path.stat().st_size != int(frame.get("bytes", -1))
            or sha256_of(path) != frame.get("sha256")
        ):
            raise PipelineError("Frame v17 ausente ou adulterado.")
        with Image.open(path) as image:
            image.load()
            if (
                image.format != "PNG"
                or image.mode != "RGB"
                or image.size not in {(640, 640), (768, 768)}
                or list(image.size) != frame.get("size_pixels")
            ):
                raise PipelineError("Frame v17 viola formato, modo ou dimensões congeladas.")
        payloads.append(path.read_bytes())
    return payloads


def validate_atlas_bundle(atlas_root: Path) -> dict:
    atlas_root = Path(atlas_root).resolve()
    cohort_path = atlas_root / "cohort_manifest.json"
    cohort = _load_json(cohort_path, "Manifesto de coorte v17")
    if (
        cohort.get("schema_version") != COHORT_SCHEMA
        or cohort.get("protocol_signature") != ATLAS_PROTOCOL_SIGNATURE
        or cohort.get("all_gates_passed") is not True
        or cohort.get("ground_truth_read") is not False
        or cohort.get("lesion_mask_read") is not False
        or cohort.get("holdout_read") is not False
        or cohort.get("eligible_for_inference") is not False
    ):
        raise PipelineError("Coorte atlas v17 violou schema ou salvaguardas.")
    records = cohort.get("cases")
    if not isinstance(records, list) or not records or len(records) != cohort.get("case_count"):
        raise PipelineError("Lista de casos do atlas v17 inconsistente.")
    cases, case_ids = [], []
    for record in records:
        case_id = str(record.get("case_id", ""))
        if not case_id.startswith("anon-openswiss-") or case_id in case_ids:
            raise PipelineError("case_id v17 inválido ou duplicado.")
        case_ids.append(case_id)
        manifest_path = _safe_child(atlas_root, str(record.get("manifest", "")))
        if sha256_of(manifest_path) != record.get("manifest_sha256"):
            raise PipelineError(f"Hash do manifesto v17 divergiu: {case_id}.")
        manifest = _load_json(manifest_path, "Manifesto de caso v17")
        atlas = manifest.get("atlas", {})
        if (
            manifest.get("schema_version") != CASE_SCHEMA
            or manifest.get("protocol_signature") != ATLAS_PROTOCOL_SIGNATURE
            or manifest.get("case_id") != case_id
            or manifest.get("ground_truth_read") is not False
            or manifest.get("lesion_mask_read") is not False
            or manifest.get("holdout_read") is not False
            or atlas.get("gate_passed") is not True
            or atlas.get("represented_axial_indices") != atlas.get("expected_axial_indices")
            or atlas.get("atlas_set_sha256") != record.get("atlas_set_sha256")
        ):
            raise PipelineError(f"Manifesto de caso v17 inválido: {case_id}.")
        payloads = _validate_case_frames(manifest_path.parent, manifest)
        cases.append(
            {
                "case_id": case_id,
                "case_dir": manifest_path.parent,
                "manifest": manifest,
                "manifest_sha256": record["manifest_sha256"],
                "atlas_set_sha256": record["atlas_set_sha256"],
                "frame_count": len(payloads),
                "tile_count": int(atlas["tile_count"]),
            }
        )
    return {
        "root": atlas_root,
        "cohort": cohort,
        "cohort_sha256": sha256_of(cohort_path),
        "case_ids": case_ids,
        "case_count": len(cases),
        "cases": cases,
        "maximum_frames": max(case["frame_count"] for case in cases),
    }


def validate_scoring_review(
    *, gallery_root: Path, review_path: Path, bundle: dict
) -> dict:
    gallery_root = Path(gallery_root).resolve()
    review_path = Path(review_path).resolve()
    gallery_path = gallery_root / "gallery_manifest.json"
    gallery = _load_json(gallery_path, "Manifesto da galeria full87 v17")
    review = _load_json(review_path, "Revisão humana full87 v17")
    confirmations = review.get("confirmations")
    unsigned = dict(review)
    signature = unsigned.pop("review_signature", None)
    if (
        gallery.get("schema_version") != GALLERY_SCHEMA
        or gallery.get("protocol_signature") != ATLAS_PROTOCOL_SIGNATURE
        or gallery.get("case_count") != bundle["case_count"]
        or gallery.get("ground_truth_read") is not False
        or gallery.get("lesion_mask_read") is not False
        or gallery.get("holdout_read") is not False
        or review.get("schema_version") != REVIEW_SCHEMA
        or review.get("status") != "approved_for_blind_4b_scoring"
        or review.get("approval_scope") != "blind_4b_scoring"
        or review.get("protocol_signature") != ATLAS_PROTOCOL_SIGNATURE
        or review.get("gallery_manifest_sha256") != sha256_of(gallery_path)
        or review.get("case_count") != bundle["case_count"]
        or not isinstance(confirmations, dict)
        or set(confirmations) != set(REQUIRED_REVIEW_CONFIRMATIONS)
        or not all(value is True for value in confirmations.values())
        or review.get("ground_truth_read") is not False
        or review.get("lesion_mask_read") is not False
        or review.get("holdout_read") is not False
        or signature != _canonical_hash(unsigned)
    ):
        raise PipelineError("Revisão humana full87 v17 ausente, divergente ou incompleta.")
    gallery_cases = gallery.get("cases")
    if not isinstance(gallery_cases, list):
        raise PipelineError("Galeria full87 v17 sem casos.")
    by_id = {case["case_id"]: case for case in bundle["cases"]}
    if {str(case.get("case_id", "")) for case in gallery_cases} != set(by_id):
        raise PipelineError("Galeria full87 v17 diverge da coorte do scorer.")
    for gallery_case in gallery_cases:
        case = by_id[str(gallery_case["case_id"])]
        expected = {frame["image"]: frame["sha256"] for frame in case["manifest"]["frames"]}
        observed = {
            Path(str(frame["image"])).name: frame["sha256"]
            for frame in gallery_case.get("frames", [])
        }
        if observed != expected:
            raise PipelineError(f"Frames da galeria divergiram: {case['case_id']}.")
    return review


def atlas_query(manifest: Mapping[str, object]) -> str:
    atlas = manifest.get("atlas")
    source = manifest.get("source")
    if not isinstance(atlas, dict) or not isinstance(source, dict):
        raise PipelineError("Manifesto v17 sem atlas ou fonte.")
    indices = atlas.get("represented_axial_indices")
    if not isinstance(indices, list) or not indices:
        raise PipelineError("Manifesto v17 sem índices axiais.")
    kind = source.get("candidate_kind")
    representation = (
        "fusao RGB arterial-portal/venosa-tardia"
        if kind == "multiphase_rgb"
        else "fallback venoso em escala de cinza"
        if kind == "venous_single_phase_fallback"
        else None
    )
    if representation is None:
        raise PipelineError("Representação v17 não autorizada para scorer.")
    return QUERY_TEMPLATE.format(
        frame_count=atlas["frame_count"],
        tile_count=atlas["tile_count"],
        first_index=indices[0],
        last_index=indices[-1],
        representation=representation,
    )


def score_log_odds(probabilities: Mapping[str, float]) -> float:
    positive = float(probabilities["POSITIVA"])
    negative = float(probabilities["NEGATIVA"])
    if not all(math.isfinite(value) and value >= 0 for value in (positive, negative)):
        raise PipelineError("Probabilidades v17 inválidas para log-odds.")
    return math.log((positive + 1e-8) / (negative + 1e-8))


def freeze_score_protocol(
    *,
    atlas_root: Path,
    gallery_root: Path,
    review_path: Path,
    config_path: Path,
    out_path: Path,
) -> dict:
    bundle = validate_atlas_bundle(atlas_root)
    if bundle["case_count"] != 87:
        raise PipelineError("Scorer v17 exige o full87 completo.")
    review = validate_scoring_review(
        gallery_root=gallery_root, review_path=review_path, bundle=bundle
    )
    med = load_screening_config(config_path)["medgemma"]
    base = {
        "schema_version": PROTOCOL_SCHEMA,
        "status": "frozen_before_blind_4b_scores",
        "atlas_protocol_signature": ATLAS_PROTOCOL_SIGNATURE,
        "atlas_cohort_sha256": bundle["cohort_sha256"],
        "review_sha256": sha256_of(Path(review_path).resolve()),
        "review_signature": review["review_signature"],
        "case_ids": bundle["case_ids"],
        "case_count": bundle["case_count"],
        "maximum_frames": bundle["maximum_frames"],
        "model_id": med["model_id"],
        "model_version": med["model_version"],
        "contract": CONTRACT,
        "endpoint_url": _score_url(str(med["endpoint_url"])),
        "instruction": INSTRUCTION,
        "query_template": QUERY_TEMPLATE,
        "scoring": {
            "response_prefix": RESPONSE_PREFIX,
            "choices": list(CHOICES),
            "method": SCORING_METHOD,
            "requests_per_case": 1,
            "automatic_retries": 0,
            "score": "log_odds_positive_vs_negative",
            "epsilon": 1e-8,
            "probability_tolerance": PROBABILITY_TOLERANCE,
        },
        "case_time_gate_seconds": CASE_TIME_GATE_SECONDS,
        "maximum_image_edge": MAX_IMAGE_EDGE,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    protocol = dict(base)
    protocol["protocol_signature"] = _canonical_hash(base)
    out_path = Path(out_path)
    if out_path.exists():
        if _load_json(out_path, "Protocolo scorer v17") != protocol:
            raise PipelineError("Protocolo scorer v17 existente diverge; sobrescrita recusada.")
        return protocol
    _atomic_json(out_path, protocol)
    return protocol


def _load_protocol(path: Path) -> dict:
    protocol = _load_json(path, "Protocolo scorer v17")
    signature = protocol.pop("protocol_signature", None)
    if signature != _canonical_hash(protocol):
        raise PipelineError("Assinatura do protocolo scorer v17 diverge.")
    protocol["protocol_signature"] = signature
    scoring = protocol.get("scoring", {})
    if (
        protocol.get("schema_version") != PROTOCOL_SCHEMA
        or protocol.get("status") != "frozen_before_blind_4b_scores"
        or protocol.get("atlas_protocol_signature") != ATLAS_PROTOCOL_SIGNATURE
        or protocol.get("contract") != CONTRACT
        or protocol.get("instruction") != INSTRUCTION
        or protocol.get("query_template") != QUERY_TEMPLATE
        or scoring.get("method") != SCORING_METHOD
        or scoring.get("choices") != list(CHOICES)
        or scoring.get("requests_per_case") != 1
        or scoring.get("automatic_retries") != 0
        or protocol.get("case_time_gate_seconds") != CASE_TIME_GATE_SECONDS
        or protocol.get("maximum_image_edge") != MAX_IMAGE_EDGE
        or protocol.get("ground_truth_read") is not False
        or protocol.get("metrics_calculated") is not False
        or protocol.get("holdout_opened") is not False
    ):
        raise PipelineError("Protocolo scorer v17 não está congelado ou viola salvaguardas.")
    return protocol


def _validate_context(
    *, atlas_root: Path, protocol_path: Path, config_path: Path
) -> tuple[dict, dict, dict]:
    bundle = validate_atlas_bundle(atlas_root)
    protocol = _load_protocol(protocol_path)
    med = load_screening_config(config_path)["medgemma"]
    if (
        protocol["atlas_cohort_sha256"] != bundle["cohort_sha256"]
        or protocol["case_ids"] != bundle["case_ids"]
        or protocol["model_id"] != med["model_id"]
        or protocol["model_version"] != med["model_version"]
        or protocol["endpoint_url"] != _score_url(str(med["endpoint_url"]))
    ):
        raise PipelineError("Atlas, config ou protocolo scorer v17 divergiram.")
    health = _request_json(
        Request(
            str(med["healthcheck_url"]),
            headers={"Accept": "application/json"},
            method="GET",
        ),
        timeout=15,
    )
    if (
        health.get("status") != "ready"
        or health.get("model_id") != protocol["model_id"]
        or health.get("model_version") != protocol["model_version"]
        or health.get("volume_score_contract") != CONTRACT
        or health.get("volume_score_method") != SCORING_METHOD
        or health.get("volume_score_supported") is not True
        or int(health.get("volume_score_max_image_edge", 0)) < MAX_IMAGE_EDGE
    ):
        raise PipelineError("Health não confirmou o contrato atlas v17.")
    return bundle, protocol, health


def _score_case(*, case: dict, protocol: dict, health: dict, out_path: Path) -> dict:
    manifest = case["manifest"]
    images = _validate_case_frames(case["case_dir"], manifest)
    query = atlas_query(manifest)
    payload = {
        "contract": CONTRACT,
        "model_id": protocol["model_id"],
        "model_version": protocol["model_version"],
        "instruction": protocol["instruction"],
        "images": [
            {"mime_type": "image/png", "base64": base64.b64encode(raw).decode("ascii")}
            for raw in images
        ],
        "query": query,
        "scoring": {"response_prefix": protocol["scoring"]["response_prefix"]},
    }
    request = Request(
        protocol["endpoint_url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    response = _request_json(request, timeout=CASE_TIME_GATE_SECONDS)
    elapsed = time.monotonic() - started
    if elapsed > CASE_TIME_GATE_SECONDS:
        raise PipelineError(f"Caso {case['case_id']} excedeu o gate temporal v17.")
    validated = _validate_score_response(
        response, protocol=protocol, slice_count=len(images)
    )
    result = {
        "schema_version": PREDICTION_SCHEMA,
        "status": "technical_passed",
        "case_id": case["case_id"],
        "protocol_signature": protocol["protocol_signature"],
        "atlas_manifest_sha256": case["manifest_sha256"],
        "atlas_set_sha256": case["atlas_set_sha256"],
        "frame_count": len(images),
        "tile_count": case["tile_count"],
        "query_sha256": _canonical_hash({"query": query}),
        "classification": validated["classification"],
        "choice_probabilities": validated["choice_probabilities"],
        "choice_token_metadata": validated["choice_token_metadata"],
        "tie_detected": validated["tie_detected"],
        "log_odds_positive_vs_negative": score_log_odds(
            validated["choice_probabilities"]
        ),
        "request_elapsed_seconds": round(elapsed, 4),
        "gateway_timings_seconds": response.get("timings_seconds"),
        "case_time_gate_seconds": CASE_TIME_GATE_SECONDS,
        "time_gate_passed": True,
        "health_model_id": health.get("model_id"),
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    _atomic_json(out_path, result)
    return result


def _validate_existing_prediction(path: Path, case: dict, protocol: dict) -> dict:
    result = _load_json(path, "Predição atlas v17")
    if (
        result.get("schema_version") != PREDICTION_SCHEMA
        or result.get("status") != "technical_passed"
        or result.get("case_id") != case["case_id"]
        or result.get("protocol_signature") != protocol["protocol_signature"]
        or result.get("atlas_manifest_sha256") != case["manifest_sha256"]
        or result.get("atlas_set_sha256") != case["atlas_set_sha256"]
        or result.get("frame_count") != case["frame_count"]
        or result.get("tile_count") != case["tile_count"]
        or result.get("query_sha256") != _canonical_hash(
            {"query": atlas_query(case["manifest"])}
        )
        or result.get("time_gate_passed") is not True
        or float(result.get("request_elapsed_seconds", 181)) > CASE_TIME_GATE_SECONDS
        or result.get("ground_truth_read") is not False
        or result.get("metrics_calculated") is not False
        or result.get("holdout_opened") is not False
    ):
        raise PipelineError("Predição atlas v17 existente não é reutilizável.")
    response = {
        "contract": CONTRACT,
        "model_id": protocol["model_id"],
        "model_version": protocol["model_version"],
        "slice_count": case["frame_count"],
        "choice": result.get("classification"),
        "choice_probabilities": result.get("choice_probabilities"),
        "scoring_method": SCORING_METHOD,
        "choice_token_metadata": result.get("choice_token_metadata"),
        "tie_detected": result.get("tie_detected"),
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    validated = _validate_score_response(
        response, protocol=protocol, slice_count=case["frame_count"]
    )
    if not math.isclose(
        float(result.get("log_odds_positive_vs_negative")),
        score_log_odds(validated["choice_probabilities"]),
        rel_tol=0,
        abs_tol=1e-12,
    ):
        raise PipelineError("Log-odds reutilizado v17 foi alterado.")
    return result


def run_blind_batch(
    *,
    atlas_root: Path,
    protocol_path: Path,
    config_path: Path,
    output_root: Path,
    max_new_cases: int | None = None,
    progress_callback=None,
) -> dict:
    if max_new_cases is not None and max_new_cases < 1:
        raise PipelineError("max_new_cases v17 deve ser positivo.")
    bundle, protocol, health = _validate_context(
        atlas_root=atlas_root, protocol_path=protocol_path, config_path=config_path
    )
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    context = {
        "schema_version": RUN_CONTEXT_SCHEMA,
        "protocol_signature": protocol["protocol_signature"],
        "atlas_cohort_sha256": bundle["cohort_sha256"],
        "case_ids": bundle["case_ids"],
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
    }
    context_path = output_root / "run_context.json"
    if context_path.exists() and _load_json(context_path, "Contexto scorer v17") != context:
        raise PipelineError("Diretório de saída v17 pertence a outro protocolo.")
    if not context_path.exists():
        _atomic_json(context_path, context)
    predictions_dir = output_root / "predictions"
    predictions_dir.mkdir(exist_ok=True)
    predictions, new_count = [], 0
    for index, case in enumerate(bundle["cases"], 1):
        path = predictions_dir / f"{case['case_id']}.json"
        reused = path.exists()
        if reused:
            result = _validate_existing_prediction(path, case, protocol)
        elif max_new_cases is not None and new_count >= max_new_cases:
            continue
        else:
            result = _score_case(
                case=case, protocol=protocol, health=health, out_path=path
            )
            new_count += 1
        predictions.append(result)
        if progress_callback:
            progress_callback(
                {
                    "index": index,
                    "case_count": bundle["case_count"],
                    "case_id": case["case_id"],
                    "frame_count": case["frame_count"],
                    "request_elapsed_seconds": result["request_elapsed_seconds"],
                    "reused": reused,
                }
            )
    records = [
        {
            "case_id": result["case_id"],
            "prediction_sha256": sha256_of(
                predictions_dir / f"{result['case_id']}.json"
            ),
            "classification": result["classification"],
            "log_odds_positive_vs_negative": result[
                "log_odds_positive_vs_negative"
            ],
            "request_elapsed_seconds": result["request_elapsed_seconds"],
        }
        for result in predictions
    ]
    progress = {
        "schema_version": PROGRESS_SCHEMA,
        "status": "complete" if len(records) == bundle["case_count"] else "partial",
        "protocol_signature": protocol["protocol_signature"],
        "case_count": bundle["case_count"],
        "completed_case_count": len(records),
        "pending_case_count": bundle["case_count"] - len(records),
        "predictions": records,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
    }
    _atomic_json(output_root / "progress.json", progress)
    if progress["status"] != "complete":
        return progress
    timings = [float(result["request_elapsed_seconds"]) for result in predictions]
    summary = {
        **progress,
        "schema_version": SUMMARY_SCHEMA,
        "request_count": len(predictions),
        "request_timing_seconds": {
            "minimum": min(timings),
            "median": statistics.median(timings),
            "mean": statistics.fmean(timings),
            "maximum": max(timings),
            "all_within_180": all(value <= CASE_TIME_GATE_SECONDS for value in timings),
        },
        "timing_scope": "precomputed_atlas_scoring_only",
        "end_to_end_180_seconds_proven": False,
        "accuracy_claimed": False,
    }
    _atomic_json(output_root / "summary.json", summary)
    return summary


def _case_pixel_workload(case: Mapping[str, object]) -> int:
    manifest = case.get("manifest")
    if not isinstance(manifest, dict):
        raise PipelineError("Caso v17 sem manifesto para carga temporal.")
    frames = manifest.get("frames")
    if not isinstance(frames, list) or not frames:
        raise PipelineError("Caso v17 sem frames para carga temporal.")
    total = 0
    for frame in frames:
        size = frame.get("size_pixels")
        if not isinstance(size, list) or len(size) != 2:
            raise PipelineError("Frame v17 sem dimensão para carga temporal.")
        total += int(size[0]) * int(size[1])
    return total


def select_timing_cases(bundle: Mapping[str, object]) -> list[dict]:
    """Seleciona sentinelas apenas por carga e representação, nunca por label."""
    cases = bundle.get("cases")
    if not isinstance(cases, list) or not cases:
        raise PipelineError("Bundle v17 vazio para piloto temporal.")
    rows = [
        {
            "case": case,
            "case_id": str(case["case_id"]),
            "pixel_workload": _case_pixel_workload(case),
            "frame_count": int(case["frame_count"]),
            "representation": case["manifest"]["source"]["candidate_kind"],
        }
        for case in cases
    ]
    rgb = [row for row in rows if row["representation"] == "multiphase_rgb"]
    fallback = [
        row
        for row in rows
        if row["representation"] == "venous_single_phase_fallback"
    ]
    if not rgb or not fallback:
        raise PipelineError("Piloto temporal v17 exige RGB e fallback venoso.")
    by_descending_load = sorted(
        rows, key=lambda row: (-row["pixel_workload"], row["case_id"])
    )
    by_ascending_load = sorted(
        rows, key=lambda row: (row["pixel_workload"], row["case_id"])
    )
    proposals = [
        (by_descending_load[0], "maximum_pixel_workload_overall"),
        (
            sorted(rgb, key=lambda row: (-row["pixel_workload"], row["case_id"]))[0],
            "maximum_pixel_workload_rgb",
        ),
        (
            sorted(
                fallback,
                key=lambda row: (-row["pixel_workload"], row["case_id"]),
            )[0],
            "maximum_pixel_workload_venous_fallback",
        ),
        (by_ascending_load[len(by_ascending_load) // 2], "median_pixel_workload"),
    ]
    selected: dict[str, dict] = {}
    for row, reason in proposals:
        record = selected.setdefault(
            row["case_id"],
            {
                "case_id": row["case_id"],
                "selection_reasons": [],
                "pixel_workload": row["pixel_workload"],
                "frame_count": row["frame_count"],
                "representation": row["representation"],
                "atlas_manifest_sha256": row["case"]["manifest_sha256"],
                "atlas_set_sha256": row["case"]["atlas_set_sha256"],
            },
        )
        record["selection_reasons"].append(reason)
    for row in by_descending_load:
        if len(selected) >= 4:
            break
        if row["case_id"] not in selected:
            selected[row["case_id"]] = {
                "case_id": row["case_id"],
                "selection_reasons": ["highest_unselected_workload_to_complete_four"],
                "pixel_workload": row["pixel_workload"],
                "frame_count": row["frame_count"],
                "representation": row["representation"],
                "atlas_manifest_sha256": row["case"]["manifest_sha256"],
                "atlas_set_sha256": row["case"]["atlas_set_sha256"],
            }
    return list(selected.values())


def freeze_timing_plan(
    *, atlas_root: Path, protocol_path: Path, output_path: Path
) -> dict:
    bundle = validate_atlas_bundle(atlas_root)
    protocol = _load_protocol(protocol_path)
    if (
        bundle["cohort_sha256"] != protocol.get("atlas_cohort_sha256")
        or bundle["case_ids"] != protocol.get("case_ids")
    ):
        raise PipelineError("Atlas e protocolo divergiram no plano temporal v17.")
    base = {
        "schema_version": TIMING_PLAN_SCHEMA,
        "status": "frozen_before_timing_inference",
        "protocol_signature": protocol["protocol_signature"],
        "atlas_cohort_sha256": bundle["cohort_sha256"],
        "selection_method": "blind_pixel_workload_and_representation_v1",
        "case_count": 4,
        "cases": select_timing_cases(bundle),
        "case_time_gate_seconds": CASE_TIME_GATE_SECONDS,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    if len(base["cases"]) != 4:
        raise PipelineError("Plano temporal v17 não selecionou quatro casos únicos.")
    plan = dict(base)
    plan["plan_signature"] = _canonical_hash(base)
    output_path = Path(output_path)
    if output_path.exists():
        if _load_json(output_path, "Plano temporal v17") != plan:
            raise PipelineError("Plano temporal v17 existente diverge.")
        return plan
    _atomic_json(output_path, plan)
    return plan


def _load_timing_plan(path: Path, *, protocol: dict, bundle: dict) -> dict:
    plan = _load_json(path, "Plano temporal v17")
    signature = plan.pop("plan_signature", None)
    if signature != _canonical_hash(plan):
        raise PipelineError("Assinatura do plano temporal v17 diverge.")
    plan["plan_signature"] = signature
    if (
        plan.get("schema_version") != TIMING_PLAN_SCHEMA
        or plan.get("status") != "frozen_before_timing_inference"
        or plan.get("protocol_signature") != protocol["protocol_signature"]
        or plan.get("atlas_cohort_sha256") != bundle["cohort_sha256"]
        or plan.get("selection_method")
        != "blind_pixel_workload_and_representation_v1"
        or plan.get("case_count") != 4
        or plan.get("case_time_gate_seconds") != CASE_TIME_GATE_SECONDS
        or plan.get("ground_truth_read") is not False
        or plan.get("metrics_calculated") is not False
        or plan.get("holdout_opened") is not False
    ):
        raise PipelineError("Plano temporal v17 inválido ou incompatível.")
    by_id = {case["case_id"]: case for case in bundle["cases"]}
    for record in plan.get("cases", []):
        case = by_id.get(record.get("case_id"))
        if (
            case is None
            or record.get("atlas_manifest_sha256") != case["manifest_sha256"]
            or record.get("atlas_set_sha256") != case["atlas_set_sha256"]
            or record.get("frame_count") != case["frame_count"]
            or record.get("pixel_workload") != _case_pixel_workload(case)
        ):
            raise PipelineError("Caso do plano temporal v17 divergiu do atlas.")
    return plan


def run_timing_plan(
    *,
    atlas_root: Path,
    protocol_path: Path,
    plan_path: Path,
    config_path: Path,
    output_root: Path,
    max_new_cases: int | None = None,
    progress_callback=None,
) -> dict:
    if max_new_cases is not None and max_new_cases < 1:
        raise PipelineError("max_new_cases temporal v17 deve ser positivo.")
    bundle, protocol, health = _validate_context(
        atlas_root=atlas_root, protocol_path=protocol_path, config_path=config_path
    )
    plan = _load_timing_plan(plan_path, protocol=protocol, bundle=bundle)
    by_id = {case["case_id"]: case for case in bundle["cases"]}
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    predictions_dir = output_root / "predictions"
    predictions_dir.mkdir(exist_ok=True)
    results, new_count = [], 0
    for record in plan["cases"]:
        case = by_id[record["case_id"]]
        path = predictions_dir / f"{case['case_id']}.json"
        reused = path.exists()
        if reused:
            result = _validate_existing_prediction(path, case, protocol)
        elif max_new_cases is not None and new_count >= max_new_cases:
            continue
        else:
            result = _score_case(
                case=case, protocol=protocol, health=health, out_path=path
            )
            new_count += 1
        results.append(result)
        if progress_callback:
            progress_callback(
                {
                    "case_id": case["case_id"],
                    "frame_count": case["frame_count"],
                    "request_elapsed_seconds": result["request_elapsed_seconds"],
                    "reused": reused,
                }
            )
    timings = [float(result["request_elapsed_seconds"]) for result in results]
    report = {
        "schema_version": TIMING_RESULT_SCHEMA,
        "status": "complete" if len(results) == len(plan["cases"]) else "partial",
        "protocol_signature": protocol["protocol_signature"],
        "plan_signature": plan["plan_signature"],
        "planned_case_count": len(plan["cases"]),
        "completed_case_count": len(results),
        "pending_case_count": len(plan["cases"]) - len(results),
        "results": [
            {
                "case_id": result["case_id"],
                "prediction_sha256": sha256_of(
                    predictions_dir / f"{result['case_id']}.json"
                ),
                "frame_count": result["frame_count"],
                "request_elapsed_seconds": result["request_elapsed_seconds"],
                "time_gate_passed": result["time_gate_passed"],
            }
            for result in results
        ],
        "timing_seconds": (
            {
                "minimum": min(timings),
                "median": statistics.median(timings),
                "mean": statistics.fmean(timings),
                "maximum": max(timings),
                "all_within_180": all(value <= CASE_TIME_GATE_SECONDS for value in timings),
            }
            if timings
            else None
        ),
        "timing_scope": "precomputed_atlas_scoring_only",
        "end_to_end_180_seconds_proven": False,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "accuracy_claimed": False,
    }
    _atomic_json(output_root / "timing_report.json", report)
    return report

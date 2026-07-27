"""Independent, label-free verification of Phase 5 and Phase 13 artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from dtwin.core import PipelineError
from dtwin.learning.protocol import canonical_sha256, sha256_file


def _json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON inválido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"Objeto JSON esperado: {path}")
    return value


def _rows(path: Path) -> list[dict]:
    try:
        values = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSONL inválido: {path}") from exc
    if any(not isinstance(row, dict) for row in values):
        raise PipelineError(f"Registro inválido: {path}")
    return values


def _signed(value: dict, key: str) -> bool:
    unsigned = dict(value)
    signature = unsigned.pop(key, None)
    return signature == canonical_sha256(unsigned)


def verify(config_path: Path, output_path: Path) -> dict:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if (
        not isinstance(config, dict)
        or config.get("schema")
        != "argos-hybrid-phase13-verification-config-v1"
    ):
        raise PipelineError("Config de verificação Phase 13 inválida.")
    expected = int(config["expected_case_count"])
    roots = {
        "phase5": Path(
            "casos/qualification/hybrid_v1/medsiglip_oof_predictions_v1"
        ),
        "head_only": Path(
            "casos/qualification/hybrid_v1/medsiglip_head_oof_predictions_v1"
        ),
        "last_block": Path(
            "casos/qualification/hybrid_v1/medsiglip_partial_oof_predictions_v1"
        ),
        "lora": Path(
            "casos/qualification/hybrid_v1/medsiglip_lora_oof_predictions_v1"
        ),
    }
    checks: dict[str, dict] = {}
    phase5_freeze = roots["phase5"] / "prediction_freeze.json"
    phase5_evaluation = Path(
        "casos/qualification/hybrid_v1/"
        "medsiglip_oof_evaluation_v1/evaluation.json"
    )
    if sha256_file(phase5_freeze) != config["phase5_prediction_freeze_sha256"]:
        raise PipelineError("Artefato congelado da Fase 5 foi alterado.")
    if sha256_file(phase5_evaluation) != config["phase5_evaluation_sha256"]:
        raise PipelineError("Avaliação congelada da Fase 5 foi alterada.")
    for name, root in roots.items():
        freeze_path = root / "prediction_freeze.json"
        predictions_path = root / "oof_predictions.jsonl"
        freeze = _json(freeze_path)
        if not _signed(freeze, "prediction_signature"):
            raise PipelineError(f"Assinatura inválida em {name}.")
        if freeze.get("oof_predictions_sha256") != sha256_file(predictions_path):
            raise PipelineError(f"Predições alteradas em {name}.")
        rows = _rows(predictions_path)
        case_ids = [str(row.get("case_id")) for row in rows]
        if len(rows) != expected or len(set(case_ids)) != expected:
            raise PipelineError(f"Cobertura OOF inválida em {name}.")
        forbidden = {"label", "ground_truth", "lesion_mask", "target"}
        leaked = [
            case_id
            for case_id, row in zip(case_ids, rows)
            if forbidden & set(row)
        ]
        if leaked:
            raise PipelineError(f"Ground truth persistido em {name}.")
        checks[name] = {
            "prediction_signature": freeze["prediction_signature"],
            "prediction_freeze_sha256": sha256_file(freeze_path),
            "oof_predictions_sha256": sha256_file(predictions_path),
            "case_count": len(rows),
            "technical_failure_count": sum(
                bool(row.get("technical_failure")) for row in rows
            ),
            "ground_truth_fields_found": 0,
        }
    body = {
        "schema": "argos-hybrid-phase13-independent-verification-v1",
        "status": "passed",
        "config_sha256": sha256_file(config_path),
        "phase5_preserved_unchanged": True,
        "checks": checks,
        "labels_read": 0,
        "lesion_masks_read": 0,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    result = {**body, "verification_signature": canonical_sha256(body)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path,
        default=Path("configs/training/phase13_verification_v1.yaml"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path(
            "casos/qualification/hybrid_v1/"
            "phase13_independent_verification_v1.json"
        ),
    )
    args = parser.parse_args()
    print(
        json.dumps(
            verify(args.config, args.output),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

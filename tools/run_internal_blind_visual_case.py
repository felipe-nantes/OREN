"""Run one label-blind internal DICOM case through the visual Etapa C flow.

This is the operational handoff entrypoint for the first real GPU smoke test.
It reads no benchmark labels or lesion masks.  Phase resolution is delegated to
the authorized server-side adapter and every downstream stage is the same one
used by the webapp visual benchmark.
"""
from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from dtwin.core import PipelineError
from dtwin.learning.internal_blind_phase_adapter import (
    BLIND_CASE_PATTERN,
    summarize_authorized_blind_phase_eligibility,
)
from webapp import server


def _write_json_atomic(path: Path, value: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case-id",
        default="auto",
        help="ARGOS-BLIND-#### ou 'auto' para o primeiro caso elegível.",
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path("ARGOS_INTERNAL_BLIND_BENCHMARK_120_V1"),
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("casos/webapp"),
    )
    parser.add_argument(
        "--scenario",
        choices=sorted(server.VISUAL_BENCHMARK_SCENARIOS),
        default="hybrid_supervised",
    )
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Persiste somente elegibilidade label-blind; não usa GPU.",
    )
    args = parser.parse_args()

    dataset_root = args.dataset_root.resolve()
    audit_path = dataset_root / "private_reference" / "conversion_audit.json"
    if not audit_path.is_file():
        print("[ERRO] Dataset ou índice autorizado não encontrado.")
        return 2
    try:
        eligibility = summarize_authorized_blind_phase_eligibility(audit_path)
    except PipelineError as exc:
        print(f"[ERRO] {exc}")
        return 2
    if args.preflight_only:
        _write_json_atomic(args.out, eligibility)
        print(
            f"[OK] preflight: {eligibility['eligible_count']} elegíveis / "
            f"{eligibility['ineligible_count']} inelegíveis; relatório={args.out}"
        )
        return 0

    case_id = str(args.case_id)
    if case_id == "auto":
        eligible = eligibility["eligible_case_ids"]
        if not eligible:
            print("[ERRO] Nenhum caso multifásico elegível.")
            return 2
        case_id = str(eligible[0])
    if not BLIND_CASE_PATTERN.fullmatch(case_id):
        print("[ERRO] --case-id deve seguir ARGOS-BLIND-#### ou ser 'auto'.")
        return 2
    if case_id not in eligibility["eligible_case_ids"]:
        print("[ERRO] Caso não é elegível para o protocolo multifásico.")
        return 2
    case_dir = dataset_root / "webapp_input" / case_id
    if not case_dir.is_dir():
        print("[ERRO] Diretório público do caso não encontrado.")
        return 2

    # These are local operator settings, never values received from a browser.
    server.WORKSPACE = args.workspace.resolve()
    server.VISUAL_AUTHORIZED_PHASE_AUDIT = str(audit_path)
    run_id = args.run_id or f"internal-blind-visual-{case_id.lower()}-{uuid.uuid4().hex[:8]}"

    try:
        result = server._run_visual_benchmark_case(
            run_id,
            1,
            {"id": case_id, "dataset": "ARGOS_INTERNAL_BLIND_BENCHMARK_120_V1"},
            case_dir,
            args.scenario,
        )
    except PipelineError as exc:
        print(f"[ERRO] {exc}")
        return 2
    _write_json_atomic(args.out, result)
    if result.get("status") != "decisive":
        print(
            f"[FALHA TÉCNICA] status={result.get('status')} "
            f"erro={result.get('error')} relatório={args.out}"
        )
        return 2
    print(
        f"[OK] {case_id}: {result.get('prediction')} "
        f"em {result.get('duration_seconds')} s; relatório={args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

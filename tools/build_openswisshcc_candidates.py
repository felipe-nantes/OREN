"""Constrói em lote candidatos OpenSwissHCC sem abrir o ground truth."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from dtwin.core import PipelineError


def _case_ids(input_root: Path) -> list[str]:
    manifest = input_root / "manifests" / "development_inputs.jsonl"
    try:
        rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Manifesto neutro inválido: {exc}") from exc
    case_ids = [str(row.get("case_id", "")) for row in rows]
    if len(case_ids) != len(set(case_ids)) or any(not case.startswith("anon-") for case in case_ids):
        raise PipelineError("Manifesto contém case_id inválido ou duplicado.")
    if any(set(row) & {"label", "truth", "hcc", "positive", "negative"} for row in rows):
        raise PipelineError("Manifesto de construção contém ground truth protegido.")
    return sorted(case_ids)


def _run(command: list[str], timeout: int, cwd: Path) -> tuple[str, float]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    elapsed = time.perf_counter() - started
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise PipelineError(detail[-4000:] or f"Subprocesso retornou {completed.returncode}.")
    return completed.stdout.strip(), elapsed


def _write_atomic(path: Path, payload: object) -> None:
    temporary = path.with_name(f".tmp-{uuid.uuid4().hex}")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Constrói painéis OpenSwissHCC sem inferência.")
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--transforms", required=True, type=Path)
    parser.add_argument("--alignments", required=True, type=Path)
    parser.add_argument("--panels", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--minimum-dice", type=float, default=0.80)
    parser.add_argument("--alignment-timeout", type=int, default=150)
    parser.add_argument("--render-timeout", type=int, default=30)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()

    cwd = Path.cwd().resolve()
    inputs = args.inputs.resolve()
    all_ids = _case_ids(inputs)
    selected = sorted(set(args.case_id)) if args.case_id else all_ids
    unknown = set(selected) - set(all_ids)
    if unknown:
        raise PipelineError(f"case_id fora do manifesto neutro: {sorted(unknown)}.")
    if args.summary.exists():
        raise PipelineError("Resumo do lote já existe; não será sobrescrito.")
    args.summary.parent.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, object]] = []
    for index, case_id in enumerate(selected, start=1):
        record: dict[str, object] = {"case_id": case_id}
        align_command = [
            sys.executable, "-B", "-m", "tools.align_openswisshcc",
            "--case-id", case_id,
            "--inputs", str(inputs),
            "--transforms", str(args.transforms.resolve()),
            "--out", str(args.alignments.resolve()),
            "--minimum-dice", str(args.minimum_dice),
        ]
        try:
            stdout, elapsed = _run(align_command, args.alignment_timeout, cwd)
            alignment = json.loads(stdout)
            record.update(
                status="aligned",
                alignment_seconds=elapsed,
                alignment_cache_reused=bool(alignment.get("cache_reused")),
            )
        except subprocess.TimeoutExpired:
            record.update(status="alignment_timeout", alignment_seconds=args.alignment_timeout)
        except (PipelineError, json.JSONDecodeError) as exc:
            message = str(exc)
            status = "alignment_gate_failure" if "AlignmentGateError" in message else "alignment_failure"
            record.update(status=status, error=message[-1000:])

        if record["status"] == "aligned":
            render_command = [
                sys.executable, "-B", "-m", "tools.render_openswisshcc_candidate",
                "--case-id", case_id,
                "--inputs", str(inputs),
                "--alignments", str(args.alignments.resolve()),
                "--out", str(args.panels.resolve()),
                "--config", str(args.config.resolve()),
                "--profile", str(args.profile.resolve()),
            ]
            try:
                stdout, elapsed = _run(render_command, args.render_timeout, cwd)
                panel = json.loads(stdout)
                record.update(
                    status="panel_ready_review_pending",
                    render_seconds=elapsed,
                    panel_cache_reused=bool(panel.get("cache_reused")),
                    eligible_for_inference=bool(panel.get("eligible_for_inference")),
                    panel_sha256=panel.get("panel_sha256"),
                )
            except subprocess.TimeoutExpired:
                record.update(status="render_timeout", render_seconds=args.render_timeout)
            except (PipelineError, json.JSONDecodeError) as exc:
                record.update(status="render_failure", error=str(exc)[-1000:])

        records.append(record)
        print(
            json.dumps(
                {"index": index, "total": len(selected), **record},
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )

    counts: dict[str, int] = {}
    for record in records:
        status = str(record["status"])
        counts[status] = counts.get(status, 0) + 1
    summary = {
        "schema": "argos-public-liver-mri-candidate-build-v1",
        "case_count": len(records),
        "status_counts": counts,
        "visible_phi_confirmed": False,
        "inference_executed": False,
        "ground_truth_read": False,
        "alignment_timeout_seconds": args.alignment_timeout,
        "render_timeout_seconds": args.render_timeout,
        "records": records,
    }
    _write_atomic(args.summary, summary)
    print(json.dumps({"summary": str(args.summary), "status_counts": counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


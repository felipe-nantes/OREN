"""Phase-10 robustness/subgroup diagnostics over one or more frozen candidates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.robustness import evaluate_robustness, render_markdown_report


def _parse_candidate(value: str) -> tuple[str, Path]:
    name, _, path = value.partition("=")
    if not name or not path:
        raise argparse.ArgumentTypeError("Use o formato nome=caminho para --candidate.")
    return name, Path(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidate",
        dest="candidates",
        action="append",
        type=_parse_candidate,
        required=True,
        help="nome=caminho_para_raiz_do_candidato (repita para comparar vários lado a lado)",
    )
    parser.add_argument(
        "--training-config",
        type=Path,
        default=Path("configs/training/hybrid_v1_protocol.yaml"),
    )
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--n-resamples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260724)
    args = parser.parse_args()

    output_root = Path(args.output).resolve()
    if output_root.exists():
        raise SystemExit(f"Saída já existe; escolha outro diretório: {output_root}")
    output_root.mkdir(parents=True)

    comparison_rows: list[str] = [
        "| Candidato | Sensibilidade | Especificidade | AUC | Pior dataset sens. | Pior dataset esp. |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    reports = {}
    for name, path in args.candidates:
        report = evaluate_robustness(
            candidate_root=path,
            training_protocol_config_path=args.training_config,
            workspace_root=args.workspace_root,
            n_resamples=args.n_resamples,
            seed=args.seed,
        )
        reports[name] = report
        candidate_dir = output_root / name
        candidate_dir.mkdir(parents=True)
        (candidate_dir / "robustness_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (candidate_dir / "robustness_report.md").write_text(
            render_markdown_report(report), encoding="utf-8"
        )
        overall = report["overall"]
        comparison_rows.append(
            f"| {name} | {100*overall['sensitivity']:.2f}% | {100*overall['specificity']:.2f}% | "
            f"{overall['roc_auc_computable_cases']} | "
            f"{report['stability']['worst_dataset_sensitivity']} | "
            f"{report['stability']['worst_dataset_specificity']} |"
        )

    (output_root / "comparison.md").write_text("\n".join(comparison_rows) + "\n", encoding="utf-8")
    print(json.dumps({name: r["report_signature"] for name, r in reports.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

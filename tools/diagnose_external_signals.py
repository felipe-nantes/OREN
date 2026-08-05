from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.external_signal_diagnostics import build_external_signal_diagnostics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prediction-root", action="append", required=True)
    parser.add_argument("--protocol-config", type=Path, default=Path("configs/training/hybrid_v1_protocol.yaml"))
    parser.add_argument("--protected-dataset-id", action="append", required=True)
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    roots = {}
    for item in args.prediction_root:
        if "=" not in item:
            raise SystemExit(f"Mapeamento invalido: {item}")
        name, path = item.split("=", 1)
        roots[name] = Path(path)
    result = build_external_signal_diagnostics(
        prediction_roots=roots, training_protocol_config_path=args.protocol_config,
        workspace_root=args.workspace_root,
        protected_dataset_ids=set(args.protected_dataset_id), output_path=args.out,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

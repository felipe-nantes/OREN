"""Verificador independente dos artefatos físicos de volumetria do OREN."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.volumetry import verify_volumetry_artifacts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("outputs", type=Path, help="Pasta outputs/ do caso")
    parser.add_argument("--out", type=Path, default=None, help="Recibo JSON opcional")
    args = parser.parse_args()
    receipt = verify_volumetry_artifacts(args.outputs)
    rendered = json.dumps(receipt, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.out.with_suffix(args.out.suffix + ".tmp")
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(args.out)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

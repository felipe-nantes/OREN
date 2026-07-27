"""Run the Etapa C visual classifier benchmark on new multiphase MR exams.

Consumes a benchmark manifest (JSON) whose cases carry the ALREADY-IDENTIFIED
phase volumes + a coarse liver mask + the ground-truth label, and produces a
report separating out-of-sample (the only honest generalization number) from
in-sample cases. This is the operational entrypoint for benchmarking the best
current flow on genuinely new data, without depending on automatic DICOM phase
identification (out of scope).

Manifest schema (one object):
{
  "dataset_name": "coorte-nova-01",
  "cases": [
    {
      "case_id": "anon-xyz",
      "patient_group_id": "anon-xyz",         # optional; defaults to case_id
      "label": "POSITIVE" | "NEGATIVE",
      "phase_paths": {                          # phases already identified
        "t1_arterial": "/abs/or/rel/art.nii.gz",
        "t1_venous":   "/abs/or/rel/ven.nii.gz",
        "t1_delayed":  "/abs/or/rel/del.nii.gz"
      },
      "coarse_liver_mask_path": "/abs/or/rel/mask_organ.nii.gz"
    }
  ]
}
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.core import PipelineError
from dtwin.learning.exam_to_panels import DEFAULT_LIVER_ENRICHED_PANEL_CONFIG
from dtwin.learning.visual_benchmark import run_visual_benchmark
from dtwin.learning.visual_inference import DEFAULT_EMBEDDING_CONFIG


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--bundle",
        type=Path,
        default=Path("casos/qualification/hybrid_v1/medsiglip_multiclass_production_bundle_v1"),
    )
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--panel-config", type=Path, default=Path(DEFAULT_LIVER_ENRICHED_PANEL_CONFIG))
    parser.add_argument("--embedding-config", type=Path, default=Path(DEFAULT_EMBEDDING_CONFIG))
    args = parser.parse_args()

    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        cases = manifest.get("cases")
        if not isinstance(cases, list) or not cases:
            raise PipelineError("Manifesto de benchmark visual sem casos.")
        report = run_visual_benchmark(
            bundle_root=args.bundle,
            cases=cases,
            work_dir=args.work_dir,
            panel_config_path=args.panel_config,
            embedding_config_path=args.embedding_config,
        )
    except PipelineError as exc:
        print(f"[ERRO] {exc}")
        return 2
    report["dataset_name"] = manifest.get("dataset_name")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    oos = report.get("out_of_sample_metrics")
    if oos:
        print(
            f"[OK] out-of-sample: {oos['case_count']} casos, "
            f"sens {100*oos['sensitivity']:.2f}% / esp {100*oos['specificity']:.2f}% "
            f"(gate 75/75: {'OK' if oos['passed_75_75'] else 'FALHA'})"
        )
    if report.get("in_sample_count"):
        print(f"[AVISO] {report['in_sample_count']} casos in-sample (inflados, separados no relatório)")
    print(f"[OK] relatório em {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

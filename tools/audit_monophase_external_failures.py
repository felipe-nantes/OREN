"""Audit frozen OpenSwiss monophase false negatives without opening holdout masks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.monophase_external_failure_audit import (
    build_monophase_external_failure_audit,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(
        "casos/qualification/hybrid_v1/medsiglip_monophase_external_failure_audit_v1"
    ))
    args = parser.parse_args()
    root = Path.cwd()
    result = build_monophase_external_failure_audit(
        prediction_root=root / "casos/qualification/hybrid_v1/medsiglip_monophase_delayed_openswiss_predictions_v1",
        evaluation_path=root / "casos/qualification/hybrid_v1/medsiglip_monophase_delayed_openswiss_evaluation_v1/evaluation.json",
        development_labels_path=root / "casos/qualification/openswisshcc_v1/prepared/development_v1/protected_ground_truth/development_labels.jsonl",
        holdout_labels_path=root / "casos/qualification/openswisshcc_v1/prepared/holdout_v21_protected_labels/holdout_labels.jsonl",
        candidate_records_path=root / "casos/qualification/hybrid_v1/medsiglip_monophase_delayed_candidates_v1/candidate_records.jsonl",
        development_audit_protocol_path=root / "casos/qualification/openswisshcc_v1/authorized_ground_truth_v16/audit_protocol_v1.json",
        development_lesion_archive_path=root / "casos/qualification/openswisshcc_v1/authorized_ground_truth_v16/derivatives.zip",
        development_localizer_csv_path=root / "casos/qualification/openswisshcc_v1/audits/dev_v16_candidate_localization_venous_v1/case_localization.csv",
        output_root=args.output,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env bash
set -euo pipefail

mkdir -p \
  /opt/argos/casos \
  "${HOME}/.cache/huggingface" \
  "${HOME}/.totalsegmentator" \
  "${HOME}/.mrsegmentator" \
  "${ARGOS_TOTALSEG_RUNTIME_DIR:-/tmp/argos_totalsegmentator_runtime}"

if [[ "${ARGOS_REQUIRE_TOTALSEG_WEIGHTS:-0}" == "1" ]]; then
  weights="${TOTALSEG_WEIGHTS_PATH:-${HOME}/.totalsegmentator/nnunet/results}"
  if [[ ! -d "${weights}" ]]; then
    echo "ARGOS: TotalSegmentator weights not found at ${weights}" >&2
    exit 78
  fi
fi

exec "$@"

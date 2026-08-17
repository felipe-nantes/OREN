#!/usr/bin/env bash
set -uo pipefail
{
  echo "== ENV FINGERPRINT =="
  python -V
  python - <<'PYEOF'
import torch
print("torch", torch.__version__, "cuda_available", torch.cuda.is_available(), "device_count", torch.cuda.device_count())
PYEOF
  echo "== PIP INSTALL (ephemeral, --user) =="
  pip install --user --no-cache-dir --disable-pip-version-check 'pytest>=8' 'httpx>=0.27' 'python-multipart>=0.0.9' > /tmp/pip.log 2>&1
  if [ $? -eq 0 ]; then echo PIP_OK; else echo PIP_FAIL; tail -30 /tmp/pip.log; exit 86; fi
  echo "== PYTEST FULL SUITE =="
  cd /workspace
  python -m pytest -q -p no:cacheprovider --basetemp=/tmp/pytest -rA --durations=25
  echo "PYTEST_EXIT_CODE=$?"
} 2>&1 | tee /scratch/ph00_pytest_full.log

#!/usr/bin/env bash
set -uo pipefail
{
  echo "== ENV FINGERPRINT =="
  python -V
  python - <<'PYEOF'
import torch
print("torch", torch.__version__, "cuda_available", torch.cuda.is_available(), "device_count", torch.cuda.device_count())
PYEOF
  echo "== APT GIT (ephemeral) =="
  apt-get update -qq > /tmp/apt.log 2>&1 && apt-get install -y -qq git >> /tmp/apt.log 2>&1
  if [ $? -eq 0 ]; then git --version; else echo GIT_FAIL; tail -20 /tmp/apt.log; fi
  echo "== PIP INSTALL (ephemeral) =="
  pip install --no-cache-dir --disable-pip-version-check 'pytest>=8' 'httpx>=0.27' 'python-multipart>=0.0.9' > /tmp/pip.log 2>&1
  if [ $? -eq 0 ]; then echo PIP_OK; else echo PIP_FAIL; tail -30 /tmp/pip.log; exit 86; fi
  pip freeze > /scratch/ph00_container_pip_freeze.txt 2>/dev/null
  echo "== COPIA GRAVAVEL =="
  cp -a /workspace /tmp/ws && echo COPY_OK || { echo COPY_FAIL; exit 87; }
  cd /tmp/ws
  echo "== PYTEST FULL SUITE (writable tree) =="
  python -m pytest -q -p no:cacheprovider --basetemp=/tmp/pytest -rA --durations=25
  echo "PYTEST_EXIT_CODE=$?"
} 2>&1 | tee /scratch/ph00_pytest_full_v2.log

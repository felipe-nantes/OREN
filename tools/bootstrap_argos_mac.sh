#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

[ "$(uname -s)" = "Darwin" ] || {
  printf 'ERRO: este bootstrap e exclusivo do macOS.\n' >&2
  exit 1
}
command -v python3 >/dev/null 2>&1 || {
  printf 'ERRO: Python 3 ausente. Instale com: brew install python@3.11\n' >&2
  exit 1
}
command -v ollama >/dev/null 2>&1 || {
  printf 'ERRO: Ollama ausente. Instale com: brew install ollama\n' >&2
  exit 1
}

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -e '.[webapp]'

MODEL="${ARGOS_OLLAMA_MODEL:-medgemma:27b-it-bf16}"
if ! ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -Fxq "$MODEL"; then
  printf 'ERRO: o modelo %s nao esta instalado.\n' "$MODEL" >&2
  printf 'Depois de aceitar os termos/licenca aplicaveis, execute: ollama pull %s\n' "$MODEL" >&2
  exit 1
fi

printf 'Bootstrap macOS concluido: Python, gateway e modelo %s disponiveis.\n' "$MODEL"

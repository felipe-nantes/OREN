#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
NO_BUILD=0
SKIP_MEDGEMMA=0
while [ $# -gt 0 ]; do
  case "$1" in
    --no-build) NO_BUILD=1 ;;
    --skip-medgemma) SKIP_MEDGEMMA=1 ;;
    -h|--help)
      printf 'Uso: %s [--no-build] [--skip-medgemma]\n' "$0"
      exit 0 ;;
    *) printf 'Argumento desconhecido: %s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done

[ "$(uname -s)" = "Darwin" ] || {
  printf 'ERRO: use este launcher no macOS.\n' >&2
  exit 1
}
command -v docker >/dev/null 2>&1 || {
  printf 'ERRO: instale e abra o Docker Desktop para Mac.\n' >&2
  exit 1
}
docker info >/dev/null 2>&1 || {
  printf 'ERRO: o Docker Desktop não está iniciado.\n' >&2
  exit 1
}

[ -f .env.docker ] || bash "$REPO/tools/initialize_argos_docker.sh"

wait_http() {
  local url="$1" timeout="$2" start body
  start="$(date +%s)"
  while :; do
    body="$(curl -fsS --max-time 5 "$url" 2>/dev/null || true)"
    [ -n "$body" ] && return 0
    [ $(( $(date +%s) - start )) -ge "$timeout" ] && return 1
    sleep 3
  done
}

if [ "$SKIP_MEDGEMMA" = "0" ] && ! wait_http http://127.0.0.1:8001/health 3; then
  bash "$REPO/tools/bootstrap_argos_mac.sh"
  PY="$REPO/.venv/bin/python"
  command -v ollama >/dev/null 2>&1 || {
    printf 'ERRO: Ollama não encontrado para iniciar o MedGemma 27B.\n' >&2
    exit 1
  }
  if ! wait_http http://127.0.0.1:11434/api/tags 3; then
    mkdir -p "$HOME/Library/Logs/ARGOS"
    nohup ollama serve > "$HOME/Library/Logs/ARGOS/ollama.log" 2>&1 &
    wait_http http://127.0.0.1:11434/api/tags 30 || {
      printf 'ERRO: Ollama não iniciou.\n' >&2; exit 1;
    }
  fi
  mkdir -p "$HOME/Library/Logs/ARGOS"
  nohup "$PY" tools/medgemma_server.py \
    --config configs/medgemma_ollama_27b.yaml --port 8001 \
    > "$HOME/Library/Logs/ARGOS/medgemma-27b.log" 2>&1 &
  wait_http http://127.0.0.1:8001/health 300 || {
    printf 'ERRO: gateway 27B não ficou pronto. Veja ~/Library/Logs/ARGOS/medgemma-27b.log\n' >&2
    exit 1
  }
fi

COMPOSE=(docker compose --env-file .env.docker -f compose.yaml -f compose.portable.yaml)
"${COMPOSE[@]}" config --quiet
UP=(up -d)
[ "$NO_BUILD" = "1" ] && UP+=(--no-build) || UP+=(--build)
"${COMPOSE[@]}" "${UP[@]}"
"${COMPOSE[@]}" up -d --force-recreate --no-deps proxy

wait_http http://127.0.0.1:8080/api/health 900 || {
  "${COMPOSE[@]}" ps
  "${COMPOSE[@]}" logs --tail 100 argos proxy
  printf 'ERRO: OREN não ficou saudável.\n' >&2
  exit 1
}

QUEST_URL="$(grep '^OREN_QUEST_BASE_URL=' .env.docker | cut -d= -f2-)"
printf '\nOREN desktop: http://127.0.0.1:8080\n'
printf 'OREN Meta Quest: %s/quest/\n' "$QUEST_URL"
printf 'Valide com: ./tools/verify_argos_docker_portable.sh\n'

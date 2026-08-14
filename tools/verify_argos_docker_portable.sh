#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
SKIP_MEDGEMMA=0
[ "${1:-}" = "--skip-medgemma" ] && SKIP_MEDGEMMA=1
[ -f .env.docker ] || { printf 'ERRO: .env.docker ausente.\n' >&2; exit 1; }
COMPOSE=(docker compose --env-file .env.docker -f compose.yaml -f compose.portable.yaml)

pass() { printf 'PASS %s\n' "$1"; }
"${COMPOSE[@]}" config --quiet; pass compose_config

for service in argos proxy neo4j; do
  cid="$("${COMPOSE[@]}" ps -q "$service")"
  [ -n "$cid" ] || { printf 'FAIL %s ausente\n' "$service" >&2; exit 1; }
  state="$(docker inspect --format '{{.State.Status}}' "$cid")"
  [ "$state" = "running" ] || { printf 'FAIL %s=%s\n' "$service" "$state" >&2; exit 1; }
done
pass containers_running

curl -fsS --max-time 20 http://127.0.0.1:8080/api/health >/dev/null
pass desktop_http
curl -kfsS --max-time 20 https://127.0.0.1:8443/quest/ >/dev/null
pass quest_https

identity="$("${COMPOSE[@]}" exec -T argos python -c 'import os,pwd; print(os.getuid(),pwd.getpwuid(os.getuid()).pw_name)')"
printf '%s' "$identity" | grep -q '^10001 argos$'
pass runtime_non_root

expected="$(grep '^ARGOS_DOCKER_PLATFORM=' .env.docker | cut -d= -f2-)"
machine="$("${COMPOSE[@]}" exec -T argos python -c 'import platform; print(platform.machine())')"
case "$expected:$machine" in
  linux/arm64:aarch64|linux/amd64:x86_64) ;;
  *) printf 'FAIL arquitetura esperada=%s obtida=%s\n' "$expected" "$machine" >&2; exit 1 ;;
esac
pass platform_architecture

"${COMPOSE[@]}" exec -T argos python -c \
  'import qrcode,torch,fastapi,SimpleITK; assert not torch.cuda.is_available(); print(torch.__version__)' >/dev/null
pass portable_dependencies

if [ "$SKIP_MEDGEMMA" = "0" ]; then
  "${COMPOSE[@]}" exec -T argos python -c \
    "import urllib.request,json; p=json.load(urllib.request.urlopen('http://host.docker.internal:8001/health',timeout=15)); assert p.get('status')=='ready'" >/dev/null
  pass medgemma_host_gateway
fi

printf 'PORTABLE_DOCKER_VERIFICATION=PASSED\n'

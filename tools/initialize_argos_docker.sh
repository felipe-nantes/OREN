#!/usr/bin/env bash
set -euo pipefail

FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO/.env.docker"

if [ -f "$ENV_FILE" ] && [ "$FORCE" = "0" ]; then
  printf 'Docker environment already exists: %s\n' "$ENV_FILE"
  exit 0
fi

command -v openssl >/dev/null 2>&1 || {
  printf 'ERRO: openssl não encontrado.\n' >&2
  exit 1
}

detect_ip() {
  if [ "$(uname -s)" = "Darwin" ]; then
    local iface
    iface="$(route -n get default 2>/dev/null | awk '/interface:/{print $2; exit}')"
    [ -n "$iface" ] && ipconfig getifaddr "$iface" 2>/dev/null && return 0
  fi
  if command -v ip >/dev/null 2>&1; then
    ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}'
  fi
}

LAN_IP="$(detect_ip || true)"
[ -n "$LAN_IP" ] || {
  printf 'ERRO: não foi possível descobrir o IPv4 da rede local.\n' >&2
  exit 1
}

ARCH="$(uname -m)"
case "$ARCH" in
  arm64|aarch64) PLATFORM="linux/arm64" ;;
  x86_64|amd64) PLATFORM="linux/amd64" ;;
  *) printf 'ERRO: arquitetura não suportada: %s\n' "$ARCH" >&2; exit 1 ;;
esac

DATA_ROOT="${ARGOS_DATA_DIR:-$HOME/ARGOS_DATA}"
CASES="$DATA_ROOT/casos"
STATE="$DATA_ROOT/docker-state"
TOTALSEG="${TOTALSEG_HOME_DIR:-$HOME/.totalsegmentator}"
MRSEG="${MRSEGMENTATOR_HOME_DIR:-$HOME/.mrsegmentator}"
HF_HUB="${HF_HUB_DIR:-$HOME/.cache/huggingface/hub}"
CERTS="$REPO/.local/quest_https"

mkdir -p "$CASES" "$STATE/neo4j/data" "$STATE/neo4j/logs" \
  "$TOTALSEG" "$MRSEG" "$HF_HUB" "$CERTS"

CERT="$CERTS/oren-quest-cert.pem"
KEY="$CERTS/oren-quest-key.pem"
if [ ! -s "$CERT" ] || [ ! -s "$KEY" ] || [ "$FORCE" = "1" ]; then
  CONFIG="$CERTS/openssl-quest.cnf"
  printf '%s\n' \
    '[req]' \
    'distinguished_name=dn' \
    'x509_extensions=v3_req' \
    'prompt=no' \
    '[dn]' \
    'CN=OREN Quest LAN' \
    '[v3_req]' \
    'basicConstraints=critical,CA:TRUE,pathlen:0' \
    'keyUsage=critical,digitalSignature,keyEncipherment,keyCertSign' \
    'extendedKeyUsage=serverAuth' \
    "subjectAltName=DNS:oren.local,DNS:localhost,IP:$LAN_IP,IP:127.0.0.1" > "$CONFIG"
  openssl req -x509 -nodes -newkey rsa:3072 -sha256 -days 825 \
    -keyout "$KEY" -out "$CERT" -config "$CONFIG" >/dev/null 2>&1
  rm -f "$CONFIG"
  chmod 600 "$KEY"
fi

PASSWORD="$(openssl rand -base64 30 | tr '/+' 'AB' | tr -d '=\n')"
cat > "$ENV_FILE" <<EOF
ARGOS_CASES_DIR=$CASES
ARGOS_DOCKER_STATE_DIR=$STATE
TOTALSEG_HOME_DIR=$TOTALSEG
MRSEGMENTATOR_HOME_DIR=$MRSEG
HF_HUB_DIR=$HF_HUB
QUEST_CERT_DIR=$CERTS
NEO4J_PASSWORD=$PASSWORD
MEDGEMMA_BASE_URL=http://host.docker.internal:8001
OREN_QUEST_BASE_URL=https://$LAN_IP:8443
ARGOS_DOCKER_PLATFORM=$PLATFORM
ARGOS_RUNTIME_IMAGE=argos-runtime-portable:local
EOF
chmod 600 "$ENV_FILE"

printf 'Ambiente Docker portátil criado em %s\n' "$ENV_FILE"
printf 'Plataforma: %s\n' "$PLATFORM"
printf 'OREN Quest: https://%s:8443/quest/\n' "$LAN_IP"
printf 'Pesos e dados permanecem fora da imagem em %s\n' "$DATA_ROOT"

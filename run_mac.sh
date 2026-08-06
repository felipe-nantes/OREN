#!/usr/bin/env bash
# =====================================================================
# run_mac.sh — sobe o OREN no MAC em um comando, na ordem correta:
#   Ollama (:11434) -> Gateway(s) MedGemma (:8001/:8002) -> Webapp (:8080)
# com verificação de saúde entre cada etapa. Ctrl+C encerra o que este
# script subiu (deixa o Ollama no ar se ele já estava rodando).
#
#   Uso:
#     ./run_mac.sh                 # ambos os modelos, escolha na interface
#     ./run_mac.sh --model 27b     # só o 27B
#     ./run_mac.sh --model 4b      # só o 4B
#     ./run_mac.sh --model both    # explícito, igual ao padrão
#     ./run_mac.sh --skip-verify   # pula a verificação de dispositivo
#
# IMPORTANTE — Apple Silicon: o classificador visual (MedSigLIP), que é o
# caminho do exame trifásico, é congelado em CUDA no config padrão e FALHA
# num Mac. Este script aponta para o config MPS. Os números do protocolo
# foram medidos em CUDA; rode a verificação (feita automaticamente na
# primeira execução) para confirmar que a troca não muda decisões.
# =====================================================================
set -euo pipefail

GATEWAY_PORT_27B=8001
GATEWAY_PORT_4B=8002
WEBAPP_PORT=8080
OLLAMA_URL="http://127.0.0.1:11434"
OLLAMA_TAG="medgemma:27b-it-bf16"

CONFIG_27B="configs/medgemma_ollama_27b.yaml"
CONFIG_4B="configs/medgemma_local_4b_mps.yaml"
EMBEDDING_CONFIG="configs/training/medsiglip_frozen_mps_v1.yaml"

MODEL="both"
SKIP_VERIFY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --model) MODEL="${2:-}"; shift 2 ;;
    --model=*) MODEL="${1#*=}"; shift ;;
    --skip-verify) SKIP_VERIFY=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) printf 'Argumento desconhecido: %s\n' "$1" >&2; exit 2 ;;
  esac
done
case "$MODEL" in
  27b|4b|both) ;;
  *) printf 'ERRO: --model aceita 27b, 4b ou both (recebi %s)\n' "$MODEL" >&2; exit 2 ;;
esac

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"
PY="$REPO/.venv/bin/python"
LOGDIR="$REPO/casos"; mkdir -p "$LOGDIR"
GW27_LOG="$LOGDIR/run_gateway_27b.log"
GW4_LOG="$LOGDIR/run_gateway_4b.log"
OL_LOG="$LOGDIR/run_ollama.log"

GW27_PID=""; GW4_PID=""; OLLAMA_PID=""; OLLAMA_STARTED=0

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[1;32mOK\033[0m  %s\n' "$*"; }
warn() { printf '    \033[1;33m!\033[0m   %s\n' "$*"; }
die()  { printf '\n\033[1;31mERRO:\033[0m %s\n' "$*" >&2; exit 1; }

cleanup() {
  trap - INT TERM EXIT
  say "Encerrando"
  for pid in "$GW27_PID" "$GW4_PID"; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  done
  if [ "$OLLAMA_STARTED" = "1" ] && [ -n "$OLLAMA_PID" ]; then
    kill "$OLLAMA_PID" 2>/dev/null || true
    ok "Ollama parado (foi iniciado por este script)."
  else
    ok "Ollama deixado no ar."
  fi
  ok "Gateway(s) parado(s)."
}
trap cleanup INT TERM EXIT

# wait_http <url> <timeout_s> [regex_esperado_no_corpo]
wait_http() {
  local url="$1" timeout="$2" re="${3:-}" start body
  start=$(date +%s)
  while :; do
    body="$(curl -fsS --max-time 5 "$url" 2>/dev/null || true)"
    if [ -n "$body" ]; then
      if [ -z "$re" ] || printf '%s' "$body" | grep -Eq "$re"; then return 0; fi
    fi
    [ $(( $(date +%s) - start )) -ge "$timeout" ] && return 1
    sleep 2
  done
}

GW_READY_RE='"status"[[:space:]]*:[[:space:]]*"ready"'

# start_gateway <nome> <config> <porta> <logfile>
# Publica o pid em LAST_GATEWAY_PID (vazio se o gateway já estava no ar).
# Usa variável global em vez de ecoar o pid porque as funções de log escrevem
# em stdout -- uma substituição de comando capturaria o texto junto com o pid.
LAST_GATEWAY_PID=""
start_gateway() {
  local nome="$1" config="$2" porta="$3" logfile="$4" pid
  LAST_GATEWAY_PID=""
  if wait_http "http://127.0.0.1:$porta/health" 3 "$GW_READY_RE"; then
    ok "Gateway $nome já estava pronto em :$porta (não foi iniciado por este script)."
    return 0
  fi
  "$PY" tools/medgemma_server.py --config "$config" --port "$porta" >"$logfile" 2>&1 &
  pid=$!
  printf '    aguardando o gateway %s ficar pronto (até 300s)...\n' "$nome"
  if wait_http "http://127.0.0.1:$porta/health" 300 "$GW_READY_RE"; then
    ok "Gateway $nome pronto em :$porta (pid $pid)."
    LAST_GATEWAY_PID="$pid"
    return 0
  fi
  printf '    --- últimas linhas de %s ---\n' "$logfile"
  tail -n 20 "$logfile" 2>/dev/null || true
  kill "$pid" 2>/dev/null || true
  return 1
}

# --- 0) Preflight ----------------------------------------------------
say "Preflight"
command -v curl >/dev/null 2>&1 || die "curl não encontrado."
[ -x "$PY" ] || die "venv não encontrado em $PY
    Crie com: python3.12 -m venv .venv && .venv/bin/python -m pip install -e '.[webapp,medgemma,seg]'"
[ -f "$EMBEDDING_CONFIG" ] || die "config de embedding MPS ausente: $EMBEDDING_CONFIG"
"$PY" -c "import dtwin, uvicorn, fastapi, SimpleITK, pydicom, yaml" 2>/dev/null \
  || die "dependências ausentes no venv. Rode: $PY -m pip install -e '.[webapp,medgemma,seg]'"
"$PY" - <<'PYCHECK' || die "PyTorch sem suporte a MPS. O classificador visual não roda neste Mac."
import sys
try:
    import torch
except ImportError:
    sys.exit(1)
backend = getattr(torch.backends, "mps", None)
sys.exit(0 if backend is not None and backend.is_available() else 1)
PYCHECK
ok "venv, dependências e MPS disponíveis."

if [ "$MODEL" = "27b" ] || [ "$MODEL" = "both" ]; then
  [ -f "$CONFIG_27B" ] || die "config não encontrada: $CONFIG_27B"
  command -v ollama >/dev/null 2>&1 || die "ollama não encontrado, exigido pelo 27B. Instale o Ollama ou use --model 4b."
fi
if [ "$MODEL" = "4b" ] || [ "$MODEL" = "both" ]; then
  [ -f "$CONFIG_4B" ] || die "config não encontrada: $CONFIG_4B"
fi

# --- 1) Ollama (:11434), só se o 27B for subir -----------------------
if [ "$MODEL" = "27b" ] || [ "$MODEL" = "both" ]; then
  say "Ollama (:11434)"
  if wait_http "$OLLAMA_URL/api/tags" 3 ""; then
    ok "Ollama já está no ar."
  else
    ok "Ollama não respondeu; iniciando 'ollama serve'..."
    nohup ollama serve >"$OL_LOG" 2>&1 &
    OLLAMA_PID=$!; OLLAMA_STARTED=1
    wait_http "$OLLAMA_URL/api/tags" 30 "" || die "Ollama não subiu. Veja $OL_LOG"
    ok "Ollama iniciado (pid $OLLAMA_PID)."
  fi
  # Checa a tag pela API, não pelo CLI numa tentativa única: o `ollama list`
  # pode falhar transitoriamente com o daemon ocupado e derrubar o launch sem
  # motivo real.
  if wait_http "$OLLAMA_URL/api/tags" 10 "\"$OLLAMA_TAG\""; then
    ok "Modelo $OLLAMA_TAG disponível."
  else
    die "Modelo '$OLLAMA_TAG' não encontrado no Ollama. Confira com: ollama list"
  fi
fi

# --- 2) Gateways MedGemma -------------------------------------------
BACKENDS=""
if [ "$MODEL" = "27b" ] || [ "$MODEL" = "both" ]; then
  say "Gateway MedGemma 27B (:$GATEWAY_PORT_27B)"
  start_gateway "27B" "$CONFIG_27B" "$GATEWAY_PORT_27B" "$GW27_LOG" \
    || die "Gateway 27B não ficou pronto. Ollama no ar? modelo com visão?"
  GW27_PID="$LAST_GATEWAY_PID"
  BACKENDS="27b=MedGemma 27B=$CONFIG_27B=http://127.0.0.1:$GATEWAY_PORT_27B/health"
fi
if [ "$MODEL" = "4b" ] || [ "$MODEL" = "both" ]; then
  say "Gateway MedGemma 1.5 4B (:$GATEWAY_PORT_4B)"
  warn "O 4B carrega os pesos em MPS; a primeira subida pode levar minutos."
  start_gateway "4B" "$CONFIG_4B" "$GATEWAY_PORT_4B" "$GW4_LOG" \
    || die "Gateway 4B não ficou pronto. Pesos baixados? 'hf auth login' feito?"
  GW4_PID="$LAST_GATEWAY_PID"
  ENTRY="4b=MedGemma 1.5 4B=$CONFIG_4B=http://127.0.0.1:$GATEWAY_PORT_4B/health"
  BACKENDS="${BACKENDS:+$BACKENDS;}$ENTRY"
fi

# Backend padrão do fallback monofásico e healthcheck do rodapé: o primeiro que subiu.
if [ "$MODEL" = "4b" ]; then
  PRIMARY_CONFIG="$CONFIG_4B"; PRIMARY_HEALTH="http://127.0.0.1:$GATEWAY_PORT_4B/health"
else
  PRIMARY_CONFIG="$CONFIG_27B"; PRIMARY_HEALTH="http://127.0.0.1:$GATEWAY_PORT_27B/health"
fi

# --- 3) Verificação de dispositivo (uma vez) -------------------------
STAMP="$LOGDIR/.medsiglip_mps_verified"
if [ "$SKIP_VERIFY" = "0" ] && [ ! -f "$STAMP" ]; then
  say "Verificando se o MPS muda alguma decisão"
  printf '    (só na primeira execução; use --skip-verify para pular)\n'
  if "$PY" tools/verify_medsiglip_device_agreement.py --limit 25; then
    date -u +%Y-%m-%dT%H:%M:%SZ >"$STAMP"
    ok "Nenhuma decisão mudou na amostra verificada."
  else
    warn "A verificação NÃO passou. O webapp sobe assim mesmo, mas os números"
    warn "medidos em CUDA não valem para este caminho sem remedição própria."
  fi
fi

# --- 4) Webapp (:8080) — primeiro plano ------------------------------
say "Webapp (:$WEBAPP_PORT)"
if wait_http "http://127.0.0.1:$WEBAPP_PORT/api/health" 2 ""; then
  die "Já existe algo respondendo em :$WEBAPP_PORT. Feche antes de subir o webapp."
fi
printf '\n\033[1;32m  ABRA NO NAVEGADOR:  http://127.0.0.1:%s\033[0m\n' "$WEBAPP_PORT"
if [ "$MODEL" = "both" ]; then
  printf '  Modelo MedGemma selecionável na própria página (27B / 4B).\n'
else
  printf '  Modelo MedGemma: %s (fixo nesta execução).\n' "$MODEL"
fi
printf '  (Ctrl+C aqui encerra o webapp e o(s) gateway(s))\n\n'
command -v open >/dev/null 2>&1 && ( sleep 4; open "http://127.0.0.1:$WEBAPP_PORT" >/dev/null 2>&1 || true ) &

WEBAPP_VISUAL_EMBEDDING_CONFIG="$EMBEDDING_CONFIG" \
WEBAPP_MEDGEMMA_CONFIG="$PRIMARY_CONFIG" \
WEBAPP_MONOPHASE_MEDGEMMA_CONFIG="$PRIMARY_CONFIG" \
WEBAPP_MEDGEMMA_HEALTH="$PRIMARY_HEALTH" \
WEBAPP_MEDGEMMA_BACKENDS="$BACKENDS" \
  "$PY" -m uvicorn webapp.server:app --host 127.0.0.1 --port "$WEBAPP_PORT"

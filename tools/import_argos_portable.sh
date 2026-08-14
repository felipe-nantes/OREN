#!/usr/bin/env bash
set -euo pipefail

BUNDLE="${1:-}"
TARGET="${2:-$HOME/ARGOS/argos-main}"
[ -n "$BUNDLE" ] || {
  printf 'Uso: bash tools/import_argos_portable.sh /caminho/argos-portable [destino]\n' >&2
  exit 2
}
BUNDLE="$(cd "$BUNDLE" && pwd)"
[ -f "$BUNDLE/checksums.sha256" ] || { printf 'ERRO: checksums.sha256 ausente.\n' >&2; exit 1; }

printf 'Verificando integridade do pacote...\n'
(cd "$BUNDLE" && shasum -a 256 -c checksums.sha256)

mkdir -p "$TARGET"
if [ -d "$BUNDLE/source" ]; then
  cp -R "$BUNDLE/source/." "$TARGET/"
elif [ -f "$BUNDLE/argos-source.zip" ]; then
  unzip -q "$BUNDLE/argos-source.zip" -d "$TARGET"
else
  printf 'ERRO: fonte do ARGOS ausente no pacote.\n' >&2
  exit 1
fi

cd "$TARGET"
chmod +x tools/*.sh run_mac.sh 2>/dev/null || true
bash tools/initialize_argos_docker.sh --force

ARCH="$(uname -m)"
if [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then
  IMAGE_TAR="$BUNDLE/images/argos-runtime-portable-arm64.tar"
  if [ -f "$IMAGE_TAR" ]; then
    docker image load -i "$IMAGE_TAR"
    sed -i.bak 's/^ARGOS_RUNTIME_IMAGE=.*/ARGOS_RUNTIME_IMAGE=argos-runtime-portable:arm64/' .env.docker
    rm -f .env.docker.bak
    printf 'Imagem ARM64 importada. Iniciando sem reconstrução...\n'
    bash tools/start_argos_docker_mac.sh --no-build
    exit 0
  fi
fi

printf 'Imagem nativa não incluída; o Docker construirá para %s.\n' "$ARCH"
bash tools/start_argos_docker_mac.sh

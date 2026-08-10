#!/usr/bin/env bash
set -Eeuo pipefail

MODE="${1:-cpu}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

mkdir -p "$(grep '^WATCH_DIR=' .env | cut -d= -f2-)" "$(grep '^OUTPUT_DIR=' .env | cut -d= -f2-)"

case "${MODE}" in
  cpu)
    docker compose up -d --build
    ;;
  gpu)
    if ! command -v nvidia-smi >/dev/null 2>&1; then
      echo "nvidia-smi was not found. Install the NVIDIA driver first." >&2
      exit 1
    fi
    docker run --rm --gpus all nvidia/cuda:12.2.2-base-ubuntu22.04 nvidia-smi >/dev/null \
      || { echo "Docker cannot access the GPU. Install/configure NVIDIA Container Toolkit." >&2; exit 1; }
    docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
    ;;
  *)
    echo "Usage: ./scripts/install.sh [cpu|gpu]" >&2
    exit 1
    ;;
esac

echo
echo "Cleanarr started in ${MODE} mode."
echo "Logs: docker logs -f cleanarr"

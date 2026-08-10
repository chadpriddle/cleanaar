#!/usr/bin/env bash
set -Eeuo pipefail
MODE="${1:-cpu}"

git pull --ff-only

if [[ "${MODE}" == "gpu" ]]; then
  docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
else
  docker compose up -d --build
fi

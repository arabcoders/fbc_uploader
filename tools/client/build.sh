#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(dirname "$0")"
DIST_DIR="${SCRIPT_DIR}/dist"
BIN_NAME="fbc"

mkdir -p "${DIST_DIR}"

build_target() {
  local goarch="$1"
  local output="${DIST_DIR}/${BIN_NAME}-linux-${goarch}"

  echo "Building ${output}"
  GOOS=linux GOARCH="${goarch}" CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o "${output}" .
}

build_target amd64
build_target arm64

echo "Built binaries in ${DIST_DIR}"

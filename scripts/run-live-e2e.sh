#!/usr/bin/env bash
set -euo pipefail

LIVE_E2E_TEMP_DIR="$(mktemp -d)"
LIVE_E2E_HOST_AUTH="${LIVE_E2E_TEMP_DIR}/auth.json"
LIVE_E2E_CONTAINER_AUTH="/tmp/qa-live-e2e-auth-$$.json"

cleanup_live_e2e_credentials() {
  docker compose -f compose.yaml exec -T api \
    rm -f "${LIVE_E2E_CONTAINER_AUTH}" >/dev/null 2>&1 || true
  rm -f "${LIVE_E2E_HOST_AUTH}"
  rmdir "${LIVE_E2E_TEMP_DIR}" 2>/dev/null || true
}
trap cleanup_live_e2e_credentials EXIT

docker compose -f compose.yaml exec -T api \
  quantum-agent seed-live-e2e \
  --output "${LIVE_E2E_CONTAINER_AUTH}" \
  --activate-course >/dev/null
docker compose -f compose.yaml exec -T api \
  quantum-agent seed-login-account --activate-course >/dev/null
# Copy the credential to the host.  ``docker compose cp`` cannot read from
# the container's tmpfs ``/tmp`` on some setups (WSL2), so stream the file
# via ``exec cat`` instead.
docker compose -f compose.yaml exec -T api cat "${LIVE_E2E_CONTAINER_AUTH}" \
  > "${LIVE_E2E_HOST_AUTH}"
chmod 0600 "${LIVE_E2E_HOST_AUTH}"

QA_E2E_AUTH_FILE="${LIVE_E2E_HOST_AUTH}" npm run test:e2e:live

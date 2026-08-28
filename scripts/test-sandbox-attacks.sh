#!/usr/bin/env bash
set -euo pipefail

SANDBOX_TEST_IMAGE="${SANDBOX_TEST_IMAGE:-quantum-agent-sandbox-attack:test}"
SANDBOX_TEST_CONTAINER="qa-sandbox-attack-${$}"

cleanup_sandbox_attack() {
  docker rm -f "${SANDBOX_TEST_CONTAINER}" >/dev/null 2>&1 || true
}
trap cleanup_sandbox_attack EXIT

SANDBOX_SOURCE_MOUNT=()
if [ "${SANDBOX_SKIP_BUILD:-0}" = "1" ]; then
  SANDBOX_SOURCE_MOUNT=(
    --volume "${PWD}/services/api/quantum_agent:/workspace/services/api/quantum_agent:ro"
  )
else
  docker build --quiet --target runtime --tag "${SANDBOX_TEST_IMAGE}" services/api >/dev/null
fi
docker run --detach --name "${SANDBOX_TEST_CONTAINER}" \
  --network none \
  --read-only \
  --tmpfs /tmp:size=128m,noexec,nosuid,nodev \
  --tmpfs /run/sandbox:size=1m,nosuid,nodev \
  --pids-limit 32 \
  --memory 768m \
  --cpus 1.0 \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  "${SANDBOX_SOURCE_MOUNT[@]}" \
  "${SANDBOX_TEST_IMAGE}" \
  uvicorn quantum_agent.sandbox_runner:app --uds /run/sandbox/runner.sock >/dev/null

for _attempt in $(seq 1 30); do
  if docker exec "${SANDBOX_TEST_CONTAINER}" python -c \
    "import httpx; t=httpx.HTTPTransport(uds='/run/sandbox/runner.sock'); r=httpx.Client(transport=t,base_url='http://sandbox').get('/health'); r.raise_for_status()" \
    >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

docker exec "${SANDBOX_TEST_CONTAINER}" python -c \
  "import httpx; t=httpx.HTTPTransport(uds='/run/sandbox/runner.sock'); r=httpx.Client(transport=t,base_url='http://sandbox').get('/health'); r.raise_for_status()" \
  >/dev/null

# No application credential or secret variable is present in the runner, and
# the runner PID namespace cannot see the API server process.
docker exec "${SANDBOX_TEST_CONTAINER}" python -c \
  "import os,pathlib; forbidden=(b'USTC_API',b'DATABASE_URL',b'REDIS_PASSWORD',b'SESSION_SECRET',b'SESSION_VAULT_KEY'); env=pathlib.Path('/proc/1/environ').read_bytes(); assert not any(name in env for name in forbidden); current=str(os.getpid()); cmdlines=b' '.join(p.read_bytes() for p in pathlib.Path('/proc').glob('[0-9]*/cmdline') if p.is_file() and p.parent.name != current); assert b'quantum_agent.main:app' not in cmdlines; assert not any(name in os.environ for name in (x.decode() for x in forbidden))"

# Even an AST-bypass-equivalent direct process cannot write the root or open
# a network connection from this container boundary.
docker exec "${SANDBOX_TEST_CONTAINER}" python -c \
  "from pathlib import Path; failed=False
try: Path('/sandbox-escape').write_text('x')
except OSError: failed=True
assert failed"
docker exec "${SANDBOX_TEST_CONTAINER}" python -c \
  "import socket; failed=False; s=socket.socket(); s.settimeout(0.5)
try: s.connect(('1.1.1.1',53))
except OSError: failed=True
finally: s.close()
assert failed"

# Exercise the real Unix-socket runner for wall-time, memory, and streamed
# output exhaustion. Each attack must fail visibly and remain bounded.
docker exec "${SANDBOX_TEST_CONTAINER}" python -c \
  "import asyncio
from quantum_agent.coding.models import CodeArtifact
from quantum_agent.coding.sandbox import RemoteSandbox
from quantum_agent.science.models import SandboxLimits
async def main():
 s=RemoteSandbox('unix:///run/sandbox/runner.sock')
 cpu=await s.execute_program(CodeArtifact(purpose='cpu attack',code='while True:\n    pass'),SandboxLimits(wall_time_seconds=0.5,memory_megabytes=64))
 assert not cpu.completed and (cpu.timed_out or cpu.exit_code != 0)
 memory=await s.execute_program(CodeArtifact(purpose='memory attack',code='x = [bytearray(1024 * 1024) for _ in range(1024)]'),SandboxLimits(wall_time_seconds=2,memory_megabytes=64))
 assert not memory.completed
 output=await s.execute_program(CodeArtifact(purpose='output attack',code=\"print('X' * 20000000)\"),SandboxLimits(wall_time_seconds=2,memory_megabytes=64))
 assert not output.completed and output.truncated and len(output.stdout_bounded) <= 8000
asyncio.run(main())"

readonly="$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "${SANDBOX_TEST_CONTAINER}")"
network="$(docker inspect --format '{{.HostConfig.NetworkMode}}' "${SANDBOX_TEST_CONTAINER}")"
pids="$(docker inspect --format '{{.HostConfig.PidsLimit}}' "${SANDBOX_TEST_CONTAINER}")"
memory="$(docker inspect --format '{{.HostConfig.Memory}}' "${SANDBOX_TEST_CONTAINER}")"
caps="$(docker inspect --format '{{json .HostConfig.CapDrop}}' "${SANDBOX_TEST_CONTAINER}")"
test "${readonly}" = "true"
test "${network}" = "none"
test "${pids}" = "32"
test "${memory}" -le 805306368
test "${caps}" = '["ALL"]'

echo "sandbox attacks: PASS (secrets/proc/network/root/cpu/memory/pids/output bounded)"

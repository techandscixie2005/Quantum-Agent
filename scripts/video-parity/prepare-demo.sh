#!/usr/bin/env bash
# Explicitly scoped self-authored demonstration course. Never imports formal sources
# or creates student answers, phases, or successful learning evidence.
set -euo pipefail
container=${QA_DEMO_API_CONTAINER:-quantum-agent-final-demo-api-1}
course=7c33796f-8d45-5fd7-93b9-13ae8c7572eb
edition=5dd085cb-831c-5ed1-ae01-327f700dc12a
document=d90091e5-bdbb-54a1-a94a-83dc26a35a20
case ${1:-ingest} in
  ingest)
    docker exec "$container" python -m quantum_agent.cli ingest \
      --manifest /workspace/content/barrier_demo/manifest.toml
    ;;
  publish-self-authored)
    docker exec "$container" python -m quantum_agent.cli publish-documents \
      --course-id "$course" --edition-id "$edition" \
      --document-version-ids "$document" \
      --rationale 'Self-authored demo lecture v1; operational automated review of finite electron barrier scope, source hash and independent numerical regression. Not faculty approval of formal course textbooks.'
    ;;
  authorize-demo-student)
    docker exec "$container" python -m quantum_agent.cli seed-login-account \
      --activate-course --course-id "$course"
    ;;
  *) echo 'Usage: prepare-demo.sh {ingest|publish-self-authored|authorize-demo-student}' >&2; exit 2 ;;
esac

# 2026-10-20 reproducible classroom trial preparation

This report records software work on `codex/classroom-teaching-evidence`. All
rosters, student answers, teacher actions and provider doubles used in automated
tests are synthetic. No actual teacher approval, student participation, classroom
result or learning gain is claimed. The eight controlled remote model calls are
automated diagnostics, not classroom data.

## Current implementation

- Scientific checks preserve strict relative accuracy for tiny positive
  transmission, distinguish numerical underflow from physical zero, and now
  allow only narrowly bounded floating-point roundoff at a unity resonance.
- A durable allowance covers each teaching turn's active work, provider HTTP
  attempts, retries and recovery. Human waiting is separate. Crash reservations
  are charged conservatively; configuration changes cannot refill them.
- First responses and authenticated HITL decisions replay with the original
  identities. The safe saved-request endpoint restores an unknown first response.
  A real pending-review queue includes pauses before a completed trace exists.
- Independent-submission conditions, numeric correctness, explanation inference
  and unassessed mastery are separate fields. Original Solo answers and raw
  submitted requests remain linked without awarding credit merely for saving them.
- Teacher review retains reasons, criterion ratings and specific follow-ups;
  eligible later teaching actions link back to those decisions. Teacher-edited
  bridges retain their inspected structure, source spans and release envelope.
  Structural validation cannot prove all arbitrary human-authored prose correct.
- Checkpoint schema setup is serialized across workers with nonblocking
  advisory-lock acquisition. Failure/cancellation closes its dedicated session.
  Runtime BLAS threads are limited to fit the isolated runner's PID budget.

Versioned teacher material is in the [held-out packet](../teacher-packets/finite-barriers-heldout/1.0.0/README.md):
three eight-question forms, separate explanations, rubric anchors, contrasting
examples and 23 independently checked high-precision reference cases. It remains
unreviewed. `finite-barriers@1.0.0` is preserved; explicit `1.1.0` clarifies
assessment semantics. Existing conversations are not silently repinned.

## Verification evidence

The raw logs live under ignored `outputs/classroom-20261020/` and
`outputs/linux-runtime/`. They are included in the final review bundle after
excluding credential-bearing runtime manifests, databases, private dumps and
browser network traces. The final bundle manifest identifies exact file bytes,
hashes and omissions. Test authorship and configured CI jobs are not passing CI
results; the runs below were executed locally.

| Executed check | Recorded result | Evidence |
|---|---|---|
| Full current Linux backend, Python 3.12.3 | 638 passed, 3 opt-in live skips, 153 warnings, 426.50 s | `linux-pytest-current-tmpfs.log`, `.xml` |
| Real PostgreSQL lease/startup/failure/cancel checks | 4 passed, 5.84 s | `postgresql-budget-startup-retry.log` |
| Fresh PostgreSQL schema head → 0008 → head | 1 passed, 28.35 s | `postgresql-migration-roundtrip.log` |
| Real browser → BFF → backend → PostgreSQL, Redis, 2 workers | 8 passed, 2.2 min | `backend-live-postgresql/attempt-02-eight-pass/results.json` |
| Real SQLite browser baseline | 7 passed, 1 explicit PostgreSQL skip | `backend-live-sqlite/attempt-02-expanded-ui/results.json` |
| Focused budget/graph/API/latency contracts | 49 passed, 83.95 s | `recovery-backend-final.log` |
| Node contracts | 94 passed | `node-final.log` |
| Container full suite and production Compose smoke | Final execution in progress; see final raw logs before acceptance | `docker-pytest-final.log`, `outputs/linux-runtime/` |

The full Linux run used tmpfs only for temporary SQLite fixture storage. It
establishes Linux test behavior, not production storage durability or latency.
PostgreSQL runs separately used the real Docker database. The browser restart
case kills the owned API process group, including both Uvicorn workers, then
checks the same persisted pause and decision replay through Redis-backed sessions.

Full TypeScript checking passed; ESLint reported zero errors and three existing
unused-variable warnings. Linux Ruff passed and strict mypy passed for 167 files
after the final recovery guard. The source capture utility also passed its own
Ruff/strict-mypy checks and verifies every archived member's digest on capture.

A current Linux repeat of [the plotting benchmark](../../scripts/benchmark-science.py)
measured 1,365.64 ms for the cold call and a 0.237 ms median for 15 warm calls
(16-entry cache, 15 hits/one miss). This isolates repeated local scientific plot
work under the recorded environment; it is not an end-to-end model latency,
classroom load or cross-platform speedup claim. Raw samples are in
`science-benchmark-current.json`.

The final browser run used a staged source SHA-256
`8721b70889ad8ea9cf0b445dfdaa378dcc89f7e01db5d671c043459c60f24510`, explicitly
identified as a source digest rather than a Git commit. Its persisted-version
audit checked 15 turns, 22 recorded model calls using only `backend-live-fixture`,
two content evidence hashes and the pinned `finite-barriers@1.0.0` digest
`dff1a96d36bc0f4345750196d8a9bc7b1ad66b6bfe05c8a897caeb5e3f96ce7d`.
It does not certify `1.1.0` classroom outcomes or model-provider generalization.

The harness uses synthetic seeded Solo readiness and an explicitly marked
test-double source review registry. The real retriever and scope/hash checks
still run; production rejects that registry. Its Vite/Vinext configuration omits
hosting-only Cloudflare machinery. Production container checks are recorded
separately. Real-provider 503/credential-router recovery is covered by focused
gateway/router tests, not by a claimed full classroom browser fault campaign.

## Failures retained and what they showed

- Docker Hub image download timed out; the documented official ECR override
  succeeded. Image/source digests are retained in build logs.
- Host PostgreSQL connections initially failed because a Docker internal-only
  network did not publish the requested ports. The trial-only override adds a
  network attachment and loopback ports; production databases remain internal.
- Two workers raced while creating checkpoint tables. A first blocking advisory
  lock then deadlocked with concurrent-index snapshot waiting. Fresh-schema
  tests exposed both failures. The nonblocking lock implementation passed the
  fresh-database, actual two-worker browser restart run.
- The initial container test run had 628 passes, two failures and 11 skips:
  missing source-manifest mounts caused both failures; unavailable course files
  caused eight additional corpus skips. Read-only content/knowledge mounts fix
  the verification configuration; no tests were silently deselected.
- The first runner attempt exited before its original diagnostics were retained.
  Failure logs are now captured. A subsequent captured startup failed because
  OpenBLAS requested 48 threads inside a 32-PID limit. One-thread runtime defaults
  pass the benign control and secret/process/network/root/CPU/memory/output attacks.
  Socket ownership is now explicit; the first missing log cannot establish its cause.
- An earlier disk-backed Linux run encountered an expired-ORM `MissingGreenlet`
  during abandoned-lease recovery. The current implementation refreshes under
  the row lock before loading the ledger and passes the current full suite.
  That slow earlier run was interrupted with SIGINT after the complete current
  run; its partial JUnit and interruption/teardown failure remain preserved.
- A scheduler-sensitive 20 ms offline timing assertion failed under load. Its
  deterministic test now injects a local clock; the actual remote experiment
  script and recorded model results were not altered.
- A terminal failed turn with a recorded approval could be replayed as a
  rejection. Regressions on the unchanged image reproduce generic-failure and
  contradictory-rejection-marker cases. The final guard returns rejection only
  for an actual matching reject decision; other terminal failures remain conflicts.
  Budget exhaustion was already protected by the repository and is not claimed
  as a newly reproduced bug. Before/after Docker logs retain both results.

See [latency and budget measurements](evidence/classroom-20261020/latency-and-budgets.md)
for all eight remote comparisons, stage/transport timing, reported versus unknown
token usage, and the limits on inference. Long waits were observed after upload;
queueing versus computation remains unknown. No reliable speedup is established.

## Reproduction and source capture

Follow [LOCAL_STACK.md](LOCAL_STACK.md) for WSL/D-drive paths, ECR builds, secrets,
migrations, timeouts and the isolated Compose override. Follow the
[real-backend browser instructions](../../tests/e2e/backend-live/README.md) for
fresh synthetic databases and the provider double. Test/recovery services must
never seed or reset a real classroom database.

The review archive contains all tracked and nonignored new source files,
referenced local evidence, explicit raw-log roots, a binary Git diff and a file
manifest. Generated environments, caches, virtual disks, container layers,
credentials and raw browser network traces are excluded explicitly. The archive
is verified member by member and includes original repository course files.
It is a local review artifact, not a deployed image attestation.

```powershell
services/api/.venv/Scripts/python.exe scripts/capture-review-snapshot.py capture `
  --output outputs/review/classroom-20261020-final `
  --compare-to 68fd4cdaf4169be40863dfd0b3bed096d885b03e `
  --raw-log-root outputs/classroom-20261019 `
  --raw-log-root outputs/classroom-20261020 `
  --raw-log-root outputs/linux-runtime `
  --raw-log-root outputs/model-latency
services/api/.venv/Scripts/python.exe scripts/capture-review-snapshot.py verify `
  outputs/review/classroom-20261020-final
```

Earlier hash-only manifests cannot recreate missing earlier source bytes.
The separate start-of-session archive and final archive preserve actual bytes
from this continuation. Retained failing logs must be read with their recorded
source/configuration, rather than reclassified as current passes.

## Remaining work requiring people or deployment ownership

Actual teachers must review scientific wording, syllabus scope, the package and
all assessment forms; pilot timing and accessibility; check prior answer-key
exposure; choose fresh private forms if necessary; and preregister allocations,
scoring, missing-data rules and the delayed interval. Public `teacher-only`
filenames do not enforce exam secrecy or demonstrate blinding.

Actual students must provide the unaided pretest, initial commitments, revisions,
immediate independent answers and delayed answers. Actual teachers must score
them with reasons, record observed assistance and technical incidents, and
confirm that linked follow-up actions were actually used. No scripts may fill
these outcomes or signatures. Follow the [classroom evaluation protocol](CLASSROOM_EVALUATION_PROTOCOL.md).

Deployment owners still need institutional identity/TLS, retention and access
policy, off-host backups and a real recovery drill, Redis-vault/key recovery,
class-sized concurrency/load measurements, monitoring and monetary quotas.
Delayed assessment and external-assistance supervision remain teacher-led.
Automatic structural/numeric checks do not establish complete prose correctness,
secure test conditions, physics mastery or educational effectiveness.

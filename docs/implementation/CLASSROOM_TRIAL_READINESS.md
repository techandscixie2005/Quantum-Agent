# 2026-10-20 reproducible classroom trial preparation

This report records software work on `codex/classroom-teaching-evidence`. All
rosters, student answers, teacher actions and provider doubles used in automated
tests are synthetic. No actual teacher approval, student participation, classroom
result or learning gain is claimed. The eight controlled remote latency-protocol
calls described here are automated diagnostics, not classroom data. Earlier
model evaluations are retained separately below.

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
| Earlier Linux snapshot, before final replay guard, Python 3.12.3 | 638 passed, 3 opt-in live skips, 153 warnings, 426.50 s | `linux-pytest-current-tmpfs.log`, `.xml` |
| Real PostgreSQL lease/startup/failure/cancel checks | 4 passed, 5.84 s | `postgresql-budget-startup-retry.log` |
| Fresh PostgreSQL schema head → 0008 → head | 1 passed, 28.35 s | `postgresql-migration-roundtrip.log` |
| Compose live infrastructure: PostgreSQL/vector, Redis, Neo4j and API | 1 passed, 1.71 s | `compose-live-infrastructure.log` |
| Real browser → BFF → backend → PostgreSQL, Redis, 2 workers | 8 passed, 2.2 min | `backend-live-postgresql/attempt-02-eight-pass/results.json` |
| Real SQLite browser baseline | 7 passed, 1 explicit PostgreSQL skip | `backend-live-sqlite/attempt-02-expanded-ui/results.json` |
| Final budget/graph/API/export/recovery contracts | 62 passed, 104.20 s | `recovery-backend-final.log` |
| Node contracts | 94 passed | `node-final.log` |
| Full final container suite, network disabled, nonroot/read-only | 642 passed, 7 opt-in live skips, 158 warnings, 381.35 s | `docker-pytest-post-replay-guard.log`, `.xml` |
| Synthetic full PostgreSQL dump/restore and mutation guards | Passed, 8.379 s; 36 table hashes and schema match; 8 mutation probes | [safe report](evidence/classroom-20261020/postgresql-backup-restore.json) |
| Compiled production Compose browser smoke, final code commit | 5 checks passed; 31 public client artifacts passed secret detection | `production-compose-smoke/attempt-02-final-commit/` |
| WSL D-drive relocation and same-volume restart | Passed: 7 services healthy, 2 API workers, 3 production-smoke records unchanged | [restart record](../../outputs/linux-runtime/post-move/verification.json) |

The earlier full Linux run used tmpfs only for temporary SQLite fixture storage. It
establishes Linux test behavior, not production storage durability or latency.
PostgreSQL runs separately used the real Docker database. The browser restart
case kills the owned API process group, including both Uvicorn workers, then
checks the same persisted pause and decision replay through Redis-backed sessions.
Six infrastructure checks skipped by the network-disabled container suite ran
separately against the live stack (four budget/startup checks, the migration
roundtrip and the infrastructure check). The opt-in live multimodal provider
test was not run; its skip is not a pass. The infrastructure check did not
require certification of a teacher-published classroom corpus.

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

The frozen code commit is `9eaea941c6b8b866a90c431b06d40f1fc34c64c3`.
The final runtime API image manifest digest is
`sha256:1c6167a16197eb1272358cdae235a48d375d916c0e49d86c1150764419f25627`;
the final test image manifest digest is
`sha256:bd8b9a921f9d98d88f0431e4bfa9d6dc829ac40678063a525c3725e94a31085c`.
Later documentation-only results updates do not change that code version.
No commit was pushed and no website/competition entry was published.

The [final production smoke record](../../outputs/classroom-20261020/production-compose-smoke/attempt-02-final-commit/final-verification.json)
rebuilt the web image and ran the post-fix API with
two workers and `BUILD_REVISION` set to that code commit. An image/source audit
matched all 101 backend and migration Python files. It exercised the compiled
student UI, exact replay/status, identity isolation, a reasoned teacher follow-up,
the first-turn pending-review UI and a linked export against real PostgreSQL and
Redis. Only the model provider was an isolated HTTP double; no test review
registry was loaded. Synthetic roster/publication setup does not constitute
actual teacher approval of source applicability. These five checks did not inject
production-container crashes. The separate eight-case integration harness kills
and restarts the actual API process group, including both workers.
All three production-smoke turns persisted the actual code commit, model alias
and content hashes. This general source-retrieval smoke did not pin a finite
barriers package; the separate eight-case suite tested that pin. The raw smoke
script's generic possible-unknown-version note is superseded for this run by
the persisted version audit, rather than edited out of the raw output.

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
- After the production smoke passed, WSL was observed stopped without a planned
  stop. Later API logs show SIGTERM/startup, while provider-fixture health metadata
  was inconsistent with its successful recent probes. The cause remains unknown.
  An explicit fixture start and readiness window produced a sample with all
  seven services healthy; that is not a causal fix or a reliability guarantee.
  Original observations remain under `post-observed-wsl-stop-*`. A separate
  audit predicate initially misread the worker count because proxy flags followed
  `--workers 2`; its corrected check passed and the original sample is retained.

See [latency and budget measurements](evidence/classroom-20261020/latency-and-budgets.md)
for all eight remote comparisons, stage/transport timing, reported versus unknown
token usage, and the limits on inference. Long waits were observed after upload;
queueing versus computation remains unknown. No reliable speedup is established.

The [earlier model evaluations](CLASSROOM_IMPROVEMENTS.md#可复现的真实模型合成评价)
retain 11 POST attempts, including four timeouts and 62–92-second teaching-stage
responses. A candidate diagnosis passed coarse contracts but incorrectly called
a longer barrier path a longer decay length at fixed κ. Its original output and
the subsequent general terminology instruction/recheck are retained. The later
small recheck did not repeat that wording; it does not establish general prose
accuracy. Neither those 11 calls nor the eight tiny latency probes estimate
classroom effectiveness or held-out scientific accuracy.

The [backup/restore drill](evidence/classroom-20261020/backup-restore.md) retains
failed exact-definition comparisons and explains the narrow PostgreSQL CHECK
canonicalization before the passing comparison. The full dump remains private
and excluded from the review bundle. This does not certify Redis/key recovery,
off-host storage, school retention policy or restoration of real student data.

## Reproduction and source capture

Follow [LOCAL_STACK.md](LOCAL_STACK.md) for WSL/D-drive paths, ECR builds, secrets,
migrations, timeouts and the isolated Compose override. Follow the
[real-backend browser instructions](../../tests/e2e/backend-live/README.md) for
fresh synthetic databases and the provider double. Test/recovery services must
never seed or reset a real classroom database.

Ubuntu 24.04's registered WSL2 data path is now `D:\WSL\Ubuntu-24.04`, outside
the Git checkout. The first managed move hit `ERROR_SHARING_VIOLATION` after a
clean service stop. WSL shutdown and a successful exclusive-file probe preceded
the successful retry; the original attempt remains in `wsl-move.log`. The
[post-move commands](../../outputs/linux-runtime/wsl-post-move-verify.txt) reuse
the [allowlisted runtime/provenance audit](../../outputs/classroom-20261020/production-compose-smoke/attempt-02-final-commit/capture_final.py).
The new registered path, seven healthy services, pinned images, two workers,
API/web readiness and unchanged three-turn provenance were checked. No external
model request was made. This preserves existing local volumes; it is not a
backup restoration, a solution to the earlier unexplained runtime anomaly or
an institutional availability guarantee.

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
The [start-of-session archive](../../outputs/review/classroom-20261020-start/source-and-evidence.tar.gz)
and its [manifest](../../outputs/review/classroom-20261020-start/manifest.json)
preserve the actual earlier bytes (557 files, archive SHA-256
`99a1f2db68d2e7f6e27962a6dfa9d62b6a8dfc8c9a7269a103905dc709d0c36f`).
Those references are included in the final archive as evidence. Retained failing
logs must be read with their recorded source/configuration, rather than
reclassified as current passes.

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

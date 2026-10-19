# Measured latency and durable execution budgets

These are automated synthetic diagnostics and software verification results. They are not classroom results, evidence of learning gains, unaided performance, or actual teacher approvals. No held-out assessment packet or answer key was supplied to the latency model.

## Windows model latency protocol

The [reproducible protocol](../../../../scripts/investigate-model-latency.py) made exactly **8 POST requests**, with no retries or fallback, to the exact requested alias `deepseek-flash`. Every response reported that same alias and passed the tiny `{"ok":true}` JSON schema. The serving weights/version remain unknown. The run took **300.828 seconds**, starting at 2026-10-19 17:05:46 UTC (2026-10-20 01:05:46 China time).

The [sanitized actual report](latency-protocol.json) is copied byte-for-byte from `outputs/model-latency/90f3f960-012f-4c22-90f3-eac79310c42c/report.json`, after checking that trace entries contain only event names and timestamps and that no authorization/key fields were recorded. Report SHA-256: `756d5c44fc4ec1aab36d72297d35bc933b10e151a5f4c0eac153e7fe91173748`. Script SHA-256 at execution: `9f3b086f056aa0605c9dd455578d268e4e32fa8268e7ae4756057a59d0323e7e`. Installed transport versions were `httpx2 2.12.0` and `httpcore2 2.12.0`.

Every case used a fresh client, the same tiny prompt, temperature 0, and at most 64 output tokens. The request deadline was 120 seconds; the total allowance was 900 seconds. Each block used ABBA ordering, with two samples per condition. No seed was added because provider support was unverified.

| Block/order | Condition | Total seconds | First observed content chunk seconds |
|---|---|---:|---:|
| Thinking A1 | Provider default, nonstream | 47.765 | Unobservable in nonstream response |
| Thinking B1 | Disabled, nonstream | 27.297 | Unobservable |
| Thinking B2 | Disabled, nonstream | 48.156 | Unobservable |
| Thinking A2 | Provider default, nonstream | 36.594 | Unobservable |
| Streaming A1 | Disabled, nonstream | 27.797 | Unobservable |
| Streaming B1 | Disabled, stream | 22.640 | 22.547 |
| Streaming B2 | Disabled, stream | 35.422 | 35.125 |
| Streaming A2 | Disabled, nonstream | 55.125 | Unobservable |

The thinking-block medians were 42.1795 seconds for default and 37.7265 seconds for disabled. The streaming-block medians were 41.461 seconds for nonstream and 29.031 seconds for stream. **n=2 per condition is descriptive only**: samples overlap, and these observations do not establish a reliable speedup or a causal effect of either setting.

Trace events placed the dominant delays **after POST upload and before response headers**, approximately 22.5–55.1 seconds. For example, the first case completed connection/proxy negotiation/TLS/upload by about 0.140 seconds, then waited until 47.765 seconds for headers. This separates the initial connection from the observed wait for that request. It does not distinguish provider queueing, routing, computation, or reasoning time. `connect_tcp` combines resolver and TCP work; proxy-side target DNS was not independently observable. No DNS preflight was performed.

The two streams delivered their first content chunks only 0.093 and 0.297 seconds before case completion. A content chunk can contain several tokens; it is not an individual-token timing measurement. No reasoning chunks were observed in these disabled streams. JSON/schema measurements rounded to zero at this run's Windows monotonic-clock granularity; this means below observed timer resolution, not zero computation.

Six nonstream responses reported a combined **160 prompt + 60 completion = 220 tokens**. Both streams omitted usage; their usage is **unknown**, so the full run total and monetary cost remain unknown. Default cases each reported 44 prompt/18 completion tokens; disabled nonstream cases each reported 18/6. Private reasoning content, response error bodies, headers, and keys were not retained.

Reproduction spends real calls and requires explicit authorization:

```powershell
$env:USTC_API = [Environment]::GetEnvironmentVariable('USTC_API', 'User')
services/api/.venv/Scripts/python.exe scripts/investigate-model-latency.py --allow-live
```

The [offline protocol tests](../../../../services/api/tests/test_model_latency_protocol.py) passed 5/5. They verify single-factor ABBA bodies, fragmented SSE parsing, trace-info exclusion, fresh clients, no retries, unknown usage on timeouts, and stopping later requests at the total deadline. No additional provider calls were made for these tests.

A later focused Windows run initially reported 48 passed/1 failed: its 20 ms real-clock deadline assertion assumed the scheduler would never wake a timeout early. With the observed Windows timer granularity, two tiny attempts could begin before that test's measured deadline. The regression test now advances a script-local injected clock deterministically, without modifying asyncio's shared clock or the actual measured protocol script. The complete focused rerun then passed **49/49 in 83.95 seconds**. This test repair did not change or repeat the eight-call live experiment.

## Persisted teaching budgets

[Migration 0011](../../../../services/api/alembic/versions/0011_teaching_execution_budget.py) adds a per-turn ledger. The [budget implementation](../../../../services/api/quantum_agent/teaching/execution_budget.py) persists limits and admitted provider requests before network I/O. [TutorGraph](../../../../services/api/quantum_agent/tutor/graph.py) and the legacy state machine use the same allowance across stages, router/SDK retries and HITL recovery. Completed first-turn/HITL replays read their saved results without spending it again.

The defaults are 180 seconds of active execution, 12 admitted provider HTTP requests, 131,072 token admission units, 2,048 output tokens per generation, and 65,536 serialized request bytes. Configurable settings are `TEACHING_EXECUTION_SECONDS`, `TEACHING_EXECUTION_PROVIDER_REQUESTS`, `TEACHING_EXECUTION_TOKEN_UNITS`, `TEACHING_EXECUTION_OUTPUT_TOKENS`, and `TEACHING_EXECUTION_REQUEST_BYTES`. Existing turn limits are immutable; a deployment change cannot refill them.

Token admission units conservatively reserve serialized UTF-8 input bytes plus 1,024 framing units plus the requested output cap. They are an admission envelope, not exact tokenizer counts or billing. Provider-reported input/output/total usage is recorded separately when available; absent usage is not fabricated. HTTP reservations include SDK/router attempts and external embedding calls; a reservation is charged even if cancellation prevents confirmation that it reached the provider.

The active clock stops atomically with a persisted human-review pause. Human waiting is tracked separately and is not charged as active execution. An abandoned worker cannot prove unused time, so expiry conservatively consumes its outstanding active reservation. A live lease rejects competing execution, and row-lock fencing prevents a late worker from overwriting a recovered or exhausted ledger. A cancellation before a resumable checkpoint ends the turn safely. A durable HITL decision saved before a checkpoint failure remains recoverable with the same decision and remaining original allowance.

The ledger also records timings and outcome counts for the 12 fixed graph node names. These are observed whole-stage active durations, which can include provider/network waits and SQL work; they do not identify pure model computation. Provider transport traces in the diagnostic above measure a different layer. Stage boundaries add small persistence transactions; the real database/browser harness should continue measuring their overhead under classroom concurrency.

The exact validated initial request is saved before active work, including a nested Solo submission that might otherwise be lost if execution stops before native assessment. It is exported as `submitted_request`. This is an audit of what was submitted; it does **not** assert task matching, valid independent submission, correctness, or mastery. Qualified native assessment evidence remains separate.

The [scoped status API](../../../../services/api/quantum_agent/api/teaching.py) exposes IDs, status, safe budget counters, and a recovery action for the original client request ID. The [bounded student BFF](../../../../app/api/teaching/requests/status/route.ts) removes unknown/private fields and caps the response at 32 KiB. [Evidence export](../../../../services/api/quantum_agent/api/learning_records.py) includes the safe budget projection and submitted request with its existing integrity digest. Account/course/Solo permissions still apply.

The default teaching proxy deadline is **210 seconds**: 180 active seconds plus a 30-second transport/persistence margin. `TEACHING_PROXY_TIMEOUT_SECONDS` must allow at least a 15-second margin above the configured active limit. The student UI retains the original request ID after a lost response, checks saved status, and restores a completed result or pending review. An exhausted terminal turn is not resubmitted indefinitely: restore its conversation, then explicitly send a new turn if appropriate. Creating that new request is a deliberate student action.

## Database/recovery verification

The [deterministic budget tests](../../../../services/api/tests/test_execution_budget.py) passed 12/12 after adding fencing and initial-request retention. They cover cumulative active work, a 10,000-second human wait without active charging, immutable allowances after a new session/configuration, SDK/router HTTP attempts, output/body/token admission, cancellation/deadline persistence, reported-usage deduplication, late-worker fencing, and free completed/HITL replays. The final focused budget/pending-review/graph/teaching-API/latency rerun passed 49/49 in 83.95 seconds. Full Node verification passed 94/94; TypeScript, targeted ESLint, backend Ruff/mypy, and public-artifact secret scanning passed. The final broad Docker/browser verification is a separate run and should be read alongside these focused results.

The [opt-in PostgreSQL test](../../../../services/api/tests/live/test_live_execution_budget.py) then passed **1/1 in 7.01 seconds** against the isolated real PostgreSQL trial database. Independent sessions raced for the same lease: one claimed it and one was rejected. A fresh session recovered the expired reservation and could not refill elapsed time or provider count with larger limits. It creates/deletes only its own synthetic scope and performs no model traffic.

The first infrastructure attempt failed before fixture creation because `127.0.0.1:55432` refused connections. That original failure is preserved at `outputs/classroom-20261020/postgresql-budget.log`; after the trial network/loopback binding was corrected, the passing rerun is at `outputs/classroom-20261020/postgresql-budget-retry.log`. This was an infrastructure correction, not a silently excluded test failure. The trial network override does not change the production internal database network.

The real two-worker browser startup also exposed concurrent checkpoint DDL: both workers could try to create `checkpoint_migrations` before either saw it. [Checkpoint setup](../../../../services/api/quantum_agent/tutor/checkpoints.py) now serializes the entire saver setup under a session advisory lock held by a dedicated autocommit connection. The lock remains held across the saver's own autocommitted migrations and concurrent-index creation, and the dedicated connection always closes on failure/cancellation.

A first advisory-lock implementation using blocking `pg_advisory_lock` failed the fresh-schema concurrency test: the waiting SELECT could retain a snapshot needed by the holder's `CREATE INDEX CONCURRENTLY`. The failure is preserved at `outputs/classroom-20261020/postgresql-budget-startup.log`. Acquisition now uses completed autocommitted `pg_try_advisory_lock` statements and short asynchronous backoff, so it does not hold that waiting snapshot. The final real PostgreSQL suite passed **4/4 in 5.84 seconds**, covering fresh-schema simultaneous actual saver setup, lock release after injected failure, lock release after cancellation, and the execution lease test. The passing rerun is `outputs/classroom-20261020/postgresql-budget-startup-retry.log`. The full browser suite must separately verify the actual two-worker process lifecycle after synchronizing this change.

The [pending-review test](../../../../services/api/tests/test_pending_reviews.py) passed using real authenticated API/SQL/LangGraph behavior. First-turn pauses are discoverable without fabricating an `AgentTrace`; student access is denied, course/edition filtering and pagination are checked, and an actual synthetic staff resolution removes the pending item. This demonstrates software behavior only; the synthetic staff account is not actual teacher approval.

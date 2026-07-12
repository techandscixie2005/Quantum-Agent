# Quantum Agent API Reference

All endpoints are served from the same Cloudflare Worker origin. The frontend bundle,
API, and static assets share one domain.

## Conventions

- `POST /api/tutor`, `POST /api/verify`, and `POST /api/sandbox` accept JSON bodies;
  other endpoints use `GET`.
- Teacher endpoints require a valid `qa_teacher` cookie (see [Teacher Auth](#teacher-auth)).
- Error responses: `{ "error": "human-readable message", "detail": "internal detail" }`
  with appropriate HTTP status codes.

## Student-facing endpoints

### `GET /api/health`

Returns service status and capability readiness.

```json
{"status":"ok","service":"quantum-agent","version":"0.5.0","time":"2026-07-12T...","capabilities":[{"id":"quick","configured":false},...]}
```

### `GET /api/ready`

Readiness check with database and model provider status.

```json
{"status":"ready","service":"quantum-agent","version":"0.5.0","database":"connected","modelProvider":"deterministic-fallback","time":"..."}
```
HTTP 503 if database is unreachable.

### `GET /api/capabilities`

Returns the public capability list (labels only, no model names or providers).

```json
{"capabilities":[{"id":"quick","label":"快速问答","shortLabel":"快速","description":"...","acceptsImages":false,"configured":false},...],"routing":"server-controlled"}
```

### `GET /api/courseware`

Returns the course manifest and index totals.

```json
{"course":{"id":"qp-2026-spring","title":"量子物理","term":"2026 春"},"sources":[...],"totals":{"sources":7,"pages":737,"chunks":726}}
```

### `POST /api/tutor`

Main teaching interaction. Body:

```json
{
  "mode": "concept|derivation|experiment|project",
  "capability": "quick|deep|vision|vision-reasoner|code",
  "message": "学生问题 (1-12000 characters)",
  "sessionId": "optional-session-id",
  "courseId": "optional, defaults to qp-2026-spring",
  "attemptedWork": "optional prior work text",
  "requestedHintLevel": 2,
  "attachments": [{"name":"file.png","mimeType":"image/png","dataUrl":"data:image/png;base64,..."}]
}
```

Response is a `TutorResponse` with sessionId, turnId, taskClass, hintLevel, answer (6 fields), citations, evidence, trace, model info, and createdAt.

### `POST /api/verify`

Run a deterministic scientific validator. Body:

```json
{
  "tool": "hermiticity|normalization|probability_conservation|commutator|boundary_continuity|matrix_symmetry|eigenvalue_residual|dimensional_consistency|numerical_convergence|shape_consistency|orthogonality",
  "input": {"matrix": [...], "tolerance": 1e-9},
  "sessionId": "optional"
}
```

Response: `{ "tool": "...", "status": "passed|failed|inconclusive", "summary": "...", "details": {...}, "tolerance": ..., "inputs": {...}, "timestamp": "...", "provenance": "deterministic", "persisted": true, "durationMs": ... }`

### `GET /api/sessions`

Returns the current student's recent sessions (up to 20). Requires ChatGPT Sign-In headers or falls back to demo identity.

### `GET /api/student/state`

Returns the current student's mastery states (up to 100).

### `GET /api/projects`

Returns all 4 project definitions with the current student's progress for each.

### `POST /api/projects`

Save project progress. Body: `{ "projectId": "tunneling-wavepacket", "progress": 0.58, "currentMilestone": 3, "state": {} }`

### `POST /api/sandbox`

Submit Python code for isolated execution. The worker performs a static safety preflight and delegates to an external sandbox service if configured. Returns `{ "status": "completed|rejected|unavailable|failed", ... }`. Fails closed if the sandbox service is absent.

### `GET /api/trace`

Retrieve the full trajectory for a session. Query: `?sessionId=<id>`. Returns session metadata and ordered turn list with evidence and trace arrays parsed out of storage JSON.

### `POST /api/knowledge` (teacher/manual)

Upsert a knowledge chunk to the D1 knowledgeSources table.

## Teacher endpoints

### `POST /api/teacher/login`

Authenticate with teacher password. Body: `{ "password": "..." }`. Sets the `qa_teacher` HttpOnly cookie on success. Rate-limited to 5 attempts per 5 minutes per IP.

### `POST /api/teacher/logout`

Clears the teacher session cookie.

### `GET /api/teacher/analytics`

Requires valid `qa_teacher` cookie. Returns aggregate analytics snapshot: active students, pending escalations, high hint dependency count, failed tool runs, misconception frequency, recent escalations.

## User data endpoints

### `GET /api/user/export`

Returns the caller's stored data: sessions, turns (with model provider info redacted for deterministic), mastery states, and export timestamp.

### `POST /api/user/delete`

Deletes the caller's sessions, turns, student states, and project progress. Returns a summary of deleted records.

## Teacher auth

The teacher dashboard uses HMAC-signed cookie sessions. Set `TEACHER_PASSWORD` as a Worker secret. Optionally set `SESSION_SECRET` for a separate session signing key. Sessions expire after 8 hours. The frontend role toggle is a view switch only; teacher data is not served without a valid cookie.
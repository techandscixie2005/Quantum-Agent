# Privacy

Quantum Agent collects minimal data necessary for its teaching function. This document describes what data is stored, why, and how users can control it.

## Data stored

### Learning records (D1)
- **Session metadata**: session ID, user ID, course ID, mode (concept/derivation/etc.), title derived from first message, hint level, status, timestamps.
- **Turn content**: student messages and assistant responses (including the six-field teaching answer: conclusion, physicalPicture, mathematics, misconception, checkQuestion, suggestedAction).
- **Internal audit fields**: task classification, model provider name (internal only), model name (internal only), evidence JSON, trace JSON.
- **Student mastery state**: concept ID, mastery score (0–1), hint dependency ratio, misconception label, learning status.
- **Project progress**: project ID, completion percentage, current milestone, state JSON.
- **Escalations**: session ID, escalation reason, status, timestamps.
- **Tool run records**: tool name, input/output JSON, status, duration.

### Not stored
- **Uploaded images**: Validated and forwarded to the selected model for the current turn only. Never written to D1, R2, or disk.
- **Raw passwords**: `TEACHER_PASSWORD` is compared in constant time and never stored.
- **Complete private conversations**: Turn content is stored for learning analytics; delete functionality is available.

## Access control

- **Student data**: Accessible only to the authenticated user via ChatGPT Sign-In headers (or demo identity in local development).
- **Teacher analytics**: Protected by a server-side password gate (`qa_teacher` HttpOnly HMAC-signed cookie). Aggregated anonymized data only; individual student identities are not exposed in analytics.
- **No public endpoints**: All data access requires either platform-authenticated identity headers or the teacher session cookie.

## Data retention

- Sessions and turns persist indefinitely by default (intended for course-duration use).
- User data can be exported via `GET /api/user/export`.
- User data can be deleted via `POST /api/user/delete` (removes sessions, turns, student states, and project records).
- Escalation records are retained until manually resolved.
- No automated retention cleanup is configured; this is a known limitation for production deployment.

## Third-party model providers

- Student messages and (optionally) uploaded images are transmitted to the USTC model gateway (`https://api.llm.ustc.edu.cn`) for inference.
- The USTC gateway is the only external model provider; no data is sent to OpenAI, Anthropic, Google, or other providers unless explicitly configured.
- The USTC API key (`USTC_API`) is a server-side secret. It is never exposed to the browser or included in client bundles.
- Sanitized internal model names (provider + model) are stored server-side for audit; they are not returned in public API responses.

## Cookies

The only cookie set by Quantum Agent is:
- `qa_teacher` — HttpOnly, SameSite=Lax, signed HMAC session token for teacher dashboard access. Expires after 8 hours.

No tracking cookies, analytics cookies, or third-party cookies.

## Legal

Quantum Agent is an academic competition entry. It is not a commercial service. The courseware PDFs indexed by the RAG system are USTC course materials; they are not publicly distributed. The GitHub repository is private.

## User rights

- **Export**: `GET /api/user/export` returns all stored data associated with the authenticated identity.
- **Delete**: `POST /api/user/delete` removes all stored data for the authenticated identity.
- **No profiling or automated decision-making**: Hints and answer-release levels are pedagogical policy decisions, not automated profiling. Teacher analytics are learning-intervention signals, not student rankings.

## Security measures

See `docs/SECURITY.md` for the full security checklist including: parameterized D1 queries, strict attachment validation, rate limiting, prompt-injection boundaries, CSP, CORS, and secret management.
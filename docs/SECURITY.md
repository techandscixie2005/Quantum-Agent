# Security and privacy checklist

- Keep `.env.local` out of Git; rotate any key that has been pasted into a public channel.
- The client cannot supply a provider, base URL or model name.
- `/api/capabilities` exposes only labels and readiness, never model identities or secrets.
- Images: allowed MIME types only, base64 validation, ≤3 files, ≤5 MB each, ≤10 MB total; not persisted.
- Tutor requests: 12,000-character ceiling and per-instance rate limiting.
- Course excerpts, images, code and student text are wrapped as untrusted material in the model prompt.
- Missing evidence triggers escalation; unsupported images and unavailable sandboxes fail closed.
- Database access uses Drizzle parameter binding.
- For public deployment, add an edge/WAF rate limit and a durable per-user quota; the included in-memory limiter is a safe local guard, not a distributed quota system.

# Operations Runbook

## Health and readiness

### Health check
```bash
curl https://<worker>/api/health | jq .
# Expected: {"status":"ok","service":"quantum-agent","version":"0.5.0",...}
```

### Readiness check
```bash
curl https://<worker>/api/ready | jq .
# Expected: {"status":"ready","database":"connected","modelProvider":"configured",...}
# HTTP 503 if database unreachable
```

## Monitoring checklist

| Signal | Where | Action if abnormal |
|---|---|---|
| Worker errors | Cloudflare Dashboard → Workers → quantum-agent → Logs | Check structured logs for USTC API failures, D1 errors, or unhandled exceptions |
| D1 query latency | Cloudflare Dashboard → D1 → Analytics | Index queries if >500ms p50; review `tutorSessions` and `tutorTurns` growth |
| USTC model failure rate | Server logs (grep for `MODEL_GENERATION failed`) | Check USTC API status; verify `USTC_API` secret is valid; check model names |
| Citation rejection rate | Server logs (grep for `CITATION_ALLOWLIST`) | If rejections rise, retrieval index may be stale; rebuild with `scripts/build-courseware-index.mjs` |
| Escalation backlog | Teacher dashboard → TA Queue | Resolve open escalations in D1 `escalations` table; set `resolvedAt` |
| Rate limit hits | Server logs (grep for `429`) | If legitimate users hit limits, adjust `checkRateLimit` window in `lib/security.ts` |

## Secret management

### Set or rotate `USTC_API`
```bash
npx wrangler secret put USTC_API
```

### Set teacher password
```bash
npx wrangler secret put TEACHER_PASSWORD
```

### Verify secrets are set (admin only)
```bash
npx wrangler secret list
```

## Database operations

### Apply new migrations
```bash
npx drizzle-kit push
# OR
npx wrangler d1 execute <DB_NAME> --file=drizzle/<new_migration>.sql
```

### Inspect data (local dev only)
```bash
npx wrangler d1 execute <DB_NAME> --command="SELECT COUNT(*) FROM tutor_sessions;"
```

### Clean demo data
```sql
DELETE FROM tutor_turns WHERE session_id IN (SELECT id FROM tutor_sessions WHERE created_at < '2026-02-01');
DELETE FROM tutor_sessions WHERE created_at < '2026-02-01';
DELETE FROM student_states WHERE updated_at < '2026-02-01';
DELETE FROM escalations WHERE created_at < '2026-02-01';
DELETE FROM tool_runs WHERE created_at < '2026-02-01';
```

## Rebuilding the courseware index

After replacing a lecture PDF:
```bash
# 1. Extract text
pdftotext -layout new-lecture.pdf courseware-source/text/<chapter-name>.txt

# 2. Update sources array in scripts/build-courseware-index.mjs

# 3. Rebuild index
node scripts/build-courseware-index.mjs

# 4. Verify
node --import tsx/esm --test tests/backend.test.ts

# 5. Spot-check citations
# Search for a known topic and verify the returned page number is correct
```

## Incident response

### USTC API is down
- System automatically falls back to deterministic teaching engine.
- Student experience degrades gracefully: answers still structured, courseware citations still real, no image/code.
- Fix: verify `USTC_API` secret, check USTC gateway status, redeploy if model names changed.

### D1 database is unreachable
- All API routes that depend on D1 catch errors and return empty/degraded responses.
- Tutor workflow still works (in-memory retrieval from `lib/courseware.generated.json`).
- Fix: check D1 binding in Worker config, verify database exists and is not in maintenance.

### Suspicious escalation spike
- Check teacher dashboard → TA Queue for patterns.
- Look for prompt-injection attempts in escalation reasons.
- If legitimate (new course topic not in index), rebuild courseware index or add manual knowledge chunks.

### Frontend bundle leak
```bash
grep -riE 'deepseek|qwen|glm|api\.llm\.ustc|sk-' dist/client/
```
If any match is found:
1. Check `lib/providers.ts` — model names should never appear in client-reachable code.
2. Check `app/page.tsx` — UI labels only, no model identifiers in capability objects.
3. Verify `/api/capabilities` response does not include model names.
4. Rebuild and re-check.

## Deployment rollback

```bash
# Roll back to previous Worker version
npx wrangler rollback

# Or deploy a specific commit
git checkout <commit-sha>
npm ci
npx vinext build
npx vinext deploy
```

## Local development setup

```bash
git clone <private-repo-url>
cd Quantum-Agent
npm ci
cp .env.example .env.local
# Edit .env.local with USTC_API_KEY if available
npm run dev
```

Without `USTC_API_KEY`, the system uses the deterministic fallback engine. All teaching workflows still function.
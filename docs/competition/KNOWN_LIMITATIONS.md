# Known Limitations

## No live deployment

The project has not been deployed to a live Cloudflare Worker in this environment because `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` are not configured. Deployment is a documented manual step (`docs/DEPLOYMENT.md`). The build, test suite, and local smoke verification are complete.

## Teacher auth is a shared-password gate

Teacher dashboard access uses a `TEACHER_PASSWORD` Worker secret with HMAC-signed cookie sessions (`lib/teacher-auth.ts`). This is a demo-grade mechanism appropriate for a competition entry. It is not USTC SSO integration. The auth layer is replaceable — swap `lib/teacher-auth.ts` and the login route for any OAuth/OIDC provider without changing the analytics or data layer.

## Sandbox execution is an adapter that fails closed

`lib/sandbox.ts` performs static code safety checks and delegates to an external isolated execution service. If no sandbox service is configured, the endpoint returns HTTP 503. There is no in-Worker Python execution. The UI should indicate "execution unavailable" when the sandbox is absent.

## Courseware PDFs are private

The 7 USTC lecture PDFs in `public/courseware/` contain course materials whose publication rights have not been confirmed. The GitHub repository is private. The reproducible ingestion workflow (`scripts/build-courseware-index.mjs` + `courseware-source/text/*.txt`) is preserved locally so the index can be rebuilt from text extracts without packaging the PDFs in a public distribution.

## Rate limiting is in-memory

`lib/security.ts` `checkRateLimit()` uses an in-memory `Map` per Worker instance. This is a safe local guard but not a distributed quota system. For production deployment, add a Cloudflare WAF rate-limit rule or a D1-backed counter.

## No streaming support

The USTC model adapter (`lib/providers.ts`) uses non-streaming `/v1/chat/completions` calls. Streaming is not implemented. This is acceptable for a teaching agent where response completeness matters more than token-by-token display.

## No real model API testing in CI

All automated tests use the `demo` provider (deterministic fallback). No real USTC API tokens are consumed during CI. Live model behavior — response quality, latency, multimodal correctness — must be verified manually with a valid `USTC_API`.

## No automated accessibility audit

Manual keyboard navigation and screen-reader compatibility checks are recommended before production deployment. No automated a11y tests are included in the CI pipeline.

## Single-region Worker deployment

The Cloudflare Worker is deployed to a single region. Multi-region D1 replication is not configured. This is adequate for a course-scale deployment but not for global production traffic.

## Chinese-only UI

The student and teacher interfaces are in Chinese. Internationalization is not implemented. This matches the target audience (USTC quantum physics course, Chinese-language instruction).

## No offline/PWA support

The application requires a network connection to the Cloudflare Worker. There is no service worker, offline cache, or PWA manifest.

## Honest assessment

These limitations are acceptable for a competition entry. The core innovation — workflow-first architecture with deterministic control over teaching policy, evidence, and scientific validation — is fully implemented and tested. The documented limitations are deployment-environment constraints and scope decisions, not implementation failures.
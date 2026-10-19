import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mock, test } from "node:test";

import { POST } from "../app/api/auth/login/route";
import { checkRateLimit } from "../lib/security";

const apiKey = "sk-TEST-ONLY-provider-key-1234567890";

function request(invitation?: string, ip?: string): Request {
  return new Request("https://classroom.example/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(ip ? { "cf-connecting-ip": ip } : {}) },
    body: JSON.stringify({ api_key: apiKey, classroom_access_token: invitation }),
  });
}

test("BFF permits distinct classroom invitations behind the same proxy", async () => {
  const previousBase = process.env.QUANTUM_API_BASE_URL;
  process.env.QUANTUM_API_BASE_URL = "https://backend.invalid";
  let probes = 0;
  const fetch = mock.method(globalThis, "fetch", async () => {
    probes += 1;
    return Response.json({ session_token: "TEST-ONLY-opaque-session-token" });
  });
  try {
    for (let i = 0; i < 12; i += 1) {
      const response = await POST(request(randomUUID().replaceAll("-", "") + randomUUID()));
      assert.equal(response.status, 200);
    }
    assert.equal(probes, 12);
  } finally {
    fetch.mock.restore();
    if (previousBase === undefined) delete process.env.QUANTUM_API_BASE_URL;
    else process.env.QUANTUM_API_BASE_URL = previousBase;
  }
});

test("BFF preserves per-invitation bad-key quota and missing-invitation coarse quota", async () => {
  const previousBase = process.env.QUANTUM_API_BASE_URL;
  process.env.QUANTUM_API_BASE_URL = "https://backend.invalid";
  const invitation = randomUUID().replaceAll("-", "") + randomUUID();
  let upstreamCalls = 0;
  const fetch = mock.method(globalThis, "fetch", async () => {
    upstreamCalls += 1;
    return Response.json({ error: "rejected" }, { status: 401 });
  });
  try {
    for (let i = 0; i < 11; i += 1) {
      assert.equal((await POST(request(invitation))).status, i < 10 ? 401 : 429);
    }
    const ip = randomUUID();
    for (let i = 0; i < 11; i += 1) {
      assert.equal((await POST(request(undefined, ip))).status, i < 10 ? 401 : 429);
    }
    assert.equal(upstreamCalls, 20);
  } finally {
    fetch.mock.restore();
    if (previousBase === undefined) delete process.env.QUANTUM_API_BASE_URL;
    else process.env.QUANTUM_API_BASE_URL = previousBase;
  }
});

test("rate bucket capacity refuses new keys without resetting active quotas", () => {
  let now = Date.now() + 600_000;
  const clock = mock.method(Date, "now", () => now);
  const prefix = randomUUID();
  try {
    for (let i = 0; i < 10_000; i += 1) {
      assert.equal(checkRateLimit(`${prefix}:${i}`, 1, 60_000).allowed, true);
    }
    assert.equal(checkRateLimit(`${prefix}:over-capacity`, 1, 60_000).allowed, false);
    assert.equal(checkRateLimit(`${prefix}:0`, 1, 60_000).allowed, false);
    now += 60_001;
    assert.equal(checkRateLimit(`${prefix}:after-expiry`, 1, 60_000).allowed, true);
  } finally {
    clock.mock.restore();
  }
});

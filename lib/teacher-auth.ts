import { runtimeStrings } from "./runtime-env";

const SESSION_COOKIE = "qa_teacher";
const SESSION_DURATION_MS = 8 * 60 * 60 * 1000; // 8 hours

function constantTimeEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  let result = 0;
  for (let i = 0; i < a.length; i += 1) result |= a[i] ^ b[i];
  return result === 0;
}

function base64ToBytes(base64: string): Uint8Array {
  return new Uint8Array(Uint8Array.from(atob(base64), (c) => c.charCodeAt(0)));
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

async function hmacSha256(keyBytes: Uint8Array, data: string): Promise<Uint8Array> {
  const buffer = keyBytes.buffer as unknown as ArrayBuffer;
  const key = await crypto.subtle.importKey("raw", buffer, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(data)));
}

export function sessionKey(): Uint8Array {
  const runtime = runtimeStrings();
  const secret = runtime.SESSION_SECRET || runtime.TEACHER_PASSWORD || "quantum-agent-default-session-key";
  const keyBytes = new TextEncoder().encode(secret.slice(0, 64));
  if (keyBytes.length < 16) {
    const padded = new Uint8Array(32);
    padded.set(keyBytes);
    return padded;
  }
  return keyBytes;
}

export async function verifyTeacherPassword(password: string): Promise<boolean> {
  const runtime = runtimeStrings();
  const expected = runtime.TEACHER_PASSWORD;
  if (!expected) return false;
  const a = new TextEncoder().encode(password);
  const b = new TextEncoder().encode(expected);
  return constantTimeEqual(a, b);
}

export async function issueTeacherSession(): Promise<string> {
  const key = sessionKey();
  const sessionId = crypto.randomUUID();
  const expiresAt = Date.now() + SESSION_DURATION_MS;
  const payload = `${sessionId}.${expiresAt}`;
  const mac = await hmacSha256(key, payload);
  const token = `${payload}.${bytesToBase64(mac)}`;
  return token;
}

export async function verifyTeacherSession(token: string): Promise<boolean> {
  try {
    const key = sessionKey();
    const lastDot = token.lastIndexOf(".");
    if (lastDot < 0) return false;
    const payload = token.slice(0, lastDot);
    const providedMac = base64ToBytes(token.slice(lastDot + 1));
    const expectedMac = await hmacSha256(key, payload);
    if (!constantTimeEqual(providedMac, expectedMac)) return false;
    const parts = payload.split(".");
    const expiresAt = Number(parts[1]);
    if (Number.isNaN(expiresAt) || Date.now() > expiresAt) return false;
    return true;
  } catch {
    return false;
  }
}

export function setTeacherCookie(value: string, maxAgeSeconds = Math.floor(SESSION_DURATION_MS / 1000)): string {
  const secure = true;
  const sameSite = "Strict";
  return `${SESSION_COOKIE}=${encodeURIComponent(value)}; HttpOnly; Max-Age=${maxAgeSeconds}; Path=/; SameSite=${sameSite}${secure ? "; Secure" : ""}`;
}

export function clearTeacherCookie(): string {
  return `${SESSION_COOKIE}=; HttpOnly; Max-Age=0; Path=/; SameSite=Strict; Secure`;
}

export function extractTeacherCookie(request: Request): string | undefined {
  const cookie = request.headers.get("Cookie");
  if (!cookie) return undefined;
  for (const part of cookie.split(";")) {
    const trimmed = part.trim();
    if (trimmed.startsWith(`${SESSION_COOKIE}=`)) {
      return decodeURIComponent(trimmed.slice(SESSION_COOKIE.length + 1));
    }
  }
  return undefined;
}
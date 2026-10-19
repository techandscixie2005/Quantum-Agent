import type { TutorAttachment } from "./types";

const allowedMimeTypes = new Set<TutorAttachment["mimeType"]>(["image/png", "image/jpeg", "image/webp", "image/gif"]);
const MAX_RATE_BUCKETS = 10_000;
const windows = new Map<string, { expiresAt: number; count: number }>();

export function validateAttachments(value: unknown): TutorAttachment[] {
  if (value === undefined) return [];
  if (!Array.isArray(value) || value.length > 3) throw new Error("最多上传 3 张图片");
  let totalBytes = 0;
  return value.map((item, index) => {
    if (!item || typeof item !== "object") throw new Error(`第 ${index + 1} 个附件格式无效`);
    const attachment = item as Partial<TutorAttachment>;
    if (!attachment.mimeType || !allowedMimeTypes.has(attachment.mimeType as TutorAttachment["mimeType"])) throw new Error("仅支持 PNG、JPEG、WEBP 或 GIF 图片");
    if (!attachment.dataUrl || !attachment.dataUrl.startsWith(`data:${attachment.mimeType};base64,`)) throw new Error("图片必须使用合法的 data URL");
    const encoded = attachment.dataUrl.slice(attachment.dataUrl.indexOf(",") + 1);
    if (!/^[A-Za-z0-9+/=]+$/.test(encoded)) throw new Error("图片编码无效");
    const bytes = Math.floor(encoded.length * 0.75);
    if (bytes > 5 * 1024 * 1024) throw new Error("单张图片不能超过 5 MB");
    totalBytes += bytes;
    if (totalBytes > 10 * 1024 * 1024) throw new Error("图片总大小不能超过 10 MB");
    return { name: String(attachment.name ?? `image-${index + 1}`).slice(0, 120), mimeType: attachment.mimeType as TutorAttachment["mimeType"], dataUrl: attachment.dataUrl };
  });
}

export function checkRateLimit(key: string, limit = 30, intervalMs = 60_000) {
  const now = Date.now();
  const current = windows.get(key);
  if (!current || now >= current.expiresAt) {
    if (!current && windows.size >= MAX_RATE_BUCKETS) {
      for (const [bucket, value] of windows) {
        if (now >= value.expiresAt) windows.delete(bucket);
      }
      // Active buckets retain their counts: evicting them would let an
      // attacker reset an exhausted quota by flooding the key space.
      if (windows.size >= MAX_RATE_BUCKETS) {
        return { allowed: false, retryAfterSeconds: Math.max(1, Math.ceil(intervalMs / 1000)) };
      }
    }
    windows.set(key, { expiresAt: now + intervalMs, count: 1 });
    return { allowed: true, retryAfterSeconds: 0 };
  }
  current.count += 1;
  if (current.count <= limit) return { allowed: true, retryAfterSeconds: 0 };
  return { allowed: false, retryAfterSeconds: Math.max(1, Math.ceil((current.expiresAt - now) / 1000)) };
}

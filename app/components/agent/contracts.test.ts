import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("attachment mutation BFFs reject cross-origin requests before parsing input", async () => {
  const [upload, confirmation] = await Promise.all([
    readFile(new URL("../../api/agent/attachments/route.ts", import.meta.url), "utf8"),
    readFile(
      new URL("../../api/agent/attachments/[attachmentId]/confirm/route.ts", import.meta.url),
      "utf8",
    ),
  ]);

  for (const route of [upload, confirmation]) {
    const originCheck = route.indexOf("requireSameOrigin(request)");
    assert.notEqual(originCheck, -1);
    assert.ok(originCheck < route.indexOf("request.formData()") || route.indexOf("request.formData()") === -1);
    assert.ok(originCheck < route.indexOf("request.json()") || route.indexOf("request.json()") === -1);
  }
});

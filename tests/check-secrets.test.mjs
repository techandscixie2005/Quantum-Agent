import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

test("public artifact scanner rejects empty output and detects credentials without printing them", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "qa-public-scan-"));
  const scan = () => spawnSync(process.execPath, ["scripts/check-secrets.mjs", directory], { encoding: "utf8" });
  try {
    await mkdir(path.join(directory, "client"));
    assert.equal(scan().status, 1);
    await writeFile(path.join(directory, "client", "app.js"), 'const icon = "flask-conical-abcdefghijklmnop";');
    assert.equal(scan().status, 0);
    const synthetic = "sk-" + "A".repeat(24);
    await writeFile(path.join(directory, "client", "app.js"), `const synthetic = "${synthetic}";`);
    const rejected = scan();
    assert.equal(rejected.status, 1);
    assert.match(rejected.stderr, /provider key/);
    assert.ok(!rejected.stderr.includes(synthetic));
  } finally {
    assert.equal(path.dirname(path.resolve(directory)), path.resolve(tmpdir()));
    assert.ok(path.basename(directory).startsWith("qa-public-scan-"));
    await rm(directory, { recursive: true, force: true });
  }
});

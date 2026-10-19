// Scan compiled public artifacts without printing matched credential material.
import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";

const root = path.resolve(process.argv[2] ?? "dist", "client");
const patterns = [
  ["provider endpoint", /api\.llm\.ustc\.edu\.cn/],
  ["backend key setting", /USTC_API/],
  ["provider model alias", /deepseek-v[0-9]|qwen([0-9.]+)?-(chat|reasoner|embedding|reranker)|glm-[0-9]/],
  ["provider key", /(^|[^A-Za-z0-9_])sk-[A-Za-z0-9_-]{16,}/m],
  ["bearer credential", /[Bb]earer\s+[A-Za-z0-9._~-]{16,}/],
  ["server secret setting", /TEACHER_PASSWORD|SESSION_SECRET|SANDBOX_API_KEY/],
];
const files = [];
async function walk(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) await walk(full);
    else if (entry.isFile() && /\.(js|mjs|cjs|css|html|json|map|txt)$/.test(entry.name)) files.push(full);
  }
}
try {
  if (!(await stat(root)).isDirectory()) throw new Error("Client artifacts are missing; build first.");
  await walk(root);
  if (!files.length) throw new Error("No public text artifacts found; refusing an empty scan.");
  let failures = 0;
  for (const file of files) {
    const content = await readFile(file, "utf8");
    for (const [label, pattern] of patterns) if (pattern.test(content)) {
      console.error(`FAIL: ${label} in ${path.relative(root, file)}`);
      failures += 1;
    }
  }
  if (failures) process.exitCode = 1;
  else console.log(`Secret detection PASSED: ${files.length} public artifacts checked.`);
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}

import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
const OUT = "/home/xiangyu_xie/QuantumAgent/test-results/topbar-inspect";
mkdirSync(OUT, { recursive: true });
const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const EDITION_ID = "22222222-2222-4222-8222-222222222222";
const CONVERSATION_ID = "33333333-3333-4333-8333-333333333333";
const STUDENT_CONTEXT = {
  user_id: "66666666-6666-4666-8666-666666666666", display_name: "学量子",
  courses: [
    { course_id: COURSE_ID, course_code: "quantum-physics-2026-fall", course_title: "量子物理", institution: "USTC", role: "student", curriculum_edition_id: EDITION_ID, edition_title: "《量子物理》教学大纲 — 2026 秋", academic_year: "2026", term: "秋", chapters: [{ id: "77777777-7777-4777-8777-777777777777", ordinal: 1, title: "量子隧穿", canonical_path: "Ch. 2 / Tunneling" }] },
    { course_id: COURSE_ID, course_code: "quantum-physics-2026-fall", course_title: "量子物理", institution: "USTC", role: "student", curriculum_edition_id: "22222222-2222-4222-8222-222222222223", edition_title: "2022 课件与教师知识图谱课程结构", academic_year: "2022", term: null, chapters: [{ id: "77777777-7777-4777-8777-777777777778", ordinal: 1, title: "第一章", canonical_path: "Ch. 1" }] },
  ],
};
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
await page.route("**/api/agent/context", async (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(STUDENT_CONTEXT) }));
await page.route("**/api/teaching/turns/stream**", async (r) => r.fulfill({ status: 200, contentType: "text/event-stream", body: "event: workflow.started\ndata: {}\n\n" }));
await page.goto("http://127.0.0.1:5173/agent", { waitUntil: "domcontentloaded" });
await page.getByTestId("agent-experience").waitFor({ timeout: 30000 });
await page.waitForTimeout(800);
await page.screenshot({ path: `${OUT}/topbar.png`, fullPage: false });
// topbar text dump
const topbarText = await page.locator("header").first().innerText();
console.log("TOPBAR TEXT:", JSON.stringify(topbarText));
// cmd palette course group
await page.keyboard.press("ControlOrMeta+k");
await page.waitForTimeout(400);
const cmdText = await page.getByRole("dialog", { name: "命令面板" }).innerText();
console.log("CMD PALETTE TEXT:", JSON.stringify(cmdText.split("\n").slice(0, 25)));
await page.screenshot({ path: `${OUT}/cmd-palette.png`, fullPage: false });
// count buttons in topActions area
const btnCount = await page.locator('[class*="topActions"] button').count();
const topActionsHtml = await page.locator('[class*="topActions"]').first().innerText();
console.log("TOP ACTIONS TEXT:", JSON.stringify(topActionsHtml));
await browser.close();

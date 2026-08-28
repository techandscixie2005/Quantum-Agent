import { readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";

import {
  expect,
  request as playwrightRequest,
  test,
  type Page,
} from "@playwright/test";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

type LiveAuth = Readonly<{
  course_id: string;
  curriculum_edition_id: string;
  student_token: string;
  ta_token: string;
}>;

function liveAuth(): LiveAuth {
  const configured = process.env.QA_E2E_AUTH_FILE?.trim();
  if (!configured) throw new Error("QA_E2E_AUTH_FILE is required for the live browser suite");
  const path = resolve(configured);
  if ((statSync(path).mode & 0o077) !== 0) {
    throw new Error("The live E2E credential file must not be readable by group or others");
  }
  const value: unknown = JSON.parse(readFileSync(path, "utf8"));
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("The live E2E credential file is invalid");
  }
  const input = value as Record<string, unknown>;
  for (const key of ["course_id", "curriculum_edition_id"] as const) {
    if (typeof input[key] !== "string" || !UUID.test(input[key])) {
      throw new Error(`The live E2E ${key} is invalid`);
    }
  }
  for (const key of ["student_token", "ta_token"] as const) {
    if (typeof input[key] !== "string" || input[key].length < 32 || input[key].length > 512) {
      throw new Error(`The live E2E ${key} is invalid`);
    }
  }
  return input as LiveAuth;
}

async function installStudentSession(page: Page, auth: LiveAuth): Promise<void> {
  const origin = process.env.BASE_URL ?? "http://127.0.0.1:3000";
  await page.context().addCookies([
    {
      name: "qa_session",
      value: auth.student_token,
      url: origin,
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
}

async function canvasPng(page: Page, kind: "derivation" | "plot"): Promise<Buffer> {
  const dataUrl = await page.evaluate((imageKind) => {
    const canvas = document.createElement("canvas");
    canvas.width = 1180;
    canvas.height = 760;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Canvas is unavailable");
    context.fillStyle = "#f5f1e6";
    context.fillRect(0, 0, canvas.width, canvas.height);
    if (imageKind === "derivation") {
      context.fillStyle = "#17352d";
      context.font = "italic 34px monospace";
      context.save();
      context.rotate(-0.012);
      context.fillText("Handwritten quantum derivation", 90, 110);
      context.fillText("Step 1: E = hbar**2*k**2/(2*m)", 105, 265);
      context.fillText("Step 2: E = hbar**2*k?/(2*m)", 92, 420);
      context.fillText("The mark after k is smudged: exponent 1 or 2?", 120, 580);
      context.restore();
      for (let index = 0; index < 120; index += 1) {
        context.fillStyle = `rgba(32, 59, 51, ${0.02 + (index % 3) * 0.006})`;
        context.fillRect((index * 83) % canvas.width, (index * 47) % canvas.height, 1, 1);
      }
    } else {
      context.strokeStyle = "#243b35";
      context.lineWidth = 3;
      context.beginPath();
      context.moveTo(115, 620);
      context.lineTo(1080, 620);
      context.moveTo(115, 620);
      context.lineTo(115, 80);
      context.stroke();
      context.fillStyle = "#243b35";
      context.font = "28px sans-serif";
      context.fillText("time", 560, 690);
      context.save();
      context.translate(42, 390);
      context.rotate(-Math.PI / 2);
      context.fillText("P(excited)", 0, 0);
      context.restore();
      context.fillText("Two-level Rabi oscillation", 390, 55);
      context.strokeStyle = "#147058";
      context.lineWidth = 5;
      context.beginPath();
      for (let index = 0; index <= 900; index += 1) {
        const x = 120 + index;
        const probability = Math.sin(index / 145) ** 2;
        const y = 615 - probability * 500;
        if (index === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      }
      context.stroke();
    }
    return canvas.toDataURL("image/png");
  }, kind);
  return Buffer.from(dataUrl.split(",", 2)[1] ?? "", "base64");
}

async function uploadBuffer(
  page: Page,
  file: Readonly<{ name: string; mimeType: string; buffer: Buffer }>,
): Promise<"succeeded" | "needs_confirmation" | "confirmed"> {
  await page.locator('input[type="file"]').setInputFiles(file);
  const card = page.getByTestId("agent-attachment").filter({ hasText: file.name }).last();
  await expect(card).toBeVisible();
  await expect(card).toHaveAttribute(
    "data-attachment-status",
    /^(succeeded|needs_confirmation|confirmed)$/,
    { timeout: 180_000 },
  );
  const status = await card.getAttribute("data-attachment-status");
  if (status !== "succeeded" && status !== "needs_confirmation" && status !== "confirmed") {
    throw new Error(`Unexpected attachment extraction status: ${status ?? "missing"}`);
  }
  return status;
}

async function waitForWorkflowTerminal(page: Page): Promise<"completed" | "interrupted"> {
  await expect
    .poll(
      async () => {
        if (await page.getByTestId("agent-tutor-result").isVisible()) return "completed";
        if (await page.getByTestId("hitl-interrupt").isVisible()) return "interrupted";
        return "pending";
      },
      { timeout: 180_000 },
    )
    .toMatch(/^(completed|interrupted)$/);
  return (await page.getByTestId("agent-tutor-result").isVisible())
    ? "completed"
    : "interrupted";
}

async function resolveStudentTranscriptionInterrupt(
  page: Page,
  confirmedText: string,
): Promise<void> {
  const card = page.getByTestId("hitl-interrupt");
  if (!(await card.isVisible())) return;
  const confirm = card.getByRole("button", { name: "确认转录并继续" });
  if (!(await confirm.isVisible())) {
    throw new Error("The live workflow paused for staff review, not student transcription");
  }
  await card.getByLabel("确认后的推导或尝试").fill(confirmedText);
  await confirm.click();
  await expect(page.getByTestId("agent-tutor-result")).toBeVisible({ timeout: 180_000 });
  await expect(card).toBeHidden();
}

function interruptedPayload(sse: string): Record<string, unknown> {
  for (const block of sse.replace(/\r\n/g, "\n").split("\n\n")) {
    if (!block.includes("event: workflow.interrupted")) continue;
    const data = block
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n");
    const payload: unknown = JSON.parse(data);
    if (payload && typeof payload === "object" && !Array.isArray(payload)) {
      return payload as Record<string, unknown>;
    }
  }
  throw new Error("The workflow did not return an interrupt payload");
}

test.describe.serial("Quantum Agent live competition workflow", () => {
  test("student opens the standalone responsive scientific workspace", async ({ page }) => {
    const auth = liveAuth();
    await installStudentSession(page, auth);
    await page.goto("/agent");
    await expect(page.getByTestId("agent-experience")).toBeVisible();
    await expect(page.getByRole("heading", { name: "推导工作台" })).toBeVisible();
    await expect(page.getByTestId("model-service-status")).toBeVisible();

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole("button", { name: "打开课程导航" })).toBeVisible();
    await page.getByRole("button", { name: "打开证据面板" }).click();
    await expect(page.getByRole("heading", { name: "本轮依据" })).toBeVisible();
  });

  test("handwritten derivation reaches diagnosis, verifier, citations, and source preview", async ({ page }) => {
    const auth = liveAuth();
    await installStudentSession(page, auth);
    await page.goto("/agent");
    await expect(page.getByTestId("agent-experience")).toBeVisible();
    const extractionStatus = await uploadBuffer(page, {
      name: "handwritten-derivation.png",
      mimeType: "image/png",
      buffer: await canvasPng(page, "derivation"),
    });
    await page.getByLabel("给 Quantum Agent 的问题").fill(
      "检查这个动能本征值推导，定位第一个有后果的错误，并用课程证据支持最小提示。",
    );
    const streamResponsePromise = page.waitForResponse(
      (response) => response.url().includes("/api/teaching/turns/stream") && response.ok(),
    );
    await page.getByRole("button", { name: "发送 / 运行" }).click();
    const terminal = await waitForWorkflowTerminal(page);
    const streamResponse = await streamResponsePromise;
    if (extractionStatus === "needs_confirmation") {
      expect(terminal).toBe("interrupted");
    }
    if (terminal === "interrupted") {
      const pause = interruptedPayload(await streamResponse.text());
      const conversationId = pause.conversation_id;
      if (typeof conversationId !== "string" || !UUID.test(conversationId)) {
        throw new Error("The transcription interrupt conversation id is invalid");
      }
      const resumeResponsePromise = page.waitForResponse(
        (response) => response.url().includes(`/teaching/threads/${conversationId}/resume`),
      );
      const card = page.getByTestId("hitl-interrupt");
      await expect(card.getByLabel("确认后的推导或尝试")).not.toHaveValue("");
      await card.getByLabel("确认后的推导或尝试").fill(
        "E = hbar**2*k**2/(2*m)\nE = hbar**2*k/(2*m)",
      );
      await card.getByRole("button", { name: "确认转录并继续" }).click();
      const resumeResponse = await resumeResponsePromise;
      expect(resumeResponse.status()).toBe(200);
      const resumed = (await resumeResponse.json()) as Record<string, unknown>;
      expect(resumed.conversation_id).toBe(conversationId);
      await expect(page.getByTestId("agent-tutor-result")).toBeVisible({ timeout: 180_000 });
      await expect(card).toBeHidden();
      await expect(page.getByText("symbolic equivalence", { exact: false })).toBeVisible();
    } else {
      await expect(page.getByTestId("agent-tutor-result")).toBeVisible();
    }
    await expect(page.getByTestId("agent-citation").first()).toBeVisible();
    await page.getByTestId("agent-citation").first().click();
    await expect(page.getByTestId("source-preview")).toBeVisible();
    await expect(page.getByTestId("source-preview").locator("iframe")).toBeVisible();
  });

  test("native course document and plot uploads use their real pipelines", async ({ page }) => {
    const auth = liveAuth();
    await installStudentSession(page, auth);
    await page.goto("/agent");
    await expect(page.getByTestId("agent-experience")).toBeVisible();

    await page.getByRole("button", { name: /^概念/ }).click();
    await uploadBuffer(page, {
      name: "course-syllabus.docx",
      mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      buffer: readFileSync(resolve("knowledge/量子物理-教学大纲.docx")),
    });
    await page.getByLabel("给 Quantum Agent 的问题").fill(
      "结合课程证据，识别这份文档中的波函数与概率解释。",
    );
    await page.getByRole("button", { name: "发送 / 运行" }).click();
    const documentTerminal = await waitForWorkflowTerminal(page);
    if (documentTerminal === "interrupted") {
      await resolveStudentTranscriptionInterrupt(
        page,
        "这份课程文档讨论波函数及其概率解释。",
      );
    }

    await page.getByRole("button", { name: /^实验/ }).click();
    await uploadBuffer(page, {
      name: "rabi-plot.png",
      mimeType: "image/png",
      buffer: await canvasPng(page, "plot"),
    });
    await page.getByLabel("给 Quantum Agent 的问题").fill(
      "先检查数值不变量，再解释图中的 Rabi 振荡与坐标轴。",
    );
    await page.getByRole("button", { name: "发送 / 运行" }).click();
    const plotTerminal = await waitForWorkflowTerminal(page);
    if (plotTerminal === "interrupted") {
      await resolveStudentTranscriptionInterrupt(
        page,
        "图中横轴为 time，纵轴为 P(excited)，曲线呈周期性 Rabi 振荡。",
      );
    }
    await expect(page.getByText("two level simulation", { exact: false })).toBeVisible();
  });

  test("TA resumes the exact interrupted LangGraph thread and inspects its trace", async ({ page }) => {
    const auth = liveAuth();
    await installStudentSession(page, auth);
    await page.goto("/agent");
    await expect(page.getByTestId("agent-experience")).toBeVisible();
    const responsePromise = page.waitForResponse(
      (response) => response.url().includes("/api/teaching/turns/stream") && response.ok(),
    );
    await page.getByRole("button", { name: /^概念/ }).click();
    await page.getByLabel("给 Quantum Agent 的问题").fill(
      "@TA 请检查我对波函数概率解释的理解。",
    );
    await page.getByLabel("学生当前尝试").fill("我认为波函数本身就是可观测概率。");
    await page.getByRole("button", { name: "发送 / 运行" }).click();
    const streamResponse = await responsePromise;
    const pause = interruptedPayload(await streamResponse.text());
    await expect(page.getByTestId("hitl-interrupt")).toBeVisible();
    const conversationId = pause.conversation_id;
    if (typeof conversationId !== "string" || !UUID.test(conversationId)) {
      throw new Error("The interrupted conversation id is invalid");
    }

    const api = await playwrightRequest.newContext({
      baseURL: process.env.QUANTUM_API_BASE_URL ?? "http://127.0.0.1:8000",
      extraHTTPHeaders: { Authorization: `Bearer ${auth.ta_token}` },
    });
    try {
      const threadPath =
        `/api/v1/courses/${auth.course_id}/editions/${auth.curriculum_edition_id}` +
        `/teaching/threads/${conversationId}`;
      const inspection = await api.get(`${threadPath}/interrupt`);
      expect(inspection.status()).toBe(200);
      const inspected = (await inspection.json()) as Record<string, unknown>;
      expect(inspected.conversation_id).toBe(conversationId);

      const resumed = await api.post(`${threadPath}/resume`, { data: { action: "approve" } });
      expect(resumed.status()).toBe(200);
      const result = (await resumed.json()) as Record<string, unknown>;
      expect(result.conversation_id).toBe(conversationId);

      const traceBase =
        `/api/v1/courses/${auth.course_id}/editions/${auth.curriculum_edition_id}` +
        "/teacher/agent-traces";
      const tracesResponse = await api.get(traceBase);
      expect(tracesResponse.status()).toBe(200);
      const traces = (await tracesResponse.json()) as {
        items: Array<{ id: string; conversation_id: string }>;
      };
      const trace = traces.items.find((item) => item.conversation_id === conversationId);
      expect(trace).toBeTruthy();
      const detailResponse = await api.get(`${traceBase}/${trace?.id ?? "missing"}`);
      expect(detailResponse.status()).toBe(200);
      const detail = (await detailResponse.json()) as Record<string, unknown>;
      expect(detail.evidence_bundle).toBeTruthy();
      expect(detail.diagnosis).toBeTruthy();
      expect(detail.release_decision).toBeTruthy();
      expect(Array.isArray(detail.hitl_events) && detail.hitl_events.length > 0).toBe(true);

      const origin = process.env.BASE_URL ?? "http://127.0.0.1:3000";
      await page.context().addCookies([
        {
          name: "qa_session",
          value: auth.ta_token,
          url: origin,
          httpOnly: true,
          sameSite: "Lax",
        },
      ]);
      const traceQuery = new URLSearchParams({
        course_id: auth.course_id,
        curriculum_edition_id: auth.curriculum_edition_id,
      });
      await page.goto(`/teacher/traces?${traceQuery.toString()}`);
      await expect(page.getByText("教学工作流审阅台", { exact: true })).toBeVisible();
      await expect(page.getByRole("complementary", { name: "Agent trace 队列" })).toBeVisible();
      await expect(page.getByRole("heading", { name: /教学工作流$/ }).first()).toBeVisible({
        timeout: 30_000,
      });
      await expect(page.getByRole("heading", { name: "课程证据与来源定位" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "确定性科学工具" })).toBeVisible();
    } finally {
      await api.dispose();
    }
  });
});

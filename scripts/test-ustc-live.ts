/**
 * Live USTC model gateway test.
 *
 * Usage: npm run test:ustc-live
 * Skips cleanly when USTC_API is absent.
 * Tests every configured capability route.
 * Reports route, status, latency, output-schema validity, and redacted failure.
 * Never prints or persists the credential.
 */

import { z } from "zod/v4";
import { capabilityCatalog, generateModelText } from "../lib/providers";
import { runtimeStrings } from "../lib/runtime-env";
import type { CapabilityId, ProviderConfig } from "../lib/types";

const runtime = runtimeStrings();
const apiKey = runtime.USTC_API;

if (!apiKey) {
  console.log("SKIP: USTC_API not configured. Set USTC_API to run live tests.");
  process.exit(0);
}

// Redact any credential from output
function redact(s: string): string {
  return s.replace(/Bearer\s+\S+/gi, "Bearer [REDACTED]")
    .replace(/sk-[A-Za-z0-9]+/g, "sk-[REDACTED]");
}

const TutorAnswerSchema = z.object({
  conclusion: z.string(),
  physicalPicture: z.string(),
  mathematics: z.string(),
  misconception: z.string(),
  checkQuestion: z.string(),
  suggestedAction: z.string(),
});

const SYSTEM_PROMPT = "你是一个量子物理助教。请以JSON返回，包含conclusion, physicalPicture, mathematics, misconception, checkQuestion, suggestedAction六个中文字段。只输出JSON。";

const TEST_MESSAGES: Record<CapabilityId, string> = {
  quick: "什么是量子隧穿效应？请简要解释。",
  deep: "请详细解释Franck-Condon原理及其物理图像。",
  vision: "请描述量子力学中波函数的概率解释。",
  "vision-reasoner": "请解释为什么简并态不能直接用非简并微扰理论处理。",
  code: "请写一个一维谐振子的Python数值求解代码框架。",
};

async function testRoute(capability: CapabilityId): Promise<void> {
  const definition = capabilityCatalog.find((c) => c.id === capability)!;
  const config: ProviderConfig = {
    provider: "ustc",
    model: definition.defaultModel,
    apiKey,
    baseUrl: "https://api.llm.ustc.edu.cn",
    timeoutMs: 30000,
    maxTokens: definition.maxTokens,
  };

  const user = `请回答以下问题（${definition.label}能力）：${TEST_MESSAGES[capability]}`;
  const started = Date.now();

  try {
    const text = await generateModelText({
      system: SYSTEM_PROMPT,
      user,
      config,
      attachments: [],
    });

    const latencyMs = Date.now() - started;
    const clean = text.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "").trim();

    let parseResult: { ok: boolean; error?: string };
    try {
      const parsed = JSON.parse(clean) as Record<string, unknown>;
      const validated = TutorAnswerSchema.safeParse(parsed);
      parseResult = validated.success
        ? { ok: true }
        : { ok: false, error: validated.error.message.slice(0, 200) };
    } catch (e) {
      parseResult = { ok: false, error: String(e).slice(0, 200) };
    }

    const status = parseResult.ok ? "PASS" : "SCHEMA_FAIL";
    console.log(
      `[${status}] ${capability.padEnd(16)} | model: ${definition.defaultModel.padEnd(26)} | latency: ${String(latencyMs).padStart(5)}ms | schema: ${parseResult.ok ? "valid" : redact(parseResult.error ?? "")}`,
    );
  } catch (error) {
    const latencyMs = Date.now() - started;
    const errMsg = error instanceof Error ? error.message : String(error);
    console.log(
      `[ERROR] ${capability.padEnd(16)} | model: ${definition.defaultModel.padEnd(26)} | latency: ${String(latencyMs).padStart(5)}ms | ${redact(errMsg.slice(0, 120))}`,
    );
  }
}

async function main() {
  console.log("Quantum Agent — USTC Live Model Gateway Test\n");
  console.log(`Endpoint: https://api.llm.ustc.edu.cn/v1/chat/completions`);
  console.log(`API key: ${apiKey ? "[CONFIGURED]" : "[NOT CONFIGURED]"}\n`);
  console.log(`${"Status".padEnd(12)} ${"Capability".padEnd(18)} ${"Model".padEnd(28)} Latency  Schema/Error`);
  console.log("-".repeat(100));

  const capabilities: CapabilityId[] = ["quick", "deep", "vision", "vision-reasoner", "code"];

  // Sequential to respect rate limits
  for (const cap of capabilities) {
    await testRoute(cap);
  }

  console.log("\n---");
  console.log("Live USTC test complete. No credentials were printed.\n");
}

main().catch((err) => {
  console.error("USTC live test fatal error:", redact(String(err)));
  process.exit(1);
});
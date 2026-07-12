import type { CapabilityId, ProviderConfig, TutorAttachment } from "./types";

export const capabilityCatalog: Array<{
  id: CapabilityId;
  label: string;
  shortLabel: string;
  description: string;
  modelEnv: string;
  defaultModel: string;
  acceptsImages: boolean;
  maxTokens: number;
}> = [
  { id: "quick", label: "快速问答", shortLabel: "快速", description: "适合概念澄清与短问题，优先低延迟。", modelEnv: "USTC_MODEL_QUICK", defaultModel: "deepseek-v4-flash-ascend1", acceptsImages: false, maxTokens: 1800 },
  { id: "deep", label: "深度讲解", shortLabel: "深度", description: "适合复杂推导、跨章节联系与严谨分析。", modelEnv: "USTC_MODEL_DEEP", defaultModel: "deepseek-v4-pro", acceptsImages: false, maxTokens: 3600 },
  { id: "vision", label: "图片识别", shortLabel: "识图", description: "读取题目截图、手写推导和实验图像。", modelEnv: "USTC_MODEL_VISION", defaultModel: "qwen3.6-chat", acceptsImages: true, maxTokens: 2400 },
  { id: "vision-reasoner", label: "图片深度推理", shortLabel: "图像推理", description: "对复杂图表、多步手写推导进行更深入分析。", modelEnv: "USTC_MODEL_VISION_REASONER", defaultModel: "qwen3.6-reasoner", acceptsImages: true, maxTokens: 3600 },
  { id: "code", label: "编程实验", shortLabel: "编程", description: "解释、调试和完善量子物理数值代码。", modelEnv: "USTC_MODEL_CODE", defaultModel: "glm-5.2", acceptsImages: false, maxTokens: 3200 },
];

type GenerateInput = { system: string; user: string; config: ProviderConfig; attachments?: TutorAttachment[] };

function timeoutSignal(milliseconds = 60000) {
  return AbortSignal.timeout(Math.min(Math.max(milliseconds, 3000), 120000));
}

async function readError(response: Response) {
  const body = await response.text();
  return `${response.status} ${response.statusText}: ${body.slice(0, 500)}`;
}

function openAIOutputText(payload: Record<string, unknown>) {
  if (typeof payload.output_text === "string") return payload.output_text;
  const output = Array.isArray(payload.output) ? payload.output : [];
  return output.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const content = Array.isArray((item as { content?: unknown[] }).content) ? (item as { content: unknown[] }).content : [];
    return content.map((part) => part && typeof part === "object" && "text" in part ? String((part as { text: unknown }).text) : "");
  }).filter(Boolean).join("\n");
}

function completionUrl(baseUrl: string) {
  const base = baseUrl.replace(/\/$/, "");
  if (/\/chat\/completions$/i.test(base)) return base;
  if (/\/v1$/i.test(base)) return `${base}/chat/completions`;
  return `${base}/v1/chat/completions`;
}

function userContent(user: string, attachments: TutorAttachment[]) {
  if (!attachments.length) return user;
  return [
    { type: "text", text: user },
    ...attachments.map((attachment) => ({ type: "image_url", image_url: { url: attachment.dataUrl } })),
  ];
}

export async function generateModelText({ system, user, config, attachments = [] }: GenerateInput): Promise<string> {
  if (config.provider === "demo") throw new Error("demo provider does not call an external model");
  if (!config.apiKey) throw new Error("Model API key is not configured");
  const signal = timeoutSignal(config.timeoutMs);
  const maxTokens = config.maxTokens ?? 2400;
  if (config.provider === "openai") {
    const response = await fetch(`${config.baseUrl ?? "https://api.openai.com"}/v1/responses`, { method: "POST", signal, headers: { Authorization: `Bearer ${config.apiKey}`, "Content-Type": "application/json" }, body: JSON.stringify({ model: config.model, instructions: system, input: user, max_output_tokens: maxTokens }) });
    if (!response.ok) throw new Error(await readError(response));
    return openAIOutputText(await response.json() as Record<string, unknown>);
  }
  if (config.provider === "anthropic") {
    const response = await fetch(`${config.baseUrl ?? "https://api.anthropic.com"}/v1/messages`, { method: "POST", signal, headers: { "x-api-key": config.apiKey, "anthropic-version": "2023-06-01", "Content-Type": "application/json" }, body: JSON.stringify({ model: config.model, max_tokens: maxTokens, system, messages: [{ role: "user", content: user }] }) });
    if (!response.ok) throw new Error(await readError(response));
    const data = await response.json() as { content?: Array<{ type?: string; text?: string }> };
    return data.content?.filter((part) => part.type === "text").map((part) => part.text ?? "").join("\n") ?? "";
  }
  if (config.provider === "google") {
    const response = await fetch(`${config.baseUrl ?? "https://generativelanguage.googleapis.com"}/v1beta/models/${encodeURIComponent(config.model)}:generateContent`, { method: "POST", signal, headers: { "x-goog-api-key": config.apiKey, "Content-Type": "application/json" }, body: JSON.stringify({ systemInstruction: { parts: [{ text: system }] }, contents: [{ role: "user", parts: [{ text: user }] }], generationConfig: { maxOutputTokens: maxTokens, responseMimeType: "application/json" } }) });
    if (!response.ok) throw new Error(await readError(response));
    const data = await response.json() as { candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }> };
    return data.candidates?.[0]?.content?.parts?.map((part) => part.text ?? "").join("\n") ?? "";
  }
  const response = await fetch(completionUrl(config.baseUrl ?? "https://api.llm.ustc.edu.cn"), {
    method: "POST",
    signal,
    headers: { Authorization: `Bearer ${config.apiKey}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      model: config.model,
      messages: [{ role: "system", content: system }, { role: "user", content: userContent(user, attachments) }],
      max_tokens: maxTokens,
    }),
  });
  if (!response.ok) throw new Error(await readError(response));
  const data = await response.json() as { choices?: Array<{ message?: { content?: string } }> };
  return data.choices?.[0]?.message?.content ?? "";
}

function routeOverride(capability: CapabilityId, runtime: Record<string, string | undefined>) {
  if (!runtime.MODEL_ROUTES_JSON) return null;
  try {
    const routes = JSON.parse(runtime.MODEL_ROUTES_JSON) as Partial<Record<CapabilityId, { provider?: ProviderConfig["provider"]; model?: string; baseUrl?: string }>>;
    return routes[capability] ?? null;
  } catch {
    return null;
  }
}

export function providerConfigForCapability(capability: CapabilityId, runtime: Record<string, string | undefined>): ProviderConfig {
  const definition = capabilityCatalog.find((item) => item.id === capability) ?? capabilityCatalog[0];
  const override = routeOverride(definition.id, runtime);
  const provider = override?.provider ?? "ustc";
  const apiKeys: Partial<Record<ProviderConfig["provider"], string | undefined>> = {
    ustc: runtime.USTC_API,
    compatible: runtime.COMPATIBLE_API_KEY,
    openai: runtime.OPENAI_API_KEY,
    anthropic: runtime.ANTHROPIC_API_KEY,
    google: runtime.GEMINI_API_KEY,
  };
  const baseUrls: Partial<Record<ProviderConfig["provider"], string | undefined>> = {
    ustc: runtime.USTC_BASE_URL ?? "https://api.llm.ustc.edu.cn",
    compatible: runtime.COMPATIBLE_BASE_URL,
    openai: runtime.OPENAI_BASE_URL,
    anthropic: runtime.ANTHROPIC_BASE_URL,
    google: runtime.GEMINI_BASE_URL,
  };
  return {
    provider,
    model: override?.model?.trim() || runtime[definition.modelEnv]?.trim() || definition.defaultModel,
    apiKey: apiKeys[provider],
    baseUrl: override?.baseUrl?.trim() || baseUrls[provider],
    timeoutMs: Number(runtime.MODEL_TIMEOUT_MS ?? 60000),
    maxTokens: definition.maxTokens,
  };
}

export function publicCapabilities(runtime: Record<string, string | undefined>) {
  return capabilityCatalog.map((item) => ({
    id: item.id,
    label: item.label,
    shortLabel: item.shortLabel,
    description: item.description,
    acceptsImages: item.acceptsImages,
    configured: Boolean(providerConfigForCapability(item.id, runtime).apiKey),
  }));
}

# Model Routing

Quantum Agent's model routing is **server-side and capability-based**. The browser sends only a
capability identifier; it cannot specify a provider, endpoint, or model name.

## Capability catalog (server-only)

| Capability ID | UI Label | Default Model | Env Override | Accepts Images |
|---|---|---|---|---|
| `quick` | 快速问答 | `deepseek-v4-flash-ascend1` | `USTC_MODEL_QUICK` | No |
| `deep` | 深度讲解 | `deepseek-v4-pro` | `USTC_MODEL_DEEP` | No |
| `vision` | 图片识别 | `qwen3.6-chat` | `USTC_MODEL_VISION` | Yes |
| `vision-reasoner` | 图片深度推理 | `qwen3.6-reasoner` | `USTC_MODEL_VISION_REASONER` | Yes |
| `code` | 编程实验 | `glm-5.2` | `USTC_MODEL_CODE` | No |

All routing logic lives in `lib/providers.ts` (`providerConfigForCapability`).

## How routing works

1. The frontend sends `POST /api/tutor` with `"capability": "deep"`.
2. The API route (`app/api/tutor/route.ts`) validates the capability against a server-side allowlist.
3. `providerConfigForCapability` resolves the capability to a `ProviderConfig`:
   - Provider (default: `ustc`)
   - Model name (from env override or default)
   - API key (from `USTC_API_KEY` or `USTC_API`)
   - Base URL (from `USTC_BASE_URL` or default `https://api.llm.ustc.edu.cn`)
   - Timeout and max tokens from the capability definition
4. If the provider key is absent, the workflow falls back to the deterministic teaching engine.

## Overriding routes

### Per-capability model override

Set environment variables on the Worker:

```env
USTC_MODEL_QUICK=deepseek-v5-flash
USTC_MODEL_DEEP=deepseek-v5-pro
```

### Full route override via JSON

Set `MODEL_ROUTES_JSON` to override the entire route for a capability, including provider:

```json
{"deep":{"provider":"openai","model":"gpt-5","baseUrl":"https://api.openai.com"}}
```

This allows routing a single capability to a non-USTC provider without code changes.

## Public API response

`GET /api/capabilities` returns:

```json
{"capabilities":[{"id":"deep","label":"深度讲解","shortLabel":"深度","description":"...","acceptsImages":false,"configured":true}],"routing":"server-controlled"}
```

The response contains:
- Chinese capability labels
- Whether the capability has a configured API key
- No model names, provider names, base URLs, or API keys

`GET /api/health` returns a similar condensed view.

## What the browser never sees

- Model names (`deepseek-v4-flash-ascend1`, `qwen3.6-chat`, `glm-5.2`, etc.)
- Provider identities (`ustc`, `openai`, `anthropic`, `google`, `compatible`)
- The USTC API base URL
- The `USTC_API` key
- The `MODEL_ROUTES_JSON` configuration

## When the model call fails

1. Timeout, invalid JSON response, missing API key, or provider error → falls back to deterministic engine.
2. The response's `model.source` field becomes `"deterministic-fallback"`.
3. The trace node `MODEL_GENERATION` records the failure reason.
4. The student sees the fallback answer (still cites real courseware, still provides the six teaching fields, still follows policy).
5. The fallback never fabricates image analysis, code execution results, or tool conclusions.

## Streaming

The USTC adapter uses the standard OpenAI-compatible `/v1/chat/completions` endpoint.
Streaming is not currently implemented; responses are non-streaming with a configurable
timeout (default 60 seconds, clamp range 3–120 seconds).

If streaming is added later, it should be opt-in per capability and must still enforce
the six-field JSON response contract.

## Vibe-coding note

Do not add model-selector UI or provider-chooser controls to the student or teacher frontend.
Students choose **capabilities** (what they want to do), not **models** (what does it).
The server controls what model fulfills each capability.
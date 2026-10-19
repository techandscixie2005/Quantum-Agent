import { z } from "zod";

const uuid = z.string().uuid();
const seconds = z.number().finite().nonnegative().max(10_000_000_000);
const count = z.number().int().nonnegative().max(2_000_000_000);
const stages = ["interpret", "learning_native_pre", "prepare_commitment_gate", "retrieve_evidence",
  "diagnose", "apply_policy", "scientific_tools", "generate_response", "learning_native",
  "hitl_gate", "reject_turn", "assemble_result"] as const;
const budget = z.object({
  state: z.enum(["not_initialized", "ready", "running", "waiting", "finished", "cancelled", "failed", "exhausted"]),
  active_used_seconds: seconds.optional(),
  active_remaining_seconds: seconds.optional(),
  human_wait_seconds: seconds.optional(),
  provider_requests: count.optional(),
  reserved_token_units: count.optional(),
  reported_input_tokens: count.optional(),
  reported_output_tokens: count.optional(),
  reported_total_tokens: count.optional(),
  usage_reported_requests: count.optional(),
  limits: z.object({ active_seconds: seconds, provider_requests: count, token_units: count,
    output_tokens: count, request_bytes: count }).optional(),
  stage_timings: z.partialRecord(z.enum(stages), z.object({ active_seconds: seconds,
    invocations: count, completed: count.optional(), failed: count.optional(),
    cancelled: count.optional(), interrupted: count.optional(), finished: count.optional(),
    exhausted: count.optional() })).optional(),
});
const status = z.object({
  client_request_id: z.string().min(1).max(128),
  conversation_id: uuid,
  turn_id: uuid,
  status: z.enum(["running", "completed", "failed"]),
  execution_budget: budget,
  recovery_action: z.enum(["wait_then_retry_same_request", "replay_same_request", "review_required", "new_explicit_turn"]),
});

export type TeachingRequestStatus = z.infer<typeof status>;

export function parseTeachingRequestStatus(value: unknown, clientRequestId: string): TeachingRequestStatus {
  const parsed = status.parse(value);
  if (parsed.client_request_id !== clientRequestId) throw new Error("Request identity mismatch");
  const expected = parsed.status === "completed" ? "replay_same_request"
    : parsed.status === "failed" ? "new_explicit_turn"
    : parsed.execution_budget.state === "waiting" ? "review_required" : "wait_then_retry_same_request";
  if (parsed.recovery_action !== expected) throw new Error("Inconsistent request recovery state");
  return parsed;
}

export function recoveryMatchesView(
  requested: { epoch: number; userId: string; courseId: string; editionId: string },
  current: { epoch: number; userId: string | null; courseId: string | null; editionId: string | null },
): boolean {
  return requested.epoch === current.epoch && requested.userId === current.userId
    && requested.courseId === current.courseId && requested.editionId === current.editionId;
}

export async function boundedStatusJson(response: Response): Promise<unknown> {
  const maxBytes = 32_768;
  if (Number(response.headers.get("content-length") ?? 0) > maxBytes || !response.body) {
    throw new Error("Status payload exceeds limit");
  }
  const reader = response.body.getReader();
  let bytes = 0;
  let text = "";
  const decoder = new TextDecoder();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > maxBytes) throw new Error("Status payload exceeds limit");
      text += decoder.decode(value, { stream: true });
    }
    return JSON.parse(text + decoder.decode()) as unknown;
  } catch (error) {
    await reader.cancel().catch(() => undefined);
    throw error;
  } finally {
    reader.releaseLock();
  }
}

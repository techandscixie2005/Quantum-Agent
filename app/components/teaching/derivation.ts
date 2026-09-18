import { z } from "zod";

const source = z.object({ evidence_id: z.string().uuid(), quote: z.string().min(1).max(2000) }).strict();
const labels = z.array(z.string().min(1).max(2000)).max(8);

export const derivationBridgeSchema = z.object({
  source_step: z.string().min(1).max(2000),
  target_step: z.string().min(1).max(2000),
  missing_steps: z.array(z.object({
    formula: z.string().min(1).max(2000),
    justification: z.string().min(1).max(1000),
    source_refs: z.array(source).min(1).max(6),
  }).strict()).min(1).max(8),
  used_definitions: labels,
  assumptions: labels,
  prerequisites: labels,
  validity_conditions: labels,
  source_refs: z.array(source).min(1).max(6),
  support_basis: z.literal("unverified_model_inference"),
  partial: z.boolean(),
}).strict();

export type DerivationBridge = z.infer<typeof derivationBridgeSchema>;

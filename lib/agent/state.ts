import { StateSchema, ReducedValue, MessagesValue, UntrackedValue } from "@langchain/langgraph";
import { z } from "zod/v4";
import type { Citation, Evidence, TutorAttachment } from "../types";
import type { TutorMode, CapabilityId, TaskClass, HintLevel } from "../types";

// ── Pedagogical action enum ──
export const PedagogicalAction = z.enum([
  "ASK_GOAL",
  "ASK_FOR_ATTEMPT",
  "ELICIT_PREDICTION",
  "ASK_SELF_EXPLANATION",
  "GIVE_CONCEPT_CUE",
  "GIVE_FORMULA_CUE",
  "GIVE_PROCESS_CUE",
  "SHOW_LOCAL_EXAMPLE",
  "SHOW_COUNTEREXAMPLE",
  "COMPARE_REPRESENTATIONS",
  "RUN_RETRIEVAL",
  "RUN_SYMBOLIC_VERIFIER",
  "RUN_NUMERIC_VERIFIER",
  "RUN_SIMULATION",
  "REVIEW_CODE_LOCALLY",
  "SUMMARIZE_PROGRESS",
  "GIVE_TRANSFER_CHECK",
  "RELEASE_FULL_EXPLANATION",
  "ESCALATE_TO_TA",
  "REFUSE_OUT_OF_SCOPE",
]);
export type PedagogicalAction = z.infer<typeof PedagogicalAction>;

// ── Tutor state schema ──
const TutorAnswerSchema = z.object({
  conclusion: z.string(),
  physicalPicture: z.string(),
  mathematics: z.string(),
  misconception: z.string(),
  checkQuestion: z.string(),
  suggestedAction: z.string(),
});

const CitationSchema = z.object({
  id: z.string(),
  title: z.string(),
  chapter: z.string(),
  pages: z.string(),
  excerpt: z.string(),
  score: z.number(),
  sourceUrl: z.string().optional(),
});

const EvidenceSchema = z.object({
  type: z.enum(["course", "symbolic", "numerical", "code", "model", "teacher"]),
  label: z.string(),
  status: z.enum(["passed", "failed", "inconclusive", "inferred"]),
  detail: z.string(),
});

const TraceStepSchema = z.object({
  node: z.string(),
  status: z.enum(["passed", "adjusted", "skipped", "failed"]),
  detail: z.string(),
  durationMs: z.number().optional(),
});

const VerifierResultSchema = z.object({
  id: z.string(),
  status: z.enum(["passed", "failed", "inconclusive"]),
  summary: z.string(),
  details: z.record(z.string(), z.unknown()),
  tolerance: z.number().optional(),
});

export const TutorStateSchema = new StateSchema({
  // ── Input ──
  message: z.string(),
  mode: z.enum(["concept", "derivation", "experiment", "project"]),
  sessionId: z.string().optional(),
  courseId: z.string().optional(),
  attemptedWork: z.string().optional(),
  requestedHintLevel: z.number().optional(),
  capability: z.enum(["quick", "deep", "vision", "vision-reasoner", "code"]),
  attachments: z.array(z.object({
    name: z.string(),
    mimeType: z.enum(["image/png", "image/jpeg", "image/webp", "image/gif"]),
    dataUrl: z.string(),
  })).optional(),

  // ── Identity ──
  userEmail: z.string().default("demo.student@quantum-agent.local"),
  userDisplayName: z.string().default("演示学生"),

  // ── Authentication ──
  authenticated: z.boolean().default(false),

  // ── Task & policy ──
  taskClass: z.enum(["COURSE_QA", "DERIVATION_CHECK", "SIMULATION_GUIDANCE", "PROJECT_COACHING", "IMAGE_INTERPRETATION", "CODE_ASSISTANCE"]).optional(),
  hintLevel: z.number().min(1).max(5).default(1),
  maxHintLevel: z.number().default(3),

  // ── Course & retrieval ──
  citations: new ReducedValue(
    z.array(CitationSchema).default(() => []),
    { inputSchema: z.array(CitationSchema), reducer: (_prev, next) => next },
  ),
  citationAllowlist: new ReducedValue(
    z.array(z.string()).default(() => []),
    { inputSchema: z.array(z.string()), reducer: (_prev, next) => next },
  ),
  retrievedCount: z.number().default(0),

  // ── Misconception ──
  misconceptionId: z.string().optional(),
  misconceptionLabel: z.string().optional(),
  misconceptionDetail: z.string().optional(),

  // ── Model generation ──
  modelRawText: z.string().optional(),
  modelSource: z.enum(["api", "deterministic-fallback"]).default("deterministic-fallback"),
  modelCapability: z.string().optional(),
  answer: TutorAnswerSchema.optional(),

  // ── Pedagogical action ──
  allowedActions: new ReducedValue(
    z.array(PedagogicalAction).default(() => []),
    { inputSchema: z.array(PedagogicalAction), reducer: (_prev, next) => next },
  ),
  selectedAction: PedagogicalAction.optional(),

  // ── Scientific verification ──
  verifierResults: new ReducedValue(
    z.array(VerifierResultSchema).default(() => []),
    { inputSchema: z.array(VerifierResultSchema), reducer: (_prev, next) => next },
  ),

  // ── Evidence ──
  evidence: new ReducedValue(
    z.array(EvidenceSchema).default(() => []),
    { inputSchema: z.array(EvidenceSchema), reducer: (_prev, next) => next },
  ),

  // ── Escalation ──
  escalationReason: z.string().optional(),
  escalated: z.boolean().default(false),
  needsTeacherReview: z.boolean().default(false),

  // ── Confidence & risk ──
  confidence: z.number().min(0).max(1).default(0.5),
  riskLevel: z.enum(["low", "medium", "high"]).default("low"),

  // ── Trace ──
  trace: new ReducedValue(
    z.array(TraceStepSchema).default(() => []),
    { inputSchema: z.array(TraceStepSchema), reducer: (_prev, next) => next },
  ),

  // ── Persistence markers ──
  persistedTurn: z.boolean().default(false),
  persistedState: z.boolean().default(false),

  // ── Error handling ──
  error: z.string().optional(),
  fallbackApplied: z.boolean().default(false),

  // ── Timing ──
  startedAt: z.string().optional(),
  completedAt: z.string().optional(),
});

export type TutorState = typeof TutorStateSchema.State;
export type TutorStateUpdate = typeof TutorStateSchema.Update;
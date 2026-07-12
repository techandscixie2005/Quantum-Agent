export type TutorMode = "concept" | "derivation" | "experiment" | "project";
export type CapabilityId = "quick" | "deep" | "vision" | "vision-reasoner" | "code";
export type TaskClass = "COURSE_QA" | "DERIVATION_CHECK" | "SIMULATION_GUIDANCE" | "PROJECT_COACHING" | "IMAGE_INTERPRETATION" | "CODE_ASSISTANCE";
export type HintLevel = 1 | 2 | 3 | 4 | 5;
export type ProviderId = "demo" | "ustc" | "openai" | "anthropic" | "google" | "compatible";

export type TutorAttachment = {
  name: string;
  mimeType: "image/png" | "image/jpeg" | "image/webp" | "image/gif";
  dataUrl: string;
};

export type Citation = {
  id: string;
  title: string;
  chapter: string;
  pages: string;
  excerpt: string;
  score: number;
  sourceUrl?: string;
};

export type Evidence = {
  type: "course" | "symbolic" | "numerical" | "code" | "model" | "teacher";
  label: string;
  status: "passed" | "failed" | "inconclusive" | "inferred";
  detail: string;
};

export type TutorTraceStep = {
  node: string;
  status: "passed" | "adjusted" | "skipped" | "failed";
  detail: string;
  durationMs?: number;
};

export type TutorAnswer = {
  conclusion: string;
  physicalPicture: string;
  mathematics: string;
  misconception: string;
  checkQuestion: string;
  suggestedAction: string;
};

export type TutorRequest = {
  message: string;
  mode: TutorMode;
  sessionId?: string;
  courseId?: string;
  attemptedWork?: string;
  requestedHintLevel?: number;
  capability?: CapabilityId;
  attachments?: TutorAttachment[];
};

export type TutorResponse = {
  sessionId: string;
  turnId: string;
  taskClass: TaskClass;
  hintLevel: HintLevel;
  answer: TutorAnswer;
  citations: Citation[];
  evidence: Evidence[];
  trace: TutorTraceStep[];
  misconceptionId: string | null;
  model: { capability: CapabilityId; label: string; source: "api" | "deterministic-fallback" };
  createdAt: string;
};

export type ProviderConfig = {
  provider: ProviderId;
  model: string;
  apiKey?: string;
  baseUrl?: string;
  timeoutMs?: number;
  maxTokens?: number;
};

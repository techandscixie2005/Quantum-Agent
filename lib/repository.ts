import { and, desc, eq } from "drizzle-orm";
import { getDb } from "../db";
import { courses, escalations, knowledgeSources, studentStates, toolRuns, tutorSessions, tutorTurns, users } from "../db/schema";
import { DEFAULT_COURSE_ID, type KnowledgeChunk } from "./course-knowledge";
import type { TutorRequest, TutorResponse } from "./types";
import type { VerificationResult } from "./verifiers";

const now = () => new Date().toISOString();

export async function ensureUser(email: string, displayName: string) {
  const db = getDb();
  const existing = await db.select().from(users).where(eq(users.email, email)).limit(1);
  if (existing[0]) return existing[0];
  const user = { id: crypto.randomUUID(), email, displayName, role: "student" as const, createdAt: now() };
  await db.insert(users).values(user).onConflictDoNothing();
  return (await db.select().from(users).where(eq(users.email, email)).limit(1))[0] ?? user;
}

export async function ensureCourse() {
  const db = getDb();
  await db.insert(courses).values({ id: DEFAULT_COURSE_ID, title: "量子物理", term: "2026 春", instructor: "课程主讲教师", answerPolicy: "guided", maxHintLevel: 3, createdAt: now() }).onConflictDoNothing();
}

export async function loadPublishedKnowledge(courseId = DEFAULT_COURSE_ID): Promise<KnowledgeChunk[]> {
  try {
    const rows = await getDb().select().from(knowledgeSources).where(and(eq(knowledgeSources.courseId, courseId), eq(knowledgeSources.status, "published"))).limit(100);
    return rows.map((row) => ({ id: row.id, courseId: row.courseId, title: row.title, chapter: row.chapter, pages: row.pageStart ? `${row.pageStart}${row.pageEnd && row.pageEnd !== row.pageStart ? `–${row.pageEnd}` : ""}` : "未标页码", content: row.content, keywords: row.content.slice(0, 160).split(/[，。\s]/).filter((x) => x.length >= 2).slice(0, 12), status: "published" as const }));
  } catch { return []; }
}

export async function persistTutorExchange(user: { email: string; displayName: string }, request: TutorRequest, response: TutorResponse, internalModel?: { provider: string; model: string }) {
  const db = getDb(); await ensureCourse(); const savedUser = await ensureUser(user.email, user.displayName); const timestamp = now();
  await db.insert(tutorSessions).values({ id: response.sessionId, userId: savedUser.id, courseId: request.courseId ?? DEFAULT_COURSE_ID, mode: request.mode, title: request.message.slice(0, 60), hintLevel: response.hintLevel, status: "active", createdAt: timestamp, updatedAt: timestamp }).onConflictDoUpdate({ target: tutorSessions.id, set: { hintLevel: response.hintLevel, updatedAt: timestamp, mode: request.mode } });
  await db.insert(tutorTurns).values([
    { id: crypto.randomUUID(), sessionId: response.sessionId, role: "student", content: request.message, taskClass: response.taskClass, hintLevel: response.hintLevel, evidenceJson: "[]", traceJson: "[]", createdAt: timestamp },
    { id: response.turnId, sessionId: response.sessionId, role: "assistant", content: JSON.stringify(response.answer), taskClass: response.taskClass, hintLevel: response.hintLevel, modelProvider: internalModel?.provider ?? "deterministic", modelName: internalModel?.model ?? "quantum-tutor-rules-v2", evidenceJson: JSON.stringify(response.evidence), traceJson: JSON.stringify(response.trace), createdAt: timestamp },
  ]);
  if (response.misconceptionId) await db.insert(studentStates).values({ id: crypto.randomUUID(), userId: savedUser.id, courseId: request.courseId ?? DEFAULT_COURSE_ID, conceptId: response.misconceptionId, mastery: 0.35, hintDependency: response.hintLevel / 5, misconception: response.misconceptionId, status: "learning", updatedAt: timestamp }).onConflictDoUpdate({ target: [studentStates.userId, studentStates.courseId, studentStates.conceptId], set: { hintDependency: response.hintLevel / 5, misconception: response.misconceptionId, updatedAt: timestamp } });
  const escalationTrace = response.trace.find((step) => step.node === "HUMAN_ESCALATION");
  if (escalationTrace) await db.insert(escalations).values({ id: crypto.randomUUID(), sessionId: response.sessionId, reason: escalationTrace.detail, status: "open", createdAt: timestamp });
}

export async function persistToolRun(sessionId: string | undefined, input: Record<string, unknown>, result: VerificationResult, durationMs: number) {
  await getDb().insert(toolRuns).values({ id: crypto.randomUUID(), sessionId: sessionId ?? null, toolName: result.tool, inputJson: JSON.stringify(input), outputJson: JSON.stringify(result), status: result.status, durationMs, createdAt: now() });
}

export async function recentSessions(email: string) {
  const db = getDb(); const user = (await db.select().from(users).where(eq(users.email, email)).limit(1))[0]; if (!user) return [];
  return db.select().from(tutorSessions).where(eq(tutorSessions.userId, user.id)).orderBy(desc(tutorSessions.updatedAt)).limit(20);
}

export async function analyticsSnapshot() {
  const db = getDb();
  const [turnRows, escalationRows, stateRows, toolRows] = await Promise.all([db.select().from(tutorTurns).limit(500), db.select().from(escalations).where(eq(escalations.status, "open")).limit(100), db.select().from(studentStates).limit(500), db.select().from(toolRuns).limit(500)]);
  const misconceptions = new Map<string, number>(); stateRows.forEach((row) => { if (row.misconception) misconceptions.set(row.misconception, (misconceptions.get(row.misconception) ?? 0) + 1); });
  return { activeStudents: new Set(turnRows.filter((row) => row.role === "student").map((row) => row.sessionId)).size, pendingEscalations: escalationRows.length, highHintDependency: stateRows.filter((row) => row.hintDependency >= 0.6).length, failedToolRuns: toolRows.filter((row) => row.status === "failed").length, misconceptionCounts: [...misconceptions.entries()].map(([id, count]) => ({ id, count })).sort((a, b) => b.count - a.count), recentEscalations: escalationRows.slice(0, 5) };
}

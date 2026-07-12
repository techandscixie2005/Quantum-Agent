import { and, eq } from "drizzle-orm";
import { getDb } from "../../../db";
import { projects } from "../../../db/schema";
import { DEFAULT_COURSE_ID } from "../../../lib/course-knowledge";
import { projectDefinitions } from "../../../lib/projects";
import { ensureCourse, ensureUser } from "../../../lib/repository";
import { requestUser } from "../../../lib/request-user";

export async function GET(request: Request) {
  let progress: typeof projects.$inferSelect[] = [];
  try { const user = await ensureUser(requestUser(request).email, requestUser(request).displayName); progress = await getDb().select().from(projects).where(and(eq(projects.courseId, DEFAULT_COURSE_ID), eq(projects.userId, user.id))); } catch { /* definitions remain available */ }
  return Response.json({ projects: projectDefinitions.map((definition) => ({ ...definition, progress: progress.find((item) => item.title === definition.title) ?? null })) });
}

export async function POST(request: Request) {
  try {
    const body = await request.json() as { projectId?: string; progress?: number; currentMilestone?: number; state?: Record<string, unknown> };
    const definition = projectDefinitions.find((item) => item.id === body.projectId);
    if (!definition) return Response.json({ error: "Unknown project" }, { status: 400 });
    await ensureCourse(); const identity = requestUser(request); const user = await ensureUser(identity.email, identity.displayName); const updatedAt = new Date().toISOString();
    const value = { id: crypto.randomUUID(), courseId: DEFAULT_COURSE_ID, userId: user.id, title: definition.title, progress: Math.min(Math.max(Number(body.progress ?? 0), 0), 1), currentMilestone: Math.min(Math.max(Number(body.currentMilestone ?? 1), 1), definition.milestones.length), stateJson: JSON.stringify(body.state ?? {}), updatedAt };
    await getDb().insert(projects).values(value).onConflictDoUpdate({ target: [projects.courseId, projects.userId, projects.title], set: { progress: value.progress, currentMilestone: value.currentMilestone, stateJson: value.stateJson, updatedAt } });
    return Response.json({ progress: value });
  } catch (error) { return Response.json({ error: "Project progress could not be saved", detail: error instanceof Error ? error.message : "Unknown error" }, { status: 500 }); }
}


import { eq } from "drizzle-orm";
import { getDb } from "../../../db";
import { knowledgeSources } from "../../../db/schema";
import { DEFAULT_COURSE_ID } from "../../../lib/course-knowledge";

export async function GET() {
  try { return Response.json({ sources: await getDb().select().from(knowledgeSources).where(eq(knowledgeSources.courseId, DEFAULT_COURSE_ID)).limit(100) }); }
  catch { return Response.json({ sources: [], persisted: false }); }
}

export async function POST(request: Request) {
  try {
    const body = await request.json() as { title?: string; chapter?: string; content?: string; pageStart?: number; pageEnd?: number; status?: "draft" | "reviewed" | "published" };
    if (!body.title?.trim() || !body.content?.trim()) return Response.json({ error: "title and content are required" }, { status: 400 });
    const timestamp = new Date().toISOString();
    const source = { id: crypto.randomUUID(), courseId: DEFAULT_COURSE_ID, title: body.title.trim(), sourceType: "lecture", status: body.status ?? "draft", chapter: body.chapter?.trim() ?? "", pageStart: body.pageStart ?? null, pageEnd: body.pageEnd ?? null, content: body.content.trim(), checksum: "", createdAt: timestamp, publishedAt: body.status === "published" ? timestamp : null };
    await getDb().insert(knowledgeSources).values(source);
    return Response.json({ source }, { status: 201 });
  } catch (error) { return Response.json({ error: "Knowledge source could not be saved", detail: error instanceof Error ? error.message : "Unknown error" }, { status: 500 }); }
}


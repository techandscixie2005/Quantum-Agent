/**
 * Teacher resume endpoint for LangGraph interrupt/resume.
 *
 * POST /api/tutor/resume
 * Body: { sessionId: string, approved: boolean, comment?: string }
 *
 * Issues a Command({ resume: ... }) to continue a paused graph.
 */

import { Command } from "@langchain/langgraph";
import { tutorGraph } from "../../../../lib/agent";
import { extractTeacherCookie, verifyTeacherSession } from "../../../../lib/teacher-auth";

export async function POST(request: Request) {
  try {
    // Authenticate teacher
    const cookie = extractTeacherCookie(request);
    if (!cookie || !(await verifyTeacherSession(cookie))) {
      return Response.json({ error: "需要教师权限" }, { status: 401 });
    }

    const body = await request.json() as {
      sessionId?: string;
      approved?: boolean;
      comment?: string;
    };

    const sessionId = body.sessionId;
    if (!sessionId) {
      return Response.json({ error: "sessionId is required" }, { status: 400 });
    }

    const threadId = `tutor-${sessionId}`;

    // Resume the graph with teacher approval/denial
    const result = await tutorGraph.invoke(
      new Command({
        resume: {
          approved: body.approved ?? true,
          comment: body.comment ?? "",
          reviewer: "teacher",
          reviewedAt: new Date().toISOString(),
        },
      }),
      {
        configurable: {
          thread_id: threadId,
        },
      },
    );

    return Response.json({
      resumed: true,
      threadId,
      state: {
        riskLevel: (result as Record<string, unknown>).riskLevel,
        escalated: (result as Record<string, unknown>).escalated,
        needsTeacherReview: (result as Record<string, unknown>).needsTeacherReview,
      },
    });
  } catch (error) {
    return Response.json(
      {
        error: "Resume failed",
        detail: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 500 },
    );
  }
}
import { z } from "zod";
import type { TraceScope } from "./contracts";

export const pendingReviewPageSchema = z.object({
  course_id: z.string().uuid(), curriculum_edition_id: z.string().uuid(),
  items: z.array(z.object({
    conversation_id: z.string().uuid(), turn_id: z.string().uuid(),
    interrupt_id: z.string().uuid(), student_user_id: z.string().uuid(),
    student_display_name: z.string().max(500), mode: z.enum([
      "learn_concepts", "review_derivations", "run_experiments", "work_on_projects",
    ]),
    reasons: z.array(z.string().max(100)).max(32), status: z.literal("pending"),
    created_at: z.string().datetime({ offset: true }),
  }).strict()).max(100),
  total: z.number().int().nonnegative(), limit: z.number().int().min(1).max(100),
  offset: z.number().int().nonnegative(), has_more: z.boolean(),
}).strict();

export type PendingReview = z.infer<typeof pendingReviewPageSchema>["items"][number];
export function parsePendingReviews(raw: unknown, scope: TraceScope) {
  const page = pendingReviewPageSchema.parse(raw);
  if (page.course_id !== scope.courseId || page.curriculum_edition_id !== scope.curriculumEditionId) {
    throw new Error("Pending reviews crossed the requested course boundary");
  }
  return page;
}

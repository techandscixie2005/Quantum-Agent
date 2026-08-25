import { z } from "zod";

import type { TeachingScope } from "@/app/components/teaching/contracts";

const uuid = z.string().uuid();

export const chapterContextSchema = z
  .object({
    id: uuid,
    ordinal: z.number().int().nonnegative(),
    title: z.string().min(1).max(1_000),
    canonical_path: z.string().min(1).max(1_000),
  })
  .strict();

export const courseEditionContextSchema = z
  .object({
    course_id: uuid,
    course_code: z.string().min(1).max(100),
    course_title: z.string().min(1).max(500),
    institution: z.string().min(1).max(300),
    role: z.enum(["student", "ta", "teacher", "admin"]),
    curriculum_edition_id: uuid,
    edition_title: z.string().min(1).max(500),
    academic_year: z.string().max(40).nullable(),
    term: z.string().max(80).nullable(),
    chapters: z.array(chapterContextSchema).max(200),
  })
  .strict();

export const studentCourseContextSchema = z
  .object({
    user_id: uuid,
    display_name: z.string().min(1).max(200),
    courses: z.array(courseEditionContextSchema).max(50),
  })
  .strict();

export type ChapterContext = z.infer<typeof chapterContextSchema>;
export type CourseEditionContext = z.infer<typeof courseEditionContextSchema>;
export type StudentCourseContext = z.infer<typeof studentCourseContextSchema>;

const extractionSchema = z
  .object({
    id: uuid,
    kind: z.string().min(1).max(80),
    pipeline_name: z.string().min(1).max(200),
    pipeline_version: z.string().min(1).max(100),
    extraction_method: z.string().min(1).max(100),
    status: z.enum([
      "pending",
      "running",
      "needs_confirmation",
      "succeeded",
      "confirmed",
      "rejected",
      "failed",
    ]),
    confidence: z.number().min(0).max(1).nullable(),
    requires_confirmation: z.boolean(),
    evidence: z.record(z.string(), z.unknown()),
    ambiguities: z.array(z.record(z.string(), z.unknown())).max(100),
    confirmation: z.record(z.string(), z.unknown()),
    failure_code: z.string().max(160).nullable(),
    created_at: z.string().datetime({ offset: true }),
    updated_at: z.string().datetime({ offset: true }),
  })
  .strict();

export const attachmentSchema = z
  .object({
    id: uuid,
    course_id: uuid,
    curriculum_edition_id: uuid,
    kind: z.enum(["image", "document", "text"]),
    filename: z.string().min(1).max(255),
    media_type: z.string().min(1).max(255),
    byte_size: z.number().int().positive(),
    sha256: z.string().regex(/^[a-f0-9]{64}$/),
    status: z.enum(["quarantined", "ready", "rejected", "deleted"]),
    validation: z.record(z.string(), z.unknown()),
    created_at: z.string().datetime({ offset: true }),
    updated_at: z.string().datetime({ offset: true }),
    idempotent_replay: z.boolean(),
    extraction: extractionSchema.nullable(),
  })
  .strict();

export type AgentAttachment = z.infer<typeof attachmentSchema>;

export function parseStudentCourseContext(value: unknown): StudentCourseContext {
  return studentCourseContextSchema.parse(value);
}

export function parseAgentAttachment(value: unknown): AgentAttachment {
  return attachmentSchema.parse(value);
}

export function scopeFromCourse(course: CourseEditionContext): TeachingScope {
  return {
    courseId: course.course_id,
    curriculumEditionId: course.curriculum_edition_id,
  };
}

import { index, integer, real, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

export const users = sqliteTable("users", {
  id: text("id").primaryKey(),
  email: text("email").notNull(),
  displayName: text("display_name").notNull(),
  role: text("role", { enum: ["student", "ta", "teacher", "admin"] }).notNull().default("student"),
  createdAt: text("created_at").notNull(),
}, (table) => [uniqueIndex("users_email_idx").on(table.email)]);

export const courses = sqliteTable("courses", {
  id: text("id").primaryKey(),
  title: text("title").notNull(),
  term: text("term").notNull(),
  instructor: text("instructor").notNull(),
  answerPolicy: text("answer_policy").notNull().default("guided"),
  maxHintLevel: integer("max_hint_level").notNull().default(3),
  createdAt: text("created_at").notNull(),
});

export const courseMembers = sqliteTable("course_members", {
  id: text("id").primaryKey(),
  courseId: text("course_id").notNull().references(() => courses.id),
  userId: text("user_id").notNull().references(() => users.id),
  role: text("role").notNull(),
  joinedAt: text("joined_at").notNull(),
}, (table) => [uniqueIndex("course_member_unique_idx").on(table.courseId, table.userId)]);

export const knowledgeSources = sqliteTable("knowledge_sources", {
  id: text("id").primaryKey(),
  courseId: text("course_id").notNull().references(() => courses.id),
  title: text("title").notNull(),
  sourceType: text("source_type").notNull().default("lecture"),
  status: text("status", { enum: ["draft", "reviewed", "published", "archived"] }).notNull().default("draft"),
  chapter: text("chapter").notNull().default(""),
  pageStart: integer("page_start"),
  pageEnd: integer("page_end"),
  content: text("content").notNull(),
  checksum: text("checksum").notNull().default(""),
  createdAt: text("created_at").notNull(),
  publishedAt: text("published_at"),
}, (table) => [index("knowledge_course_status_idx").on(table.courseId, table.status)]);

export const tutorSessions = sqliteTable("tutor_sessions", {
  id: text("id").primaryKey(),
  userId: text("user_id").notNull().references(() => users.id),
  courseId: text("course_id").notNull().references(() => courses.id),
  mode: text("mode").notNull(),
  title: text("title").notNull(),
  hintLevel: integer("hint_level").notNull().default(1),
  status: text("status").notNull().default("active"),
  createdAt: text("created_at").notNull(),
  updatedAt: text("updated_at").notNull(),
}, (table) => [index("sessions_user_updated_idx").on(table.userId, table.updatedAt)]);

export const tutorTurns = sqliteTable("tutor_turns", {
  id: text("id").primaryKey(),
  sessionId: text("session_id").notNull().references(() => tutorSessions.id),
  role: text("role", { enum: ["student", "assistant"] }).notNull(),
  content: text("content").notNull(),
  taskClass: text("task_class"),
  hintLevel: integer("hint_level"),
  modelProvider: text("model_provider"),
  modelName: text("model_name"),
  evidenceJson: text("evidence_json").notNull().default("[]"),
  traceJson: text("trace_json").notNull().default("[]"),
  createdAt: text("created_at").notNull(),
}, (table) => [index("turns_session_created_idx").on(table.sessionId, table.createdAt)]);

export const toolRuns = sqliteTable("tool_runs", {
  id: text("id").primaryKey(),
  sessionId: text("session_id").references(() => tutorSessions.id),
  toolName: text("tool_name").notNull(),
  inputJson: text("input_json").notNull(),
  outputJson: text("output_json").notNull(),
  status: text("status", { enum: ["passed", "failed", "inconclusive"] }).notNull(),
  durationMs: integer("duration_ms").notNull().default(0),
  createdAt: text("created_at").notNull(),
}, (table) => [index("tool_runs_session_idx").on(table.sessionId)]);

export const studentStates = sqliteTable("student_states", {
  id: text("id").primaryKey(),
  userId: text("user_id").notNull().references(() => users.id),
  courseId: text("course_id").notNull().references(() => courses.id),
  conceptId: text("concept_id").notNull(),
  mastery: real("mastery").notNull().default(0),
  hintDependency: real("hint_dependency").notNull().default(0),
  misconception: text("misconception"),
  status: text("status").notNull().default("learning"),
  updatedAt: text("updated_at").notNull(),
}, (table) => [uniqueIndex("student_concept_unique_idx").on(table.userId, table.courseId, table.conceptId)]);

export const escalations = sqliteTable("escalations", {
  id: text("id").primaryKey(),
  sessionId: text("session_id").notNull().references(() => tutorSessions.id),
  reason: text("reason").notNull(),
  status: text("status").notNull().default("open"),
  createdAt: text("created_at").notNull(),
  resolvedAt: text("resolved_at"),
}, (table) => [index("escalations_status_idx").on(table.status, table.createdAt)]);

export const projects = sqliteTable("projects", {
  id: text("id").primaryKey(),
  courseId: text("course_id").notNull().references(() => courses.id),
  userId: text("user_id").notNull().references(() => users.id),
  title: text("title").notNull(),
  progress: real("progress").notNull().default(0),
  currentMilestone: integer("current_milestone").notNull().default(1),
  stateJson: text("state_json").notNull().default("{}"),
  updatedAt: text("updated_at").notNull(),
}, (table) => [uniqueIndex("project_user_title_idx").on(table.courseId, table.userId, table.title)]);

export const modelSettings = sqliteTable("model_settings", {
  id: text("id").primaryKey(),
  scope: text("scope").notNull().default("course"),
  scopeId: text("scope_id").notNull(),
  provider: text("provider").notNull(),
  model: text("model").notNull(),
  updatedBy: text("updated_by").notNull(),
  updatedAt: text("updated_at").notNull(),
}, (table) => [uniqueIndex("model_scope_unique_idx").on(table.scope, table.scopeId)]);


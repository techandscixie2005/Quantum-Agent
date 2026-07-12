CREATE TABLE `course_members` (
	`id` text PRIMARY KEY NOT NULL,
	`course_id` text NOT NULL,
	`user_id` text NOT NULL,
	`role` text NOT NULL,
	`joined_at` text NOT NULL,
	FOREIGN KEY (`course_id`) REFERENCES `courses`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `course_member_unique_idx` ON `course_members` (`course_id`,`user_id`);--> statement-breakpoint
CREATE TABLE `courses` (
	`id` text PRIMARY KEY NOT NULL,
	`title` text NOT NULL,
	`term` text NOT NULL,
	`instructor` text NOT NULL,
	`answer_policy` text DEFAULT 'guided' NOT NULL,
	`max_hint_level` integer DEFAULT 3 NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `escalations` (
	`id` text PRIMARY KEY NOT NULL,
	`session_id` text NOT NULL,
	`reason` text NOT NULL,
	`status` text DEFAULT 'open' NOT NULL,
	`created_at` text NOT NULL,
	`resolved_at` text,
	FOREIGN KEY (`session_id`) REFERENCES `tutor_sessions`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `escalations_status_idx` ON `escalations` (`status`,`created_at`);--> statement-breakpoint
CREATE TABLE `knowledge_sources` (
	`id` text PRIMARY KEY NOT NULL,
	`course_id` text NOT NULL,
	`title` text NOT NULL,
	`source_type` text DEFAULT 'lecture' NOT NULL,
	`status` text DEFAULT 'draft' NOT NULL,
	`chapter` text DEFAULT '' NOT NULL,
	`page_start` integer,
	`page_end` integer,
	`content` text NOT NULL,
	`checksum` text DEFAULT '' NOT NULL,
	`created_at` text NOT NULL,
	`published_at` text,
	FOREIGN KEY (`course_id`) REFERENCES `courses`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `knowledge_course_status_idx` ON `knowledge_sources` (`course_id`,`status`);--> statement-breakpoint
CREATE TABLE `model_settings` (
	`id` text PRIMARY KEY NOT NULL,
	`scope` text DEFAULT 'course' NOT NULL,
	`scope_id` text NOT NULL,
	`provider` text NOT NULL,
	`model` text NOT NULL,
	`updated_by` text NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `model_scope_unique_idx` ON `model_settings` (`scope`,`scope_id`);--> statement-breakpoint
CREATE TABLE `projects` (
	`id` text PRIMARY KEY NOT NULL,
	`course_id` text NOT NULL,
	`user_id` text NOT NULL,
	`title` text NOT NULL,
	`progress` real DEFAULT 0 NOT NULL,
	`current_milestone` integer DEFAULT 1 NOT NULL,
	`state_json` text DEFAULT '{}' NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`course_id`) REFERENCES `courses`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `project_user_title_idx` ON `projects` (`course_id`,`user_id`,`title`);--> statement-breakpoint
CREATE TABLE `student_states` (
	`id` text PRIMARY KEY NOT NULL,
	`user_id` text NOT NULL,
	`course_id` text NOT NULL,
	`concept_id` text NOT NULL,
	`mastery` real DEFAULT 0 NOT NULL,
	`hint_dependency` real DEFAULT 0 NOT NULL,
	`misconception` text,
	`status` text DEFAULT 'learning' NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`course_id`) REFERENCES `courses`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `student_concept_unique_idx` ON `student_states` (`user_id`,`course_id`,`concept_id`);--> statement-breakpoint
CREATE TABLE `tool_runs` (
	`id` text PRIMARY KEY NOT NULL,
	`session_id` text,
	`tool_name` text NOT NULL,
	`input_json` text NOT NULL,
	`output_json` text NOT NULL,
	`status` text NOT NULL,
	`duration_ms` integer DEFAULT 0 NOT NULL,
	`created_at` text NOT NULL,
	FOREIGN KEY (`session_id`) REFERENCES `tutor_sessions`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `tool_runs_session_idx` ON `tool_runs` (`session_id`);--> statement-breakpoint
CREATE TABLE `tutor_sessions` (
	`id` text PRIMARY KEY NOT NULL,
	`user_id` text NOT NULL,
	`course_id` text NOT NULL,
	`mode` text NOT NULL,
	`title` text NOT NULL,
	`hint_level` integer DEFAULT 1 NOT NULL,
	`status` text DEFAULT 'active' NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`course_id`) REFERENCES `courses`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `sessions_user_updated_idx` ON `tutor_sessions` (`user_id`,`updated_at`);--> statement-breakpoint
CREATE TABLE `tutor_turns` (
	`id` text PRIMARY KEY NOT NULL,
	`session_id` text NOT NULL,
	`role` text NOT NULL,
	`content` text NOT NULL,
	`task_class` text,
	`hint_level` integer,
	`model_provider` text,
	`model_name` text,
	`evidence_json` text DEFAULT '[]' NOT NULL,
	`trace_json` text DEFAULT '[]' NOT NULL,
	`created_at` text NOT NULL,
	FOREIGN KEY (`session_id`) REFERENCES `tutor_sessions`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `turns_session_created_idx` ON `tutor_turns` (`session_id`,`created_at`);--> statement-breakpoint
CREATE TABLE `users` (
	`id` text PRIMARY KEY NOT NULL,
	`email` text NOT NULL,
	`display_name` text NOT NULL,
	`role` text DEFAULT 'student' NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `users_email_idx` ON `users` (`email`);
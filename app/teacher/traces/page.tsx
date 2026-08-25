import type { Metadata } from "next";
import Link from "next/link";

import { TraceQueryProvider } from "@/app/components/teacher-traces/TraceQueryProvider";
import { TraceReviewWorkspace } from "@/app/components/teacher-traces/TraceReviewWorkspace";
import {
  traceScopeSchema,
  type TraceScope,
} from "@/app/components/teacher-traces/contracts";
import styles from "@/app/components/teacher-traces/trace-review.module.css";

export const metadata: Metadata = {
  title: "Agent Trace 复核 · Quantum Agent",
  description: "教学团队检查课程证据、诊断、策略、工具结果与 LangGraph 人工复核状态。",
};

type PageSearchParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function scopeHref(path: string, scope: TraceScope): string {
  const query = new URLSearchParams({
    course_id: scope.courseId,
    curriculum_edition_id: scope.curriculumEditionId,
  });
  return `${path}?${query.toString()}`;
}

export default async function TeacherTracesPage({
  searchParams,
}: Readonly<{ searchParams: Promise<PageSearchParams> }>) {
  const params = await searchParams;
  const parsed = traceScopeSchema.safeParse({
    courseId: first(params.course_id).trim(),
    curriculumEditionId: first(params.curriculum_edition_id).trim(),
  });

  return (
    <div className={styles.pageShell}>
      <header className={styles.masthead}>
        <Link className={styles.brand} href="/">
          <span className={styles.brandMark} aria-hidden="true">
            Ψ
          </span>
          <span>
            <strong>Quantum Agent</strong>
            <small>Teaching governance</small>
          </span>
        </Link>
        <div className={styles.mastheadTitle}>
          <span>QA / TRACE REVIEW</span>
          <strong>教学工作流审阅台</strong>
        </div>
        <nav className={styles.topNav} aria-label="教学团队导航">
          {parsed.success ? (
            <Link href={scopeHref("/teacher/knowledge", parsed.data)}>知识治理</Link>
          ) : null}
          <Link href="/agent">学生 Agent</Link>
        </nav>
      </header>

      {parsed.success ? (
        <TraceQueryProvider>
          <TraceReviewWorkspace scope={parsed.data} />
        </TraceQueryProvider>
      ) : (
        <main className={styles.scopeGate}>
          <span className={styles.sectionLabel}>COURSE BOUNDARY</span>
          <h1>先选择要审阅的课程版本</h1>
          <p>
            Trace、人工复核状态与证据均按课程和版本隔离。此页面使用当前登录的课程会话，不接受独立教师密码。
          </p>
          <form method="get" action="/teacher/traces" className={styles.scopeForm}>
            <label>
              <span>Course UUID</span>
              <input
                required
                name="course_id"
                defaultValue={first(params.course_id)}
                autoComplete="off"
                placeholder="00000000-0000-0000-0000-000000000000"
              />
            </label>
            <label>
              <span>Curriculum edition UUID</span>
              <input
                required
                name="curriculum_edition_id"
                defaultValue={first(params.curriculum_edition_id)}
                autoComplete="off"
                placeholder="00000000-0000-0000-0000-000000000000"
              />
            </label>
            <button type="submit">进入审阅台</button>
          </form>
        </main>
      )}
    </div>
  );
}

import Link from "next/link";

import { isValidTeachingScope, type TeachingScope } from "./contracts";
import styles from "./teaching.module.css";

function scopeQuery(scope?: TeachingScope): string {
  if (!scope || !isValidTeachingScope(scope)) return "";
  const params = new URLSearchParams({
    course_id: scope.courseId,
    curriculum_edition_id: scope.curriculumEditionId,
  });
  return `?${params.toString()}`;
}

export function TeachingHeader({ scope }: { scope?: TeachingScope }) {
  const query = scopeQuery(scope);
  return (
    <header className={styles.header}>
      <Link className={styles.brand} href={`/course${query}`} aria-label="Quantum Agent 学习工作台">
        <span aria-hidden="true">QA</span>
        <span>
          <strong>Quantum Agent</strong>
          <small>量子物理 · 教学工作台</small>
        </span>
      </Link>
      <nav className={styles.topNav} aria-label="课程区域">
        <Link href={`/course${query}`} aria-current="page">学习工作台</Link>
        <Link href={`/knowledge-graph${query}`}>课程图谱</Link>
        <Link href={`/teacher/knowledge${query}`}>教师复核</Link>
      </nav>
      <div className={styles.workflowSeal}>
        <span aria-hidden="true" />
        固定流程 · 证据优先
      </div>
    </header>
  );
}

export function TeachingScopeGate({
  courseId = "",
  curriculumEditionId = "",
}: {
  courseId?: string;
  curriculumEditionId?: string;
}) {
  return (
    <main className={styles.scopePage} id="main-content">
      <section className={styles.scopeSheet} aria-labelledby="teaching-scope-title">
        <p className={styles.eyebrow}>COURSE BOUNDARY</p>
        <h1 id="teaching-scope-title">先确定课程与教学版本</h1>
        <p>
          每次解释、提示和科学验证都绑定同一门课程与课程版本。平台不会跨版本检索，也不会用示例答案填补缺失资料。
        </p>
        <form method="get" action="/course">
          <label htmlFor="course-id">
            课程 ID <span>必填</span>
          </label>
          <input
            id="course-id"
            name="course_id"
            defaultValue={courseId}
            autoComplete="off"
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            required
            pattern="[0-9a-fA-F-]{36}"
          />
          <label htmlFor="edition-id">
            课程版本 ID <span>必填</span>
          </label>
          <input
            id="edition-id"
            name="curriculum_edition_id"
            defaultValue={curriculumEditionId}
            autoComplete="off"
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            required
            pattern="[0-9a-fA-F-]{36}"
          />
          <button type="submit">进入学习工作台</button>
        </form>
        <small>后端仍会校验登录会话与课程成员身份；修改 URL 不会扩大权限。</small>
      </section>
    </main>
  );
}

export function TeachingScopeStamp({ scope }: { scope: TeachingScope }) {
  return (
    <div className={styles.scopeStamp} aria-label="当前课程范围">
      <span>COURSE</span>
      <code title={scope.courseId}>{scope.courseId}</code>
      <span>EDITION</span>
      <code title={scope.curriculumEditionId}>{scope.curriculumEditionId}</code>
    </div>
  );
}


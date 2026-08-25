import Link from "next/link";

import { isValidScope, type PhaseOneScope } from "./contracts";
import styles from "./phase-one.module.css";

type HeaderProps = Readonly<{
  area: "student" | "teacher";
  scope?: PhaseOneScope;
}>;

export function PhaseOneHeader({ area, scope }: HeaderProps) {
  const scopedQuery =
    scope && isValidScope(scope)
      ? `?course_id=${encodeURIComponent(scope.courseId)}&curriculum_edition_id=${encodeURIComponent(scope.curriculumEditionId)}`
      : "";
  return (
    <header className={styles.header}>
      <div className={styles.brandBlock}>
        <span className={styles.brandSigil} aria-hidden="true">QA</span>
        <div>
          <strong>Quantum Agent</strong>
          <span>课程知识模型 · Phase 1</span>
        </div>
      </div>
      <nav className={styles.areaNav} aria-label="知识图谱区域">
        <Link
          href={`/knowledge-graph${scopedQuery}`}
          aria-current={area === "student" ? "page" : undefined}
        >
          学生图谱
        </Link>
        <Link
          href={`/teacher/knowledge${scopedQuery}`}
          aria-current={area === "teacher" ? "page" : undefined}
        >
          教师复核
        </Link>
      </nav>
      <div className={styles.releaseGate}>
        <span aria-hidden="true" />
        {area === "student" ? "仅已批准并发布" : "教师治理视图"}
      </div>
    </header>
  );
}

/**
 * The legacy root layout registers a DOMContentLoaded callback before the
 * optional CDN auto-render script is guaranteed to exist. Phase 1 formulas use
 * the safer KaTeX render API directly, but this tiny early guard prevents a
 * network-blocked CDN from crashing unrelated knowledge pages.
 */
export function PhaseOneMathGuard() {
  return (
    <script
      // Static code only: no course or user content crosses this boundary.
      dangerouslySetInnerHTML={{
        __html: "window.renderMathInElement=window.renderMathInElement||function(){};",
      }}
    />
  );
}

type ScopeGateProps = Readonly<{
  area: "student" | "teacher";
  courseId?: string;
  curriculumEditionId?: string;
}>;

export function ScopeGate({ area, courseId = "", curriculumEditionId = "" }: ScopeGateProps) {
  return (
    <main className={styles.scopePage}>
      <section className={styles.scopeSheet} aria-labelledby="scope-title">
        <p className={styles.eyebrow}>课程边界</p>
        <h1 id="scope-title">选择课程与课程版本</h1>
        <p>
          知识图谱不会跨课程或跨教学版本检索。请使用平台分配的 UUID；这里不提供示例数据，也不会猜测当前课程。
        </p>
        <form method="get" action={area === "student" ? "/knowledge-graph" : "/teacher/knowledge"}>
          <label>
            课程 ID
            <input
              name="course_id"
              defaultValue={courseId}
              inputMode="text"
              autoComplete="off"
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              required
              pattern="[0-9a-fA-F-]{36}"
            />
          </label>
          <label>
            课程版本 ID
            <input
              name="curriculum_edition_id"
              defaultValue={curriculumEditionId}
              inputMode="text"
              autoComplete="off"
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              required
              pattern="[0-9a-fA-F-]{36}"
            />
          </label>
          <button type="submit">进入{area === "student" ? "课程图谱" : "复核工作台"}</button>
        </form>
        <small>身份与课程成员权限仍由后端校验；修改 URL 不能扩大访问范围。</small>
      </section>
    </main>
  );
}

export function ScopeStamp({ scope }: { scope: PhaseOneScope }) {
  return (
    <div className={styles.scopeStamp} aria-label="当前课程范围">
      <span>COURSE</span>
      <code title={scope.courseId}>{scope.courseId}</code>
      <span>EDITION</span>
      <code title={scope.curriculumEditionId}>{scope.curriculumEditionId}</code>
    </div>
  );
}

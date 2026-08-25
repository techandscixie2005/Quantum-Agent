import type { Metadata } from "next";

import { PhaseOneMathGuard } from "@/app/components/knowledge/PhaseOneChrome";
import {
  TeachingHeader,
  TeachingScopeGate,
  TeachingScopeStamp,
} from "@/app/components/teaching/TeachingChrome";
import { TeachingWorkspace } from "@/app/components/teaching/TeachingWorkspace";
import {
  isTeachingMode,
  isValidTeachingScope,
  type TeachingMode,
  type TeachingScope,
} from "@/app/components/teaching/contracts";
import styles from "@/app/components/teaching/teaching.module.css";

export const metadata: Metadata = {
  title: "学习工作台 · Quantum Agent",
  description: "基于课程知识图谱、教师答案政策与科学工具验证的量子物理学习工作台。",
};

type PageSearchParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

export default async function CourseTeachingPage({
  searchParams,
}: {
  searchParams: Promise<PageSearchParams>;
}) {
  const params = await searchParams;
  const scope: TeachingScope = {
    courseId: first(params.course_id).trim(),
    curriculumEditionId: first(params.curriculum_edition_id).trim(),
  };
  const requestedMode = first(params.mode).trim();
  const mode: TeachingMode = isTeachingMode(requestedMode) ? requestedMode : "learn_concepts";
  const validScope = isValidTeachingScope(scope);

  return (
    <div className={styles.shell}>
      <PhaseOneMathGuard />
      <a className={styles.skipLink} href="#main-content">跳到主要内容</a>
      <TeachingHeader scope={validScope ? scope : undefined} />
      {validScope ? (
        <main className={styles.main} id="main-content">
          <TeachingScopeStamp scope={scope} />
          <TeachingWorkspace
            key={`${scope.courseId}:${scope.curriculumEditionId}:${mode}`}
            scope={scope}
            initialMode={mode}
          />
        </main>
      ) : (
        <TeachingScopeGate
          courseId={scope.courseId}
          curriculumEditionId={scope.curriculumEditionId}
        />
      )}
    </div>
  );
}

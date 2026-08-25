import type { Metadata } from "next";

import {
  PhaseOneHeader,
  PhaseOneMathGuard,
  ScopeGate,
  ScopeStamp,
} from "@/app/components/knowledge/PhaseOneChrome";
import { StudentGraphExplorer } from "@/app/components/knowledge/StudentGraphExplorer";
import {
  isValidScope,
  type PhaseOneScope,
} from "@/app/components/knowledge/contracts";
import styles from "@/app/components/knowledge/phase-one.module.css";

export const metadata: Metadata = {
  title: "课程知识图谱 · Quantum Agent",
  description: "检索教师批准的量子物理概念、先修关系、公式与原始课程证据。",
};

type PageSearchParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

export default async function KnowledgeGraphPage({
  searchParams,
}: {
  searchParams: Promise<PageSearchParams>;
}) {
  const params = await searchParams;
  const scope: PhaseOneScope = {
    courseId: first(params.course_id).trim(),
    curriculumEditionId: first(params.curriculum_edition_id).trim(),
  };

  return (
    <div className={styles.shell}>
      <PhaseOneMathGuard />
      <PhaseOneHeader area="student" scope={isValidScope(scope) ? scope : undefined} />
      {isValidScope(scope) ? (
        <main className={styles.studentMain}>
          <ScopeStamp scope={scope} />
          <StudentGraphExplorer scope={scope} />
        </main>
      ) : (
        <ScopeGate
          area="student"
          courseId={scope.courseId}
          curriculumEditionId={scope.curriculumEditionId}
        />
      )}
    </div>
  );
}

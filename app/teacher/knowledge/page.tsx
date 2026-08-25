import type { Metadata } from "next";

import {
  PhaseOneHeader,
  PhaseOneMathGuard,
  ScopeGate,
  ScopeStamp,
} from "@/app/components/knowledge/PhaseOneChrome";
import { TeacherKnowledgeReview } from "@/app/components/knowledge/TeacherKnowledgeReview";
import {
  isValidScope,
  type PhaseOneScope,
} from "@/app/components/knowledge/contracts";
import styles from "@/app/components/knowledge/phase-one.module.css";

export const metadata: Metadata = {
  title: "知识治理复核 · Quantum Agent",
  description: "教师检查、批准或拒绝带原始课程证据的量子物理知识图谱候选项。",
};

type PageSearchParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

export default async function TeacherKnowledgePage({
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
      <PhaseOneHeader area="teacher" scope={isValidScope(scope) ? scope : undefined} />
      {isValidScope(scope) ? (
        <main className={styles.teacherMain}>
          <ScopeStamp scope={scope} />
          <TeacherKnowledgeReview scope={scope} />
        </main>
      ) : (
        <ScopeGate
          area="teacher"
          courseId={scope.courseId}
          curriculumEditionId={scope.curriculumEditionId}
        />
      )}
    </div>
  );
}

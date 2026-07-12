import courseware from "./courseware.generated.json";

export const DEFAULT_COURSE_ID = "qp-2026-spring";

export type KnowledgeChunk = {
  id: string;
  sourceId?: string;
  courseId: string;
  title: string;
  chapter: string;
  pages: string;
  pageNumber?: number;
  sourceUrl?: string;
  content: string;
  keywords: string[];
  status: "published";
};

export type CoursewareManifestItem = {
  id: string;
  title: string;
  chapter: string;
  pageCount: number;
  pdfUrl: string;
  topics: string[];
  checksum: string;
};

export const coursewareManifest = courseware.manifest as CoursewareManifestItem[];
export const seedKnowledge = courseware.chunks as KnowledgeChunk[];

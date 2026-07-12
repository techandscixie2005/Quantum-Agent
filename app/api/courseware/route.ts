import { coursewareManifest, seedKnowledge } from "../../../lib/course-knowledge";

export async function GET() {
  return Response.json({
    course: { id: "qp-2026-spring", title: "量子物理", term: "2026 春" },
    sources: coursewareManifest.map(({ checksum, ...source }) => ({ ...source, indexed: true, integrity: checksum.slice(0, 12) })),
    totals: { sources: coursewareManifest.length, pages: coursewareManifest.reduce((sum, source) => sum + source.pageCount, 0), chunks: seedKnowledge.length },
  });
}

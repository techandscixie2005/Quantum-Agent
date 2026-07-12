import type { Citation } from "./types";

/**
 * Builds a set of allowed citation IDs from the retrieval results.
 * Only these ids may appear in model-generated citations or UI evidence.
 */
export function buildCitationAllowlist(citations: Citation[]): Set<string> {
  const allowlist = new Set<string>();
  for (const citation of citations) {
    allowlist.add(citation.id);
    // Also allow chapter-based lookups for fuzzy matching
    if (citation.chapter) {
      allowlist.add(`chapter:${citation.chapter}`);
    }
  }
  return allowlist;
}

/**
 * Filters a list of citations to only those present in the allowlist.
 * Any citation not in the allowlist is dropped (could be a model hallucination).
 * Returns the filtered list and a list of rejected citation ids for audit.
 */
export function enforceCitationAllowlist(
  citations: Citation[],
  allowlist: Set<string>,
): { allowed: Citation[]; rejected: string[] } {
  const allowed: Citation[] = [];
  const rejected: string[] = [];
  for (const citation of citations) {
    if (allowlist.has(citation.id)) {
      allowed.push(citation);
    } else {
      rejected.push(citation.id);
    }
  }
  return { allowed, rejected };
}

/**
 * Check if a model-generated text references a citation id that is not in the
 * allowlist. Returns any suspicious citation references found.
 */
export function detectFabricatedCitations(
  text: string,
  allowlist: Set<string>,
): string[] {
  const fabricated: string[] = [];
  // Match patterns like [citation:xxx] or ref ids from retrieval
  const matches = text.matchAll(/\[(?:citation|ref|page):([^\]]+)\]/gi);
  for (const match of matches) {
    const id = match[1].trim();
    if (!allowlist.has(id) && !allowlist.has(`chapter:${id}`)) {
      fabricated.push(id);
    }
  }
  return [...new Set(fabricated)];
}
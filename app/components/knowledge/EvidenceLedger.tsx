import {
  locatorLabel,
  type ReviewEvidence,
  type StudentCitation,
} from "./contracts";
import styles from "./phase-one.module.css";

type LedgerCitation =
  | Readonly<{ source: "student"; citation: StudentCitation }>
  | Readonly<{ source: "review"; citation: ReviewEvidence }>;

function citationFields(item: LedgerCitation) {
  if (item.source === "student") {
    return {
      id: item.citation.evidence_id,
      title: item.citation.document_title,
      fileName: item.citation.source_file_name,
      version: item.citation.document_version,
      locator: locatorLabel(item.citation.locator),
      snippet: item.citation.evidence_snippet,
      sourceChunk: item.citation.source_chunk,
      sourceHash: item.citation.source_file_sha256,
      chunkHash: item.citation.source_chunk_sha256,
      evidenceHash: item.citation.evidence_sha256,
      support: item.citation.kind,
      section:
        [item.citation.chapter, ...item.citation.section_path].filter(Boolean).join(" / ") || null,
    };
  }
  return {
    id: item.citation.evidence_id,
    title: item.citation.source_document_title,
    fileName: item.citation.source_file_name,
    version: null,
    locator: locatorLabel(item.citation.locator),
    snippet: item.citation.evidence_snippet,
    sourceChunk: item.citation.source_chunk,
    sourceHash: item.citation.source_file_sha256,
    chunkHash: null,
    evidenceHash: null,
    support: item.citation.support_role,
    section: null,
  };
}

export function EvidenceLedger({
  citations,
  heading = "原始课程证据",
}: {
  citations: readonly LedgerCitation[];
  heading?: string;
}) {
  return (
    <section className={styles.evidenceLedger} aria-labelledby="evidence-ledger-title">
      <div className={styles.ledgerHeading}>
        <div>
          <p className={styles.eyebrow}>PROVENANCE LEDGER</p>
          <h2 id="evidence-ledger-title">{heading}</h2>
        </div>
        <span>{citations.length} 条可追溯证据</span>
      </div>
      {citations.length === 0 ? (
        <div className={styles.emptyState}>
          <strong>没有可验证的原始证据</strong>
          <p>该条目不能被批准，也不会出现在学生图谱中。</p>
        </div>
      ) : (
        <ol className={styles.evidenceRail}>
          {citations.map((item) => {
            const citation = citationFields(item);
            return (
              <li key={citation.id}>
                <div className={styles.railMarker} aria-hidden="true" />
                <article>
                  <div className={styles.citationTopline}>
                    <span>课程材料 · {citation.support}</span>
                    <code>{citation.locator}</code>
                  </div>
                  <h3>{citation.title}</h3>
                  <p className={styles.fileLine}>
                    <strong>{citation.fileName}</strong>
                    {citation.version ? ` · 版本 ${citation.version}` : ""}
                    {citation.section ? ` · ${citation.section}` : ""}
                  </p>
                  <blockquote>{citation.snippet}</blockquote>
                  <details>
                    <summary>核对完整来源块与哈希</summary>
                    <pre>{citation.sourceChunk}</pre>
                    <dl className={styles.hashGrid}>
                      <div>
                        <dt>文件 SHA-256</dt>
                        <dd><code>{citation.sourceHash}</code></dd>
                      </div>
                      {citation.chunkHash ? (
                        <div>
                          <dt>来源块 SHA-256</dt>
                          <dd><code>{citation.chunkHash}</code></dd>
                        </div>
                      ) : null}
                      {citation.evidenceHash ? (
                        <div>
                          <dt>证据 SHA-256</dt>
                          <dd><code>{citation.evidenceHash}</code></dd>
                        </div>
                      ) : null}
                    </dl>
                  </details>
                </article>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

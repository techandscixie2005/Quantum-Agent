"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { EvidenceLedger } from "./EvidenceLedger";
import { FormulaDisplay } from "./FormulaDisplay";
import {
  ContractError,
  parseApiError,
  parseCandidateActionResponse,
  parseReviewCandidateDetail,
  parseReviewQueueResponse,
  type CandidateActionResponse,
  type PhaseOneApiError,
  type PhaseOneScope,
  type ReviewCandidateDetail,
  type ReviewQueueItem,
} from "./contracts";
import styles from "./phase-one.module.css";

class ReviewRequestFailure extends Error {
  readonly code: string;
  readonly traceId?: string;

  constructor(error: PhaseOneApiError["error"]) {
    super(error.message);
    this.name = "ReviewRequestFailure";
    this.code = error.code;
    this.traceId = error.trace_id;
  }
}

function requestError(error: unknown): ReviewRequestFailure {
  if (error instanceof ReviewRequestFailure) return error;
  if (error instanceof ContractError) {
    return new ReviewRequestFailure({
      code: "CLIENT_CONTRACT_REJECTED",
      message: "服务响应未通过浏览器契约校验，候选项未被显示或修改。",
    });
  }
  return new ReviewRequestFailure({
    code: "NETWORK_FAILURE",
    message: "复核步骤未完成；当前选择和理由已保留，请检查连接后重试。",
  });
}

async function readResponse<T>(response: Response, parser: (value: unknown) => T): Promise<T> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ContractError("复核接口返回非 JSON 内容");
  }
  if (!response.ok) {
    const parsed = parseApiError(payload);
    throw new ReviewRequestFailure(
      parsed?.error ?? {
        code: `HTTP_${response.status}`,
        message: "复核请求失败；数据库状态未在页面中乐观更新。",
      },
    );
  }
  return parser(payload);
}

function scopeQuery(scope: PhaseOneScope): string {
  return new URLSearchParams({
    course_id: scope.courseId,
    curriculum_edition_id: scope.curriculumEditionId,
  }).toString();
}

function reviewStatus(status: ReviewQueueItem["status"]): string {
  const labels: Record<ReviewQueueItem["status"], string> = {
    review_required: "REVIEW_REQUIRED",
    in_review: "复核中",
    approved: "已批准",
    rejected: "已拒绝",
    superseded: "已合并替代",
  };
  return labels[status];
}

function timeLabel(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function ReviewErrorNotice({ error, onRetry }: { error: ReviewRequestFailure; onRetry: () => void }) {
  return (
    <div className={styles.errorNotice} role="alert">
      <strong>{error.message}</strong>
      <span>失败步骤未提交；候选项、证据和已输入理由保持不变。</span>
      <code>{error.code}{error.traceId ? ` · trace ${error.traceId}` : ""}</code>
      <button type="button" onClick={onRetry}>重试失败步骤</button>
    </div>
  );
}

type QueueProps = Readonly<{
  queue: readonly ReviewQueueItem[];
  selectedId: string | null;
  isLoading: boolean;
  hasLoaded: boolean;
  filter: string;
  onFilter: (value: string) => void;
  onSelect: (item: ReviewQueueItem) => void;
}>;

function ReviewQueue({ queue, selectedId, isLoading, hasLoaded, filter, onFilter, onSelect }: QueueProps) {
  const normalizedFilter = filter.trim().toLocaleLowerCase("zh-CN");
  const visibleQueue = useMemo(
    () =>
      normalizedFilter
        ? queue.filter((item) =>
            `${item.label} ${item.type_name} ${item.kind}`
              .toLocaleLowerCase("zh-CN")
              .includes(normalizedFilter),
          )
        : queue,
    [normalizedFilter, queue],
  );

  return (
    <aside className={styles.reviewQueue} aria-labelledby="review-queue-heading" aria-busy={isLoading}>
      <div className={styles.panelTitle}>
        <div>
          <p className={styles.eyebrow}>GOVERNANCE QUEUE</p>
          <h2 id="review-queue-heading">待复核候选</h2>
        </div>
        <span>{visibleQueue.length} / 本批 {queue.length}</span>
      </div>
      <label className={styles.queueFilter}>
        在当前批次筛选
        <input
          value={filter}
          onChange={(event) => onFilter(event.target.value)}
          placeholder="名称、类型或 node / relation"
        />
      </label>
      {isLoading && queue.length === 0 ? (
        <div className={styles.skeletonList} aria-label="正在加载复核队列"><i /><i /><i /></div>
      ) : null}
      {!isLoading && !hasLoaded ? (
        <div className={styles.emptyState}>
          <strong>复核批次尚未读取</strong>
          <p>使用页面上方的“加载批次”按钮，从教师鉴权接口读取当前课程版本。</p>
        </div>
      ) : null}
      {!isLoading && hasLoaded && queue.length === 0 ? (
        <div className={styles.emptyState}>
          <strong>当前批次没有待复核项</strong>
          <p>这只表示该接口返回的前 100 项为空，不代表所有课程材料都已完成治理。</p>
        </div>
      ) : null}
      {queue.length > 0 && visibleQueue.length === 0 ? (
        <div className={styles.emptyState}>
          <strong>筛选后没有候选项</strong>
          <p>清除筛选词可恢复当前批次；后台记录没有改变。</p>
        </div>
      ) : null}
      <ol className={styles.queueList}>
        {visibleQueue.map((item) => (
          <li key={`${item.kind}:${item.candidate_id}`}>
            <button
              type="button"
              aria-pressed={selectedId === item.candidate_id}
              onClick={() => onSelect(item)}
            >
              <div>
                <span className={item.status === "review_required" ? styles.reviewBadge : styles.neutralBadge}>
                  {reviewStatus(item.status)}
                </span>
                <code>{item.kind} · {item.type_name}</code>
              </div>
              <strong>{item.label}</strong>
              <small>
                修订 {item.revision_number} · {item.evidence_count} 条证据 · {timeLabel(item.updated_at)}
              </small>
            </button>
          </li>
        ))}
      </ol>
    </aside>
  );
}

function CandidateInspector({ detail, isLoading }: { detail: ReviewCandidateDetail | null; isLoading: boolean }) {
  const propertyCount = detail ? Object.keys(detail.properties).length : 0;
  return (
    <section className={styles.candidateInspector} aria-labelledby="candidate-heading" aria-busy={isLoading}>
      <div className={styles.panelTitle}>
        <div>
          <p className={styles.eyebrow}>TYPED CANDIDATE</p>
          <h2 id="candidate-heading">候选项检查</h2>
        </div>
        {detail ? <span>修订 {detail.item.revision_number}</span> : null}
      </div>
      {isLoading ? <div className={styles.graphLoading} role="status">正在读取候选项及来源绑定…</div> : null}
      {!detail && !isLoading ? (
        <div className={styles.graphEmpty}>
          <div className={styles.energyDiagram} aria-hidden="true"><i /><i /><i /></div>
          <strong>从左侧队列选择候选项</strong>
          <p>批准前需核对类型、端点、公式、抽取置信度和每条原始证据。</p>
        </div>
      ) : null}
      {detail ? (
        <article className={styles.candidateSheet}>
          <div className={styles.candidateHeading}>
            <div>
              <span className={detail.item.status === "review_required" ? styles.reviewBadge : styles.neutralBadge}>
                {reviewStatus(detail.item.status)}
              </span>
              <span className={styles.kindBadge}>{detail.item.kind} · {detail.item.type_name}</span>
              <h3>{detail.item.label}</h3>
            </div>
            <div className={styles.confidenceStamp}>
              <strong>{Math.round(detail.item.confidence * 100)}%</strong>
              <span>抽取置信度</span>
              <small>不是科学真值</small>
            </div>
          </div>
          <dl className={styles.candidateMetadata}>
            <div><dt>规范键</dt><dd><code>{detail.canonical_key}</code></dd></div>
            <div><dt>候选 ID</dt><dd><code>{detail.item.candidate_id}</code></dd></div>
            {detail.source_candidate_id ? (
              <div><dt>关系起点</dt><dd><code>{detail.source_candidate_id}</code></dd></div>
            ) : null}
            {detail.target_candidate_id ? (
              <div><dt>关系终点</dt><dd><code>{detail.target_candidate_id}</code></dd></div>
            ) : null}
          </dl>
          <section className={styles.claimBlock}>
            <span>候选说明</span>
            {detail.description ? <p>{detail.description}</p> : <p>抽取结果没有提供说明文字。</p>}
          </section>
          {detail.formula_latex ? <FormulaDisplay latex={detail.formula_latex} /> : null}
          {propertyCount > 0 ? (
            <details className={styles.propertyBlock}>
              <summary>检查 {propertyCount} 个结构化属性</summary>
              <pre>{JSON.stringify(detail.properties, null, 2)}</pre>
            </details>
          ) : (
            <p className={styles.noProperties}>没有额外结构化属性。</p>
          )}
        </article>
      ) : null}
    </section>
  );
}

type DecisionPanelProps = Readonly<{
  detail: ReviewCandidateDetail | null;
  rationale: string;
  pendingAction: "approve" | "reject" | null;
  decision: CandidateActionResponse | null;
  onRationale: (value: string) => void;
  onDecision: (action: "approve" | "reject") => void;
}>;

function DecisionPanel({
  detail,
  rationale,
  pendingAction,
  decision,
  onRationale,
  onDecision,
}: DecisionPanelProps) {
  const canDecide =
    detail !== null &&
    detail.evidence.length > 0 &&
    rationale.trim().length > 0 &&
    pendingAction === null &&
    decision?.candidate_id !== detail.item.candidate_id;
  return (
    <section className={styles.decisionPanel} aria-labelledby="decision-heading">
      <div className={styles.panelTitle}>
        <div>
          <p className={styles.eyebrow}>AUDITED DECISION</p>
          <h2 id="decision-heading">复核决定</h2>
        </div>
      </div>
      {!detail ? (
        <p className={styles.panelPrompt}>选择候选项后才能记录批准或拒绝理由。</p>
      ) : (
        <form onSubmit={(event) => event.preventDefault()}>
          <label htmlFor="review-rationale">
            决定理由 <span>必填，将进入审计记录</span>
          </label>
          <textarea
            id="review-rationale"
            value={rationale}
            onChange={(event) => onRationale(event.target.value)}
            minLength={1}
            maxLength={4000}
            required
            placeholder="说明证据是否支持术语、公式或关系，并记录需要保留的限定条件。"
          />
          {detail.evidence.length === 0 ? (
            <p className={styles.decisionBlocker}>没有可验证证据，批准操作已禁用。</p>
          ) : null}
          <div className={styles.decisionActions}>
            <button type="button" disabled={!canDecide} onClick={() => onDecision("approve")}>
              {pendingAction === "approve" ? "正在记录…" : "批准并排队投影"}
            </button>
            <button type="button" disabled={!canDecide} onClick={() => onDecision("reject")}>
              {pendingAction === "reject" ? "正在记录…" : "拒绝候选项"}
            </button>
          </div>
          <small>页面不会在后端事务完成前显示“已批准”。Neo4j 同步仍是后续、可重试的投影步骤。</small>
        </form>
      )}
      {decision && detail && decision.candidate_id === detail.item.candidate_id ? (
        <output className={styles.decisionReceipt} aria-live="polite">
          <strong>决定已写入审计事务</strong>
          <span>动作：{decision.action} · 投影状态：{decision.projection_state}</span>
          <code>decision {decision.decision_id}</code>
        </output>
      ) : null}
    </section>
  );
}

export function TeacherKnowledgeReview({ scope }: { scope: PhaseOneScope }) {
  const [queue, setQueue] = useState<readonly ReviewQueueItem[]>([]);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<ReviewQueueItem | null>(null);
  const [detail, setDetail] = useState<ReviewCandidateDetail | null>(null);
  const [rationale, setRationale] = useState("");
  const [decision, setDecision] = useState<CandidateActionResponse | null>(null);
  const [isQueueLoading, setIsQueueLoading] = useState(false);
  const [hasLoadedQueue, setHasLoadedQueue] = useState(false);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [pendingAction, setPendingAction] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<ReviewRequestFailure | null>(null);
  const queueAbort = useRef<AbortController | null>(null);
  const detailAbort = useRef<AbortController | null>(null);

  const loadQueue = useCallback(async () => {
    queueAbort.current?.abort();
    const controller = new AbortController();
    queueAbort.current = controller;
    setIsQueueLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/phase1/review/queue?${scopeQuery(scope)}`, {
        cache: "no-store",
        signal: controller.signal,
      });
      const parsed = await readResponse(response, parseReviewQueueResponse);
      setQueue(parsed);
      setHasLoadedQueue(true);
    } catch (caught) {
      if (!controller.signal.aborted) setError(requestError(caught));
    } finally {
      if (!controller.signal.aborted) setIsQueueLoading(false);
    }
  }, [scope]);

  useEffect(() => {
    return () => {
      queueAbort.current?.abort();
      detailAbort.current?.abort();
    };
  }, [loadQueue]);

  async function loadDetail(item: ReviewQueueItem) {
    detailAbort.current?.abort();
    const controller = new AbortController();
    detailAbort.current = controller;
    setSelected(item);
    setDetail(null);
    setRationale("");
    setDecision(null);
    setIsDetailLoading(true);
    setError(null);
    const params = new URLSearchParams({
      course_id: scope.courseId,
      curriculum_edition_id: scope.curriculumEditionId,
      candidate_id: item.candidate_id,
      kind: item.kind,
    });
    try {
      const response = await fetch(`/api/phase1/review/detail?${params}`, {
        cache: "no-store",
        signal: controller.signal,
      });
      const parsed = await readResponse(response, parseReviewCandidateDetail);
      setDetail(parsed);
    } catch (caught) {
      if (!controller.signal.aborted) setError(requestError(caught));
    } finally {
      if (!controller.signal.aborted) setIsDetailLoading(false);
    }
  }

  async function submitDecision(action: "approve" | "reject") {
    if (!detail || rationale.trim().length === 0 || pendingAction) return;
    setPendingAction(action);
    setError(null);
    try {
      const response = await fetch(`/api/phase1/review/decision?${scopeQuery(scope)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          candidate_id: detail.item.candidate_id,
          kind: detail.item.kind,
          action,
          rationale: rationale.trim(),
        }),
      });
      const parsed = await readResponse(response, parseCandidateActionResponse);
      setDecision(parsed);
      void loadQueue();
    } catch (caught) {
      setError(requestError(caught));
    } finally {
      setPendingAction(null);
    }
  }

  const retry = selected && !detail ? () => loadDetail(selected) : loadQueue;

  return (
    <>
      <section className={styles.teacherIntro}>
        <div>
          <p className={styles.eyebrow}>TEACHER GOVERNANCE · POSTGRES AUTHORITY</p>
          <h1>让每个知识项都经得起回看</h1>
          <p>逐项核对显式本体、候选差异与原始材料。批准决定先写入审计事务，再异步投影到 Neo4j。</p>
        </div>
        <div className={styles.queueBatchStatus}>
          <span>当前接口批次</span>
          <strong>
            {isQueueLoading ? "读取中" : hasLoadedQueue ? `${queue.length} 项` : "未读取"}
          </strong>
          <small>最多 100 项；不是全库总量</small>
          <button type="button" onClick={() => void loadQueue()} disabled={isQueueLoading}>
            {hasLoadedQueue ? "刷新批次" : "加载批次"}
          </button>
        </div>
      </section>

      {error ? <ReviewErrorNotice error={error} onRetry={() => void retry()} /> : null}

      <div className={styles.teacherGrid}>
        <ReviewQueue
          queue={queue}
          selectedId={selected?.candidate_id ?? null}
          isLoading={isQueueLoading}
          hasLoaded={hasLoadedQueue}
          filter={filter}
          onFilter={setFilter}
          onSelect={loadDetail}
        />
        <CandidateInspector detail={detail} isLoading={isDetailLoading} />
        <div className={styles.reviewEvidenceColumn}>
          <EvidenceLedger
            heading="候选项来源证据"
            citations={(detail?.evidence ?? []).map((citation) => ({ source: "review" as const, citation }))}
          />
          <DecisionPanel
            detail={detail}
            rationale={rationale}
            pendingAction={pendingAction}
            decision={decision}
            onRationale={setRationale}
            onDecision={submitDecision}
          />
        </div>
      </div>
    </>
  );
}

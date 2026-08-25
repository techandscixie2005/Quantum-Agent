"use client";

import {
  type FormEvent,
  type KeyboardEvent,
  useMemo,
  useRef,
  useState,
} from "react";

import { EvidenceLedger } from "./EvidenceLedger";
import { FormulaDisplay } from "./FormulaDisplay";
import {
  ContractError,
  parseApiError,
  parseConceptSearchResponse,
  parsePrerequisitePathsResponse,
  parseStudentSubgraphResponse,
  type ConceptSearchResponse,
  type PhaseOneApiError,
  type PhaseOneScope,
  type PrerequisitePathsResponse,
  type StudentGraphEdge,
  type StudentGraphNode,
  type StudentSubgraphResponse,
} from "./contracts";
import styles from "./phase-one.module.css";

class RequestFailure extends Error {
  readonly code: string;
  readonly traceId?: string;

  constructor(error: PhaseOneApiError["error"]) {
    super(error.message);
    this.name = "RequestFailure";
    this.code = error.code;
    this.traceId = error.trace_id;
  }
}

async function requestValidated<T>(
  url: string,
  parser: (value: unknown) => T,
  signal: AbortSignal,
): Promise<T> {
  const response = await fetch(url, { cache: "no-store", signal });
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ContractError("浏览器边界收到非 JSON 响应");
  }
  if (!response.ok) {
    const parsed = parseApiError(payload);
    throw new RequestFailure(
      parsed?.error ?? {
        code: `HTTP_${response.status}`,
        message: "知识服务请求失败；当前页面没有使用替代数据。",
      },
    );
  }
  return parser(payload);
}

function scopedParams(scope: PhaseOneScope) {
  return new URLSearchParams({
    course_id: scope.courseId,
    curriculum_edition_id: scope.curriculumEditionId,
  });
}

function readableFailure(error: unknown): RequestFailure {
  if (error instanceof RequestFailure) return error;
  if (error instanceof ContractError) {
    return new RequestFailure({
      code: "CLIENT_CONTRACT_REJECTED",
      message: "响应未通过浏览器契约校验；未经验证的数据未被显示。",
    });
  }
  return new RequestFailure({
    code: "NETWORK_FAILURE",
    message: "请求未完成；请检查连接后重试。当前页面没有使用生成内容替代。",
  });
}

function nodeTypeLabel(nodeType: string): string {
  const labels: Record<string, string> = {
    Chapter: "章节",
    Section: "小节",
    Concept: "概念",
    Principle: "原理",
    PhysicalSystem: "物理系统",
    MathematicalObject: "数学对象",
    Operator: "算符",
    QuantumState: "量子态",
    Approximation: "近似",
    Formula: "公式",
    Symbol: "符号",
    Derivation: "推导",
    Example: "例题",
    Exercise: "练习",
    Misconception: "常见误解",
    Hint: "提示",
    Experiment: "实验",
    Visualization: "可视化",
    Project: "项目",
  };
  return labels[nodeType] ?? nodeType;
}

type PositionedNode = Readonly<{ node: StudentGraphNode; x: number; y: number }>;
type GraphLayout = Readonly<{ nodes: readonly PositionedNode[]; height: number }>;

function graphLayout(
  nodes: readonly StudentGraphNode[],
  edges: readonly StudentGraphEdge[],
  rootId: string,
): GraphLayout {
  const incoming = new Set(
    edges.filter((edge) => edge.target_id === rootId).map((edge) => edge.source_id),
  );
  const outgoing = new Set(
    edges.filter((edge) => edge.source_id === rootId).map((edge) => edge.target_id),
  );
  const columns: StudentGraphNode[][] = [[], [], []];
  for (const node of nodes) {
    if (node.id === rootId || (incoming.has(node.id) && outgoing.has(node.id))) columns[1]?.push(node);
    else if (incoming.has(node.id)) columns[0]?.push(node);
    else if (outgoing.has(node.id)) columns[2]?.push(node);
    else columns[1]?.push(node);
  }
  for (const column of columns) column.sort((a, b) => a.label.localeCompare(b.label, "zh-CN"));
  const maxRows = Math.max(1, ...columns.map((column) => column.length));
  const height = Math.max(360, maxRows * 92 + 64);
  const xPositions = [130, 420, 710] as const;
  return {
    height,
    nodes: columns.flatMap((column, columnIndex) => {
      const gap = height / (column.length + 1);
      return column.map((node, rowIndex) => ({
        node,
        x: xPositions[columnIndex] ?? 420,
        y: gap * (rowIndex + 1),
      }));
    }),
  };
}

function clippedLabel(label: string): string {
  return label.length > 16 ? `${label.slice(0, 15)}…` : label;
}

function ErrorNotice({ error, onRetry }: { error: RequestFailure; onRetry?: () => void }) {
  return (
    <div className={styles.errorNotice} role="alert">
      <strong>{error.message}</strong>
      <span>步骤：课程知识读取 · 当前选择已保留</span>
      <code>{error.code}{error.traceId ? ` · trace ${error.traceId}` : ""}</code>
      {onRetry ? <button type="button" onClick={onRetry}>重试此步骤</button> : null}
    </div>
  );
}

function DegradedNotice({ warnings }: { warnings: readonly string[] }) {
  if (warnings.length === 0) return null;
  return (
    <details className={styles.degradedNotice}>
      <summary>部分图谱项因证据或投影校验未显示</summary>
      <p>其余内容仍来自已发布课程证据；系统没有补写缺失节点。</p>
      <ul>
        {warnings.map((warning) => <li key={warning}><code>{warning}</code></li>)}
      </ul>
    </details>
  );
}

type SearchResultsProps = Readonly<{
  response: ConceptSearchResponse | null;
  selectedId: string | null;
  isSearching: boolean;
  onSelect: (node: StudentGraphNode) => void;
}>;

function SearchResults({ response, selectedId, isSearching, onSelect }: SearchResultsProps) {
  return (
    <aside className={styles.searchRail} aria-labelledby="search-results-heading" aria-busy={isSearching}>
      <div className={styles.panelTitle}>
        <div>
          <p className={styles.eyebrow}>APPROVED INDEX</p>
          <h2 id="search-results-heading">概念索引</h2>
        </div>
        {response ? <span>{response.results.length} 个匹配</span> : null}
      </div>
      {isSearching && !response ? <div className={styles.skeletonList} aria-label="正在检索"><i /><i /><i /></div> : null}
      {!response && !isSearching ? (
        <div className={styles.emptyState}>
          <strong>从课程术语开始</strong>
          <p>例如输入“波函数的统计解释”。只检索教师批准且材料已发布的知识。</p>
        </div>
      ) : null}
      {response && response.results.length === 0 ? (
        <div className={styles.emptyState}>
          <strong>没有已发布的匹配项</strong>
          <p>这不等于课程中不存在该概念。可以调整关键词，或请教师检查发布状态。</p>
        </div>
      ) : null}
      {response && response.results.length > 0 ? (
        <ol className={styles.resultList}>
          {response.results.map(({ node, score }) => (
            <li key={node.id}>
              <button
                type="button"
                onClick={() => onSelect(node)}
                aria-pressed={selectedId === node.id}
              >
                <span>{nodeTypeLabel(node.node_type)}</span>
                <strong>{node.label}</strong>
                <small>{node.citations.length} 条来源 · 相关度 {score.toFixed(3)}</small>
              </button>
            </li>
          ))}
        </ol>
      ) : null}
      <DegradedNotice warnings={response?.warnings ?? []} />
    </aside>
  );
}

type GraphPanelProps = Readonly<{
  graph: StudentSubgraphResponse | null;
  rootFallback: StudentGraphNode | null;
  focusedNodeId: string | null;
  view: "graph" | "list";
  isLoading: boolean;
  onViewChange: (view: "graph" | "list") => void;
  onFocus: (nodeId: string) => void;
  onRecenter: (node: StudentGraphNode) => void;
}>;

function GraphPanel({
  graph,
  rootFallback,
  focusedNodeId,
  view,
  isLoading,
  onViewChange,
  onFocus,
  onRecenter,
}: GraphPanelProps) {
  const layout = useMemo(
    () => graphLayout(graph?.nodes ?? [], graph?.edges ?? [], graph?.root_candidate_id ?? ""),
    [graph],
  );
  const positions = useMemo(
    () => new Map(layout.nodes.map((item) => [item.node.id, item])),
    [layout.nodes],
  );
  const labels = useMemo(
    () => new Map((graph?.nodes ?? []).map((node) => [node.id, node.label])),
    [graph?.nodes],
  );
  const focusedNode =
    graph?.nodes.find((node) => node.id === focusedNodeId) ?? rootFallback;

  function activateNode(event: KeyboardEvent<SVGGElement>, nodeId: string) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onFocus(nodeId);
    }
  }

  return (
    <section className={styles.graphPanel} aria-labelledby="semantic-canvas-heading" aria-busy={isLoading}>
      <div className={styles.panelTitle}>
        <div>
          <p className={styles.eyebrow}>COURSE SEMANTIC MODEL</p>
          <h2 id="semantic-canvas-heading">关系与先修结构</h2>
        </div>
        <div className={styles.segmentedControl} aria-label="图谱显示方式">
          <button type="button" aria-pressed={view === "graph"} onClick={() => onViewChange("graph")}>图谱</button>
          <button type="button" aria-pressed={view === "list"} onClick={() => onViewChange("list")}>列表</button>
        </div>
      </div>

      {isLoading ? (
        <div className={styles.graphLoading} role="status">
          <span className={styles.energyPulse} aria-hidden="true" />
          正在同时核对图谱投影与原始课程证据…
        </div>
      ) : null}
      {!graph && !isLoading ? (
        <div className={styles.graphEmpty}>
          <div className={styles.energyDiagram} aria-hidden="true"><i /><i /><i /></div>
          <strong>选择一个概念以展开有证据的子图</strong>
          <p>节点与边只有在 PostgreSQL 发布门和来源哈希复核通过后才会出现。</p>
        </div>
      ) : null}
      {graph && !graph.root_visible ? (
        <div className={styles.errorNotice} role="status">
          <strong>根节点未通过学生可见性复核</strong>
          <span>图谱服务未返回任何替代说明；请让教师检查来源材料及发布状态。</span>
        </div>
      ) : null}

      {graph && graph.root_visible && view === "graph" ? (
        <div className={styles.svgScroller}>
          <p id="graph-summary" className={styles.srOnly}>
            当前子图包含 {graph.nodes.length} 个有课程证据的节点和 {graph.edges.length} 条关系。
            可按 Tab 浏览节点，按 Enter 查看证据。
          </p>
          <svg
            className={styles.semanticGraph}
            viewBox={`0 0 840 ${layout.height}`}
            role="img"
            aria-labelledby="graph-title"
            aria-describedby="graph-summary"
          >
            <title id="graph-title">课程知识子图</title>
            <defs>
              <marker id="qa-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" />
              </marker>
            </defs>
            <g className={styles.graphEdges}>
              {graph.edges.map((edge) => {
                const source = positions.get(edge.source_id);
                const target = positions.get(edge.target_id);
                if (!source || !target) return null;
                const midX = (source.x + target.x) / 2;
                return (
                  <path
                    key={edge.id}
                    d={`M ${source.x} ${source.y} C ${midX} ${source.y}, ${midX} ${target.y}, ${target.x} ${target.y}`}
                    markerEnd="url(#qa-arrow)"
                  >
                    <title>{edge.relationship_type}</title>
                  </path>
                );
              })}
            </g>
            {layout.nodes.map(({ node, x, y }) => (
              <g
                key={node.id}
                className={`${styles.graphNode} ${focusedNodeId === node.id ? styles.graphNodeSelected : ""}`}
                transform={`translate(${x - 95} ${y - 28})`}
                role="button"
                tabIndex={0}
                aria-label={`${nodeTypeLabel(node.node_type)}：${node.label}，${node.citations.length} 条证据`}
                onClick={() => onFocus(node.id)}
                onKeyDown={(event) => activateNode(event, node.id)}
              >
                <rect width="190" height="56" rx="6" />
                <text x="12" y="20" className={styles.graphNodeType}>{nodeTypeLabel(node.node_type)}</text>
                <text x="12" y="41">{clippedLabel(node.label)}</text>
                <title>{node.label}</title>
              </g>
            ))}
          </svg>
        </div>
      ) : null}

      {graph && graph.root_visible && view === "list" ? (
        <div className={styles.graphTableWrap}>
          <table className={styles.graphTable}>
            <caption>当前有证据的节点；选择一行查看其原始课程引用</caption>
            <thead><tr><th>类型</th><th>知识项</th><th>证据</th><th>操作</th></tr></thead>
            <tbody>
              {graph.nodes.map((node) => (
                <tr key={node.id} data-selected={focusedNodeId === node.id}>
                  <td>{nodeTypeLabel(node.node_type)}</td>
                  <th scope="row">{node.label}</th>
                  <td>{node.citations.length}</td>
                  <td><button type="button" onClick={() => onFocus(node.id)}>查看证据</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {graph.edges.length > 0 ? (
            <details className={styles.relationList}>
              <summary>检查 {graph.edges.length} 条有证据关系</summary>
              <ul>
                {graph.edges.map((edge) => (
                  <li key={edge.id}>
                    <span>{labels.get(edge.source_id) ?? edge.source_id}</span>
                    <code>{edge.relationship_type}</code>
                    <span>{labels.get(edge.target_id) ?? edge.target_id}</span>
                    <small>{edge.citations.length} 条证据</small>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </div>
      ) : null}

      {focusedNode ? (
        <article className={styles.selectedConcept}>
          <div>
            <span>{nodeTypeLabel(focusedNode.node_type)}</span>
            <h3>{focusedNode.label}</h3>
            {focusedNode.description ? <p>{focusedNode.description}</p> : <p>课程图谱未提供经过批准的说明文字。</p>}
          </div>
          {graph && focusedNode.id !== graph.root_candidate_id ? (
            <button type="button" onClick={() => onRecenter(focusedNode)}>以此项为中心展开</button>
          ) : null}
          {focusedNode.formula_latex ? <FormulaDisplay latex={focusedNode.formula_latex} /> : null}
        </article>
      ) : null}
      <DegradedNotice warnings={graph?.warnings ?? []} />
    </section>
  );
}

function PrerequisitePanel({ prerequisites }: { prerequisites: PrerequisitePathsResponse | null }) {
  return (
    <section className={styles.prerequisitePanel} aria-labelledby="prerequisite-heading">
      <div className={styles.panelTitle}>
        <div>
          <p className={styles.eyebrow}>LEARNING ORDER</p>
          <h2 id="prerequisite-heading">已批准的先修路径</h2>
        </div>
        {prerequisites ? <span>{prerequisites.paths.length} 条路径</span> : null}
      </div>
      {!prerequisites ? (
        <p className={styles.panelPrompt}>选择概念后查看课程定义的先修链。</p>
      ) : prerequisites.paths.length === 0 ? (
        <div className={styles.emptyState}>
          <strong>没有已批准的先修路径</strong>
          <p>这不表示该概念不需要基础知识；可能尚未建模或尚未发布。</p>
        </div>
      ) : (
        <ol className={styles.pathList}>
          {prerequisites.paths.map((path, pathIndex) => (
            <li key={`${path.nodes.map((node) => node.id).join(":")}-${pathIndex}`}>
              <span>路径 {pathIndex + 1}</span>
              <div>
                {path.nodes.map((node, nodeIndex) => (
                  <span key={node.id}>
                    <b>{node.label}</b>
                    {nodeIndex < path.nodes.length - 1 ? <i aria-label="先修于">→</i> : null}
                  </span>
                ))}
              </div>
            </li>
          ))}
        </ol>
      )}
      <DegradedNotice warnings={prerequisites?.warnings ?? []} />
    </section>
  );
}

export function StudentGraphExplorer({ scope }: { scope: PhaseOneScope }) {
  const [query, setQuery] = useState("");
  const [searchResponse, setSearchResponse] = useState<ConceptSearchResponse | null>(null);
  const [graph, setGraph] = useState<StudentSubgraphResponse | null>(null);
  const [prerequisites, setPrerequisites] = useState<PrerequisitePathsResponse | null>(null);
  const [selectedRoot, setSelectedRoot] = useState<StudentGraphNode | null>(null);
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);
  const [view, setView] = useState<"graph" | "list">("list");
  const [isSearching, setIsSearching] = useState(false);
  const [isLoadingSelection, setIsLoadingSelection] = useState(false);
  const [error, setError] = useState<RequestFailure | null>(null);
  const searchAbort = useRef<AbortController | null>(null);
  const selectionAbort = useRef<AbortController | null>(null);

  const focusedNode =
    graph?.nodes.find((node) => node.id === focusedNodeId) ?? selectedRoot;

  async function runSearch(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const normalized = query.trim().replace(/\s+/g, " ");
    if (!normalized) return;
    searchAbort.current?.abort();
    selectionAbort.current?.abort();
    const controller = new AbortController();
    searchAbort.current = controller;
    setIsSearching(true);
    setError(null);
    setGraph(null);
    setPrerequisites(null);
    setSelectedRoot(null);
    setFocusedNodeId(null);
    try {
      const params = scopedParams(scope);
      params.set("q", normalized);
      const response = await requestValidated(
        `/api/phase1/graph/search?${params}`,
        parseConceptSearchResponse,
        controller.signal,
      );
      setSearchResponse(response);
    } catch (caught) {
      if (!controller.signal.aborted) setError(readableFailure(caught));
    } finally {
      if (!controller.signal.aborted) setIsSearching(false);
    }
  }

  async function loadSelection(node: StudentGraphNode) {
    selectionAbort.current?.abort();
    const controller = new AbortController();
    selectionAbort.current = controller;
    setSelectedRoot(node);
    setFocusedNodeId(node.id);
    setGraph(null);
    setPrerequisites(null);
    setIsLoadingSelection(true);
    setError(null);
    const params = scopedParams(scope);
    params.set("candidate_id", node.id);
    try {
      const [nextGraph, nextPrerequisites] = await Promise.all([
        requestValidated(
          `/api/phase1/graph/subgraph?${params}`,
          parseStudentSubgraphResponse,
          controller.signal,
        ),
        requestValidated(
          `/api/phase1/graph/prerequisites?${params}`,
          parsePrerequisitePathsResponse,
          controller.signal,
        ),
      ]);
      setGraph(nextGraph);
      setPrerequisites(nextPrerequisites);
    } catch (caught) {
      if (!controller.signal.aborted) setError(readableFailure(caught));
    } finally {
      if (!controller.signal.aborted) setIsLoadingSelection(false);
    }
  }

  return (
    <>
      <section className={styles.studentIntro}>
        <div>
          <p className={styles.eyebrow}>KNOWLEDGE GRAPH · STUDENT VIEW</p>
          <h1>从概念走回课程原文</h1>
          <p>搜索课程术语，检查先修结构、公式和关系，并沿证据轨定位到原始页、幻灯片或表格行。</p>
        </div>
        <form className={styles.conceptSearch} onSubmit={runSearch} role="search">
          <label htmlFor="concept-query">搜索已发布课程知识</label>
          <div>
            <input
              id="concept-query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              maxLength={300}
              placeholder="输入概念、公式或课程术语"
              autoComplete="off"
            />
            <button type="submit" disabled={isSearching || query.trim().length === 0}>
              {isSearching ? "核对中…" : "检索证据"}
            </button>
          </div>
          <small>Neo4j 负责关系导航；原文、页码与哈希由课程材料记录重新核对。</small>
        </form>
      </section>

      {error ? (
        <ErrorNotice
          error={error}
          onRetry={selectedRoot ? () => loadSelection(selectedRoot) : () => runSearch()}
        />
      ) : null}

      <div className={styles.studentGrid}>
        <SearchResults
          response={searchResponse}
          selectedId={selectedRoot?.id ?? null}
          isSearching={isSearching}
          onSelect={loadSelection}
        />
        <div className={styles.graphColumn}>
          <GraphPanel
            graph={graph}
            rootFallback={selectedRoot}
            focusedNodeId={focusedNodeId}
            view={view}
            isLoading={isLoadingSelection}
            onViewChange={setView}
            onFocus={setFocusedNodeId}
            onRecenter={loadSelection}
          />
          <PrerequisitePanel prerequisites={prerequisites} />
        </div>
        <EvidenceLedger
          citations={(focusedNode?.citations ?? []).map((citation) => ({ source: "student" as const, citation }))}
        />
      </div>
    </>
  );
}

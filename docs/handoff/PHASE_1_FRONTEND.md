# PHASE 1 — FINAL FRONTEND FREEZE

> Scientific Quiet UI for the Quantum Agent `/agent` workspace.
> Frontend-only. No backend, LangGraph, Tutor Graph, pedagogical policy,
> LearningPhase semantics, Coding Agent, Sandbox, Verifier, persistence, or
> auth behavior was changed.

## 1. Visual changes

The `/agent` workspace was reduced to **One Learning Stage** — a single visual
center — with all peripheral functions collapsed into lightweight, on-demand
surfaces.

- **Top bar**: brand reduced to an icon-only mark; a `⌘K` command-palette hint
  sits beside the model-service status; the only persistent right-side action
  is a compact "证据" (Evidence) button.
- **Left navigation**: collapsed from a wide sidebar (course picker, mode list,
  chapter list, project meta) into a **60 px icon rail**. Modes are icon
  buttons with `data-active` state + tooltips; the rail also holds Evidence,
  graph, ⌘K, and "new thread" actions.
- **Right Evidence rail**: removed as a permanent column. Evidence, diagnosis,
  citations, and the policy gate now live in a slide-in **Sheet** (translateX,
  opened via the top bar, the rail, or ⌘K). A scrim backdrop closes it.
- **Workspace title** ("推导工作台" etc.) and the permanent 6-step engineering
  pipeline (输入/感知/证据/诊断/验证/提示) were **removed**. A quiet
  `stageHead` (small h1 + phase pill) replaces them.
- **Empty canvas**: explanatory paragraph removed (>60% text reduction); only
  the mode prompt + the golden-loop entry remain.
- **Scientific objects are the hero**: deterministic verification results
  (scientific-tool-result, tunnelling-metrics, tunnelling-regime) moved **into
  the central Stage** as first-class objects with a mint tint — no longer
  buried in the right rail. Claims, equations, plots, and code already
  rendered in-Stage.
- **Progressive disclosure on claims**: each claim shows its text + a
  `为什么？` toggle. Expanding reveals the support basis, linked scientific
  results, linked course evidence with `查看原文`, and a `在证据面板查看全部 →`
  link — the PRD's `检查 κ 的定义 → [Why?] → κ = … → [View course evidence]`
  pattern.
- **Compact floating composer**: the oversized input area was replaced by a
  centered floating composer (default **123 px** tall, max-width 880 px). The
  second "attempt" textarea is now behind an `附上尝试` toggle (hidden by
  default). Text/image/PDF/attachments/submit all still work; the composer
  expands only when needed.
- **Evidence Spine** visually hidden (sr-only) — it remains in the DOM for
  structure but no longer competes for attention.

## 2. Components removed / added

**Removed from the DOM / layout**
- Permanent right Evidence `<aside>` column (now a closed Sheet by default).
- Workspace title block ("推导工作台") and the 6-step pipeline strip.
- Left sidebar course picker, mode list, chapter list, sidebar project meta,
  and the old `newThread` button — replaced by the icon rail.
- Duplicate 验证器 `<section>` in the right panel (scientific-tool-result /
  tunnelling-metrics testids were duplicated in Stage and rail — the rail copy
  was removed so each testid is unique).
- Empty-canvas explanatory paragraph and the `START WITH EVIDENCE` kicker.
- Unused `ChevronDown` import.

**Added**
- `⌘K` **Command Palette** (custom, built on `@radix-ui/react-dialog`):
  fuzzy filter over learning modes, courses, and actions (open evidence, start
  golden loop, new thread). Global `Ctrl/⌘+K` keydown listener toggles it.
- Icon **rail** (`railIconButton`, `railDivider`, `railSpacer`) with active
  state + tooltips.
- Slide-in **Evidence Sheet** (`mobilePanelTitle` close button + backdrop).
- **`stageHead`** (quiet h1 + `phaseTag` pill) driven by `LearningPhase`.
- **`stageVerification`** block rendering deterministic verification inside the
  Stage.
- **Progressive disclosure** on claims: `whyToggle` + `claimBasis` +
  `basisList` + `basisLink`.
- Collapsible **attempt input** (`附上尝试` toggle) in the composer.

## 3. Screenshot paths

Captured by `shot-baseline.mjs` (mock SSE, no tokens) at 1440×900 and
1920×1080 for each phase:

```
test-results/phase1-baseline/
  1440x900-00-initial.png      1920x1080-00-initial.png
  1440x900-commitment.png      1920x1080-commitment.png
  1440x900-diagnosis.png       1920x1080-diagnosis.png
  1440x900-experiment.png      1920x1080-experiment.png
  1440x900-teachback.png       1920x1080-teachback.png
  1440x900-transfer.png        1920x1080-transfer.png
  1440x900-mirror.png          1920x1080-mirror.png
```

Programmatic visual-QA artifact (experiment phase, 1440×900):
`test-results/phase1-qa/1440x900-experiment.png`

## 4. Visual QA result

`shot-qa.mjs` asserts the structural design contract against a live page
(mock SSE). **14/14 passed**:

| Check | Result |
|---|---|
| No horizontal overflow | PASS (overflowX=0) |
| Left nav ≤ 72 px icon rail | PASS (60 px) |
| No permanent right Evidence rail | PASS (rightX=1461, off-canvas) |
| No giant workspace title | PASS (0 matches) |
| No permanent engineering pipeline | PASS (0 pipeline elements) |
| Compact floating composer ≤ 160 px | PASS (123 px) |
| Main stage dominates (width > 600 px) | PASS (1440 px) |
| Scientific verification visible in Stage (right panel closed) | PASS |
| No duplicate verification testid | PASS (count=1) |
| ⌘K command-palette hint visible | PASS |
| ⌘K opens the palette | PASS |
| Evidence Sheet expands | PASS |
| Evidence Sheet contains course citations | PASS |
| Progressive disclosure `[为什么？]` toggle on claims | PASS |

Coverage: initial Stage, Diagnosis, Derivation/Experiment, Verification,
Teach-Back, Transfer/Solo, Cognitive Mirror, Evidence Sheet, Command Palette
— verified at 1440×900 and 1920×1080.

## 5. Tests / build result

| Gate | Command | Result |
|---|---|---|
| Lint | `npm run lint` | 0 errors, 4 pre-existing warnings |
| Typecheck | `npx tsc --noEmit` | exit 0 |
| Unit + golden eval | `npm run test:unit` | 68/68 passed |
| E2E (Playwright) | `npx playwright test` | 4/4 passed (golden-loop + learning-native×3) |
| Production build | `npm run build` | exit 0, Sites artifact validated |
| Secret scan | `npm run check:secrets` | PASS — no sk-/USTC_API/model patterns in bundle |

No tests were skipped or weakened. The `tunnelling-metrics` / scientific-tool-result
testids remain unique and are asserted visible in `golden-loop.spec.ts` **without**
opening the right panel — now satisfied by the in-Stage verification block.

## 6. Remaining frontend issues (non-blocking)

- **Evidence Sheet on mobile**: the sheet is usable but the close affordance
  relies on the backdrop + header `X`; a swipe-to-close gesture is not wired
  (low priority — the backdrop + button cover the flow).
- **Command Palette keyboard navigation**: items are clickable and `Esc`
  closes; full arrow-key `rovingFocus` is not implemented (Radix `Command`
  primitive is unavailable in this repo). Filter + Enter-to-select is a future
  enhancement.
- **Cognitive Mirror / Transfer / Solo scenes** inherit the existing
  `LearningNative` cards (preserved testids + copy). They are visually quiet
  but not yet re-skinned per-phase beyond the shared `learningCard` style —
  acceptable for freeze, refinement deferred to a later pass.
- **KaTeX / math typography**: `MathText` already renders math; no change was
  needed, but a dedicated math-type scale pass could further elevate equations
  as hero objects (deferred).

## 7. Commit

See the commit SHA at the end of this freeze. Frontend-only; no backend,
policy, persistence, auth, or test-contract changes.

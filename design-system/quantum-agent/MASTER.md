# Quantum Agent design system

This file is the visual source of truth for new product surfaces. Page-specific
files in `pages/` may override it.

## Direction

Subject: an evidence-governed university Quantum Physics course. Audience:
students reading equations and teachers reviewing claims. The graph explorer’s
single job is to move from a concept to its prerequisite and original course
evidence; the review page’s single job is to make an approval decision without
losing provenance.

The generated recommendation was an OLED cyan/magenta FAQ site. That reads as a
generic “quantum computer” interface, conflicts with the PRD’s restrained
academic workbench, and would make status colors harder to interpret. The
adopted direction is a cool mineral-paper workspace paired with a low-glare
blackboard theme. It is information-dense but not cramped, formula-first, and
never styled like consumer chat.

## Tokens

| Role | Light | Blackboard | Meaning |
|---|---|---|---|
| canvas | `#F6F7F3` | `#0C1714` | cool lab paper / chalkboard |
| surface | `#FFFFFF` | `#12231E` | primary working plane |
| ink | `#18231F` | `#EDF4F0` | main text |
| muted | `#5E6C66` | `#A6B7AF` | secondary text, still AA |
| line | `#D5DCD7` | `#30463E` | hierarchy and graph edges |
| course | `#235F91` | `#86BCE4` | course-source evidence |
| approved | `#17664C` | `#78D0AA` | approved knowledge |
| review | `#9A571B` | `#F1B46B` | review required |
| danger | `#A43E36` | `#F18C84` | reject/error only |

Use semantic variables; components never contain raw status colors. Do not use
gradients, neon, glow, glass blur, or decorative “atomic orbit” backgrounds.

Spacing follows `4 / 8 / 12 / 16 / 24 / 32 / 48`. Touch targets are at least
44px. Cards use 10px corners; evidence and data tables use 4–6px corners.
Shadows are reserved for floating sheets (`0 16px 48px rgb(20 40 31 / 12%)`);
normal hierarchy comes from surface, line and spacing.

## Type

- Display and concept names: `"Noto Serif SC", "Source Han Serif SC", "Songti SC", serif`.
- Body and controls: `"Noto Sans SC", "Source Han Sans SC", system-ui, sans-serif`.
- Formula fallback: KaTeX fonts, then `STIX Two Math`.
- Locators, hashes and numeric data: `"IBM Plex Mono", "SFMono-Regular", monospace` with tabular figures.

Base text is 16px/1.6. Dense metadata may be 13px/1.45, never below 12px.
Reading columns stop at 72 characters. Serif is used with restraint for the
course hierarchy and physical claims, not for controls or long tables.

## Layout concepts

Graph explorer, desktop:

```text
┌ course / curriculum / search ─────────────────────────────────────────┐
├ outline + filters ┬ semantic canvas or list ┬ provenance ledger       │
│ chapter versions  │ selected concept         │ original source        │
│ node types        │ prerequisites / formula │ page · section · hash  │
│ approved only     │ related exercises       │ exact evidence snippet │
└───────────────────┴──────────────────────────┴─────────────────────────┘
```

Teacher review, desktop:

```text
┌ queue totals + publication health + filters ─────────────────────────┐
├ review queue ┬ candidate / relation diff ┬ source page and decisions │
│ keyboard nav │ ontology + confidence      │ approve / edit / reject  │
│ status text  │ endpoints + evidence       │ merge + audit reason     │
└──────────────┴────────────────────────────┴───────────────────────────┘
```

At 820px, the outline becomes a drawer and evidence becomes a labeled sheet.
At 560px, graph/list is an explicit toggle; the default is an accessible list,
not a tiny force-directed canvas. Deep selections remain URL-addressable.

## Signature: the evidence rail

The memorable element is a vertical provenance rail based on an energy-level
diagram. Each selected claim, formula or relation occupies a horizontal level;
a precise line connects it to an evidence locator in the ledger. Line style
encodes channel (solid course source, double symbolic verification, dotted
model inference) and is always paired with a text badge. This is a functional
traceability control, not decoration, and replaces the generic neon node cloud.

Spend visual boldness only here. Surrounding navigation, forms and tables stay
quiet.

## Interaction and accessibility

- Keyboard focus is a 2px semantic ring with 2px offset; never remove it.
- Every icon uses one Lucide outline family and has a text label or accessible name.
- Approval state is conveyed by icon, status text and color.
- Async panels reserve space and show a skeleton after 300ms; mutation buttons
  disable while pending and retain the candidate selection on failure.
- Errors state the failed step, preservation status, recovery action and trace ID.
- Graph nodes are reachable in an equivalent sortable tree/table; citations and
  tooltips work on focus and click, not hover only.
- Motion is limited to 150–220ms opacity/transform transitions that explain
  panel selection. `prefers-reduced-motion` removes them.
- Graph and charts include a concise text summary and data/table alternative.
- Test at 375, 768, 1024 and 1440px, browser zoom 200%, both themes, and keyboard only.

## React/Next implementation rules

- Keep pages server-rendered where practical; client components own only graph
  interaction, filters and mutations.
- Start independent fetches together and use Suspense boundaries instead of
  request waterfalls.
- Dynamically import the graph renderer, KaTeX, Monaco and Plotly only in modes
  that need them.
- Do not pass whole graph datasets through client props; query a bounded subgraph.
- Use TanStack Query for client cache/deduplication and invalidate only affected
  review records.
- Do not define components inside components; derive state during render and use
  primitive effect dependencies.

## Prohibited patterns

- Generic chatbot bubbles as the primary content structure.
- Cyan/magenta sci-fi HUDs, glowing graph nodes, or orbital decoration.
- Tiny unlabeled icon controls, hover-only provenance, color-only status.
- Fake KPI values, static graph data presented as live, or optimistic “approved”
  state before the backend audit transaction completes.
- Showing Neo4j text as if it were original evidence.

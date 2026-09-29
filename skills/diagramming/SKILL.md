---
name: diagramming
description: >
  Use BEFORE drawing any architecture picture, and BEFORE trusting one already in a
  spec, PR, or design doc: which diagram type (sequence, flowchart, state, ER/class,
  C4 context/container, deployment) at which of three detail levels (L1 orientation,
  L2 implementer, L3 debugging/spec), for a request/response flow, branching logic,
  an entity's lifecycle, data shape, a system boundary, or infrastructure topology.
  Also fire WHEN reviewing a design doc, spec, or PR that includes a diagram, a
  screenshot of one, or claims a flow works with no diagram at all. Validated by
  `scripts/check_diagrams.py`.
---

# Diagramming

Prose hides shape. A paragraph can describe a login flow that silently skips the
lockout check, and nothing about the sentence looks wrong. A diagram with the same
gap has a dangling arrow. This skill is not "draw more pictures" — most repos
checked for this skill draw almost none, on purpose (see Sources). It is: draw the
*right* picture, at the *right* detail, and check it mechanically so it cannot rot
the way every hand-drawn architecture PNG in every repo surveyed has rotted.

## Trigger

**Fire when:** about to describe, in a spec, PR, or design doc, any of: a request/
response or event flow crossing 2+ components; branching/decision logic inside one
process; an entity with states over time (order, session, payment, job, retry);
data shape and relationships; where a system sits relative to others; or
infrastructure topology. Also fire when reviewing any of those with no diagram, or
with a diagram that is a screenshot instead of committed text.

**Do not fire when:** the change touches one function with no branch, one table
with no relationship, or the flow is unchanged and already diagrammed elsewhere in
the spec — redrawing an unchanged flow is decoration, not discipline.

## Diagram type × task

| type | right when | wrong when | level → audience |
|---|---|---|---|
| **sequence** | a request/response or event flow crossing 2+ components — *who calls whom, in what order* | branching inside one process (flowchart); an entity's states over time (state) | L2 default (implementer); L3 for debugging/spec, every branch; rarely L1 — motion is the wrong thing to show someone orienting |
| **flowchart** | branching/decision logic inside one process, function, or algorithm | a call crossing a network boundary (sequence names *who*; flowchart doesn't); a persistent lifecycle (state) | any level; L1 = happy path only, L3 = every branch incl. error exits |
| **state** | the lifecycle of one entity across time: order status, session state, a retry/backoff machine | a one-shot process that never re-enters a prior state (flowchart is cheaper) | L2 typical; L1 if a decision-maker only needs *which states exist* |
| **ER / class** | data shape: entities, fields, relationships, cardinality | control flow or timing — it shows *what*, never *when* | L1 = entity names + relationships; L3 = every field, FK, cardinality label |
| **C4 context/container** | "where does this system sit" — boundaries, external dependencies | internal function-level logic (drop to sequence/flowchart once inside one box) | L1 by definition — this *is* the orientation level |
| **deployment** | infra topology: hosts, networks, regions, what sits behind what LB | application logic | L1/L2 for orientation; L3 is rare — every port and env var is a runbook |

Mermaid has no dedicated deployment syntax; real repos draw it as a `flowchart`
with one `subgraph` per host/region — the same technique
`grafana/grafana@main:contribute/architecture/k8s-inspired-backend-arch.md` uses for
its container-level view.

**Plain English, for the table above:** sequence = one vertical line per
participant, arrows are messages in time order, top to bottom. flowchart = boxes
joined by arrows meaning "then," with a diamond where the path splits. state =
rounded boxes are states; an arrow is the only allowed way from one to the next —
no arrow between two states means that change cannot happen. ER/class = boxes are
things, lines are how they relate. C4 context/container = boxes are systems,
arrows are "talks to." deployment = boxes are machines/regions, arrows are network
paths.

Checked against a general-purpose visual-technique catalogue (`local:
visual-learning-guide skill bundle (user-supplied)`, §1 selection guide): it agrees
— sequence for "messages between parties," state machine for "states and
transitions." It also names **swimlane** (a flowchart with one subgraph per actor)
as the alternative to sequence when *who does what* matters more than exact
message order — reach for it on a multi-actor process with no clean
request/response shape. One disagreement: its "flow (boxes + arrows)" covers any
ordered steps, branching or not. Here, flowchart is reserved for branching — a
strictly linear process is prose or a numbered list, because a diagram earns
nothing over words until there is a decision point to track.

## Detail levels

Declare the level right after the diagram-type line: `%% level: 1`, `2`, or `3`.
Undeclared diagrams are inferred by node count and reported, not blocked — except
an inferred-L3-sized diagram still owes L3's structural requirements below, whether
declared or not: size earns the obligation either way.

| level | audience | node budget | what's collapsed | step table |
|---|---|---|---|---|
| **L1 high** | someone new, or a decision-maker | **≤ 12 nodes** | every external system → one box; no retries, no error paths | not required |
| **L2 medium** | the implementer writing the code | **≤ 30 nodes** | components shown individually; only calls crossing a component boundary | not required |
| **L3 detailed** | debugging, review, an unambiguous spec | no cap | nothing — every branch, every error/timeout/retry path | **required**: numbered table below the diagram, ≥ 1 shown branch |

The same login flow drawn at all three is `reviewers/_diagram-levels.md` — read
that before drawing your first L3 diagram; the difference is visible there, not
just described.

## Rules

1. A diagram used in a spec or design doc is fenced `mermaid` text, not a
   screenshot or hand-drawn image — a raster image cannot be diffed, reviewed, or
   checked by any tool, and every repo surveyed that uses one has let it go stale.
   *Enforced by:* convention

2. Every sequence diagram declares each participant with `participant`/`actor`
   before it appears in a message. `scripts/design_drift.py` only reads explicit
   declarations — an alias mermaid auto-creates from its first message is invisible
   to drift-checking.
   *Enforced by:* `python3 scripts/check_diagrams.py <file>`

3. Sequence arrows use one of `-> --> ->> -->> -x --x` — the exact set
   `design_drift.py`'s message regex recognizes. An async `-)` arrow renders fine in
   Mermaid and disappears from drift-checking.
   *Enforced by:* `python3 scripts/check_diagrams.py <file>`

4. External participants (UI, browser, third-party API) are marked `actor` or
   listed in `%% external:` — otherwise `design_drift.py` reports them as
   unimplemented code that was never meant to exist.
   *Enforced by:* `python3 scripts/check_diagrams.py <file>` + `design_drift.py`

5. A declared or forced level's node budget is a hard gate; an undeclared diagram
   is inferred and reported instead of blocked.
   *Enforced by:* `python3 scripts/check_diagrams.py <file>`

6. L3 diagrams — declared or inferred by size — carry a numbered step table
   immediately below and show ≥ 1 branch/error path in the diagram itself. A wall
   of 40 happy-path arrows numbered in sequence is not a spec.
   *Enforced by:* `python3 scripts/check_diagrams.py <file>`

7. No placeholder text (`TODO`, `<!-- action -->`, `<...>`) survives in a diagram
   or its step table.
   *Enforced by:* `python3 scripts/check_diagrams.py <file>`

8. A sequence diagram in a feature spec stays current against the implementation —
   this skill supplies the diagram discipline `feature-planning` rule 5 depends on.
   *Enforced by:* `python3 scripts/design_drift.py specs/<name>/spec.md <code-dir>`

## Verify

```bash
# single spec, ~1s
python3 scripts/check_diagrams.py specs/login/spec.md
# force-check against a stricter level than declared/inferred, ~1s
python3 scripts/check_diagrams.py specs/login/spec.md --level 3
# every mermaid block under a directory, ~1s for this repo
python3 scripts/check_diagrams.py specs/
# the worked example — all three levels must pass clean
python3 scripts/check_diagrams.py reviewers/_diagram-levels.md
# regression suite against the real fixture + deliberately broken blocks, ~2s
bash tests/test_check_diagrams.sh
```

## Failure modes

This skill rejects:

- **A diagram that is a PNG/screenshot** pasted into a spec — cannot be diffed,
  reviewed inline, or checked; it is the single most common pattern found across
  the repos surveyed (see Sources) and the reason diagrams rot silently.
- **A participant used before it is declared** — mermaid renders it fine by
  auto-creating it; `design_drift.py` never sees it, so drift in that participant's
  messages is permanently invisible.
- **An async `-)` arrow, or any arrow outside `-> --> ->> -->> -x --x`** — same
  failure: renders correctly, invisible to the round-trip.
- **A `%% external:` directive naming a participant that was never declared** — a
  typo that silently does nothing, so the "external" exclusion never applies.
- **A declared L1 diagram with 40 nodes** — the budget exists so "orientation"
  cannot quietly become "everything," which is how L1 diagrams stop getting drawn
  at all.
- **An L3 diagram with numbered arrows but no step table, or no shown branch** —
  a happy-path-only diagram wearing L3's numbering without L3's obligations.
- **`<!-- action -->` or `TODO` left in a shipped diagram or its step table.**

**Honest limitations:** this is a syntax + structure check, not a renderer — it
does not catch every mermaid parse error a real render would. Arrow-form validity
is enforced strictly only for sequence diagrams, because that is the type
`design_drift.py` depends on; flowchart/state/class/ER/C4 get node/edge counting,
one well-known label-escaping check (unquoted parens in a `[...]` label), and the
level budget, not a full grammar. Node-count inference is a ceiling, not a content
judgement — a 7-node diagram that jumps straight to internal collaborators still
infers as L1-sized; declare `%% level: 2` explicitly when it is the content, not
the size, that makes it an implementer diagram.

## Scale

`solo`: the diagram is often the only place the intended design was ever stated —
skip the discipline and there is nothing to check code against later.
`small-team`: the diagram becomes the review artifact; a wrong arrow is cheaper to
catch in a 30-second diagram read than in a 300-line diff.
`org`: the L1 context diagram is what a new team reads before their first PR; if it
lags reality, onboarding routes people to the wrong owner for months.
`high-blast-radius`: the L3 diagram with every error path *is* the incident
runbook's first page — this is where the discipline pays for itself fastest.

## Sources

- **Absence is the finding.** `kubernetes/enhancements@master:keps/` has 671 KEP
  directories; a random sample of 25 READMEs had 1 with a mermaid diagram, 2 with an
  embedded image, and 22 (88%) with neither — and the KEP template itself
  (`keps/NNNN-kep-template/README.md`, 830 lines) never mentions a diagram.
  `backstage/backstage@master:docs/architecture-decisions/` has 15 ADRs; 1
  references a diagram image. `argoproj/argo-cd@master:docs/proposals/
  001-proposal-template.md` has no diagram section at all, and its two real
  architecture docs (`docs/operator-manual/architecture.md`,
  `docs/developer-guide/architecture/components.md`) each embed exactly one static
  PNG, zero mermaid. `microsoft/vscode.wiki@master` has 90 pages: 0 use mermaid, 23
  (26%) embed a raster image, including the core `Source-Code-Organization.md`.
  `cilium/cilium@main:Documentation/overview/component-overview.rst` explains its
  architecture with one static PNG. None of these are diffable, reviewable inline,
  or checkable by any tool — which is why they drift and nobody notices.
- **Text-as-diagram, where it exists, is the exception, not the norm.**
  `grafana/grafana@main:contribute/architecture/` has 3 docs; only the newest
  (`k8s-inspired-backend-arch.md`) uses mermaid (2 `graph TD`/`TB` box diagrams with
  subgraphs — container-level, not sequence). `temporalio/temporal@main:docs/
  architecture/` is the strongest positive counter-example found: 12 architecture
  docs backed by 18 versioned `.d2` diagram-as-code sources
  (`docs/_assets/chasm-lifecycle.d2` etc.) rendered to SVG — diagrams as reviewable
  text, the same principle this skill enforces via mermaid.
- **The three-level zoom hierarchy** is arc42's building-block view —
  `arc42/arc42-template@master:EN/adoc/05_building_block_view.adoc` defines Level
  1/2/3 as white-box/black-box zoom, cited in full in
  `reviewers/_diagram-levels.md`. The C4 context/container/component/code hierarchy
  is `c4model.com`, fetched directly (not archived) 2026-09-29.
- Node/edge budgets and the arrow whitelist: `SOURCE: original`, chosen to match
  `scripts/design_drift.py`'s existing participant/message regexes exactly, so a
  diagram that passes `check_diagrams.py` is guaranteed parseable by
  `design_drift.py`.
- The diagram-type selection guide is checked, not copied, against `local:
  visual-learning-guide skill bundle (user-supplied)` — a general-purpose
  text-to-visual guide, not an engineering-spec tool, so it is used for its
  taxonomy and plain-English phrasing only; its catalogue has no runnable check or
  failure mode, which this plugin's contract requires.

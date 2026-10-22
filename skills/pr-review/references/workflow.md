# Review workflow — steps 0–12

Reference for `pr-review` (loaded on demand). The numbered rules live in `../SKILL.md`; record
rules in `rubric.md`. `CR` = the per-repo review root, `<snap>` = the snapshot directory,
`<scratch>` = the session scratchpad. Every `gh pr`/`gh issue` call takes `-R HOST/OWNER/REPO`,
every `gh api` call takes `--hostname HOST`, all three parsed from the PR URL.

| # | Step | Command / action |
|---|---|---|
| 0a | Clone | `--repo <dir>` if given; else the current git repo when one of its remotes points at the PR's `HOST/OWNER/REPO`; else ask the user for a clone path (offer `git clone --filter=blob:none <repo-url> <dir>` and run it only on a yes). The clone is fetched into, never checked out |
| 0b | Init + paths | `100x pr_review init --url <pr-url> --repo <clone> [--out <dir>] --json` (idempotent: creates `CONTEXT.md`, `INDEX.md`, `_meta/{focus.md,decisions.md,settings.json}` only when missing) · `100x pr_review paths --url <pr-url> --repo <clone> [--out <dir>] --json` → `cr`, `context`, `meta` (which `_meta` files exist), `profile`, `parent_rules`. Say in the report which source decided `CR` |
| 0c | Context | fill `$CR/CONTEXT.md` when it has any `<!-- fill: … -->` placeholder, is older than ~30 days, or the default branch moved a lot since it was written (see "Filling CONTEXT.md"); then `100x pr_review context --refresh "$CR"`. `/pr-review init` stops here |
| 0d | Where it goes | per PR: `100x pr_review find "$CR" <pr-url>` (folder + bare number given: `find "$CR" <folder> <n>`; its 5th column is the PR URL). A `<folder>` the user named always wins over a found one. **Found** → re-review: feature = first folder under `CR` of the newest hit; run root = `100x pr_review next-run "$CR/<feature>"` (`runs/<date>`, `-2`, `-3` … same day); `PRIOR` = that newest `review.json` (its `user` + `posted` blocks carry forward). **Exit 1** (never reviewed) → feature = `--feature` or `100x pr_review slug <headRefName>` (if `$CR/<slug>` exists for another PR, add `-<n>`); run root = `$CR/<feature>/`. Several PRs: one run root per feature. Say in the report which case applied, and whether the head SHA is unchanged since `PRIOR` |
| 1 | Resolve + metadata | `gh pr view <arg> -R … --json url,number,title,author,headRefName,headRefOid,baseRefName,additions,deletions,changedFiles,body` · `gh pr checks <n> -R …` · `gh api --hostname HOST user -q .login` · resolve `--lang auto` from `body` (mostly Japanese → `ja`, else `settings.json` `lang`, else `en`) |
| 2 | Snapshot | `100x pr_snapshot --repo <clone> --url <pr-url> --pr <n> [--pr <m> …] --dest <scratch>/snap [--base <baseRefName>]` (pass `--base` when the base is not the default branch; PRs on different bases → one call and one `--dest` each) → copy `PINS.md` to the run root |
| 3 | Context | `gh issue view <n> -R …`, then `gh issue view <n> -R … --comments` for each linked issue/spec |
| 4 | Existing comments | `gh pr view <n> -R … --comments`, `gh api --hostname HOST repos/OWNER/REPO/pulls/<n>/comments`, `…/reviews` → passed to every agent (dedupe, rubric §1.8) |
| 5 | Load order | `$CR/CONTEXT.md` → repo `CLAUDE.md`/`AGENTS.md` (from `<snap>/<n>/`) → `meta/focus.md` + `meta/decisions.md` if present → `profile` if present. Pass them all to every agent; never invent one that is absent. On a conflicting code convention the repo's own files win over `CONTEXT.md` |
| 6 | Size tier + folders | `additions + deletions` → agents per rubric §6; Design / Scenario lenses per its Lenses table or `--design` / `--scenarios`, noting the trigger for the report · `<run-root>/PR-<num>__<area>-<short-title>__<author>/` (area = backend/frontend/spec/mixed) |
| 7 | Fan out | ONE message, all `run_in_background: true`, ≤ 10 agents, lenses included (subagents cannot spawn subagents, so the main session starts every agent); prompt = `reviewer-prompt.md` filled, row from its Variants. FOCUS = `focus-generic.md` blocks + `meta/focus.md` + `reviewers/<stack>.md` for each stack `100x stack_audit <snap>/<n> --here` reports |
| 8 | Merge fragments | `100x pr_review merge <pr-dir> <scratch>/{sec,des,scn}-<n>/fragment.json …` (whichever ran); move `5-security.md` in; for each "skipped X (same as Y)" line, fold any stronger evidence/fix into Y by hand; paste the Design fragment's `decisions` into `1-context.md` `## Author's decisions` as `Risk if wrong` · `Cost to undo` columns (a decision the PR reviewer did not list gets its own row) |
| 8b | Cross-examine | for every new `DES`/`SCN` item open the cited line at the pinned SHA (`<snap>/<n>/<path>`) or rerun the cited command; not confirmed → `evidence: inferred`, status `question`, `blocks` other than merge (normally `none`), `confirm_by` + `unknown` (G15) |
| 9 | Check suggestions | `100x pr_suggest <pr-dir> --repo <clone> --snap <snap> --write`, plus `--cmd "<typecheck>"` and `--link <rel>=<abs>` from `meta/settings.json` (`typecheck`, `links`) when the clone has deps; else `--note "<why not>"`. Failing changes are downgraded to `pseudo` |
| 10 | Verify | re-open the top ~8 claims yourself (snapshot grep, `git -C <clone> show <sha>:<path>`, rerun commands); fix or drop what does not hold, in `review.json` |
| 11 | Render + gate | `100x pr_review render <pr-dir>` · `100x pr_review feature <run-root>` · `100x pr_review_gate <run-root> --snap <snap>` → 0 · then `100x pr_review index "$CR"` (`INDEX.md` is always regenerated, never hand-edited) |
| 12 | Report | below. Never fix code; never post here |

**Report** (≤ 20 lines): per PR the README's In-10-seconds line, one line on which lenses ran and why (rubric §6 Lenses), the recommendation, the action
table rows as `# · type · where · blocks`, who must answer what (file 3), and the path to
`README.md`. End with the three-step loop: "1. Read `README.md` + `2-comments-to-post.md`.
2. Change anything: `/pr-review adjust <pr-url>`. 3. Post: `/pr-review post <pr-url>`." Never
offer to post in the same turn as the review.

## Filling CONTEXT.md

Read the repo at the default branch (the snapshot's `<default>` tree, or `git -C <clone> show
<remote>/HEAD:<path>`) and write only inside the `<!-- fill: … -->` slots — never inside
`<!-- auto:start/end -->`, which `context --refresh` owns (identity, stack, layout, convention
sources, related repos, last-refreshed date + HEAD sha). Target < 150 lines; a table beats a
paragraph. What the hand-filled slots should capture:

| Topic | Read |
|---|---|
| Conventions | `CLAUDE.md`, `AGENTS.md`, nested ones on hot paths |
| Repo's own review rubric | `.github/skills/code-review/SKILL.md`, `.github/copilot-instructions.md`, `CONTRIBUTING.md` — record its severity labels and how they map to rubric §3 |
| Architecture / layering | top-level dirs, module boundaries, where business logic is allowed to live |
| Auth and security boundaries | where identity is verified, tenancy key, what must never be called directly |
| Related repos | sibling repos it calls or is called by, and how (HTTP, package, events) |

## Prior findings and learning

| When | Do |
|---|---|
| `meta/decisions.md` exists, or a prior run of this PR exists | pass to every agent; accepted gaps and author decisions → `not_to_raise` or `status: accepted`; others re-checked |
| A reviewer found a bug class missing from every focus source | add one line to `$CR/_meta/focus.md` after the report (create it if absent) |

## Gotchas

| Situation | What happens | What to do |
|---|---|---|
| GitHub Enterprise host | `gh` is authenticated per host | `gh auth status --hostname <host>`; if it fails, tell the user to run `gh auth login --hostname <host>` — never work around it |
| Fork PR | the head is not on any branch of the clone's remotes | `pr_snapshot` fetches `pull/<n>/head`; nothing to do |
| `npx` missing | mermaid cannot be rendered | the gate warns and runs a syntax check instead; not a failure |
| Scratchpad gone between turns | `<snap>` no longer exists | re-run step 2 before any `--snap` gate |
| `100x …` runs `cd` or something else | a shell alias or function named `100x` shadows the plugin tool | run `command 100x <tool>` |
| zsh runs backticked names or fails on `*`/`?`/`=` | an unquoted heredoc, an unquoted glob, or a word starting with `=` | write JSON with `<<'EOF'` or a Python file, quote globs and `=`-words |

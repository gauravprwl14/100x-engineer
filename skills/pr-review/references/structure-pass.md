# Structure pass — approach, naming, placement, readability

Reference for `pr-review` (loaded on demand). The PR reviewer runs it after reading every
changed file and before writing items. It answers one question the other checks do not: **would
this repo build it this way?** A review that only checks what the diff does misses what a
colleague would say on a walk-through: "use the class we already have", "this name is wrong",
"this file does not belong there".

Switch: `<CR>/_meta/settings.json` `"structure_pass": false` skips it (default on). Judgement
comes from `diff-review` R1, R2, R8 (`skills/diff-review/SKILL.md`, "The questions nothing else
answers") and `reviewers/_code-craft.md`; this file only says where to look and how to write it up.

## Steps

1. **Solution first.** From the issue or spec and the repo, write three lines in your notes:
   how you would build this here, using classes, modules and helpers that already exist. Only
   then compare with the PR. A review that starts from the author's design polishes it.
2. **Closest analog.** For every new class, file, hook, helper or constant, grep for its nearest
   sibling (`git grep` at the pinned SHA). Does the PR follow it, extend it, or invent a parallel
   one? Cite the analog as `path:line` in the item.
3. **Walk the table** below over the changed files.
4. **Write at most 5 items**, ranked by how many places a future change would touch.

| Shape | Ask | Typical comment |
|---|---|---|
| Wrap, patch or extend | Are several hooks, wrappers or reassigned methods attached to a library object where one subclass, override or constructor option would hold them? | "four places attach telemetry to `X`; one `class Y extends X` overriding `get` and `getMany` puts them in one file" |
| Two writers, two facts | Is one value written from two places, or does one fact live in two metrics, columns or flags (an error counted as a miss and again as its own counter)? | "make `error` a third value of the one counter, written once" |
| Parallel invention | Does new logic repeat an existing sibling under another name (R2)? | "`dedupeIds` exists in `ids.ts`; reuse it" |
| Earns its place | Does a new file, helper, option or branch have no caller or one caller (R1, R8)? Does a function return its own arguments? | "no caller yet; drop it until the first use" |
| Name and place | Is a file named after a screen or an implementation detail? Does the folder force an import cycle? Does a constant lack the unit suffix its siblings carry? | "rename `user-card.cache.ts` to `users.cache.ts`; it is not a UI concept" |
| Readable | Is a function defined inline inside a `return`, a flag parameter selecting behaviour, `this.x` where siblings use the class name, a magic number? | `reviewers/_code-craft.md` shapes 1–14 |
| Free now | Is the shape still free to change because nothing has shipped, but not once a dashboard, API client or migration depends on it? | "nothing reads this metric yet; change its shape now" |

## Writing an item

| Field | Rule |
|---|---|
| `id` | `<PR>-STR-NN` |
| `kind` | `suggestion` or `question`; never `issue` unless it breaks a convention the repo states |
| `blocks` | `none`; `merge` only when it breaks a convention the repo states, cited from its own files |
| `why` | the maintenance scenario: who changes this next, and what they must touch |
| `comment` | quotes the code, or sketches in a few lines what it becomes (`change.type: pseudo`) |
| `evidence` | `read` at the pinned SHA, with the analog's `path:line` when there is one |

Leave it out when `<CR>/_meta/decisions.md` records the choice as accepted, or when the repo's own
`CLAUDE.md`/`AGENTS.md` prescribes it. Coverage rows: "Approach & structure" and "Naming,
placement, readability" (rubric §5); with the switch off write `Skipped — structure_pass off`.

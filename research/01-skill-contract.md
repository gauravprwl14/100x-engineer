# The Skill Contract

Every SKILL.md in this plugin must satisfy this contract. A skill that cannot is
deleted, not weakened. This exists because the dominant failure mode of AI-agent
instruction files is **unfalsifiable advice** — prose that sounds wise, changes no
behaviour, and can never fail.

## Required sections

### 1. Frontmatter
```yaml
---
name: kebab-case-name
description: >
  Third-person, keyword-dense trigger. Must name the concrete artifacts and verbs
  that should fire it. Starts with "Use when ...".
---
```
The `description` is the only thing the model sees when deciding whether to load
the skill. It is a **retrieval key, not a summary**. Vague descriptions are the
single biggest cause of skills never firing.

### 2. `## Trigger`
Explicit fire / do-not-fire conditions. A skill that fires always is noise; a
skill that never fires is dead weight. Both are bugs.

### 3. `## Rules`
Numbered. Each rule is one line of instruction plus an `Enforced by:` tag:

| Tag | Meaning |
|-----|---------|
| `Enforced by: <command>` | a command that exits non-zero on violation |
| `Enforced by: review` | needs human or LLM judgement — no mechanical check exists |
| `Enforced by: convention` | honour-system. **Cap: 3 per skill.** |

The cap on `convention` is the load-bearing constraint of this whole plugin.
Without it every skill silently degrades into a wish list.

### 4. `## Verify`
A copy-pasteable block that proves the work is correct. This is the section that
matters most — it is what the agent runs before claiming done.

```bash
# each line must exit non-zero on failure
<command>
```
Rules for this block:
- No command may be aspirational. If the repo lacks the tool, the skill must
  detect that and say so, not pretend.
- Prefer **diff-scoped** checks over whole-repo checks — whole-repo gates are
  unrunnable on an existing codebase and get disabled, which is worse than absent.
- State the expected runtime. A 40-minute check will be skipped.

### 5. `## Failure modes`
What this skill REJECTS, with a concrete example of the bad output it catches.
If you cannot write this section, the skill has no teeth — delete it.

### 6. `## Scale`
When this practice starts paying for itself:
`solo | small-team (2-10) | org (10+) | high-blast-radius`
Kubernetes' process would sink a 3-person team. Tagging prevents cargo-culting.

### 7. `## Sources`
`owner/repo@ref:path` for every non-obvious claim. A practice with no production
repo behind it is our invention and must be labelled `SOURCE: original` so the
reader knows its provenance is weaker.

## Global limits
- **≤ 250 lines** per SKILL.md. Longer goes into `references/` and is loaded on demand.
- **≤ 3** `Enforced by: convention` rules.
- **≥ 1** runnable command in `## Verify`. No exceptions.
- Every skill must be independently useful. No skill may require another to be loaded first.

## The deletion test
Before shipping any skill, answer: *what bad output does this reject that would
otherwise ship?* If there is no answer, delete the skill. Volume is not value —
30 sharp skills beat 100 vague ones, and a vague skill actively costs context
budget that a sharp one could have used.

[← INDEX](INDEX.md)

# Project rules

What explain reads from the target project, and the default when the project says nothing.
Moved out of SKILL.md so the skill stays inside the line cap.

The skill holds no knowledge of any project. Before research, read the target project's
`CLAUDE.md` / `AGENTS.md` (repo root, then any nested file on the touched paths; for a PR, from
the head snapshot) for what they say about these, and use the default when they say nothing:

| setting | default |
|---|---|
| folders to ignore | gitignored, generated and vendored files (`100x repo_map` marks them) |
| glossary (terms the page must use) | none; names come from the code |
| language | `en`; `ja` adds `title.ja` and step text in both |
| default tier | `light` |
| output dir | PR: `<CR>/<feature>/PR-<n>__…/explain/`, `CR` from `100x pr_review paths --url <pr-url> --json`; else `<root>/explain/<slug>/` |

`<root>` is the records root (`docs/OPERATING-MODEL.md` §8). The report says which settings came
from the project and which are defaults; on a conflict the project's file wins.


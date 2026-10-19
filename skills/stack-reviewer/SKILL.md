---
name: stack-reviewer
description: >
  Framework stack review — Rails, Django, FastAPI, Express, Go, NestJS, Next.js, React Native,
  Flutter, Android, iOS, Kubernetes, Terraform: stack mistakes, module boundaries, language
  pitfalls, N+1, insecure defaults. Not for toolchains (→ language-verification).
---

# Stack reviewer

Generic review advice does not catch a missing `whitelist: true` on a NestJS
`ValidationPipe`, or `key={index}` on a reorderable React list, or a Flutter
`BuildContext` used after an async gap. Those are framework-specific, and they are
where agent-written code fails most reliably.

Each reviewer file is grounded in real production repositories, including defects found
in official reference code.

## Trigger

**Fire when:** a diff touches one of the stacks below, or you are about to write code
in one.

**Do not fire when:** the change is framework-agnostic (a pure utility, a config value,
docs) — `diff-review` covers that.

## Routing

`100x stack_audit .` prints the matching reviewer files under `=== Reviewers ===`.

| signal in the repo | reviewer |
|---|---|
| `gem "rails"` in Gemfile (root or one level down) | `reviewers/rails.md` |
| `django` or `fastapi` in pyproject/requirements | `reviewers/django-fastapi.md` |
| `express` in package.json, no `@nestjs/core` | `reviewers/express-node.md` |
| `go.mod` (HTTP or gRPC service) | `reviewers/go-service.md` |
| `@nestjs/*` in package.json | `reviewers/nestjs.md` |
| `next` in package.json, `app/` or `pages/` | `reviewers/nextjs-react.md` |
| `react-native` / `expo` in package.json | `reviewers/react-native-expo.md` |
| `pubspec.yaml` | `reviewers/flutter.md` |
| `build.gradle*`, `*.xcodeproj`, `Package.swift` | `reviewers/native-mobile.md` |
| `*.yaml` with `apiVersion:`/`kind:`, `Chart.yaml`, `kustomization.yaml` | `reviewers/kubernetes.md` |
| `*.tf`, `cdk.json`, CloudFormation templates | `reviewers/cloud-iac.md` |
| any language | `skills/language-verification` for the toolchain (lint, types, tests) |

Read the one that matches. Do not read them all — that is context spent on stacks not
in the diff.

## Rules

1. Identify the stack from repo signals, then read that reviewer's
   `## Common AI failure modes` section before writing code in it. If the diff is
   in a stack you don't know well, orient first:
   `100x diagram_from_code <dir> --kind sequence --level 1` (≤12
   nodes) before reading source linearly.
   *Enforced by:* `100x stack_audit .` (lists the reviewer files for the detected stacks)

2. Apply the reviewer's `## Blocking rules`. Each is a runnable check or a yes/no
   question, never an adjective.
   *Enforced by:* the `## Verify` block in the reviewer file

3. Use the reviewer's `## Approach selection` default rather than deriving one. These are
   the recurring choices, already answered with the factor that would change the answer.
   *Enforced by:* `100x decide lint` when you depart from a default

4. Walk the reviewer's `## Edge cases routinely missed` against the diff, and its
   `## Language pitfalls`, `## Security defaults` and `## Performance` tables where present.
   These are stack-specific and are not in the generic edge-case catalogue.
   *Enforced by:* review, recorded in the spec's edge-case table

5. For a stack with no reviewer file, say so rather than substituting generic advice,
   and write one if you will work in it repeatedly.
   *Enforced by:* `ls reviewers/`

6. Run the stack's own verification commands, not a generic substitute.
   *Enforced by:* the `## Verify` block in the reviewer file, bound via `scripts/verified.py`

## Verify

```bash
# what stacks are actually here?
100x stack_audit .

# orient before reviewing an unfamiliar diff (rule 1): L1 first, L2 if you'll
# actually touch the code, not just review it
100x diagram_from_code <dir> --kind sequence --level 1
100x diagram_from_code <dir> --kind sequence --level 2

# read only the relevant reviewer's failure modes
ls reviewers/
sed -n '/## Common AI failure modes/,/## Edge cases/p' reviewers/<stack>.md

# run that stack's checks, bound to the code being shipped
100x verified --name typecheck -- <the reviewer's typecheck command>
100x verified --name test      -- <the reviewer's test command>

# then the generic pass for what no tool catches
100x review_scope --base origin/main
```

## Failure modes

This skill rejects:

- **Generic review on framework-specific code.** A NestJS `ValidationPipe` without
  `whitelist: true` silently accepts extra fields — found as a real gap in a production
  repo's own bootstrap, not a hypothetical.
- **`key={index}` on a list that can reorder** — present in Vercel's own commerce
  reference template's cart modal.
- **Deriving an architecture choice** the reviewer already answers with a default.
- **Reading every reviewer file** when one stack is in scope.
- **Substituting generic advice** for a stack with no reviewer, which produces
  confident, wrong-shaped guidance.

**Honest limitation:** these files are snapshots. Framework idioms move — App Router
conventions, Riverpod versus Bloc, Kubernetes API deprecations — so a reviewer more than
a few months old should be re-grounded against current code rather than trusted. Each
file carries its sources so that is checkable.

## Next

Once the stack is identified, the language toolchain is a separate skill:
`language-verification`. For a mobile
release specifically, add `mobile-release-safety`. Bind whatever you ran with
`verification-gate` before claiming the review is done.

## Scale

`solo` and up. Stack-specific failure modes do not vary with team size; what varies is
who catches them. At `solo`, nobody does unless this runs.

## Sources
- Each reviewer file carries its own `## Sources`, grounded in cloned production repos.
- Notable verified findings: a missing global `whitelist: true` in a production NestJS
  bootstrap; `forwardRef()` used 28 times in one repo and 0 in another on the same
  framework; `nestjs/nest`'s own coverage script suffixed `|| true`; unvalidated
  `searchParams` cast with `as` and `key={index}` on a mutable list in Vercel's commerce
  reference app. See `reviewers/nestjs.md` and `reviewers/nextjs-react.md`.
- Rails, Django/FastAPI, Express and Go reviewers cite framework docs and linter configs
  (`rails/rails@main:guides/source/active_record_querying.md`,
  `rubocop/rubocop-rails@master:config/default.yml`, `django/django@main:docs/ref/models/querysets.txt`,
  `golang/website@master:_content/doc/go1.22.md`); see each file's `## Sources`.
- Mobile release-safety and migration-test practice: `research/33-findings-mobile-verification.md`.
- Security and supply-chain baselines: `research/35-findings-security-reliability.md`.

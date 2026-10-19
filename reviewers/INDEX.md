# Reviewer index

17 reviewer files. Stack-specific failure modes, edge cases and default architectural choices. Files prefixed `_` are shared references, not stack reviewers.

| file | covers | applies when | lines |
|---|---|---|--:|
| [cloud-iac.md](cloud-iac.md) | Cloud / IaC reviewer (AWS + GCP + Terraform) | Any `*.tf`/`*.tf.json` file exists in the repo. | 139 |
| [django-fastapi.md](django-fastapi.md) | Django + FastAPI reviewer | `pyproject.toml`, `requirements*.txt` or `Pipfile` lists `django` or `fastapi`. | 122 |
| [express-node.md](express-node.md) | Express + Node.js reviewer | `package.json` has `express` as a direct dependency and no `@nestjs/core`. | 119 |
| [flutter.md](flutter.md) | Flutter reviewer | `pubspec.yaml` declares a `flutter:` SDK dependency; the diff touches `.dart` files under `lib/`. | 90 |
| [go-service.md](go-service.md) | Go service reviewer | `go.mod` exists and the module imports `net/http`, `google.golang.org/grpc`, or a router (`chi`, `gin`, `echo` | 122 |
| [kubernetes.md](kubernetes.md) | Kubernetes reviewer | Any file matches `apiVersion:` + `kind: (Deployment|StatefulSet|DaemonSet|Pod|Job|CronJob|Service|Ingress|Hori | 166 |
| [native-mobile.md](native-mobile.md) | Native Android + iOS reviewer | Android: `build.gradle`/`build.gradle.kts` present with an `com.android.application`/`library` | 169 |
| [nestjs.md](nestjs.md) | NestJS reviewer | `package.json` has `@nestjs/core` as a direct dependency. | 207 |
| [nextjs-react.md](nextjs-react.md) | Next.js + React reviewer | `next` in `package.json` `dependencies`, or `next.config.{js,mjs,ts}` present. | 149 |
| [rails.md](rails.md) | Rails reviewer | `Gemfile` declares `gem "rails"`, or `Gemfile.lock` lists `rails (`. | 166 |
| [react-native-expo.md](react-native-expo.md) | React Native + Expo reviewer | `package.json` depends on `react-native` or `expo`; an `app.json`/`app.config.js` with an | 95 |
| [_code-craft.md](_code-craft.md) | Code-craft shapes | A before/after reference for `skills/code-craft/SKILL.md`. Each shape is a | 395 |
| [_diagram-levels.md](_diagram-levels.md) | The three detail levels | One page, one flow, three drawings, so the difference is visible instead of | 177 |
| [_engineer-standards.md](_engineer-standards.md) | Engineer standards card | Read while writing, not after. Each line is a rule a reviewer will check; the skill named in | 34 |
| [_evidence-labels.md](_evidence-labels.md) | Evidence labels | A shared vocabulary for marking where a statement came from. Used by | 67 |
| [_frontend-layers.md](_frontend-layers.md) | Frontend layers: the same component, badly layered then correctly layered | A before/after reference for `skills/frontend-architecture/SKILL.md`. Same | 211 |
| [_latency-numbers.md](_latency-numbers.md) | Latency numbers every engineer should reason from | The back-of-envelope table every senior engineer has half-memorized. It exists so | 121 |

Read only the one matching the diff — see the `stack-reviewer` skill.

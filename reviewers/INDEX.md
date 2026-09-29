# Reviewer index

12 reviewer files. Stack-specific failure modes, edge cases and default architectural choices. Files prefixed `_` are shared references, not stack reviewers.

| file | covers | applies when | lines |
|---|---|---|--:|
| [cloud-iac.md](cloud-iac.md) | Cloud / IaC reviewer (AWS + GCP + Terraform) | Any `*.tf`/`*.tf.json` file exists in the repo. | 108 |
| [flutter.md](flutter.md) | Flutter reviewer | `pubspec.yaml` declares a `flutter:` SDK dependency; the diff touches `.dart` files under `lib/`. | 90 |
| [kubernetes.md](kubernetes.md) | Kubernetes reviewer | Any file matches `apiVersion:` + `kind: (Deployment|StatefulSet|DaemonSet|Pod|Job|CronJob|Service|Ingress|Hori | 147 |
| [native-mobile.md](native-mobile.md) | Native Android + iOS reviewer | Android: `build.gradle`/`build.gradle.kts` present with an `com.android.application`/`library` | 145 |
| [nestjs.md](nestjs.md) | NestJS reviewer | `package.json` has `@nestjs/core` as a direct dependency. | 195 |
| [nextjs-react.md](nextjs-react.md) | Next.js + React reviewer | `next` in `package.json` `dependencies`, or `next.config.{js,mjs,ts}` present. | 149 |
| [react-native-expo.md](react-native-expo.md) | React Native + Expo reviewer | `package.json` depends on `react-native` or `expo`; an `app.json`/`app.config.js` with an | 95 |
| [_code-craft.md](_code-craft.md) | Code-craft shapes | A before/after reference for `skills/code-craft/SKILL.md`. Each shape is a | 317 |
| [_diagram-levels.md](_diagram-levels.md) | The three detail levels | One page, one flow, three drawings, so the difference is visible instead of | 177 |
| [_evidence-labels.md](_evidence-labels.md) | Evidence labels | A shared vocabulary for marking where a statement came from. Used by | 67 |
| [_frontend-layers.md](_frontend-layers.md) | Frontend layers: the same component, badly layered then correctly layered | A before/after reference for `skills/frontend-architecture/SKILL.md`. Same | 211 |
| [_latency-numbers.md](_latency-numbers.md) | Latency numbers every engineer should reason from | The back-of-envelope table every senior engineer has half-memorized. It exists so | 121 |

Read only the one matching the diff — see the `stack-reviewer` skill.

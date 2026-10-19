---
name: app-security
description: >
  Endpoint, API route, webhook or form handler security: is it secure — authz and BOLA, tenant
  isolation, injection, XSS, CSRF, SSRF, mass assignment, secrets, OWASP API Top 10. Not for
  repo posture (→ security-baseline).
---

# App security

`security-baseline` asks whether the repository is defended: disclosure policy,
scanners that gate, pinned actions. This skill asks whether the code in the diff
is: whether user A can read user B's invoice by changing an id, whether a JSON
body can set `role: "admin"`, whether a webhook URL can reach the cloud metadata
endpoint. Those are logic defects in the feature itself, and no repo-level
scanner configuration finds them for you.

## Trigger

**Fire when:** a diff adds or changes a route, controller, resolver, server
action, webhook receiver, file upload, outbound HTTP call, raw query, HTML
rendering of stored content, auth or session code, or a config value that looks
like a credential.

**Do not fire when:** the change is pure presentation with no input, query or
secret; or the question is repo posture (go to `security-baseline`), or a
third-party repo's agent config (go to `untrusted-agent-config`).

## Rules

1. **Threat-model each feature in five minutes, STRIDE-lite.** For every new
   entry point, write one line each: who can call it (Spoofing), what it may
   change (Tampering), what is logged (Repudiation), what it can return
   (Information disclosure), how it fails under load (Denial of service), and
   what privilege it grants (Elevation). Put the lines in the spec or PR body.
   *Enforced by:* review

2. **API1, object-level authorization lives in the query.** Every lookup by id
   is scoped by owner or tenant in the same statement
   (`WHERE id = $1 AND company_id = $2`, with the tenant from the verified
   session, never the request), so a guessed id returns 404, not someone else's
   row. Add a negative test: tenant B cannot read tenant A's object.
   *Enforced by:* review, plus the per-persona tests in `security-baseline` rule 7

3. **API2, authentication is boring and strict.** Verify a token's signature,
   algorithm, expiry and audience; rate-limit login, reset and OTP endpoints;
   never put a token in a URL; rotate the session on login and privilege change.
   *Enforced by:* review

4. **API3, property-level authorization: allowlist fields in and out.** Bind
   input to a DTO that names only the writable fields (NestJS `ValidationPipe`
   with `whitelist: true, forbidNonWhitelisted: true`), copy named fields into
   the entity, and serialize responses through an explicit shape so
   `passwordHash` and `internalNotes` cannot leak.
   *Enforced by:* `100x appsec_check --only mass-assignment,dto-spread-into-orm`

5. **API4, every endpoint has a resource ceiling:** a maximum page size, body and
   upload size limits, a query timeout, and a rate limit on anything expensive.
   *Enforced by:* review

6. **API5, function-level authorization is deny-by-default.** Register a global
   guard (`APP_GUARD`) and mark public routes explicitly, rather than
   remembering `@UseGuards` per controller; admin routes check the role on the
   server, not by hiding a button.
   *Enforced by:* `100x appsec_check --only nest-controller-no-guard` (advisory), then review

7. **API6, protect sensitive business flows from automation:** sign-up,
   checkout, invitations, coupon redemption and anything that sends email or SMS
   get per-account and per-IP limits, and a step-up check where abuse costs money.
   *Enforced by:* review

8. **API7, SSRF: a server-side fetch of a user-supplied URL needs a host
   allowlist.** Parse with `new URL()`, check the hostname against the allowlist,
   reject private, loopback and link-local addresses after DNS resolution, and
   disable redirects or re-check each hop.
   *Enforced by:* `100x appsec_check --only ssrf`

9. **API8 and API9, configuration and inventory.** No `Access-Control-Allow-Origin: *`
   with credentials, no stack traces or debug mode in production responses,
   security headers set; every live route appears in the OpenAPI document, and
   old versions are retired on a date, not left running.
   *Enforced by:* review

10. **Encode output; never inject raw HTML.** Render user content as text. When
    HTML is the product (rich text), sanitize with an allowlist sanitizer such
    as DOMPurify at render time; never pass unsanitized data to
    `dangerouslySetInnerHTML`, `v-html`, `innerHTML` or `insertAdjacentHTML`.
    *Enforced by:* `100x appsec_check --only unsafe-html`

11. **Secrets never live in code, the client bundle, or logs.** Read them from
    the environment or a secret manager; never prefix one with `NEXT_PUBLIC_` or
    `VITE_` (both are inlined into browser JavaScript); redact tokens, passwords
    and keys in log output. Run gitleaks in pre-commit or CI and enable GitHub
    push protection. A committed secret is rotated, not just deleted.
    *Enforced by:* `100x appsec_check --only hardcoded-secret`

12. **Bind query parameters; never build SQL with strings.** Use the driver's
    placeholders, the ORM's query builder with named parameters, or a tagged
    template (`sql\`…\``, Prisma `$queryRaw`) that binds each value. Identifiers
    that must be dynamic come from a fixed allowlist.
    *Enforced by:* `100x appsec_check --only sql-concat`

13. **Cookie-authenticated state changes need CSRF defence:** `SameSite=Lax` or
    `Strict` on the session cookie plus a synchronizer token or an `Origin`
    header check on every non-GET request. Bearer-token APIs are exempt.
    *Enforced by:* review

14. **API10, treat third-party API responses as untrusted input.** Validate the
    shape before use, set a timeout, use TLS, and never follow a redirect or
    execute a URL a partner returned without the same checks as rule 8.
    *Enforced by:* review

## Verify

Diff-scoped; `appsec_check` runs in about a second.

```bash
100x appsec_check --list
100x appsec_check --base origin/main            # blocking findings fail
100x appsec_check --base origin/main --strict   # advisories fail too
gitleaks git --log-opts="origin/main..HEAD"     # if installed: secrets in the new commits
! grep -rnE '(NEXT_PUBLIC|VITE)_[A-Z0-9_]*(SECRET|PRIVATE|PASSWORD|TOKEN)' --include='*.ts' --include='*.tsx' --include='*.js' --exclude-dir=node_modules .
100x audit_ci_gates .                           # the SAST job actually gates (security-baseline)
```

`appsec_check` is regex with one hop of taint (request value, then a variable,
then a sink, in one file). It trusts any allowlist or sanitizer it can see by
name and skips test and fixture paths. It does not replace CodeQL or Semgrep,
and it cannot see rules 1–3, 5, 7, 9, 13 or 14; those need the STRIDE lines and
a reviewer.

## Failure modes

This skill rejects:

- **`invoiceRepo.findOne({ where: { id } })`** with no tenant in the `where`:
  any logged-in user enumerates every company's invoices (API1).
- **`Object.assign(user, req.body)`** or `prisma.user.update({ data: req.body })`:
  the client sends `"role": "admin"` and becomes one (API3).
- **`fetch(req.body.webhookUrl)`** with no allowlist: the attacker points it at
  `http://169.254.169.254/` and reads cloud credentials (API7).
- **`<div dangerouslySetInnerHTML={{ __html: comment.body }} />`**: stored XSS
  in every viewer's session.
- **``db.query(`SELECT * FROM users WHERE email = '${email}'`)``**: SQL
  injection.
- **`const STRIPE_KEY = "…"`** in source, or `NEXT_PUBLIC_STRIPE_SECRET`: the key
  ships in git history or in the browser bundle.
- **A cookie-session `POST /transfer` with no CSRF token or Origin check.**
- **A NestJS controller with no guard** in an app with no global `APP_GUARD`.

## Scale

**Every tier, `solo` included: rules 1–4, 6, 8, 10–13.** Broken object-level
authorization, injection and XSS are correctness bugs with an attacker attached;
team size does not change them. `small-team (2-10)`: add 5, 7 and 14, and run
`appsec_check --strict` in CI. `org (10+)`: add 9 with an API inventory owned by
someone, plus CodeQL `security-extended` (`security-baseline` rule 6).
`high-blast-radius`: an external penetration test before launch of any new
sensitive flow.

## Sources

- OWASP API Security Top 10 2023, API1–API10 names and scope:
  https://owasp.org/API-Security/editions/2023/en/0x11-t10/.
- STRIDE as the threat-identification prompt:
  `OWASP/CheatSheetSeries@master:cheatsheets/Threat_Modeling_Cheat_Sheet.md`.
- DTO allowlists against mass assignment:
  `OWASP/CheatSheetSeries@master:cheatsheets/Mass_Assignment_Cheat_Sheet.md`.
- SSRF allowlist approach:
  `OWASP/CheatSheetSeries@master:cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.md`.
- Output encoding and HTML sanitization:
  `OWASP/CheatSheetSeries@master:cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.md`.
- Parameterized queries:
  `OWASP/CheatSheetSeries@master:cheatsheets/Query_Parameterization_Cheat_Sheet.md`.
- CSRF (synchronizer token, SameSite):
  `OWASP/CheatSheetSeries@master:cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.md`.
- Secrets and logging: `OWASP/CheatSheetSeries@master:cheatsheets/Secrets_Management_Cheat_Sheet.md`,
  `cheatsheets/Logging_Cheat_Sheet.md`.
- Global guards: `nestjs/docs.nestjs.com@master:content/guards.md` (`APP_GUARD`,
  `useGlobalGuards()`).
- Secret patterns: `gitleaks/gitleaks@master:config/gitleaks.toml` rules
  `aws-access-token` and `private-key`; GitHub push protection "blocks pushes
  that contain secrets before they reach your repository"
  (docs.github.com, secret scanning, About push protection).
- Bundled env vars: Next.js "How to use environment variables" (`NEXT_PUBLIC_`
  is inlined into browser JS); Vite "Env Variables and Modes" (`VITE_*` must not
  hold API keys).
- `scripts/appsec_check.py` and its one-hop taint heuristic: `SOURCE: original`;
  false-positive controls in `tests/test_appsec_check.sh`.

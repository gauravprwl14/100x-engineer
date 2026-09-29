# ADR-0001: Session strategy for login

```json meta
{
  "id": "ADR-0001",
  "title": "Session strategy for login",
  "status": "accepted",
  "date": "2026-09-29",
  "decided_by": "claude",
  "tags": [
    "backend",
    "auth"
  ],
  "affects": [
    "examples/login/**"
  ],
  "commit": null,
  "assumptions": [
    {
      "id": "A1",
      "claim": "Sessions must be revocable within one request (logout, password change, admin ban)",
      "verify": "test -f examples/login/spec.md && grep -qi 'revocable' examples/login/spec.md",
      "revisit_when": "product accepts a revocation delay of minutes, e.g. for a read-only public API",
      "confidence": "high"
    },
    {
      "id": "A2",
      "claim": "A server-side session store is available and its loss is tolerable (users re-login)",
      "verify": "grep -qE 'redis|session_store' examples/login/spec.md",
      "revisit_when": "the deployment target has no shared store, e.g. pure edge functions",
      "confidence": "medium"
    },
    {
      "id": "A3",
      "claim": "This assumption is deliberately left unverifiable to prove the tool reports it",
      "verify": "",
      "revisit_when": "never",
      "confidence": "low"
    }
  ],
  "options": [
    {
      "name": "Stateless JWT in a cookie",
      "chosen": false,
      "why_not": "cannot revoke before expiry without a denylist, which reintroduces the state it was meant to avoid"
    },
    {
      "name": "Opaque server session id in an httpOnly cookie",
      "chosen": true,
      "why": "revocation is a single delete; the deciding factor is A1"
    },
    {
      "name": "JWT access token + refresh token rotation",
      "chosen": false,
      "why_not": "correct for third-party API clients; unnecessary complexity for a first-party web app with a shared store"
    }
  ],
  "supersedes": null,
  "revisit_by": "2026-01-01"
}
```

## Context

<!-- What forced a decision. One paragraph. What was true at the time that made this
     a choice rather than an obvious default. -->

## Options considered

<!-- One subsection per option. For each: what it is, and the concrete reason it
     was or was not chosen. An option with no stated downside was not really
     considered. -->

### Option A — <name>
### Option B — <name>

## Decision

<!-- What was chosen, and the single deciding factor. -->

## Consequences

<!-- What this makes easy, and what it makes hard or expensive later. The second
     half is the one people skip and the one that matters. -->

## Gaps accepted

<!-- What this decision deliberately does NOT handle. An agent that records nothing
     here is claiming it thought of everything, which is never true. Each gap needs
     either a follow-up reference or an explicit "accepted, not planned". -->

| gap | consequence if hit | accepted? | follow-up |
|-----|--------------------|-----------|-----------|

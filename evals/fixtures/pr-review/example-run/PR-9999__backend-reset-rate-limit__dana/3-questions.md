# PR 9999 — open questions

> **In 10 seconds:** 1 thing this review could not confirm or needs someone to answer — answered by: Infra on-call, author.

| # | What we don't know | Why it matters | How to confirm | Who answers | Where to ask | Comment |
|---|---|---|---|---|---|---|
| 2 | Whether prod runs more than one API instance | Each server counts alone. With 4 servers the real cap is about 12 a minute, not 3. Fine for one server, wrong for many. | `kubectl get deploy api -o jsonpath='{.spec.replicas}'` in prod; > 1 means the cap is multiplied | author; also Infra on-call | line comment; Slack #infra | [#2](2-comments-to-post.md#c2) |

# Actions and the reducer, v1 (frozen)

A step's `do` is a list of `[action, …args]`. State after step *i* is a pure reduce over every
action of steps 0..*i*, from `initial`. `scripts/flow.py` (`reduce_scenario`) and the JS player
implement the same semantics; `tests/flow/states.json` is the golden output both must match.
Adding an action or changing one is a schema change, not an edit here.

## Vocabulary

`node:<role>` = a node id of that role; `?` = optional; Text, value: see `schema.md`.

| action | args | effect on state | active nodes |
|---|---|---|---|
| `send` | from: node, to: node, label?: Text | appends `{kind: "send", from, to, label}` to the step's `messages` | from, to |
| `reply` | from: node, to: node, label?: Text | same, `kind: "reply"`; the label may carry an HTTP status | from, to |
| `enqueue` | queue: node:queue, job: string | appends `job` to `queues[queue]` | queue |
| `pickup` | queue: node:queue, worker: node:worker | moves the queue's head job into the worker's first free slot; error if the queue is empty or no slot is free | queue, worker |
| `free` | worker: node:worker, job?: string | empties the slot holding `job`, else the first busy slot; error if none | worker |
| `cache.get` | cache: node:cache, key | sets the step's `hit` to `"hit"` if the key is present (stale or not), else `"miss"` | cache |
| `cache.set` | cache: node:cache, key, value \| `$var` | stores `{v, stale, src}`; a `$var` copies the variable's value and `src`; see hazards | cache |
| `cache.set-if-fresh` | cache: node:cache, key, `$var` | the fix for a stale writeback: if the store value `$var` was read from (its `src`) still equals `$var`, stores `{v, stale: false, src}`; otherwise writes nothing and adds `{cache, key, store, store_key, read, current}` to the step's `skipped`. Never raises a hazard; a literal value is a finding. The reducer does the compare and the write as one step; the code does not, so a step using it must cite in `ev` the primitive that makes it atomic (finding otherwise) | cache |
| `cache.del` | cache: node:cache, key | removes the key (absent is a no-op) | cache |
| `cache.expire` | cache: node:cache, key | removes the key; drawn as a TTL running out | cache |
| `mark-stale` | cache: node:cache, key | sets the entry's `stale` to true; error if absent | cache |
| `db.read` | store: node:store, key, var? | binds `vars[var]` (default `read`) to `{v: stored value or null, src: [store, key]}` | store |
| `db.write` | store: node:store, key, value \| `$var` | sets `stores[store][key]`; every cache entry whose `src` is `[store, key]` and whose value differs becomes `stale` | store |
| `wait` | duration: `{{name}}` | adds the number, in ms, to `clock_ms`; its unit is `ms`, `s`, `min` or `h`; rounded half up (`Math.round`) | — |
| `counter` | name, delta: int | `counters[name] += delta` (starts at 0) | — |
| `fail` | node, label?: Text | adds node to `failed` (once) and `{node, label}` to the step's `failures` | node |
| `note` | text: Text | appends to the step's `notes` | — |

`active` lists each touched node once, in first-touch order. `$var` references and variable names
match `[a-z][a-z0-9_]*`; an unbound `$var` is a reducer error.

## Hazard: `stale-writeback`

Raised by `cache.set(cache, key, $var)` when `$var` came from `db.read(store, skey)` and
`stores[store][skey]` no longer equals that value: a write landed between the read and the
fill. The entry is stored with `stale: true` and the step's `hazards` gets
`{kind: "stale-writeback", cache, key, store, store_key}`. The step must declare
`"hazard": "stale-writeback"`; an undeclared one, or a declared one that does not happen, is a
finding. A literal `cache.set` value has `src: null` and never raises it. Staleness from a
`db.write` after the fill (the normal invalidation window) sets `stale` but raises no hazard.
`cache.set-if-fresh` is the guarded form of the same fill: it never stores a value whose source
changed, so it never raises the hazard; a lost race shows up in `skipped` instead. A fix scenario
that swaps `cache.set` for it replays the issue's timeline with the hazard gone.

`set-if-fresh` is atomic only in the reducer: there the compare and the write cannot be
interleaved; in a real cache client a plain `GET`-compare-`SET` can, and a write landing between
them brings the hazard back. A fix scenario using it is a claim about a primitive in the code: a
compare-and-set, a Lua script run by the cache, a version column the fill compares, or a lock or
lease. Cite that line in the step's `ev`; `flow check` rejects a step that uses the action with no
evidence.

It compares values, not versions (ABA): the guard asks whether the store holds the same value
the read returned. If the value changes and changes back (`v1` → `v2` → `v1`) between the read and
the fill, the reducer writes, because the values match. That is harmless for this cache, whose entry
equals the store, but it hides that two writes happened, and it is not how a version guard behaves:
a version column would reject the fill. When the order of writes matters, model the version as the
stored value (`v1`, `v2`, `v3`, never reused) rather than the payload.

v1 detects no other hazard; other races are scenarios the agent writes and the reader judges.

## State shape

One object per step a reader sees (inherited steps included), as `flow reduce --json` prints
under `scenarios.<id>`:

```json
{
  "step": 4, "origin": "race", "origin_step": 4, "inherited": false,
  "clock_ms": 0,
  "active": ["cache"],
  "messages": [{"kind": "send", "from": "reader", "to": "api", "label": "GET /notes/:id"}],
  "hit": null,
  "queues": {"jobs": ["job-b"]},
  "workers": {"pool": ["job-a", null]},
  "caches": {"cache": {"note:a": {"v": "v1", "stale": true, "src": ["db", "notes/a"]}}},
  "stores": {"db": {"notes/a": "v2"}},
  "vars": {"read": {"v": "v1", "src": ["db", "notes/a"]}},
  "counters": {"enqueued": 2},
  "failed": ["mailer"],
  "failures": [{"node": "mailer", "label": "timeout"}],
  "notes": ["Stale for up to {{cache_ttl}} after the fill."],
  "hazards": [{"kind": "stale-writeback", "cache": "cache", "key": "note:a", "store": "db", "store_key": "notes/a"}],
  "skipped": []
}
```

| field | scope | |
|---|---|---|
| `step`, `origin`, `origin_step`, `inherited` | position | `origin` is the scenario that owns the step; `origin_step` its index there |
| `clock_ms`, `queues`, `workers`, `caches`, `stores`, `vars`, `counters`, `failed` | cumulative | every queue, worker, cache and store node has a key from step 0; `workers` has `slots` entries, `null` = free |
| `active`, `messages`, `hit`, `failures`, `notes`, `hazards`, `skipped` | this step only | `hit` is the last `cache.get` of the step, or null |

Labels and notes keep their Text form and `{{name}}` placeholders; the renderer substitutes them.

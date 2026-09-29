# Code-craft shapes

A before/after reference for `skills/code-craft/SKILL.md`. Each shape is a
named smell with a mechanical check where possible (`scripts/craft_check.py`)
and a review question where it isn't. This file is examples; the skill is
the contract.


## Contents

| # | section | what it answers | size |
|---|---------|-----------------|------|
| 1 | [Naming reveals intent](#naming-reveals-intent) | naming reveals intent | 24 lines |
| 2 | [One level of abstraction per function](#one-level-of-abstraction-per-function) | one level of abstraction per function | 22 lines |
| 3 | [Function length](#function-length) | function length | 10 lines |
| 4 | [Parameter count and the parameter object](#parameter-count-and-the-parameter-object) | parameter count and the parameter object | 19 lines |
| 5 | [No boolean flag parameters that select behaviour](#no-boolean-flag-parameters-that-select-behaviour) | no boolean flag parameters that select behaviour | 21 lines |
| 6 | [Guard clauses and nesting depth](#guard-clauses-and-nesting-depth) | guard clauses and nesting depth | 30 lines |
| 7 | [Cohesion, coupling, and the Law of Demeter concretely](#cohesion-coupling-and-the-law-of-demeter-concretely) | cohesion, coupling, and the law of demeter concretely | 27 lines |
| 8 | [Error handling as design](#error-handling-as-design) | error handling as design | 29 lines |
| 9 | [Comments: why, not what](#comments-why-not-what) | comments: why, not what | 6 lines |
| 10 | [Mutability and hidden temporal coupling](#mutability-and-hidden-temporal-coupling) | mutability and hidden temporal coupling | 25 lines |
| 11 | [Primitive obsession, concretely for fintech](#primitive-obsession-concretely-for-fintech) | primitive obsession, concretely for fintech | 26 lines |
| 12 | [Symmetry and consistency](#symmetry-and-consistency) | symmetry and consistency | 20 lines |
| 13 | [Sources](#sources) | the repos every claim is grounded in | 20 lines |

## Naming reveals intent

No `data`/`info`/`manager`/`helper`/`util`/`temp`/`obj`/`val`/`thing`/`stuff`/
`handle`/`process` as a primary noun. `google/styleguide@gh-pages:pyguide.md`
3.16.1: "descriptiveness should be proportional to the name's scope of
visibility." No surveyed repo enforces a stoplist mechanically —
`airbnb/javascript@master:.../eslint-config-airbnb-base/rules/style.js:108-113`
sets `'id-denylist': 'off'`, the one ESLint rule built for this.

```python
# before
def process(data):
    manager = data.get("items")
    return manager

# after
def summarize_order(order_payload):
    line_items = order_payload.get("items")
    return line_items
```

Booleans should read as predicates (`is_active`, `has_discount`, not `active`,
`discount`). `Enforced by: craft_check.py --only vague-names` (advisory,
stoplist only) + review for predicates/abbreviations/codebase consistency.

## One level of abstraction per function

Mixing "parse the header," "validate the checksum," and "compute i = i + 1"
in one body forces the reader to context-switch line by line. Extract until
each function reads at one altitude.

```python
# before -- version parsing, checksum math and row parsing all in one body
def handle_upload(raw):
    lines = raw.decode().split("\n")
    if lines[0].split(",")[0] != "v2": raise ValueError("bad version")
    if sum(raw) % 256 != raw[-1]: raise ValueError("bad checksum")
    return lines[1:]

# after -- one call per concern, each readable without the others' detail
def handle_upload(raw):
    validate_version(raw)
    validate_checksum(raw)
    return parse_rows(raw)
```
`Enforced by: review` — no mechanical test distinguishes altitude-mixing from
a genuinely short, flat function.

## Function length

`Enforced by: craft_check.py --only function-length` (advisory, default 60).
Range found: `google/styleguide@gh-pages:pyguide.md` 3.18 gives a SOFT ~40-line
prompt ("no hard limit... if a function exceeds about 40 lines, think about
whether it can be broken up"); ESLint's documented `max-lines-per-function`
default is 50, shipped `off` in `airbnb/javascript@master:.../style.js:223-230`;
`rust-lang/rust-clippy@master:clippy_config/src/conf.rs:781` defaults
`too-many-lines-threshold` to 100 and **is** enforced by inheritance in
`zed-industries/zed` (unconfigured).

## Parameter count and the parameter object

`Enforced by: craft_check.py --only param-count` (advisory, default 5).
`eslint-config-airbnb-base@master:rules/style.js:235` documents `max-params`
default 3, shipped `off`; `facebook/react@main:.eslintrc.js` sets
`'max-params': OFF` too. `rust-clippy`'s `too-many-arguments-threshold`
defaults to 7 and **is** enforced in `zed-industries/zed` (unconfigured).
Once a function's parameters always travel and change together, that's a
parameter object, not loose values:

```python
# before
def create_shipment(street, city, state, zip_code, country, weight_kg):
    ...

# after
def create_shipment(address: Address, weight_kg: float):
    ...
```

## No boolean flag parameters that select behaviour

`Enforced by: craft_check.py --only boolean-flag-arg` (advisory; SOURCE:
original — no surveyed lint config flags this). A positional `True`/`False`
at a call site is unreadable without opening the function, and usually means
the function does two different things depending on the flag.

```python
# before
def send_message(text, urgent):
    return push_immediately(text) if urgent else queue_for_batch(text)
send_message("server down", True)   # what does True mean, at the call site?

# after
def send_urgent_message(text): return push_immediately(text)
def queue_message(text): return queue_for_batch(text)
send_urgent_message("server down")
```
A keyword-only flag with a sensible default that does NOT branch behaviour
(`include_tax=True` just toggles one line of output) is fine — the smell is a
flag that routes to different code paths, not any boolean parameter.

## Guard clauses and nesting depth

`Enforced by: craft_check.py --only nesting-depth` (advisory, default 4).
`eslint-config-airbnb-base@master:rules/style.js:202` documents `max-depth`
default 4, shipped `off`, same in `facebook/react@main:.eslintrc.js`;
`rust-clippy`'s `excessive-nesting-threshold` (`conf.rs:572`) defaults to
**0, i.e. disabled**, unless a project opts in — `zed` does not. 4 is the
only live number found; nesting depth is otherwise unenforced by default
everywhere surveyed.

```python
# before
def eligible(user):
    if user is not None:
        if user.active:
            if user.balance > 0:
                return True
    return False

# after
def eligible(user):
    if user is None:
        return False
    if not user.active:
        return False
    return user.balance > 0
```
No flag variables driving control flow either — `should_continue = True` then
threading it through three nested loops is the same smell as nested `if`s,
just spread across more lines.

## Cohesion, coupling, and the Law of Demeter concretely

A module has one reason to change (list the actors who'd ask for a change —
more than one actor is more than one reason). Dependency direction points
inward: a domain/core module never imports an adapter (DB driver, HTTP
client) — adapters import the core. `Enforced by: review`.

**Demeter, concretely:** a method may call methods on (1) itself, (2) its own
fields, (3) its parameters, (4) objects it creates — not on a collaborator's
collaborator. `order.total` is fine; `order.customer.address.city.upper()`
walks four deep — a change to how `Customer` stores addresses now breaks a
caller three types away with no business knowing addresses exist.

```python
# before
def format_shipping_label(order):
    return order.customer.address.city.upper()

# after
def format_shipping_label(order):
    return order.shipping_city().upper()   # Order asks Customer, once
```
`Enforced by: craft_check.py --only demeter-chain` (advisory, default 3 dots
= a 4-link chain like `a.b.c.d(`). SOURCE: original — no surveyed repo
enforces chain depth mechanically. A fluent builder/query-chain
(`query.filter(...).order_by(...)`) looks the same to a regex; that's why
this stays advisory.

## Error handling as design

A typed error taxonomy beats a stringly-typed one: `raise InsufficientFunds
(account_id, shortfall)` carries data a caller can branch on; `raise
Exception("insufficient funds")` does not. Translate errors at the edge (an
HTTP handler maps a domain error to a status code), not scattered through the
core. Never swallow: `except Exception: pass` destroys the only evidence a
bug existed. `Enforced by: craft_check.py --only bare-except` (**blocking** —
empty/log-only catch with no re-raise, same bar as `bloat_check.py`'s
assertionless-test check).

```python
# before
try:
    charge_card(order)
except Exception:
    pass  # silently succeeds from the caller's point of view

# after
try:
    charge_card(order)
except CardDeclined as e:
    raise PaymentFailed(order.id, reason=e.decline_code) from e
```
**Expected failure vs. bug:** a declined card is expected — model it as a
typed return (`Result`/`Either`) or a checked domain exception the caller
must handle. A null a precondition should have prevented is a bug — let it
`throw`/`panic`. `Enforced by: review` (only the swallow pattern is
mechanical).

## Comments: why, not what

Covered by `skills/minimal-diff/SKILL.md` rule 10 (mechanical half: a comment
restating the code). This skill adds the shape argument: a function needing a
comment to explain *what* it does usually needs renaming or splitting, not a
comment. See minimal-diff rather than duplicating its rule here.

## Mutability and hidden temporal coupling

Prefer immutable data at a module's boundary — return a new value instead of
mutating input you don't own. **Hidden temporal coupling**: code that only
works if callers invoke method A before method B, with nothing in the
signature saying so.

```python
# before -- caller must remember connect() before send(), nothing enforces it
class Client:
    def connect(self): self._conn = open_socket()
    def send(self, msg): self._conn.send(msg)   # AttributeError if skipped

# after -- the type itself proves the precondition
class Client:
    def connect(self) -> "ConnectedClient": return ConnectedClient(open_socket())

class ConnectedClient:                            # send() only exists once connected
    def __init__(self, conn): self._conn = conn
    def send(self, msg): self._conn.send(msg)
```
Detection: grep for a class whose methods reference `self.<attr>` set in a
method other than the constructor, then check every public method guards
against that attribute being unset. `Enforced by: convention` (no mechanical
check, and no crisp yes/no review question either).

## Primitive obsession, concretely for fintech

A money amount, an id, a duration are types, not `number`/`string`/`float`.
`Enforced by: craft_check.py --only money-as-float` (advisory; SOURCE:
original — no surveyed linter checks this). Binary floats cannot represent
decimal currency exactly (`0.1 + 0.2 != 0.3` in every language surveyed);
storing money as `float` is a latent rounding-error bug, not a style
preference.

```python
# before -- 19.99 is not exactly representable in binary float
def charge(amount: float, currency: str): ...
charge(19.99, "USD")

# after -- integers add/subtract exactly
@dataclass(frozen=True)
class Money:
    minor_units: int   # cents
    currency: str
def charge(amount: Money): ...
charge(Money(1999, "USD"))
```
Same argument for an id (`user_id: str` accepts *any* string, including a
product id passed by mistake — a `UserId` newtype does not) and a duration
(`timeout: int` — seconds or ms? a `timedelta`/`Duration` type removes the
ambiguity).

## Symmetry and consistency

Parallel operations should look parallel. If `create`/`read`/`update` all
take `(ctx, id)` and `delete` alone takes `(id, ctx)`, that inversion is a
smell regardless of which order is "correct" — a reader who learned the
pattern from the first three will misuse the fourth.

```python
# before
def create_user(ctx, payload): ...
def update_user(ctx, user_id, payload): ...
def delete_user(user_id, ctx): ...   # argument order flipped, no reason given

# after
def create_user(ctx, payload): ...
def update_user(ctx, user_id, payload): ...
def delete_user(ctx, user_id): ...
```
`Enforced by: review` — SOURCE: original; this is a codebase-consistency
argument, not something any surveyed style guide numbers.

## Sources

- `google/styleguide@gh-pages:pyguide.md` §3.16 (Naming), §3.18 (Function length).
- `airbnb/javascript@master:packages/eslint-config-airbnb-base/rules/style.js`
  (max-depth, max-len, max-lines, max-lines-per-function, max-params,
  id-denylist, id-length — documented, all shipped `off`) and
  `rules/best-practices.js` (`complexity`, documented `off`).
- `facebook/react@main:.eslintrc.js` (`max-depth`, `max-params`,
  `max-statements`, `complexity` all explicitly `OFF`).
- `rust-lang/rust-clippy@master:clippy_config/src/conf.rs` (defaults:
  `too_many_arguments_threshold` 7, `too_many_lines_threshold` 100,
  `cognitive_complexity_threshold` 25, `excessive_nesting_threshold` 0/off);
  `zed-industries/zed@main:clippy.toml` overrides none of it.
- `golangci/golangci-lint@main:.golangci.reference.yml` (`gocyclo` default
  `min-complexity: 30`); `grafana/grafana@main:.golangci.yml` enables it
  unconfigured (inherits 30); `prometheus/prometheus@main:.golangci.yml`
  does not enable `gocyclo`/`gocognit` at all.
- Parameter-object/guard-clause/error-taxonomy vocabulary: `SOURCE:
  original` (Fowler's refactoring-catalog terms, applied to this plugin's
  own researched thresholds).

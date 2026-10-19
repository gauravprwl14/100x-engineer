# Engineer standards card

Read while writing, not after. Each line is a rule a reviewer will check; the skill named in
brackets holds the full contract. Repo precedent beats this card where they differ.

| # | rule | before → after | source |
|---|---|---|---|
| 1 | Functions are verb phrases naming the effect; variables are nouns for what they hold | `def user(id)` → `def load_user(user_id)` | `code-craft` rule 1 |
| 2 | Booleans are predicates | `active`, `discount` → `is_active`, `has_discount` | `code-craft` rule 1 |
| 3 | Name length grows with scope: `i` in a 3-line loop, `pending_invoice_ids` at module level | `x = fetch()` (module scope) → `overdue_invoices = fetch_overdue()` | `google/styleguide@gh-pages:pyguide.md` §3.16 |
| 4 | No abbreviation the repo does not already use | `usr_cfg_mgr` → `user_settings` | `google/styleguide@gh-pages:pyguide.md` §3.16; `code-craft` rule 1 |
| 5 | No hidden side effects: a `get_*`/`is_*` never writes, sends or caches | `get_cart()` that creates a cart → `get_or_create_cart()` | `code-craft` rule 11 |
| 6 | Reuse first: `grep -rn` or `100x repo_map <repo> --symbol <Name>` for an existing helper before writing one | a second `format_money()` → import the one in `billing/format.py` | SOURCE: original (private-repo PR survey: 105 human PRs, ~180 review comments) |
| 7 | Rule of three: copy once, extract on the third caller, never for one | `BaseExporter` with one subclass → one plain function | `minimal-diff` rule 3 |
| 8 | No magic numbers; no hard-coded URLs, timeouts or feature flags | `sleep(30)`, `"https://api.x.com"` → `RETRY_DELAY_S`, `settings.payments_api_url` | SOURCE: original (private-repo PR survey: 105 human PRs, ~180 review comments) |
| 9 | Config reads follow the repo's env-var naming (prefix, case, file) | `os.getenv("apiKey")` beside `APP_*` vars → `os.getenv("APP_PAYMENTS_API_KEY")` | SOURCE: original (private-repo PR survey: 105 human PRs, ~180 review comments) |
| 10 | Guard clauses over nesting | `if ok: if user: ...` → `if not ok: return` first | `code-craft` rule 6 |
| 11 | Errors are typed and never swallowed | `except Exception: pass` → `except PaymentDeclined as e: raise CheckoutFailed(...) from e` | `code-craft` rule 8 |
| 12 | Null-safety: handle the absent case where it enters, not three calls later | `user.address.city` → `if user.address is None: return MISSING_ADDRESS` | SOURCE: original |
| 13 | Immutability at boundaries: return copies or frozen values; never mutate an argument | `def add_tax(order): order.total *= 1.1` → `return replace(order, total=...)` | `code-craft` rule 11 |
| 14 | Money, ids and durations are types, not bare numbers or strings | `amount: float` → `amount: Money` | `code-craft` rule 12 |
| 15 | Comments say why in 1–2 lines and link the issue; format per `docs/WRITING.md` | `# loop over users` → `# Batched: the API rejects >100 ids (#412)` | `minimal-diff` rules 7, 10 |
| 16 | Smallest diff: no unrequested file, class, helper, error type or constant; no unrelated change or reformat | a new `utils/errors.py` for one raise → raise the existing error | `minimal-diff` rules 1, 3, 8 |
| 17 | Every changed behaviour gets a boundary test and a negative or authz test, each written to fail without the fix | only `test_create_ok` → plus `test_create_rejects_101_items`, `test_other_tenant_gets_404` | `test-design` rule 1; `minimal-diff` rule 5 |

Before you report, check these on your own diff:

```bash
100x craft_check --base <ref>        # names, length, nesting, params (py, js/ts)
100x bloat_check --base <ref>        # new files, dead code, unrequested docs
100x test_design_check --base <ref>  # tests that cannot fail
```

A finding you keep on purpose goes in the report's `decisions` with the reason.

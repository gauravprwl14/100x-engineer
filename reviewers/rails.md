# Rails reviewer

Contract: every rule below is either a runnable check or a precise review question a
human can answer yes/no. No adjectives. No "follow best practices".

## Contents

| # | section | what it answers | size |
|---|---------|-----------------|------|
| 1 | [Applies when](#applies-when) | the file/dependency signals that put this reviewer in scope | 4 lines |
| 2 | [Blocking rules](#blocking-rules) | the rules that must hold (strong params, model validations, reversible migrations, commit-safe callbacks, SQL, CSRF, log filtering), each with how it is checked | 11 lines |
| 3 | [Common AI failure modes in this stack](#common-ai-failure-modes-in-this-stack) | **start here**: what LLMs get wrong in Rails, with a detection method for each | 13 lines |
| 4 | [Language pitfalls (Ruby)](#language-pitfalls-ruby) | the "critical language" bugs: identity vs equality, shared mutable defaults, `&.`, frozen strings, Float money, truthiness, time zones | 11 lines |
| 5 | [Security defaults](#security-defaults) | which Rails defaults protect you, and the one-line change that silently turns each off | 10 lines |
| 6 | [Performance](#performance) | `includes` vs `preload` vs `eager_load`, N+1 detection, batching, counting | 10 lines |
| 7 | [Test conventions](#test-conventions) | request specs over controller specs, the cops that catch tests that cannot fail, when a query-count test earns its place | 9 lines |
| 8 | [Edge cases routinely missed](#edge-cases-routinely-missed) | the scenarios Rails code forgets, and the test that catches each | 10 lines |
| 9 | [Approach selection](#approach-selection) | the recurring choices, each with a DEFAULT so you are not asked | 8 lines |
| 10 | [Verify](#verify) | the runnable commands, diff-scoped where possible | 28 lines |
| 11 | [Sources](#sources) | where every claim above comes from | 20 lines |

## Applies when
- `Gemfile` declares `gem "rails"`, or `Gemfile.lock` lists `rails (`.
- `config/application.rb` defines a class inheriting `Rails::Application`.
- The diff touches `app/**/*.rb`, `db/migrate/*.rb`, `config/routes.rb`, `spec/**` or `test/**`.

## Blocking rules
| # | rule | how it is checked | failure it prevents |
|---|------|-------------------|---------------------|
| 1 | Every action that writes a model takes its attributes through strong params: `params.expect(user: [:name])` (Rails 8) or `params.require(:user).permit(:name)`. Never `permit!`, `to_unsafe_h`, or `params[:user]` passed straight to `new`/`create`/`update`/`assign_attributes` | `grep -rnE "permit!\|to_unsafe_h\|\.(new\|create\|update\|assign_attributes)\(params\[" app/controllers` must return empty | mass assignment: a client sets `role`, `admin` or `account_id` by adding a field (`rails/rails@main:guides/source/action_controller_overview.md`, "Strong Parameters") |
| 2 | An invariant that must hold on every write path is a model validation, and uniqueness or not-null is also a database constraint (unique index, `null: false`) | `bundle exec rubocop --only Rails/UniqueValidationWithoutIndex` (enabled by default); review: "is this check in the controller only, so a job, console or second endpoint bypasses it?" | invariant enforced in one controller and skipped everywhere else; `validates :uniqueness` racing two concurrent inserts |
| 3 | A schema migration is reversible and changes schema only. `change` uses reversible methods, or the migration defines `up`/`down` or a `reversible` block. Data backfills go in a separate task | `bundle exec rubocop --only Rails/ReversibleMigration,Rails/BulkChangeTable db/migrate`; `grep -nE "update_all\|find_each\|\.save\b\|\.update\(" db/migrate/<new>.rb` must return empty; `bin/rails db:migrate db:rollback db:migrate` exits 0 | a deploy that cannot be rolled back; a table locked for the length of the backfill, because each migration runs in one transaction (`ankane/strong_migrations@master:README.md`, "Backfilling data"; `rails/rails@main:guides/source/active_record_migrations.md`, "Data Migrations") |
| 4 | A side effect outside the database (mail, `perform_later`, HTTP call, cache write, file delete) runs in `after_commit` / `after_create_commit`, never `after_save` / `before_*` | `grep -rnE "after_(save\|create\|update\|destroy)\b" app/models` then read each hit; review: "if the transaction rolls back after this line, has anything external already happened?" | mail sent for a rolled-back record; a job that runs before its row is visible and reads `nil` (`rails/rails@main:guides/source/active_record_callbacks.md`, "`after_commit` and `after_rollback`") |
| 5 | No string-built SQL: `where("x = #{...}")`, `order(params[:sort])`, `find_by_sql` with interpolation | `bundle exec brakeman -q --no-pager` exits 0 (it exits non-zero on any warning by default); `grep -rnE "(where\|order\|find_by_sql\|pluck)\(\"[^\"]*#\{" app` must return empty | SQL injection (`rails/rails@main:guides/source/security.md`, "SQL Injection") |
| 6 | Changed Ruby files pass `rubocop` with `rubocop-rails` (and `rubocop-rspec` when RSpec is used); every new `# rubocop:disable` names a reason | `bundle exec rubocop --force-exclusion $(git diff --name-only --diff-filter=ACM origin/main... -- '*.rb')`; `git diff origin/main... \| grep '^+.*rubocop:disable' \| grep -v -- ' -- '` must return empty | idiom drift the cops already encode (`rubocop/rubocop-rails@master:config/default.yml`) |
| 7 | Cookie-session controllers keep CSRF protection: no `skip_forgery_protection`, no `protect_from_forgery with: :null_session` outside a token-authenticated API base controller | `grep -rnE "skip_forgery_protection\|null_session\|verify_authenticity_token" app/controllers` and justify each hit | cross-site request forgery; new apps have `default_protect_from_forgery` on (`rails/rails@main:guides/source/security.md`, "CSRF Countermeasures") |
| 8 | New secret-bearing params (token, otp, ssn, card) are in `config.filter_parameters` | `grep -n "filter_parameters" config/initializers/filter_parameter_logging.rb` lists them | credentials in plaintext logs (`rails/rails@main:guides/source/security.md`, "Logging") |

## Common AI failure modes in this stack
| # | what the model does | why it looks right | detection | correct move |
|---|---------------------|--------------------|-----------|--------------|
| 1 | Adds `.includes(:assoc)` to every query "to fix N+1", including queries that never read the association, or that then filter on it so Rails switches to one big `LEFT OUTER JOIN` | the guide shows `includes` as the N+1 fix, and it does remove the extra queries | Bullet reports "unused eager loading"; review: "is `assoc` read in the view or serializer? does a `where`/`order`/`references` name its table?" | `preload` when you only read the association (one extra query per association, no join); `eager_load` when you filter or sort on its columns; bare `includes` only when either is fine (`rails/rails@main:guides/source/active_record_querying.md`, "Eager Loading Associations"; `SOURCE: original (private-repo PR survey: 105 human PRs, ~180 review comments)`, 10 on this theme) |
| 2 | `record = Model.find_by(id: params[:id])` then `record.name`, so a missing row becomes `NoMethodError` and a 500 | `find_by` "avoids an exception" | grep `find_by(` hits whose result is dereferenced with no `nil` branch | `find` in controllers (raises `RecordNotFound`, which Rails renders as 404); `find_by` plus an explicit `nil` branch where absence is normal (`rails/rails@main:guides/source/active_record_querying.md`, "`find`", "`find_by`") |
| 3 | `user&.account&.plan&.limit` so a missing account yields `nil`, which the caller treats as "no limit" | no crash, tests on full fixtures pass | `bundle exec rubocop --only Lint/SafeNavigationChain,Style/SafeNavigationChainLength`; review: "is `nil` a valid state here?" | decide whether nil is legal; if not, enforce presence (validation, `find`, `!`) and fail loudly |
| 4 | Uses `update_column`, `update_all`, `insert_all` or `touch` to "avoid callbacks", skipping validations | faster and no callback surprises | `Rails/SkipsModelValidations` (enabled by default) | `update!`; keep the skip only for an intended bulk path, with a comment saying why |
| 5 | Calls `save`/`update` in a job or service and ignores the `false` it returns on a validation failure | it reads like a statement, not a query | `Rails/SaveBang` exists but is **disabled** by default: enable it, or grep `^\s+\w+\.(save\|update)\(` outside controllers | bang methods (`save!`, `update!`) outside controllers, or branch on the return value |
| 6 | Writes `type: :controller` specs (`assigns`, `assert_template`) for a new endpoint | rspec-rails still supports them | `grep -rln "type: :controller" spec/` in the diff | request spec: route, status, body and database change (`rspec/rspec-rails@main:README.md`, "Request specs") |
| 7 | Calls `update`/`save` on `self` inside a callback | it keeps related fields in sync | `grep -nA5 -E "before_(save\|update)\|after_(save\|update)" app/models` with `update(` or `save` in the body | assign attributes directly (`self.x = ...`) in `before_*`; the guide warns against side-effect calls in callbacks (`rails/rails@main:guides/source/active_record_callbacks.md`) |
| 8 | Adds `has_many` with no `dependent:` | the association works in every read | `Rails/HasManyOrHasOneDependent` (enabled by default) | choose `:destroy`, `:delete_all`, `:nullify` or `:restrict_with_error` explicitly |
| 9 | Adds a service object, concern or module for one call site | "thin controllers, fat models" read as "more layers" | `git diff --stat` shows new `app/services/*` files used once | inline it in the model or controller until a second caller exists (`SOURCE: original (private-repo PR survey: 105 human PRs, ~180 review comments)`, 37 on this theme) |
| 10 | Adds a query-count test to code with no N+1 history | it "locks in" performance | `grep -rn "assert_queries_count\|make_database_queries" spec test` in the diff | keep a query-count test only as the regression test for a fixed N+1 on a list path (`SOURCE: original (private-repo PR survey: 105 human PRs, ~180 review comments)`, 23 on this theme) |

## Language pitfalls (Ruby)
| # | pitfall | what goes wrong | detection | correct move |
|---|---------|-----------------|-----------|--------------|
| 1 | `==` vs `equal?` vs `eql?` | `equal?` is identity and must never be overridden; `eql?` is what Hash keys use, so `1 == 1.0` is true but `1.eql?(1.0)` is false; Active Record `==` compares class and id, so two unsaved records are never equal | review every `equal?`/`eql?` in the diff; `Lint/IdentityComparison` | `==` for values; `equal?` only for identity (`ruby/ruby@master:object.c`, `BasicObject#equal?` docs; `rails/rails@main:activerecord/lib/active_record/core.rb`, `#==`) |
| 2 | shared mutable defaults | unlike Python, a default argument is re-evaluated per call, so `def f(a = [])` is safe (run locally: `f; f` returns `[1]`); the real traps are `Hash.new([])`, which shares one array across every key, and mutable constants | `Lint/SharedMutableDefault` (pending: enable it), `Style/MutableConstant` (enabled) | `Hash.new { \|h, k\| h[k] = [] }`; `.freeze` constants (`rubocop/rubocop@master:config/default.yml`) |
| 3 | `&.` hides nil | `a&.b.c` raises on nil anyway; long `&.` chains turn a bug into a blank value | `Lint/SafeNavigationChain` (enabled), `Style/SafeNavigationChainLength` (pending) | see failure mode 3 |
| 4 | frozen string literals | with `# frozen_string_literal: true`, `"a" << "b"` raises `FrozenError`; Ruby 3.4 warns when a literal in a file without the comment is mutated | `Style/FrozenStringLiteralComment` (enabled); run tests with `RUBYOPT=-W:deprecated` | add the comment to new files; build strings with `+""` or `String.new` (`ruby/ruby@v3_4_0:NEWS.md`, Feature #20205) |
| 5 | `Float` for money | `0.1 + 0.2 == 0.3` is false | `Lint/FloatComparison` (enabled); `grep -rnE ":(price\|amount\|total)\w*, :float" db/migrate` | a `decimal` column with `precision:`/`scale:`, `BigDecimal` in Ruby, never `.to_f` on money (`rails/rails@main:guides/source/active_record_migrations.md`, `add_column :products, :price, :decimal, precision: 8, scale: 2`) |
| 6 | truthiness | only `nil` and `false` are falsy: `0`, `""`, `[]` and `"false"` from a form are truthy | review conditionals on raw `params` values | cast with `ActiveModel::Type::Boolean.new.cast`, compare explicitly (`ruby/ruby@master:doc/syntax/control_expressions.rdoc`) |
| 7 | rescuing too much | `rescue Exception` swallows `Interrupt` and `SignalException`; an empty `rescue` hides the bug | `Lint/RescueException`, `Lint/SuppressedException` (both enabled) | `rescue SpecificError => e`, then handle or re-raise |
| 8 | time zones | `Time.now` and `Date.today` ignore `config.time_zone` | `Rails/TimeZone`, `Rails/Date` (both enabled) | `Time.current`, `Date.current`, `Time.zone.parse` |

## Security defaults
| default | what turns it off silently | check |
|---------|----------------------------|-------|
| strong params reject unpermitted keys | `permit!`, `to_unsafe_h` | blocking rule 1 |
| `params.expect` returns 400 on a wrong shape | `params[:user][:name]` dug out by hand, so an array or a missing key becomes a 500 | `grep -rn "params\[:[a-z_]*\]\[" app/controllers` (`rails/rails@main:guides/source/action_controller_overview.md`) |
| CSRF token required for cookie sessions | `skip_forgery_protection` | blocking rule 7 |
| ERB escapes output | `html_safe`, `raw`, `<%==` | `Rails/OutputSafety` (enabled) |
| parameterised queries | string interpolation in `where`/`order` | blocking rule 5, `brakeman` |
| object-level access | `Post.find(params[:id])` where `current_user.posts.find(params[:id])` was needed | review: "is every record loaded by id scoped through the current user or tenant?" (`SOURCE: original (private-repo PR survey: 105 human PRs, ~180 review comments)`, 6 on this theme) |
| open redirects | `redirect_to params[:return_to]` | `brakeman` redirect check (`rails/rails@main:guides/source/security.md`, "Redirection") |

## Performance
| # | issue | detection | correct move |
|---|-------|-----------|--------------|
| 1 | N+1: one query per row when a view or serializer reads an association | Bullet with `Bullet.raise = true` in the test environment fails the spec; `strict_loading` raises on lazy loads | eager load; set `config.active_record.strict_loading_by_default = true` for new apps (`flyerhzm/bullet@main:README.md`; `rails/rails@main:guides/source/active_record_querying.md`, "`strict_loading`") |
| 2 | `includes` vs `preload` vs `eager_load` | review the query log: `preload` makes one query per association; `eager_load` makes one `LEFT OUTER JOIN`; `includes` picks `preload` unless the association is referenced in conditions | see failure mode 1 and Approach selection |
| 3 | `Model.all.each` over a large table loads it all into memory | `Rails/FindEach` (enabled) | `find_each` / `in_batches` |
| 4 | `.count` on a relation that is already loaded issues another `COUNT(*)` | review: is the relation iterated in the same request? | `.size` uses the loaded records when present (`rails/rails@main:activerecord/lib/active_record/relation.rb`, `#size`) |
| 5 | `map(&:id)` over records loaded only for one column | `Rails/Pluck` (pending: enable it) | `pluck(:id)`, or `ids` |
| 6 | a new `where`/`order` column, or a foreign key, with no index; or an index added without `algorithm: :concurrently` on a large Postgres table | `EXPLAIN` the new query; strong_migrations flags non-concurrent index creation | add the index with `disable_ddl_transaction!` + `algorithm: :concurrently` (`ankane/strong_migrations@master:README.md`, "Adding an index non-concurrently") |
| 7 | counting children per row (`post.comments.count` in a list) | Bullet's counter-cache suggestion | `counter_cache: true` or a grouped count |

## Test conventions
| # | convention | check |
|---|------------|-------|
| 1 | Endpoints get request specs; both the Rails and RSpec teams discourage controller tests since RSpec 3.5. UI journeys get system specs | `grep -rln "type: :controller" spec/` in the diff is empty (`rspec/rspec-rails@main:README.md`) |
| 2 | Every example asserts something | `RSpec/NoExpectationExample` (enabled) (`rubocop/rubocop-rspec@master:config/default.yml`) |
| 3 | Doubles are verified, so stubbing a method that no longer exists fails | `RSpec/VerifiedDoubles`, `RSpec/AnyInstance` (both enabled): use `instance_double`, inject the collaborator |
| 4 | Each validation has a failing-input test (422 and the error key), not only the happy path | review: for every new `validates`, is there an invalid-input example? |
| 5 | Factories build in memory unless the test needs the row | `build` / `build_stubbed` over `create` (`thoughtbot/factory_bot@main:GETTING_STARTED.md`) |
| 6 | Minitest apps use `assert_queries_count` / `assert_no_queries` only as an N+1 regression test | `rails/rails@main:guides/source/testing.md` lists both; see failure mode 10 |

## Edge cases routinely missed
| # | edge case | why it is missed | test that would catch it |
|---|-----------|------------------|--------------------------|
| 1 | id for a record that does not exist, or belongs to another user | fixtures always contain the record | request spec: unknown id returns 404; another user's id returns 404, not 200 |
| 2 | a job whose record was deleted between enqueue and perform | the record exists in every local run | job spec with the record destroyed; `discard_on ActiveJob::DeserializationError::RecordNotFound` (`rails/rails@main:guides/source/active_job_basics.md`) |
| 3 | two concurrent creates racing `validates :uniqueness` | sequential tests never race | unique index plus a rescue of `ActiveRecord::RecordNotUnique`, or `create_or_find_by` (`rails/rails@main:guides/source/active_record_querying.md`, "`create_or_find_by`") |
| 4 | blank string from a form vs `nil` | factories send `nil`, browsers send `""` | spec posting `""` for each optional field |
| 5 | an array or hash where a scalar param was expected | nobody sends `user[name][]=x` by hand | request spec with a malformed param expects 400, not 500 |
| 6 | a date at a time-zone boundary | CI runs in UTC | spec under `travel_to` near midnight in `config.time_zone` |
| 7 | an index endpoint with no page cap | the dev database has 20 rows | spec requesting `per_page=100000` expects a cap |

## Approach selection
| decision | options | deciding factor | default recommendation |
|----------|---------|-----------------|------------------------|
| eager-loading method | `includes` / `preload` / `eager_load` | do you filter or sort on the association? | **`preload`**; `eager_load` only when conditions reference the association |
| where domain logic lives | model / service object / concern | does the operation span several models or an external call? | **model methods and scopes**; a service object once one operation coordinates several models or an external system |
| data change with a schema change | in the migration / separate task | table size and rollback | **separate task** (rake task or the maintenance_tasks gem the migrations guide names), run after the schema deploy |
| N+1 guard | Bullet / `strict_loading` | new code or legacy | **`strict_loading`** for new models; Bullet in dev and test for legacy code |
| test framework | RSpec / Minitest | what the repo already uses | **follow the repo**; Minitest is the Rails default for new apps (`rails/rails@main:guides/source/testing.md`) |

## Verify
```bash
CHANGED=$(git diff --name-only --diff-filter=ACM origin/main... -- '*.rb')

# lint, diff-scoped; rubocop-rails and rubocop-rspec must be in .rubocop.yml `plugins:`
bundle exec rubocop --force-exclusion $CHANGED

# security scan; exits non-zero on any warning unless --no-exit-on-warn is passed
bundle exec brakeman -q --no-pager

# migrations really reverse, and schema.rb is committed
bin/rails db:migrate && bin/rails db:rollback && bin/rails db:migrate
git diff --exit-code db/schema.rb db/structure.sql

# tests: request specs for changed endpoints (or bin/rails test for Minitest apps)
bundle exec rspec spec/requests spec/models

# grep checks no tool covers
grep -rnE "permit!|to_unsafe_h|\.(new|create|update|assign_attributes)\(params\[" app/controllers && echo "FAIL: mass assignment (rule 1)"
grep -rnE "(where|order|find_by_sql)\(\"[^\"]*#\{" app && echo "FAIL: string-built SQL (rule 5)"
grep -rln "type: :controller" spec/ && echo "WARN: controller specs; prefer request specs"
for f in $(git diff --name-only --diff-filter=A origin/main... -- 'db/migrate/*.rb'); do
  grep -nE "update_all|find_each|\.save\b" "$f" && echo "FAIL: data change in schema migration $f (rule 3)"
done
```

Expected runtime: diff-scoped rubocop takes seconds; brakeman 10–60s; the migrate/rollback
round trip depends on schema size.

## Sources
- `rails/rails@main:guides/source/active_record_querying.md`: "`find`" (raises `RecordNotFound`), "`find_by`" (returns `nil`), "N + 1 Queries Problem", "`includes`", "`preload`", "`eager_load`", "`strict_loading`", "`find_each`", "`create_or_find_by`".
- `rails/rails@main:guides/source/action_controller_overview.md`: strong parameters, `params.expect`, `ParameterMissing` rendered as 400.
- `rails/rails@main:guides/source/active_record_callbacks.md`: the warning against `update`/`save` inside callbacks; "`after_commit` and `after_rollback`" for external systems.
- `rails/rails@main:guides/source/active_record_migrations.md`: reversible migrations, `reversible`, "Data Migrations" (not advised in migrations; maintenance_tasks), `decimal` with `precision`/`scale`.
- `rails/rails@main:guides/source/active_record_validations.md`: model validations.
- `rails/rails@main:guides/source/security.md`: "CSRF Countermeasures", "Redirection", "Logging" (`filter_parameters`), "SQL Injection" (`sanitize_sql`).
- `rails/rails@main:guides/source/testing.md`: `assert_queries_count`, `assert_no_queries`.
- `rails/rails@main:guides/source/active_job_basics.md`: `discard_on ActiveJob::DeserializationError::RecordNotFound`.
- `rails/rails@main:activerecord/lib/active_record/core.rb` (`#==`), `activerecord/lib/active_record/relation.rb` (`#size`).
- `rspec/rspec-rails@main:README.md`: "Request specs", and that as of RSpec 3.5 the Rails and RSpec teams discourage controller tests.
- `rubocop/rubocop-rails@master:config/default.yml`: enabled-by-default state of every `Rails/*` cop named above, read on 2026-10-16 (`SaveBang` false; `Pluck`, `StrongParametersExpect` pending).
- `rubocop/rubocop@master:config/default.yml`: `Lint/SharedMutableDefault` (pending), `Style/MutableConstant`, `Lint/SafeNavigationChain`, `Lint/FloatComparison`, `Style/FrozenStringLiteralComment`, `Lint/RescueException`, `Lint/SuppressedException`, `Lint/IdentityComparison`.
- `rubocop/rubocop-rspec@master:config/default.yml`: `RSpec/NoExpectationExample`, `RSpec/VerifiedDoubles`, `RSpec/AnyInstance`.
- `ruby/ruby@master:object.c` (`equal?` docs), `ruby/ruby@master:doc/syntax/control_expressions.rdoc` (only `nil` and `false` are false), `ruby/ruby@v3_4_0:NEWS.md` (Feature #20205).
- `ankane/strong_migrations@master:README.md`: "Backfilling data", "Adding an index non-concurrently".
- `presidentbeef/brakeman@main:README.md`: non-zero exit on warnings by default.
- `flyerhzm/bullet@main:README.md`: N+1, unused eager loading, counter cache, `Bullet.raise`.
- `thoughtbot/factory_bot@main:GETTING_STARTED.md`: build strategies.
- `SOURCE: original`: per-call default-argument evaluation and the `Hash.new([])` shared default were confirmed by running Ruby locally; the "is nil a valid state" and tenant-scoping review questions.
- `SOURCE: original (private-repo PR survey: 105 human PRs, ~180 review comments)`: 10 eager-loading and N+1 review comments; 37 unneeded layers; 23 tests that cannot fail or are redundant, including query-count tests reviewers asked to delete; 6 tenant and authz misses.

# Django + FastAPI reviewer

Contract: every rule below is either a runnable check or a precise review question a
human can answer yes/no. No adjectives. No "follow best practices".

## Applies when
- `pyproject.toml`, `requirements*.txt` or `Pipfile` lists `django` or `fastapi`.
- Django: `manage.py` plus a `settings.py` (or `settings/`) package. FastAPI: a module creating `FastAPI(`.
- The diff touches `models.py`, `views.py`, `serializers.py`, `forms.py`, `migrations/`, or a router module.

## Blocking rules
| # | rule | how it is checked | failure it prevents |
|---|------|-------------------|---------------------|
| 1 | `ModelForm` and DRF `ModelSerializer` list `fields` explicitly; never `fields = "__all__"` or `exclude` on a model that has, or may gain, a privileged column | `grep -rnE "fields\s*=\s*['\"]__all__['\"]\|exclude\s*=" --include=*.py .` must return empty, or each hit is justified | mass assignment when a new model field appears; Django's docs cite this as a real exploit class (`django/django@main:docs/topics/forms/modelforms.txt`, "Selecting the fields to use") |
| 2 | Every FastAPI route that returns a model declares `response_model` (or a return type) that excludes secrets and internal columns | review: "does any route return an ORM object or a model holding `password`/`hashed_*`/`token`?" | leaking fields: FastAPI filters output only to the declared response model (`fastapi/fastapi@master:docs/en/docs/tutorial/response-model.md`) |
| 3 | Request models reject unknown fields where a client could set a privileged one: `model_config = ConfigDict(extra="forbid")` | `grep -rn "extra=\"forbid\"\|extra='forbid'" app/` on request schemas; review each schema that maps to a writable model | Pydantic's default `extra="ignore"` silently drops typos and unexpected fields, so a client error passes as success (`pydantic/pydantic@main:docs/concepts/models.md`, "Extra data") |
| 4 | No blocking call inside `async def` (`requests`, `time.sleep`, sync file IO, the sync Django ORM) | `ruff check --select ASYNC .` (ASYNC210 blocking HTTP, ASYNC230 blocking `open`, ASYNC251 `time.sleep`); Django raises `SynchronousOnlyOperation` for sync ORM in async context | one slow call stalls every request on the worker; FastAPI runs plain `def` handlers in a threadpool, but `async def` handlers run on the loop (`fastapi/fastapi@master:docs/en/docs/async.md`) |
| 5 | CSRF stays on for session-cookie views: no new `@csrf_exempt` on a view that uses session auth | `grep -rn "csrf_exempt" --include=*.py .` and justify each hit | cross-site request forgery (`django/django@main:docs/ref/csrf.txt`); DRF enforces CSRF only for authenticated session requests (`encode/django-rest-framework@main:docs/api-guide/authentication.md`) |
| 6 | Secrets are read from the environment, never literals in `settings.py`; `DEBUG` is off in production | `python manage.py check --deploy --fail-level WARNING`; `ruff check --select S105,S106 .` (hard-coded passwords); FastAPI: `pydantic-settings` `BaseSettings` with `SecretStr` | a committed `SECRET_KEY` or a debug page in production (`django/django@main:docs/howto/deployment/checklist.txt`; `pydantic/pydantic-settings@main:docs/index.md`) |
| 7 | Migrations are committed and in sync with models | `python manage.py makemigrations --check --dry-run` exits 0 | a model change that deploys with no migration |
| 8 | Multi-row writes that must succeed together are wrapped in `transaction.atomic()` (Django) or one session transaction (SQLAlchemy) | review: ">1 write in this function: is there one transaction around them?" | half-applied writes after a failure (`django/django@main:docs/topics/db/transactions.txt`) |

## Common AI failure modes in this stack
| # | what the model does | why it looks right | detection | correct move |
|---|---------------------|--------------------|-----------|--------------|
| 1 | Loops over a queryset and reads `obj.author.name` or `obj.tags.all()` per row; or nests a DRF serializer with no prefetch | correct output on a 3-row fixture | `django_assert_num_queries` around the list view; django-silk or the debug toolbar in dev | `select_related` for forward FK/one-to-one (one join); `prefetch_related` for many-to-many and reverse FK (one extra query) (`django/django@main:docs/ref/models/querysets.txt`) |
| 2 | Declares a FastAPI handler `async def` and calls `requests.get` or a sync DB driver inside it | `async def` "is faster" | `ruff check --select ASYNC` | plain `def` for blocking work (FastAPI runs it in a threadpool), or an async client (`httpx.AsyncClient`, async driver) |
| 3 | Calls the sync Django ORM from an async view | the same code works in a sync view | `SynchronousOnlyOperation` at runtime; review every `async def` view | the async ORM methods (`aget`, `acreate`, `async for`) or `sync_to_async` (`django/django@main:docs/topics/async.txt`; `django/django@main:docs/topics/db/queries.txt`, "Asynchronous queries") |
| 4 | Returns the ORM object straight from a FastAPI route with no `response_model` | the JSON looks right | review: route returns an ORM row; no `response_model` or return annotation | a separate output schema without secret fields (blocking rule 2) |
| 5 | Validates request data in the view with `if` chains instead of the Pydantic model or form | it handles the case the prompt named | `grep -nE "if not (data\|request\.data)\.get\(" ` in views | constraints on the schema (`Field(gt=0)`, `EmailStr`, validators), so the 422 is automatic and documented |
| 6 | Opens a DB session per request by hand and forgets to close it on error | the happy path closes it | review: session created outside a `Depends` with `yield` | a dependency with `yield` and `finally: close()` (`fastapi/fastapi@master:docs/en/docs/tutorial/dependencies/dependencies-with-yield.md`) |
| 7 | Adds `CORSMiddleware(allow_origins=["*"], allow_credentials=True)` "to fix CORS" | the browser error goes away in dev | `grep -rn "allow_origins=\[\"\*\"\]" .` | an explicit origin list; FastAPI's docs note the wildcard excludes credentialed requests (`fastapi/fastapi@master:docs/en/docs/tutorial/cors.md`, "Wildcards") |
| 8 | Writes raw SQL with f-strings in `.raw()`/`.extra()`/`cursor.execute` | ORM feels limiting for one query | `ruff check --select S608,S611 .` | query parameters (`params=[...]`), never string formatting |

## Language pitfalls (Python)
| # | pitfall | what goes wrong | detection | correct move |
|---|---------|-----------------|-----------|--------------|
| 1 | mutable default argument | `def f(x=[])`: the default is evaluated once, so every call shares the same list | `ruff check --select B006` | `x: list \| None = None`, then `x = [] if x is None else x` (`python/cpython@main:Doc/tutorial/controlflow.rst`, "Important warning: The default value is evaluated only once") |
| 2 | late-binding closures in loops | `[lambda: i for i in range(3)]` all return 2 | `ruff check --select B023` | bind the value: `lambda i=i: i`, or `functools.partial` |
| 3 | `is` on literals | `x is 1` or `s is "a"` depends on interning | `ruff check --select F632` | `==` for values; `is` only for `None` and sentinels |
| 4 | broad `except` | bare `except:` catches `KeyboardInterrupt`; `except Exception: pass` hides the bug | `ruff check --select E722,BLE001,S110` | catch the specific exception, then handle or re-raise |
| 5 | naive datetimes | `datetime.now()` has no tz; comparing it with an aware value raises, and storing it shifts by the server zone | `ruff check --select DTZ` (DTZ005 `now()` without tz) | `django.utils.timezone.now()` with `USE_TZ = True`; `datetime.now(tz=UTC)` in FastAPI |
| 6 | Float money | `0.1 + 0.2 != 0.3` | `grep -rnE "(price\|amount\|total)\w*\s*=\s*models\.FloatField" .` | `DecimalField(max_digits=..., decimal_places=...)`, `Decimal` in Pydantic (`django/django@main:docs/ref/models/fields.txt`, `DecimalField`) |
| 7 | outbound HTTP with no timeout | `requests.get(url)` waits forever | `ruff check --select S113` | pass `timeout=`; set it on the shared client |

## Security defaults
| default | what turns it off silently | check |
|---------|----------------------------|-------|
| `CsrfViewMiddleware` on | `@csrf_exempt`, removing the middleware | blocking rule 5 |
| template auto-escaping | `mark_safe`, `\|safe`, `{% autoescape off %}` | `grep -rnE "mark_safe\|autoescape off" .` plus `grep -rnF "\|safe" templates/` (`django/django@main:docs/topics/security.txt`) |
| explicit form/serializer fields | `"__all__"`, `exclude` | blocking rule 1 |
| `DEBUG = False`, `ALLOWED_HOSTS` set | env default of `True`, `ALLOWED_HOSTS = ["*"]` | `manage.py check --deploy` |
| Pydantic validation at the boundary | `model_construct()` (skips validation), `dict` bodies | `grep -rn "model_construct(\|: dict\b" app/routers` |
| object-level access | `Model.objects.get(pk=pk)` where `request.user.items.get(pk=pk)` was needed | review: "is every lookup by id scoped to the user or tenant?" (`SOURCE: original`) |

## Performance
| # | issue | detection | correct move |
|---|-------|-----------|--------------|
| 1 | N+1 over a forward FK | `django_assert_num_queries` on the list view | `select_related("author")` |
| 2 | N+1 over many-to-many or a reverse FK, including nested DRF serializers | same | `prefetch_related("tags")`, or `Prefetch(...)` with a filtered queryset |
| 3 | unbounded `Model.objects.all()` on a list endpoint | review: is there a page size cap? | paginate; `.iterator()` for batch jobs (`django/django@main:docs/topics/db/optimization.txt`) |
| 4 | `len(qs)` or `if qs:` just to test existence | review | `.exists()`, `.count()` (same doc) |
| 5 | CPU-heavy or blocking work in `async def` | `ruff check --select ASYNC` | threadpool (`def` handler, `run_in_threadpool`) or a task queue |

## Test conventions
| # | convention | check |
|---|------------|-------|
| 1 | Tests touching the DB are marked `@pytest.mark.django_db`; tests needing real transactions use `transaction=True` | pytest-django fails unmarked DB access (`pytest-dev/pytest-django@main:docs/helpers.rst`) |
| 2 | N+1 fixes get a query-count regression test, and only those | `django_assert_num_queries` / `assertNumQueries` (`django/django@main:docs/topics/testing/tools.txt`) |
| 3 | FastAPI routes are tested through `TestClient`, with collaborators replaced via `app.dependency_overrides` | `fastapi/fastapi@master:docs/en/docs/tutorial/testing.md`; `docs/en/docs/advanced/testing-dependencies.md` |
| 4 | Every schema constraint has a failing-input test that expects 422 / 400 | review: for each new `Field(...)` constraint, is there an invalid-input test? |

## Edge cases routinely missed
| # | edge case | why it is missed | test that would catch it |
|---|-----------|------------------|--------------------------|
| 1 | `.get()` on a missing row raises `DoesNotExist`, which becomes a 500 | fixtures always contain it | test the unknown id returns 404 (`get_object_or_404`, or an `HTTPException(404)`) |
| 2 | another user's id | single-user fixtures | test returns 404/403, not 200 |
| 3 | concurrent create racing a uniqueness check | sequential tests | unique constraint plus `IntegrityError` handling, or `get_or_create` |
| 4 | an `Optional` field sent as `null` vs omitted | clients differ | PATCH test with `null` and with the key absent (`model_dump(exclude_unset=True)`) |
| 5 | a timestamp at DST or a zone boundary | CI runs in UTC | test with an aware datetime in a non-UTC zone |

## Approach selection
| decision | options | deciding factor | default recommendation |
|----------|---------|-----------------|------------------------|
| sync vs async handler | `def` / `async def` | does the body call anything blocking? | **`def`** unless every call inside is awaitable |
| related loading | `select_related` / `prefetch_related` | forward single-valued vs multi-valued relation | **`select_related`** for FK/one-to-one, **`prefetch_related`** otherwise |
| settings | `os.environ[...]` / `pydantic-settings` / `django-environ` | FastAPI or Django | **`pydantic-settings`** for FastAPI; `os.environ["X"]` (fail at boot when missing) for Django |
| API layer on Django | DRF / Django Ninja / plain views | team already on DRF? | **follow the repo**; DRF for a new Django API with session auth |

## Verify
```bash
CHANGED=$(git diff --name-only --diff-filter=ACM origin/main... -- '*.py')

# lint, including the bug classes above (B006, B023, F632, E722, DTZ, ASYNC, S1xx/S6xx)
ruff check --select E,F,B,DTZ,ASYNC,S,BLE $CHANGED

# Django: deploy checklist and migrations in sync
python manage.py check --deploy --fail-level WARNING
python manage.py makemigrations --check --dry-run

# tests (pytest-django or plain pytest for FastAPI)
pytest -q

# grep checks no tool covers
grep -rnE "fields\s*=\s*['\"]__all__['\"]" --include=*.py . && echo "FAIL: __all__ fields (rule 1)"
grep -rn "csrf_exempt" --include=*.py . && echo "REVIEW: csrf_exempt (rule 5)"
grep -rn 'allow_origins=\["\*"\]' --include=*.py . && echo "REVIEW: wildcard CORS"
```

## Sources
- `django/django@main:docs/ref/models/querysets.txt`: `select_related()` (SQL join) vs `prefetch_related()` (separate lookup).
- `django/django@main:docs/topics/db/optimization.txt`: `select_related`/`prefetch_related`, `iterator()`, `exists()`/`count()`.
- `django/django@main:docs/topics/forms/modelforms.txt`: explicit `fields`; the `__all__` security warning.
- `django/django@main:docs/topics/async.txt` and `docs/topics/db/queries.txt` ("Asynchronous queries"): `SynchronousOnlyOperation`, `aget`, `acreate`.
- `django/django@main:docs/ref/csrf.txt` (`csrf_exempt`), `docs/howto/deployment/checklist.txt` (`check --deploy`, `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`), `docs/topics/security.txt`, `docs/topics/db/transactions.txt`, `docs/topics/testing/tools.txt` (`assertNumQueries`), `docs/ref/models/fields.txt` (`DecimalField`).
- `encode/django-rest-framework@main:docs/api-guide/authentication.md` (CSRF for session auth), `docs/api-guide/serializers.md` (`fields = '__all__'`).
- `fastapi/fastapi@master:docs/en/docs/async.md` (plain `def` runs in a threadpool), `docs/en/docs/tutorial/response-model.md` (output filtering), `docs/en/docs/tutorial/dependencies/dependencies-with-yield.md`, `docs/en/docs/tutorial/cors.md`, `docs/en/docs/tutorial/testing.md`, `docs/en/docs/advanced/testing-dependencies.md`.
- `pydantic/pydantic@main:docs/concepts/models.md`: `extra` (`'ignore'` default, `'forbid'`); `pydantic/pydantic-settings@main:docs/index.md`: `SecretStr`.
- `python/cpython@main:Doc/tutorial/controlflow.rst`: default values are evaluated once.
- `astral-sh/ruff@main:crates/ruff_linter/src/rules/`: `flake8_bugbear` (B006, B023), `pyflakes` (F632), `pycodestyle` (E722), `flake8_blind_except` (BLE001), `flake8_datetimez` (DTZ005), `flake8_async` (ASYNC210, ASYNC230, ASYNC251), `flake8_bandit` (S105, S106, S110, S113, S608, S611).
- `pytest-dev/pytest-django@main:docs/helpers.rst`: `django_db`, `django_assert_num_queries`.
- `SOURCE: original`: the tenant-scoping review question and the defaults in Approach selection.

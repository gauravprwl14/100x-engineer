"""Where the plugin's records live inside the user's project.

Not a standalone tool -- imported by prd.py, plan_feature.py, testplan.py, decide.py,
ledger.py, rca.py, learn.py and check_index.py (--register). One resolver, because
eight tools each guessing the location is how one of them ends up writing specs/ at
the top of a repo while another reads docs/engineering/specs/.

Resolution, first match wins (docs/OPERATING-MODEL.md section 8):

  1. `.100x.json` at the git root: {"schema": 1, "root": "<dir relative to the git
     root>"}. Committed, so every clone and every agent agrees without exporting
     anything. Both keys are optional (a config without "root" uses the default
     below); any other key is refused with a did-you-mean, because a misspelt
     "rot" would otherwise silently fall back to the default.
  2. The environment variable HUNDREDX_ROOT_DIR, for a one-off run or CI.
  3. The default, `docs/engineering`.

The config file outranks the environment on purpose: a stray export in someone's
shell must not split one repository's records across two roots.

Backward compatibility: before the root existed, the tools wrote prds/, specs/,
decisions/, rca/, lessons/ and ledger/ at the top of the repo. When neither the
config nor the variable is set, the default directory does not exist yet, and one of
those legacy collections does, the legacy top level keeps being used and a warning
says how to settle it. Silently switching to docs/engineering/ would make every
existing record vanish from `index`, `trace` and `lint` overnight.

The record layout under the root is the same in every mode:

    <root>/prds/<name>/prd.md      <root>/specs/<name>/spec.md
    <root>/decisions/ADR-*.md      <root>/rca/RCA-*.md
    <root>/lessons/LESSON-*.md     <root>/reviews/REV-*.md
    <root>/ledger/INDEX.md, MAP.md <root>/INDEX.md  (check_index --register)

A feature's artifacts sit together in its directory, feature_dir(<name>):

    <root>/specs/<name>/spec.md           the spec (plan_feature)
    <root>/specs/<name>/plan.json         the task graph (plan_dag)
    <root>/specs/<name>/testplan.md       the test plan (testplan new --out)
    <root>/specs/<name>/reports/<id>.json one agent report per task (agent_report)

Test plans used to be written to <root>/testplans/<name>.md; LEGACY_TESTPLANS names
that directory so readers can still find one there.
"""
import difflib
import json
import os
import pathlib
import re
import subprocess
import sys

CONFIG_NAME = ".100x.json"
ENV_VAR = "HUNDREDX_ROOT_DIR"
DEFAULT_ROOT = "docs/engineering"
CONFIG_SCHEMA = 1
CONFIG_KEYS = ("schema", "root")
LEGACY_TESTPLANS = "testplans"
FEATURE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# A legacy collection is recognised by the records the tools themselves wrote, not by
# the bare directory name: `specs/` and `ledger/` are common names for unrelated
# things, and mistaking them for records would pin a new user to the old layout.
LEGACY_MARKERS = (("prds", "*/prd.md"), ("specs", "*/spec.md"),
                  ("decisions", "ADR-*.md"), ("rca", "RCA-*.md"),
                  ("lessons", "LESSON-*.md"), ("reviews", "REV-*.md"),
                  ("ledger", "INDEX.md"))

_warned = False


def git_root(cwd=None):
    """(repo_root, in_git_repo) for `cwd` (default: the process cwd). Outside a repo
    the directory stands in for reads only; writers must still refuse via
    _mutation_guard.require_git_root."""
    base = pathlib.Path(cwd) if cwd is not None else pathlib.Path.cwd()
    r = subprocess.run(["git", "-C", str(base), "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return pathlib.Path(r.stdout.strip()), True
    return base, False


def _fail(msg):
    print(f"100x: {msg}", file=sys.stderr)
    sys.exit(2)


def _inside(repo, value, origin):
    """Resolve a configured root and refuse one that leaves the repository.

    An absolute path or a `..` escape would let a committed config file make every
    record-writing tool write outside the project -- the same class of escape
    _mutation_guard.safe_record_name blocks for record names.
    """
    if not isinstance(value, str) or not value.strip():
        _fail(f"{origin}: root must be a non-empty string, got {value!r}")
    raw = pathlib.PurePosixPath(value.strip().replace("\\", "/"))
    if raw.is_absolute() or ".." in raw.parts:
        _fail(f"{origin}: root {value!r} must be a path inside the repository, "
              f"relative to its top level, with no '..' -- e.g. \"docs/engineering\" "
              f"or \".\"")
    root = (repo / pathlib.Path(*raw.parts)) if raw.parts else repo
    contained(root, repo, origin)
    return root


def config_root(data, cfg):
    """The root a parsed .100x.json names, after refusing what it must not contain."""
    if not isinstance(data, dict):
        _fail(f"{cfg}: expected a JSON object, e.g. {{\"schema\": {CONFIG_SCHEMA}, "
              f"\"root\": \"{DEFAULT_ROOT}\"}}")
    for k in sorted(set(data) - set(CONFIG_KEYS)):
        near = difflib.get_close_matches(k, CONFIG_KEYS, n=1, cutoff=0.5)
        _fail(f"{cfg}: unknown key {k!r} -- "
              + (f"did you mean {near[0]!r}?" if near
                 else f"known keys: {', '.join(CONFIG_KEYS)}"))
    if "schema" in data and data["schema"] != CONFIG_SCHEMA:
        _fail(f"{cfg}: \"schema\": {data['schema']!r} is not supported -- this plugin "
              f"reads schema {CONFIG_SCHEMA}")
    return data.get("root", DEFAULT_ROOT)


def feature_dir(feature, repo=None):
    """<root>/specs/<feature>/, where a feature's spec, plan.json, testplan.md and
    reports/ live. A name with a path separator or a leading dot is refused (exit 2):
    it is joined onto a write path."""
    if not isinstance(feature, str) or not FEATURE_NAME.match(feature) \
            or ".." in feature.split("."):
        _fail(f"feature name {feature!r} must be letters, digits, '.', '_' or '-', "
              f"starting with a letter or digit")
    records, _ = resolve(repo)
    return records / "specs" / feature


def legacy_collections(repo):
    return [d for d, glob in LEGACY_MARKERS if any((repo / d).glob(glob))]


def resolve(repo=None):
    """(records_root, source) where source is config | env | legacy | default."""
    global _warned
    if repo is None:
        repo, _ = git_root()
    cfg = repo / CONFIG_NAME
    if cfg.is_file():
        try:
            data = json.loads(cfg.read_text())
        except (OSError, ValueError) as e:
            _fail(f"{cfg}: not valid JSON ({e}) -- expected {{\"root\": \"docs/engineering\"}}")
        return _inside(repo, config_root(data, cfg), str(cfg)), "config"
    env = os.environ.get(ENV_VAR)
    if env:
        return _inside(repo, env, ENV_VAR), "env"
    default = repo / DEFAULT_ROOT
    if not default.exists():
        legacy = legacy_collections(repo)
        if legacy:
            if not _warned:
                _warned = True
                print(f"100x: warning: using the legacy top-level record directories "
                      f"({', '.join(d + '/' for d in legacy)}) because {DEFAULT_ROOT}/ "
                      f"does not exist and no {CONFIG_NAME} is present. To keep this "
                      f"layout, commit {CONFIG_NAME} containing {{\"root\": \".\"}}; to "
                      f"adopt the default, move those directories under {DEFAULT_ROOT}/.",
                      file=sys.stderr)
            return repo, "legacy"
    contained(default, repo, DEFAULT_ROOT)
    return default, "default"


def contained(path, repo, origin="write"):
    """The resolved path, or exit 2 if it lands outside the repository.

    Text checks (no absolute path, no `..`) are not enough: a committed symlink --
    `docs/engineering -> ../../elsewhere`, `AGENTS.md -> ~/.zshrc` -- passes them and
    still sends the write outside the project. Resolving follows every symlink in the
    chain, so whatever a cloned repo commits, the final target must sit under it.
    """
    real_repo = pathlib.Path(repo).resolve()
    target = pathlib.Path(path)
    if not target.is_absolute():
        target = pathlib.Path(repo) / target
    real = target.resolve()
    if real != real_repo and real_repo not in real.parents:
        _fail(f"{origin}: refusing to write {target} -- it resolves to {real}, outside "
              f"the repository {real_repo} (a symlink or path escape)")
    return real


def safe_write_text(path, text, repo, origin="write"):
    """Write `text` to `path` without following a symlink out of the repository.

    The content goes to a temp file created with O_CREAT|O_EXCL|O_NOFOLLOW in the same
    directory and is renamed over the target; rename replaces a symlink rather than
    writing through it, so a planted link at the destination cannot redirect the bytes.
    """
    real = contained(path, repo, origin)
    contained(real.parent, repo, origin)
    real.parent.mkdir(parents=True, exist_ok=True)
    contained(real.parent, repo, origin)
    tmp = real.parent / f".{real.name}.{os.getpid()}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                 0o644)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, real)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:  # fail-open: cleanup of our own temp file; the original error is re-raised below
            pass
        raise
    return real


def show(path, repo):
    """Repo-relative display path; falls back to the path itself outside the repo
    (macOS /tmp vs /private/tmp makes relative_to raise, not degrade)."""
    try:
        return pathlib.Path(path).resolve().relative_to(pathlib.Path(repo).resolve())
    except ValueError:
        return pathlib.Path(path)

"""Where the plugin's records live inside the user's project.

Not a standalone tool -- imported by prd.py, plan_feature.py, testplan.py, decide.py,
ledger.py, rca.py, learn.py and check_index.py (--register). One resolver, because
eight tools each guessing the location is how one of them ends up writing specs/ at
the top of a repo while another reads docs/engineering/specs/.

Resolution, first match wins (docs/OPERATING-MODEL.md section 8):

  1. `.100x.json` at the git root: {"root": "<dir relative to the git root>"}.
     Committed, so every clone and every agent agrees without exporting anything.
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
    <root>/ledger/INDEX.md, MAP.md <root>/testplans/<name>.md
    <root>/INDEX.md                (check_index --register)
"""
import json
import os
import pathlib
import subprocess
import sys

CONFIG_NAME = ".100x.json"
ENV_VAR = "HUNDREDX_ROOT_DIR"
DEFAULT_ROOT = "docs/engineering"

# A legacy collection is recognised by the records the tools themselves wrote, not by
# the bare directory name: `specs/` and `ledger/` are common names for unrelated
# things, and mistaking them for records would pin a new user to the old layout.
LEGACY_MARKERS = (("prds", "*/prd.md"), ("specs", "*/spec.md"),
                  ("decisions", "ADR-*.md"), ("rca", "RCA-*.md"),
                  ("lessons", "LESSON-*.md"), ("reviews", "REV-*.md"),
                  ("ledger", "INDEX.md"))

_warned = False


def git_root():
    """(repo_root, in_git_repo). Outside a repo the cwd stands in for reads only;
    writers must still refuse via _mutation_guard.require_git_root."""
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return pathlib.Path(r.stdout.strip()), True
    return pathlib.Path.cwd(), False


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
    return (repo / pathlib.Path(*raw.parts)) if raw.parts else repo


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
        if not isinstance(data, dict) or "root" not in data:
            _fail(f"{cfg}: expected an object with a \"root\" key, e.g. "
                  f"{{\"root\": \"docs/engineering\"}}")
        return _inside(repo, data["root"], str(cfg)), "config"
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
    return default, "default"


def show(path, repo):
    """Repo-relative display path; falls back to the path itself outside the repo
    (macOS /tmp vs /private/tmp makes relative_to raise, not degrade)."""
    try:
        return pathlib.Path(path).resolve().relative_to(pathlib.Path(repo).resolve())
    except ValueError:
        return pathlib.Path(path)

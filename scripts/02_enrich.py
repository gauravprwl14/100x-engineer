#!/usr/bin/env python3
"""Stage B+C: activity gates (A3,A4) then full tree probe for signal files.

Threaded direct-API to avoid 3000 `gh` subprocess spawns.
"""
import json, os, re, sys, time, datetime, pathlib, threading
import urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

# One-shot research-pipeline scripts with module-level execution: importing them, or
# passing --help, would otherwise start a live GitHub harvest. Answer --help from the
# docstring before any of that runs.
import sys as _sys
if __name__ != "__main__" or any(a in ("--help", "-h") for a in _sys.argv[1:]):
    print(__doc__ or __file__)
    raise SystemExit(0)


TOKEN = os.popen("gh auth token").read().strip()
assert TOKEN, "no gh token"
OUT = pathlib.Path("research/raw")
API = "https://api.github.com"
HDR = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json",
       "User-Agent": "100x-research"}

_lock = threading.Lock()
_stats = {"calls": 0, "429": 0, "err": 0}


def api(path, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(API + path, headers=HDR)
            with urllib.request.urlopen(req, timeout=45) as r:
                with _lock:
                    _stats["calls"] += 1
                if r.status == 202:           # stats still computing
                    time.sleep(2.5)
                    continue
                return json.loads(r.read().decode()), dict(r.headers)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                with _lock:
                    _stats["429"] += 1
                time.sleep(8 * (attempt + 1))
                continue
            if e.code in (404, 409, 451):
                return None, {}
        except Exception:
            time.sleep(2)
    with _lock:
        _stats["err"] += 1
    return None, {}


# ---------- signal file patterns (Part D) ----------
SIG = {
 # D3 agentic
 "agent_claude_md":      r"^CLAUDE\.md$|^\.claude/CLAUDE\.md$",
 "agent_agents_md":      r"^AGENTS\.md$",
 "agent_cursor":         r"^\.cursorrules$|^\.cursor/rules/",
 "agent_copilot":        r"^\.github/copilot-instructions\.md$",
 "agent_other_rules":    r"^\.windsurfrules$|^GEMINI\.md$|^\.clinerules|^\.aider|^\.junie/",
 "agent_claude_dir":     r"^\.claude/(skills|agents|commands|hooks)/",
 "agent_mcp":            r"^\.mcp\.json$|mcp[-_]?servers?\.json$",
 # D1 verification
 "ci_gha":               r"^\.github/workflows/.+\.ya?ml$",
 "ci_other":             r"^\.gitlab-ci\.yml$|^Jenkinsfile|^\.circleci/|^azure-pipelines|^\.buildkite/",
 "test_dir":             r"^(tests?|spec|__tests__|e2e|integration)/|/(tests?|__tests__)/",
 "test_go":              r"_test\.go$",
 "test_py":              r"^conftest\.py$|/conftest\.py$|^pytest\.ini$|^tox\.ini$",
 "test_js_cfg":          r"^(jest|vitest|playwright|cypress|karma|wdio)\.config\.[jt]s$|^jest\.config|^vitest\.config",
 "test_e2e":             r"playwright\.config|cypress\.config|^cypress/|^e2e/|^tests/e2e/",
 "test_property":        r"hypothesis|fast-?check|quickcheck|proptest|jqwik",
 "test_fuzz":            r"^fuzz/|fuzz_|_fuzz|\.options$|oss-fuzz",
 "test_snapshot":        r"__snapshots__|\.snap$|\.ambr$",
 "test_mutation":        r"stryker|mutmut|mutation-test|cosmic-ray|go-mutesting",
 "test_bench":           r"^bench(es|marks?)?/|_bench\.go$|\.bench\.[jt]s$|asv\.conf",
 "cov_cfg":              r"^codecov\.ya?ml$|^\.coveragerc$|^\.codecov|coverage\.ya?ml",
 "precommit":            r"^\.pre-commit-config\.ya?ml$|^\.husky/|^lefthook\.ya?ml$|^\.lintstagedrc",
 # type + lint
 "ts_config":            r"^tsconfig(\..+)?\.json$",
 "lint_eslint":          r"^\.eslintrc|^eslint\.config\.",
 "lint_biome":           r"^biome\.jsonc?$",
 "lint_ruff":            r"^\.?ruff\.toml$",
 "lint_golangci":        r"^\.golangci\.ya?ml$",
 "type_mypy":            r"^mypy\.ini$|^\.mypy\.ini$",
 "type_pyright":         r"^pyrightconfig\.json$",
 # D2 anti-bloat
 "bloat_knip":           r"^\.?knip\.(json|jsonc|ts|js)$|^knip\.config",
 "bloat_sizelimit":      r"^\.size-limit\.(json|js|cjs|ts)$|^size-limit",
 "bloat_bundlewatch":    r"bundlewatch|bundlesize",
 "bloat_apiextractor":   r"^api-extractor\.json$|\.api\.md$|^etc/.*\.api\.md$",
 "bloat_depcheck":       r"^\.depcheckrc|^\.unimportedrc|ts-prune",
 "bloat_deadcode":       r"vulture|deadcode|unused",
 # D5 security
 "sec_policy":           r"^SECURITY\.md$|^\.github/SECURITY\.md$",
 "sec_dependabot":       r"^\.github/dependabot\.ya?ml$",
 "sec_renovate":         r"^\.?renovate\.json5?$|^renovate\.json",
 "sec_codeql":           r"codeql",
 "sec_semgrep":          r"semgrep",
 "sec_scorecard":        r"scorecard",
 "sec_sign":             r"cosign|sigstore|\.sigstore|slsa",
 "sec_sbom":             r"sbom|cyclonedx|spdx\.json",
 # D7 governance
 "gov_codeowners":       r"CODEOWNERS$",
 "gov_contributing":     r"^CONTRIBUTING(\.md)?$|^\.github/CONTRIBUTING",
 "gov_pr_template":      r"PULL_REQUEST_TEMPLATE",
 "gov_adr":              r"^docs?/(adr|architecture|decisions)/|^adr/|^rfcs?/|^docs/rfcs?/|^proposals?/",
 "gov_changelog":        r"^CHANGELOG(\.md)?$",
 "gov_changesets":       r"^\.changeset/",
 # D6 ops
 "ops_runbook":          r"runbook|on-?call|incident|postmortem",
 "ops_slo":              r"\bslo\b|service-level",
 "ops_observability":    r"opentelemetry|otel|prometheus|tracing|grafana",
 "ops_docker":           r"^Dockerfile|^docker-compose",
 "ops_k8s":              r"^(deploy|k8s|kubernetes|charts|helm)/",
 # D4 correctness
 "corr_schema":          r"\bzod\b|pydantic|valibot|io-ts|\.proto$|openapi|json-?schema",
 "corr_migrations":      r"^(migrations?|db/migrate|alembic)/|/migrations?/",
 "corr_flags":           r"feature-?flag|launchdarkly|unleash|flipper",
 # build manifests (A8/B2)
 "mf_package_json":      r"^package\.json$",
 "mf_pyproject":         r"^pyproject\.toml$|^setup\.py$|^setup\.cfg$",
 "mf_gomod":             r"^go\.mod$",
 "mf_cargo":             r"^Cargo\.toml$",
 "mf_jvm":               r"^pom\.xml$|^build\.gradle",
 "mf_other":             r"^Gemfile$|^composer\.json$|^CMakeLists\.txt$|^Makefile$|^pubspec\.yaml$|^.*\.podspec$|^Package\.swift$",
 # release
 "rel_goreleaser":       r"^\.goreleaser",
 "rel_semantic":         r"semantic-release|release-please|release-drafter",
 # adopters
 "adopters":             r"^ADOPTERS|^USERS\.md$",
 "monorepo":             r"^(turbo\.json|nx\.json|lerna\.json|pnpm-workspace\.yaml|rush\.json)$",
}
SIGC = {k: re.compile(v, re.I) for k, v in SIG.items()}
DOC_EXT = re.compile(r"\.(md|rst|txt|adoc)$", re.I)
ASSET_EXT = re.compile(r"\.(png|jpe?g|gif|svg|pdf|mp4|webp|ico|ttf|woff2?)$", re.I)


def probe(repo):
    fn, br = repo["full_name"], repo["default_branch"]
    out = dict(repo)

    # --- A3: commits in trailing 12 months ---
    ca, _ = api(f"/repos/{fn}/stats/commit_activity")
    out["commits_52w"] = sum(w.get("total", 0) for w in ca) if isinstance(ca, list) else None

    # --- A4 proxy: top-100 all-time contributors count ---
    cb, hdrs = api(f"/repos/{fn}/contributors?per_page=100&anon=false")
    out["contributors_top100"] = len(cb) if isinstance(cb, list) else None
    out["contributors_note"] = "top-100 all-time (approximation for A4)"

    # --- C1: releases ---
    rl, _ = api(f"/repos/{fn}/releases?per_page=100")
    if isinstance(rl, list):
        out["release_count"] = len(rl)
        out["latest_release"] = rl[0]["published_at"] if rl else None
    else:
        out["release_count"], out["latest_release"] = 0, None

    # --- Stage C: recursive tree ---
    tr, _ = api(f"/repos/{fn}/git/trees/{br}?recursive=1")
    paths = []
    if isinstance(tr, dict):
        paths = [t["path"] for t in tr.get("tree", []) if t.get("type") == "blob"]
        out["tree_truncated"] = bool(tr.get("truncated"))
    else:
        out["tree_truncated"] = None
    out["file_count"] = len(paths)

    hits = {k: [] for k in SIGC}
    docs = assets = 0
    for p in paths:
        if DOC_EXT.search(p):
            docs += 1
        elif ASSET_EXT.search(p):
            assets += 1
        for k, rx in SIGC.items():
            if len(hits[k]) < 6 and rx.search(p):
                hits[k].append(p)
    out["doc_ratio"] = round(docs / len(paths), 3) if paths else None
    out["asset_ratio"] = round(assets / len(paths), 3) if paths else None
    out["signals"] = {k: v for k, v in hits.items() if v}
    out["signal_keys"] = sorted(out["signals"].keys())
    out["gha_workflow_count"] = len([p for p in paths if re.match(r"^\.github/workflows/.+\.ya?ml$", p)])
    return out


cands = json.loads((OUT / "candidates.json").read_text())
print(f"enriching {len(cands)} candidates ...", flush=True)

results, done = [], 0
with ThreadPoolExecutor(max_workers=12) as ex:
    futs = {ex.submit(probe, c): c["full_name"] for c in cands}
    for f in as_completed(futs):
        done += 1
        try:
            results.append(f.result())
        except Exception as e:
            print(f"  !! {futs[f]}: {e}", file=sys.stderr)
        if done % 100 == 0:
            print(f"  {done}/{len(cands)}  api_calls={_stats['calls']} throttled={_stats['429']} err={_stats['err']}", flush=True)

results.sort(key=lambda r: -r["stars"])
(OUT / "enriched.json").write_text(json.dumps(results, indent=1))
print(f"\ndone: {len(results)} enriched, api_calls={_stats['calls']}, throttled={_stats['429']}, err={_stats['err']}")

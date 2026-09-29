#!/usr/bin/env python3
"""Stage D: gates (A3,A4,A8,A9,B2,C) + D1-D7 scoring + cluster allocation."""
import json, re, pathlib, datetime, collections, sys

# One-shot research-pipeline scripts with module-level execution: importing them, or
# passing --help, would otherwise start a live GitHub harvest. Answer --help from the
# docstring before any of that runs.
import sys as _sys
if __name__ != "__main__" or any(a in ("--help", "-h") for a in _sys.argv[1:]):
    print(__doc__ or __file__)
    raise SystemExit(0)


OUT = pathlib.Path("research/raw")
src = OUT / ("enriched.json" if (OUT / "enriched.json").exists() else "gql_partial.json")
rows = json.loads(src.read_text())
TODAY = datetime.date.today()
print(f"source={src.name}  rows={len(rows)}\n")

SIG = {
 # ---- D3 agentic ----
 "agent_claude_md":    r"^CLAUDE\.md/?$",
 "agent_agents_md":    r"^AGENTS\.md/?$",
 "agent_cursor":       r"^\.cursorrules/?$|^\.cursor/rules/",
 "agent_copilot":      r"^\.github/copilot-instructions\.md/?$",
 "agent_other_rules":  r"^\.windsurfrules|^GEMINI\.md|^\.clinerules|^\.aider|^\.junie",
 "agent_claude_dir":   r"^\.claude/(skills|agents|commands|hooks)/",
 "agent_agents_dir":   r"^\.agents/",
 "agent_mcp":          r"^\.mcp\.json/?$",
 # ---- D1 verification ----
 "ci_gha":             r"^\.github/workflows/.+\.ya?ml/?$",
 "ci_other":           r"^\.gitlab-ci\.yml|^Jenkinsfile|^\.circleci|^azure-pipelines|^\.buildkite",
 "test_dir":           r"^(tests?|spec|e2e|__tests__)/",
 "test_cfg_js":        r"^(jest|vitest|playwright|cypress|karma|wdio|ava)\.config",
 "test_cfg_py":        r"^(pytest\.ini|tox\.ini|conftest\.py|noxfile\.py)/?$",
 "test_cfg_other":     r"^(\.rspec|phpunit\.xml|Makefile\.test)/?$",
 "test_e2e":           r"^e2e/|^cypress|^playwright\.config|^tests/e2e/",
 "test_fuzz":          r"^fuzz/",
 "test_bench":         r"^(bench(es|marks?)?)/|^asv\.conf",
 "cov_cfg":            r"^(codecov\.ya?ml|\.coveragerc|\.codecov\.ya?ml)/?$",
 "precommit":          r"^\.pre-commit-config\.ya?ml/?$|^\.husky/|^lefthook\.ya?ml/?$|^\.lintstagedrc",
 "wf_test":            r"^\.github/workflows/.*(test|ci|check|verify|build)",
 "wf_e2e":             r"^\.github/workflows/.*(e2e|integration|browser|playwright|cypress)",
 "wf_bench":           r"^\.github/workflows/.*(bench|perf)",
 # ---- D4 correctness ----
 "ts_config":          r"^tsconfig(\..+)?\.json/?$",
 "lint_eslint":        r"^\.eslintrc|^eslint\.config\.",
 "lint_biome":         r"^biome\.jsonc?/?$",
 "lint_ruff":          r"^\.?ruff\.toml/?$",
 "lint_golangci":      r"^\.golangci\.ya?ml/?$",
 "lint_editorconfig":  r"^\.editorconfig/?$",
 "type_mypy":          r"^(mypy\.ini|\.mypy\.ini)/?$",
 "type_pyright":       r"^pyrightconfig\.json/?$",
 "corr_migrations":    r"^migrations/",
 "corr_proto":         r"^(proto|protos|api)/",
 "wf_lint":            r"^\.github/workflows/.*(lint|format|style|typecheck)",
 # ---- D2 anti-bloat ----
 "bloat_knip":         r"^\.?knip\.(json|jsonc|ts|js)/?$|^knip\.config",
 "bloat_sizelimit":    r"^\.size-limit\.|^size-limit",
 "bloat_apiextractor": r"^api-extractor\.json/?$",
 "bloat_depcheck":     r"^\.depcheckrc|^\.unimportedrc",
 "monorepo":           r"^(turbo\.json|nx\.json|lerna\.json|pnpm-workspace\.yaml|rush\.json)/?$",
 "packages_dir":       r"^packages/",
 "wf_size":            r"^\.github/workflows/.*(size|bundle|deadcode|knip)",
 # ---- D5 security ----
 "sec_policy":         r"^(SECURITY\.md|\.github/SECURITY\.md)/?$",
 "sec_dependabot":     r"^\.github/dependabot\.ya?ml/?$",
 "sec_renovate":       r"^\.?renovate\.json5?/?$",
 "sec_codeql_wf":      r"^\.github/workflows/.*codeql",
 "sec_scan_wf":        r"^\.github/workflows/.*(security|scan|semgrep|trivy|audit|scorecard|snyk)",
 "sec_sign_wf":        r"^\.github/workflows/.*(sign|cosign|slsa|provenance|sbom)",
 # ---- D6 ops ----
 "ops_docker":         r"^(Dockerfile|docker-compose)",
 "ops_wf_deploy":      r"^\.github/workflows/.*(deploy|release|publish|canary|rollout)",
 "ops_adr":            r"^(docs/adr|adr|rfcs)/",
 # ---- D7 governance ----
 "gov_codeowners":     r"^(CODEOWNERS|\.github/CODEOWNERS)/?$",
 "gov_contributing":   r"^(CONTRIBUTING\.md|\.github/CONTRIBUTING\.md)/?$",
 "gov_pr_template":    r"PULL_REQUEST_TEMPLATE",
 "gov_changelog":      r"^CHANGELOG\.md/?$",
 "gov_changesets":     r"^\.changeset/",
 "gov_governance":     r"^(GOVERNANCE\.md|MAINTAINERS\.md)/?$",
 "rel_goreleaser":     r"^\.goreleaser",
 # ---- manifests ----
 "mf_package_json":    r"^package\.json/?$",
 "mf_pyproject":       r"^(pyproject\.toml|setup\.py|setup\.cfg)/?$",
 "mf_gomod":           r"^go\.mod/?$",
 "mf_cargo":           r"^Cargo\.toml/?$",
 "mf_jvm":             r"^(pom\.xml|build\.gradle)",
 "mf_other":           r"^(Gemfile|composer\.json|CMakeLists\.txt|Makefile|pubspec\.yaml|Package\.swift)/?$",
 "adopters":           r"^(ADOPTERS|USERS\.md)",
}
SIGC = {k: re.compile(v, re.I) for k, v in SIG.items()}

DIM = {
 "D1_verification": ["test_dir","test_cfg_js","test_cfg_py","test_cfg_other","test_e2e",
                     "test_fuzz","test_bench","cov_cfg","precommit","wf_test","wf_e2e","wf_bench"],
 "D2_antibloat":    ["bloat_knip","bloat_sizelimit","bloat_apiextractor","bloat_depcheck",
                     "monorepo","packages_dir","wf_size"],
 "D3_agentic":      ["agent_claude_md","agent_agents_md","agent_cursor","agent_copilot",
                     "agent_other_rules","agent_claude_dir","agent_agents_dir","agent_mcp"],
 "D4_correctness":  ["ts_config","lint_eslint","lint_biome","lint_ruff","lint_golangci",
                     "lint_editorconfig","type_mypy","type_pyright","corr_migrations",
                     "corr_proto","wf_lint"],
 "D5_security":     ["sec_policy","sec_dependabot","sec_renovate","sec_codeql_wf",
                     "sec_scan_wf","sec_sign_wf"],
 "D6_ops":          ["ops_docker","ops_wf_deploy","ops_adr"],
 "D7_governance":   ["gov_codeowners","gov_contributing","gov_pr_template","gov_changelog",
                     "gov_changesets","gov_governance","rel_goreleaser"],
}
MANIFEST = ["mf_package_json","mf_pyproject","mf_gomod","mf_cargo","mf_jvm","mf_other"]


def keys_for(paths):
    k, ev = set(), {}
    for p in paths:
        for name, rx in SIGC.items():
            if rx.search(p):
                k.add(name)
                ev.setdefault(name, [])
                if len(ev[name]) < 4: ev[name].append(p)
    return k, ev


def dim_score(keys, dk, has_ci):
    n = sum(1 for x in dk if x in keys)
    if n == 0: return 0
    if n == 1: return 1
    base = 2 if n <= 3 else 3
    return base if has_ci else max(1, base - 1)


def cluster(r, keys):
    """R4: topics + language only. Description prose is too loose a signal."""
    lang = r.get("language") or ""
    topics = {t.lower() for t in (r.get("topics") or [])}
    name = r["full_name"].lower()
    # v4: mechanical mobile detection failed 3x (see rubric v4). Language-only,
    # plus a visible 5-entry named exception list for cross-platform frameworks.
    MOBILE_LANGS = {"Swift", "Kotlin", "Dart", "Objective-C"}
    MOBILE_NAMED = {"react/react-native", "facebook/react-native", "expo/expo",
                    "flutter/flutter", "ionic-team/ionic-framework",
                    "NativeScript/NativeScript"}
    AGENT_T  = {"ai-agent","agent","llm","coding-agent","ai-coding","copilot","codegen",
                "autonomous-agents","llm-agent","agents","ai-assistant","code-generation"}
    if lang in MOBILE_LANGS or r["full_name"] in MOBILE_NAMED:
        return "mobile"
    if (topics & AGENT_T) and re.search(r"(code|coding|dev|engineer|ide|cli|agent)", name + " " + " ".join(topics)):
        return "agentic-dev"
    if lang == "Python": return "python"
    if lang == "Go": return "go"
    if lang in ("TypeScript","JavaScript"):
        blob = f"{' '.join(topics)} {name}"
        if re.search(r"(framework|compiler|bundler|runtime|build|toolchain|library|cli|linter|test|sdk|parser|transpiler)", blob):
            return "js-infra"
        return "js-app"
    return "reliability-exemplar"


kept, dropped = [], []
for r in rows:
    if not r.get("full_name"): continue
    paths = r.get("paths") or []
    keys, ev = keys_for(paths)
    has_ci = bool({"ci_gha","ci_other"} & keys)
    has_mf = bool(set(MANIFEST) & keys)
    has_test = bool(keys & set(DIM["D1_verification"]))
    fails = []
    if (r.get("commits_12mo") or 0) < 250: fails.append(f"A3:commits={r.get('commits_12mo')}")
    if (r.get("authors_last100") or 0) < 10 and (r.get("commits_12mo") or 0) < 2000:
        fails.append(f"A4:authors={r.get('authors_last100')}")
    if r.get("archived"): fails.append("A5:archived")
    if r.get("fork"): fails.append("A6:fork")
    if not r.get("license"): fails.append("A7:no license")
    if not has_mf: fails.append("A8:no build manifest")
    if not has_test: fails.append("A9:no test signal")

    # R5 A10: repo age;  R6 A11: star-velocity sanity bound
    age_m = None
    if r.get("created_at"):
        try:
            _d = datetime.datetime.fromisoformat(r["created_at"].replace("Z","+00:00")).date()
            age_m = (TODAY - _d).days / 30.44
        except Exception:
            age_m = None
    cl_pre = cluster(r, keys)
    min_age = 12 if cl_pre == "agentic-dev" else 24
    if age_m is None or age_m < min_age:
        fails.append(f"A10:age={age_m and round(age_m,1)}mo<{min_age}")
    if age_m and (r.get("stars") or 0) / max(age_m, 1) > 15000:
        fails.append(f"A11:velocity={(r['stars']/max(age_m,1)):.0f}/mo")

    c = []
    if r.get("release_count", 0) >= 12 and r.get("latest_release"):
        try:
            d = datetime.datetime.fromisoformat(r["latest_release"].replace("Z", "+00:00")).date()
            if (TODAY - d).days <= 180: c.append("C1:release-cadence")
        except Exception: pass
    if has_mf: c.append("C2:distributed")
    if "adopters" in keys: c.append("C3:adopters")
    if "sec_policy" in keys: c.append("C4:security-policy")
    if {"gov_changelog","corr_migrations","gov_changesets"} & keys: c.append("C5:change-discipline")
    if len(c) < 2: fails.append(f"C:{len(c)}/2 production proxies")

    scores = {d: dim_score(keys, ks, has_ci) for d, ks in DIM.items()}
    rec = {k: r.get(k) for k in ("full_name","stars","language","pushed_at","license",
            "commits_12mo","authors_last100","release_count","latest_release","size_kb",
            "description","topics","open_issues","open_prs","default_branch")}
    rec.update({"age_months": age_m and round(age_m,1),
                "stars_per_month": age_m and round((r.get("stars") or 0)/max(age_m,1)),
                "dim_scores": scores, "signal_score": sum(scores.values()),
                "signal_keys": sorted(keys), "evidence": ev,
                "production_evidence": c, "cluster": cluster(r, keys),
                "has_ci": has_ci, "has_manifest": has_mf,
                "workflow_count": len([p for p in paths if re.match(r"^\.github/workflows/.+\.ya?ml", p)]),
                "gate_failures": fails})
    (dropped if fails else kept).append(rec)

kept.sort(key=lambda r: (-r["signal_score"], -r["stars"]))
for r in kept:
    r["tier"] = 1 if r["signal_score"] >= 15 else (2 if r["signal_score"] >= 10 else 3)

TARGET = {"js-infra":55,"js-app":35,"python":50,"go":40,"mobile":30,
          "agentic-dev":25,"reliability-exemplar":25}
by_c = collections.defaultdict(list)
for r in kept: by_c[r["cluster"]].append(r)
corpus = []
for cl, cap in TARGET.items():
    for r in by_c[cl][:cap]:
        r["selected"] = True; corpus.append(r)

(OUT/"scored_kept.json").write_text(json.dumps(kept, indent=1))
(OUT/"scored_dropped.json").write_text(json.dumps(dropped, indent=1))
(OUT/"corpus.json").write_text(json.dumps(corpus, indent=1))

print(f"passed_gates={len(kept)}  dropped={len(dropped)}  CORPUS={len(corpus)}\n")
print(f"{'cluster':24s} {'sel':>4s} {'elig':>5s} {'target':>7s}")
for cl, cap in TARGET.items():
    print(f"{cl:24s} {len(by_c[cl][:cap]):4d} {len(by_c[cl]):5d} {cap:7d}")
print("\ntier in corpus:", {t: sum(1 for r in corpus if r["tier"]==t) for t in (1,2,3)})
print("\ngate failure frequency:")
for k,v in collections.Counter(f.split(':')[0] for r in dropped for f in r["gate_failures"]).most_common():
    print(f"  {k:12s} {v}")
print(f"\n=== D3 AGENTIC CONFIG ADOPTION (all {len(rows)} enriched) ===")
tot = 0
for k in DIM["D3_agentic"]:
    n = sum(1 for r in rows if any(SIGC[k].search(p) for p in (r.get("paths") or [])))
    print(f"  {k:20s} {n:5d}  {100*n/max(1,len(rows)):5.1f}%")
any3 = sum(1 for r in rows if keys_for(r.get('paths') or [])[0] & set(DIM["D3_agentic"]))
print(f"  {'ANY':20s} {any3:5d}  {100*any3/max(1,len(rows)):5.1f}%")

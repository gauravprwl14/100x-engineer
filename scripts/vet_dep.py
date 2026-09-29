#!/usr/bin/env python3
"""Vet a package before it is installed. stdlib only -- urllib, no `requests`.

"Trendy" is read literally as a trap: a fashionable package with one maintainer and
no release in 18 months is the worst case, not the best one. This tool treats
"trendy" as *actively maintained and safe to depend on* -- popularity (downloads) is
corroboration, never the criterion that decides ADOPT/REVIEW/AVOID.

    vet_dep.py react                       # npm by default
    vet_dep.py --registry pypi pydantic
    vet_dep.py left-pad --json
    vet_dep.py --check-manifest            # vet every direct dep in package.json /
                                            #   pyproject.toml found in the cwd
    vet_dep.py --check-manifest --list-only  # just show what would be vetted, no
                                              #   network calls (used by tests)

Fetches from the public registries with urllib:
  npm:  https://registry.npmjs.org/<pkg>
        https://api.npmjs.org/downloads/point/last-week/<pkg>
  pypi: https://pypi.org/pypi/<pkg>/json

A registry that cannot be reached prints a clear message and exits non-zero --
a vetting tool that fails open (says nothing, lets the install proceed) is worse
than no tool at all. Exit 1 on an AVOID verdict, 2 if the package could not be
vetted at all (not found / unreachable / bad manifest).

The three registry base URLs can be overridden with VET_DEP_NPM_REGISTRY,
VET_DEP_NPM_DOWNLOADS and VET_DEP_PYPI_REGISTRY (including file:// URLs) -- this is
what lets tests/test_vet_dep.sh exercise the real fetch/parse/verdict code path
against committed fixtures with zero network access.
"""
import argparse, datetime, json, os, pathlib, re, sys, urllib.error, urllib.parse, urllib.request

TIMEOUT = 10
UA = "dependency-vetting-skill/1.0 (stdlib urllib; see skills/dependency-vetting)"

NPM_REGISTRY = os.environ.get("VET_DEP_NPM_REGISTRY", "https://registry.npmjs.org")
NPM_DOWNLOADS = os.environ.get("VET_DEP_NPM_DOWNLOADS",
                                "https://api.npmjs.org/downloads/point/last-week")
PYPI_REGISTRY = os.environ.get("VET_DEP_PYPI_REGISTRY", "https://pypi.org/pypi")

# Signals below this many months old are not flagged for staleness.
STALE_MONTHS = 18
# A release younger than this has had no time for the community to catch a
# compromised point release -- curl's dependabot cooldown (research/35) scales
# this by semver-bump size; we use one flat floor since we cannot tell what kind
# of bump this is without diffing two versions.
COOLDOWN_DAYS = 7
# Install footprint big enough to be worth a second look on its own.
LARGE_INSTALL_BYTES = 8_000_000
# Direct-dependency count above which the transitive tree is worth naming in the
# report, even though it does not by itself change the verdict (a framework with
# 28 direct deps and a one-line utility with 28 direct deps are different risks;
# this tool cannot tell them apart, so it reports rather than gates).
LARGE_DEP_NOTE = 25

# Permissive licences. Anything absent or not matching one of these tokens blocks.
PERMISSIVE = {"MIT", "ISC", "APACHE-2.0", "APACHE2.0", "BSD-2-CLAUSE", "BSD-3-CLAUSE",
              "BSD", "0BSD", "UNLICENSE", "PYTHON-2.0", "PSF-2.0", "MIT-0",
              "BLUEOAK-1.0.0", "CC0-1.0", "WTFPL", "ZLIB"}

# A short, illustrative list of very well known package names, used only to flag a
# name that suspiciously resembles one of them (typosquatting). Not exhaustive by
# design -- see SKILL.md for why a hand-list beats a fetched top-N here.
POPULAR_NAMES = {
    "react", "react-dom", "vue", "angular", "lodash", "underscore", "express",
    "axios", "request", "moment", "dayjs", "chalk", "commander", "debug",
    "webpack", "babel", "eslint", "jest", "mocha", "typescript", "next",
    "svelte", "redux", "rxjs", "socket.io", "jquery", "bootstrap",
    "tailwindcss", "vite", "rollup", "prettier", "zod", "joi", "yup", "dotenv",
    "cors", "body-parser", "mongoose", "sequelize", "prisma", "graphql",
    "fastify", "koa", "cross-env", "left-pad", "colors", "faker", "numpy",
    "pandas", "requests", "flask", "django", "fastapi", "pydantic", "scipy",
    "matplotlib", "pytest", "sqlalchemy", "celery", "boto3", "click", "pillow",
    "pyyaml", "jinja2", "cryptography", "urllib3", "setuptools", "six", "attrs",
    "typing-extensions", "ua-parser-js",
}


# --------------------------------------------------------------------------- #
# fetch


def fetch_json(url):
    """Return (data, error). error is None on success, else a human-readable string.

    Every network call in this tool goes through here, so "no network" is handled
    in exactly one place and cannot be silently skipped by a code path that forgot.
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, f"not found (HTTP 404) at {url}"
        return None, f"registry returned HTTP {e.code} for {url}"
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return None, f"could not reach the registry, cannot vet ({url}): {e.reason if hasattr(e, 'reason') else e}"
    except json.JSONDecodeError as e:
        return None, f"registry response at {url} was not valid JSON: {e}"


def levenshtein(a, b):
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1]


def typosquat_match(name):
    low = name.lower()
    if low in POPULAR_NAMES:
        return None
    best = None
    for p in POPULAR_NAMES:
        d = levenshtein(low, p)
        limit = 1 if len(p) <= 6 else 2
        if d <= limit and (best is None or d < best[1]):
            best = (p, d)
    return best


def months_between(then, now):
    return (now - then).days / 30.44


# --------------------------------------------------------------------------- #
# npm


def vet_npm(name, now):
    doc, err = fetch_json(f"{NPM_REGISTRY}/{urllib.parse.quote(name, safe='@/')}")
    if err:
        return None, err
    tags = doc.get("dist-tags", {})
    latest = tags.get("latest")
    versions = doc.get("versions", {})
    if not latest or latest not in versions:
        return None, f"'{name}' has no dist-tags.latest on npm -- cannot vet"
    vd = versions[latest]
    time = doc.get("time", {})
    published = time.get(latest)
    created = time.get("created") or (min((t for k, t in time.items()
                                            if k not in ("created", "modified")),
                                           default=published))

    dl, dl_err = fetch_json(f"{NPM_DOWNLOADS}/{name}")
    downloads = dl.get("downloads") if dl and not dl_err else None

    deprecated = bool(vd.get("deprecated")) or bool(doc.get("deprecated"))
    deprecated_msg = vd.get("deprecated") or doc.get("deprecated")

    license_raw = vd.get("license") or doc.get("license")
    if isinstance(license_raw, dict):
        license_raw = license_raw.get("type")

    repo = vd.get("repository")
    repo_url = repo.get("url") if isinstance(repo, dict) else repo

    scripts = vd.get("scripts") or {}
    install_scripts = sorted(s for s in ("preinstall", "install", "postinstall") if s in scripts)

    types = vd.get("types") or vd.get("typings")
    types_state = "bundled" if types else "not declared in package.json (check @types/" + name + " separately)"

    n_versions = len(versions)
    age_years = max(months_between(_parse(created), now), 1) / 12 if created else None

    return {
        "registry": "npm",
        "name": name,
        "version": latest,
        "published": published,
        "created": created,
        "n_versions": n_versions,
        "age_years": age_years,
        "downloads_week": downloads,
        "downloads_note": dl_err,
        "deprecated": deprecated,
        "deprecated_msg": deprecated_msg,
        "maintainers": len(doc.get("maintainers", []) or []),
        "maintainers_source": "npm maintainers field (publish-access accounts, not GitHub contributors)",
        "license": license_raw,
        "repo_url": repo_url,
        "n_deps": len(vd.get("dependencies") or {}),
        "install_size": (vd.get("dist") or {}).get("unpackedSize"),
        "install_scripts": install_scripts,
        "types": types_state,
    }, None


def _parse(iso):
    if not iso:
        return None
    return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))


# --------------------------------------------------------------------------- #
# pypi


def vet_pypi(name, now):
    doc, err = fetch_json(f"{PYPI_REGISTRY}/{name}/json")
    if err:
        return None, err
    info = doc.get("info", {})
    releases = doc.get("releases", {}) or {}
    version = info.get("version")
    urls = doc.get("urls", []) or []
    published = urls[0].get("upload_time_iso_8601") if urls else None
    if not published and version in releases and releases[version]:
        published = releases[version][0].get("upload_time_iso_8601")

    # PyPI's JSON API has no "maintainers" role list the way npm does -- the
    # closest public proxy is the author/maintainer email field(s), which is a
    # weaker signal (it can list people with no publish rights, or be stale).
    maint_field = info.get("maintainer_email") or info.get("author_email") or ""
    maint_count = len([p for p in maint_field.split(",") if p.strip()]) or 1

    license_raw = info.get("license_expression")
    if not license_raw:
        classifiers = info.get("classifiers") or []
        m = [c.split("::")[-1].strip() for c in classifiers if c.startswith("License ::")]
        license_raw = m[0] if m else (info.get("license") or None)

    deps = [d for d in (info.get("requires_dist") or []) if "extra ==" not in d]

    n_releases = len([k for k, v in releases.items() if v])
    all_upload_times = []
    for files in releases.values():
        for f in files:
            t = f.get("upload_time_iso_8601")
            if t:
                all_upload_times.append(_parse(t))
    created = min(all_upload_times) if all_upload_times else None
    age_years = max(months_between(created, now), 1) / 12 if created else None

    return {
        "registry": "pypi",
        "name": name,
        "version": version,
        "published": published,
        "created": created.isoformat() if created else None,
        "n_versions": n_releases,
        "age_years": age_years,
        "downloads_week": None,
        "downloads_note": "pypi.org/pypi does not expose download counts; pypistats.org "
                           "would be a separate call, not one of the three registries this "
                           "tool talks to",
        "deprecated": info.get("yanked", False),
        "deprecated_msg": info.get("yanked_reason") if info.get("yanked") else None,
        "maintainers": maint_count,
        "maintainers_source": "PyPI has no public maintainer-role list; this is a count of "
                               "distinct addresses in maintainer_email/author_email, a weaker proxy",
        "license": license_raw,
        "repo_url": (info.get("project_urls") or {}).get("Source")
                    or (info.get("project_urls") or {}).get("Homepage"),
        "n_deps": len(deps),
        "install_size": None,
        "install_scripts": [],
        "types": "n/a (pypi -- see py.typed marker in the sdist, not visible from this API)",
    }, None


# --------------------------------------------------------------------------- #
# verdict


def evaluate(sig, now):
    blocking, review, notes = [], [], []

    if sig["deprecated"]:
        blocking.append(f"deprecated in the registry: {sig['deprecated_msg'] or '(no message given)'}")

    lic = (sig["license"] or "").upper().replace(" ", "")
    if not sig["license"]:
        blocking.append("no licence declared -- cannot legally establish the right to use/adapt it")
    elif not any(tok in lic for tok in PERMISSIVE):
        blocking.append(f"licence '{sig['license']}' is not on the permissive allowlist "
                         f"({', '.join(sorted(PERMISSIVE))}) -- confirm it is compatible "
                         f"before depending on it")

    if sig["maintainers"] == 1:
        review.append(f"single maintainer ({sig['maintainers_source']}) -- a bus-factor and "
                       f"account-takeover risk (ua-parser-js, event-stream: both compromised "
                       f"through a single maintainer's account)")

    pub = _parse(sig["published"]) if sig["published"] else None
    if pub:
        age_months = months_between(pub, now)
        if age_months > STALE_MONTHS:
            review.append(f"last publish {age_months:.0f} months ago (flag threshold "
                           f"{STALE_MONTHS}mo) -- may simply be finished, not abandoned; "
                           f"check open issues/PRs before treating this as a red flag")
        elif age_months * 30.44 < COOLDOWN_DAYS:
            review.append(f"latest release is {age_months*30.44:.1f} days old (cooldown floor "
                           f"{COOLDOWN_DAYS}d) -- wait before adopting a brand-new release; "
                           f"see curl's semver-scaled dependabot cooldown")

    if sig["repo_url"]:
        notes.append(f"repository declared: {sig['repo_url']} (not fetched -- resolvability "
                      f"not checked over the network by this tool)")
    else:
        review.append("no repository link in registry metadata -- cannot inspect source, "
                       "issues, or who actually maintains this")

    if sig["install_scripts"]:
        review.append(f"has install-time script(s): {', '.join(sig['install_scripts'])} -- "
                       f"arbitrary code execution at `npm install` time (ua-parser-js 2021 "
                       f"shipped its payload exactly this way)")

    if sig["install_size"] and sig["install_size"] > LARGE_INSTALL_BYTES:
        review.append(f"install size {sig['install_size']/1_000_000:.1f} MB exceeds the "
                       f"{LARGE_INSTALL_BYTES/1_000_000:.0f} MB note threshold")

    tsq = typosquat_match(sig["name"])
    if tsq:
        review.append(f"name is edit-distance {tsq[1]} from popular package '{tsq[0]}' -- "
                       f"verify this is not a typosquat before installing (cross-env/crossenv "
                       f"is the canonical real incident)")

    if sig["n_deps"] > LARGE_DEP_NOTE:
        notes.append(f"{sig['n_deps']} direct dependencies (note threshold {LARGE_DEP_NOTE}) -- "
                      f"report only, since a framework and a one-line utility carry this "
                      f"differently; judge in context")
    else:
        notes.append(f"{sig['n_deps']} direct dependencies")

    if sig["downloads_week"] is not None:
        notes.append(f"~{sig['downloads_week']:,} weekly downloads (corroboration only -- "
                      f"never the reason to adopt)")
    elif sig["downloads_note"]:
        notes.append(f"downloads: {sig['downloads_note']}")

    if sig["age_years"]:
        notes.append(f"{sig['n_versions']} releases over ~{sig['age_years']:.1f} years "
                      f"({sig['n_versions']/sig['age_years']:.1f}/yr) -- a 0.x with hundreds "
                      f"of releases and a 0.x with 3 are different risk profiles")

    notes.append(f"types: {sig['types']}")

    verdict = "AVOID" if blocking else ("REVIEW" if review else "ADOPT")
    return verdict, blocking, review, notes


# --------------------------------------------------------------------------- #
# manifest discovery


def parse_pkg_name(spec):
    return re.match(r"^(@?[^<>=!~\s\[;]+)", spec).group(1) if spec.strip() else ""


def read_manifest_deps(root: pathlib.Path):
    """Return {'npm': [names], 'pypi': [names]} from package.json / pyproject.toml
    found in root. Pure file reads -- no network."""
    out = {"npm": [], "pypi": []}

    pj = root / "package.json"
    if pj.exists():
        try:
            data = json.loads(pj.read_text())
            out["npm"] = sorted((data.get("dependencies") or {}).keys())
        except (json.JSONDecodeError, OSError) as e:
            print(f"warning: could not parse {pj}: {e}", file=sys.stderr)

    pp = root / "pyproject.toml"
    if pp.exists():
        try:
            import tomllib
            data = tomllib.loads(pp.read_text())
            deps = list((data.get("project") or {}).get("dependencies") or [])
            poetry = (((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {})
            deps += [k for k in poetry.keys() if k.lower() != "python"]
            out["pypi"] = sorted({parse_pkg_name(d) for d in deps if parse_pkg_name(d)})
        except Exception as e:
            print(f"warning: could not parse {pp}: {e}", file=sys.stderr)

    return out


# --------------------------------------------------------------------------- #
# output


def print_report(sig, verdict, blocking, review, notes):
    print(f"\n{sig['name']} ({sig['registry']}) @ {sig['version']}  ->  {verdict}")
    print(f"  last publish: {sig['published']}")
    if blocking:
        print("  BLOCKING:")
        for b in blocking:
            print(f"    - {b}")
    if review:
        print("  REVIEW:")
        for r in review:
            print(f"    - {r}")
    print("  context:")
    for n in notes:
        print(f"    - {n}")


def vet_one(name, registry, now):
    fn = vet_npm if registry == "npm" else vet_pypi
    sig, err = fn(name, now)
    if err:
        return None, err
    verdict, blocking, review, notes = evaluate(sig, now)
    return {"signals": sig, "verdict": verdict, "blocking": blocking,
            "review": review, "notes": notes}, None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package", nargs="?", help="package name to vet")
    ap.add_argument("--registry", choices=["npm", "pypi"], default="npm")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON only")
    ap.add_argument("--check-manifest", action="store_true",
                     help="vet every direct dependency in package.json / pyproject.toml "
                          "found in the current directory")
    ap.add_argument("--list-only", action="store_true",
                     help="with --check-manifest: only list discovered deps, no network calls")
    a = ap.parse_args()

    now = datetime.datetime.now(datetime.timezone.utc)

    if a.check_manifest:
        found = read_manifest_deps(pathlib.Path.cwd())
        if a.list_only:
            if a.json:
                print(json.dumps(found, indent=2))
            else:
                for reg, names in found.items():
                    print(f"{reg}: {len(names)} direct dep(s)")
                    for n in names:
                        print(f"  {n}")
            return 0

        results, any_avoid, any_error = [], False, False
        for reg, names in found.items():
            for n in names:
                r, err = vet_one(n, reg, now)
                if err:
                    any_error = True
                    print(f"{n} ({reg}): could not vet -- {err}", file=sys.stderr)
                    continue
                results.append(r)
                if not a.json:
                    print_report(r["signals"], r["verdict"], r["blocking"], r["review"], r["notes"])
                if r["verdict"] == "AVOID":
                    any_avoid = True
        if a.json:
            print(json.dumps(results, indent=2, default=str))
        else:
            print(f"\n--check-manifest: {len(results)} vetted, "
                  f"{sum(1 for r in results if r['verdict']=='AVOID')} AVOID, "
                  f"{sum(1 for r in results if r['verdict']=='REVIEW')} REVIEW")
        return 1 if any_avoid else (2 if any_error and not results else 0)

    if not a.package:
        ap.error("a package name is required unless --check-manifest is given")

    r, err = vet_one(a.package, a.registry, now)
    if err:
        if a.json:
            print(json.dumps({"package": a.package, "registry": a.registry, "error": err}))
        else:
            print(f"{a.package} ({a.registry}): {err}", file=sys.stderr)
        return 2

    if a.json:
        print(json.dumps(r, indent=2, default=str))
    else:
        print_report(r["signals"], r["verdict"], r["blocking"], r["review"], r["notes"])
        if r["verdict"] == "AVOID":
            print("\n  verdict: AVOID -- see BLOCKING reasons above")
        elif r["verdict"] == "REVIEW":
            print("\n  verdict: REVIEW -- see REVIEW reasons above; not an automatic block")
        else:
            print("\n  verdict: ADOPT -- no blocking or review signals found")

    return 1 if r["verdict"] == "AVOID" else 0


if __name__ == "__main__":
    sys.exit(main())

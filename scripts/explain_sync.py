#!/usr/bin/env python3
"""Explain-page drift since the last sync: which merges to main touched which pages.

An explain page is a snapshot of the code at the moment it was checked. Every merge to
main can move a cited line, rename a function in a page's code reference, or add a part
no page covers, and nothing says so until a reader trips on it. This keeps a pin, the
last main commit the pages were synced to, in `explain/.sync.json` (committed, so every
clone and every session agrees), and compares against it. Think of a bookmark in a
changelog: the next sync starts reading where the last one stopped, instead of
re-checking every page from scratch.

    explain_sync.py status [--ref main] [--dir explain] [--repo .] [--json]
    explain_sync.py pin    [--ref main] [--dir explain] [--repo .] [--force]

`status` lists every first-parent commit on --ref since the pin (each merge of a PR is one;
one that changes only the docs folder, such as the sync itself, is skipped), the files it changed, and the pages that depend on any of them: a page depends on every
path its scenario.json cites (evidence `at` and absence `path`, `reference` files, and node
`ref`s naming a file; a box labelled with a folder such as `skills/` is display only). It also runs `flow check` on every page, so a page whose cited line moved shows up
even when no file it names changed in a way the path match sees, and lists changed
plugin files (skills/, scripts/, hooks/, agents/) that no page cites: candidates for a new
page. Exit 0 in sync (nothing since the pin and every page checks clean), 1 something to
do, 2 an error (no git, unreadable state, pin not on --ref's history).

`pin` moves the pin to --ref's tip after a sync. It refuses while any page fails
`flow check`, unless --force, so the pin never records a sync that did not happen.
"""
import argparse, datetime, json, pathlib, subprocess, sys

SCRIPTS = pathlib.Path(__file__).resolve().parent
STATE = ".sync.json"
SCHEMA = 1
PLUGIN_DIRS = ("skills/", "scripts/", "hooks/", "agents/")


class SyncError(Exception):
    pass


def git(repo, *args):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise SyncError(f"git {' '.join(args)}: {p.stderr.strip() or 'failed'}")
    return p.stdout


def resolve(repo, ref):
    return git(repo, "rev-parse", "--verify", "--quiet", ref + "^{commit}").strip()


def load_state(path):
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SyncError(f"cannot read {path}: {e}")
    if not isinstance(state, dict) or state.get("schema") != SCHEMA or not isinstance(state.get("pin"), str):
        raise SyncError(f"{path}: expected {{\"schema\": {SCHEMA}, \"pin\": \"<sha>\", ...}}")
    return state


def pages(explain_dir):
    return sorted(p.parent for p in explain_dir.glob("*/scenario.json"))


def page_paths(scenario):
    """Every repo path a page's claims rest on."""
    try:
        doc = json.loads(scenario.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    out = set()
    for e in (doc.get("evidence") or {}).values():
        if isinstance(e, dict):
            if isinstance(e.get("at"), str):
                out.add(e["at"].split("@")[0].rsplit(":", 1)[0])
            if isinstance(e.get("path"), str):
                out.add(e["path"])
    for r in doc.get("reference") or []:
        if isinstance(r, dict) and isinstance(r.get("path"), str):
            out.add(r["path"])
    for n in doc.get("nodes") or []:  # a box labelled with a whole folder claims nothing about it
        if isinstance(n, dict) and isinstance(n.get("ref"), str) and not n["ref"].endswith("/"):
            out.add(n["ref"].split(":")[0])
    return {p for p in out if p}


def depends(paths, changed):
    """Changed files a page depends on; a cited path ending in / (or a pathspec dir) matches beneath it."""
    hit = set()
    for c in changed:
        for p in paths:
            if c == p or c.startswith(p.rstrip("/") + "/"):
                hit.add(c)
    return hit


def merges_since(repo, pin, tip, docs_dir):
    """[(sha, subject, [files])] for each first-parent commit in pin..tip, oldest first. A commit
    that changes only files under docs_dir is the docs themselves (a sync, its pin) and is left
    out, or every sync would leave one unsynced merge behind it."""
    if pin == tip:
        return []
    try:
        git(repo, "merge-base", "--is-ancestor", pin, tip)
    except SyncError:
        raise SyncError(f"the pin {pin[:12]} is not on the history of the ref; history was rewritten. "
                        "Check every page, then run `explain_sync pin --force`")
    out = []
    log = git(repo, "log", "--first-parent", "--reverse", "--format=%H%x09%s", f"{pin}..{tip}")
    for line in log.splitlines():
        sha, _, subject = line.partition("\t")
        files = git(repo, "diff", "--name-only", f"{sha}^1", sha).split()
        if files and all(f.startswith(docs_dir + "/") for f in files):
            continue
        out.append((sha, subject, files))
    return out


def flow_check(repo, scenario):
    p = subprocess.run([sys.executable, str(SCRIPTS / "flow.py"), "check", str(scenario), "--repo", str(repo),
                        "--json"], capture_output=True, text=True)
    try:
        findings = json.loads(p.stdout).get("findings", [])
    except ValueError:
        findings = [{"loc": "flow check", "message": (p.stderr.strip() or "no output").splitlines()[-1]}]
    return p.returncode, findings


def status(repo, ref, explain_dir, docs_dir):
    tip = resolve(repo, ref)
    state = load_state(explain_dir / STATE)
    pin = state["pin"] if state else None
    if pin:
        pin = resolve(repo, pin)
    merges = merges_since(repo, pin, tip, docs_dir) if pin else []
    changed = sorted({f for _, _, files in merges for f in files})
    report = {"ref": ref, "tip": tip, "pin": pin, "merges": [], "pages": [], "uncovered": []}
    for sha, subject, files in merges:
        report["merges"].append({"sha": sha, "subject": subject, "files": files})
    cited = set()
    for page in pages(explain_dir):
        paths = page_paths(page / "scenario.json")
        cited |= paths
        rc, findings = flow_check(repo, page / "scenario.json")
        touched = sorted(depends(paths, changed))
        by = [m["sha"][:12] for m in report["merges"] if depends(paths, m["files"])]
        report["pages"].append({"page": page.name, "check_ok": rc == 0, "findings": findings,
                                "changed_files": touched, "merges": by,
                                "needs_sync": rc != 0 or bool(touched)})
    report["uncovered"] = [f for f in changed if f.startswith(PLUGIN_DIRS) and not depends(cited, [f])]
    report["in_sync"] = bool(pin) and not merges and all(p["check_ok"] for p in report["pages"])
    return report


def print_status(r):
    print(f"explain_sync: {r['ref']} at {r['tip'][:12]}, pin "
          + (r["pin"][:12] if r["pin"] else "none (never synced: run `explain_sync pin` once every page checks clean)"))
    if r["merges"]:
        print(f"\nmerges since the pin ({len(r['merges'])}):")
        for m in r["merges"]:
            print(f"  {m['sha'][:12]} {m['subject']} ({len(m['files'])} files)")
    print("\npages:")
    for p in r["pages"]:
        mark = "SYNC" if p["needs_sync"] else "ok  "
        why = []
        if not p["check_ok"]:
            why.append(f"flow check: {len(p['findings'])} finding(s)")
        if p["changed_files"]:
            why.append("cites changed " + ", ".join(p["changed_files"][:4])
                       + (f" +{len(p['changed_files']) - 4}" if len(p["changed_files"]) > 4 else "")
                       + f" (merges {', '.join(p['merges'])})")
        print(f"  {mark} {p['page']}" + (": " + "; ".join(why) if why else ""))
        for f in p["findings"][:3]:
            print(f"         {f['loc']}: {f['message']}")
    if r["uncovered"]:
        print("\nchanged plugin files no page cites (a new page, or a line on an existing one?):")
        for f in r["uncovered"]:
            print(f"  {f}")
    n = sum(p["needs_sync"] for p in r["pages"])
    print("\nexplain_sync: " + ("in sync" if r["in_sync"] else f"{n} page(s) to sync" if n else
                                "no page affected; review the files above, then `explain_sync pin`"
                                if r["pin"] else "no pin yet"))


def pin(repo, ref, explain_dir, docs_dir, force):
    r = status(repo, ref, explain_dir, docs_dir)
    failing = [p["page"] for p in r["pages"] if not p["check_ok"]]
    if failing and not force:
        raise SyncError(f"not pinned: {', '.join(failing)} fail flow check; fix them, or pass --force")
    state = {"schema": SCHEMA, "pin": r["tip"], "ref": ref,
             "pinned_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "pages": [p["page"] for p in r["pages"]]}
    (explain_dir / STATE).write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")
    old = r["pin"][:12] if r["pin"] else "none"
    print(f"explain_sync: pinned {old} -> {r['tip'][:12]} ({len(r['pages'])} page(s))")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="100x explain_sync", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("status", "pin"):
        s = sub.add_parser(name)
        s.add_argument("--ref", default="main", help="the branch merges land on (default main)")
        s.add_argument("--dir", default="explain", help="folder holding one sub-folder per page")
        s.add_argument("--repo", default=".")
        if name == "status":
            s.add_argument("--json", action="store_true")
        else:
            s.add_argument("--force", action="store_true", help="pin even though a page fails flow check")
    a = ap.parse_args(argv)
    repo = pathlib.Path(a.repo)
    explain_dir = repo / a.dir
    try:
        if not explain_dir.is_dir():
            raise SyncError(f"no {explain_dir} folder")
        if a.cmd == "pin":
            pin(repo, a.ref, explain_dir, a.dir.strip("/"), a.force)
            return 0
        r = status(repo, a.ref, explain_dir, a.dir.strip("/"))
        if a.json:
            print(json.dumps(r, indent=1))
        else:
            print_status(r)
        return 0 if r["in_sync"] else 1
    except SyncError as e:
        print(f"100x explain_sync: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Prove every suggestion/diff in a review applies to the pinned head, and optionally typechecks.

    pr_suggest.py <pr-dir | review.json> --repo CLONE [--snap SNAP] [--cmd "<typecheck>"]
                  [--link REL=ABS]... [--note "<why no typecheck>"] [--write]

The head tree is copied into a temporary directory (from <snap>/<pr> when --snap is given,
else `git archive <pr.head_sha>` from --repo); the clone and the snapshot are never written.
  --cmd    run from the work copy root after each change, e.g. "npx tsc --noEmit -p backend";
           split into an argument list (no shell); exit 0 = ok
  --link   symlink deps into the work copy, e.g. backend/node_modules=<clone>/backend/node_modules
  --note   recorded when no --cmd is given, e.g. "no node_modules in the snapshot"
  --write  update review.json: change.checked per result; a change that does not apply or fails
           the command is downgraded to type "pseudo". Without --write: report only.
Always writes <pr-dir>/suggestion-checks.json -- the proof the gate (G5-checked) matches every
"... ok" / "applies cleanly" claim against. Exit codes: 0 ok, 1 cannot run, 2 usage.
Python stdlib only.
"""
import argparse, hashlib, io, json, pathlib, shlex, shutil, subprocess, sys, tarfile, tempfile

TAIL_CHARS = 120


def apply_suggestion(text, item):
    w = item["where"]; a, b = (w.get("start_line") or w["line"]), w["line"]
    lines = text.split("\n")
    if b > len(lines): return None
    return "\n".join(lines[:a - 1] + item["change"]["body"].rstrip("\n").split("\n") + lines[b:])


def parse_diff(body):
    """[(path, [(old_block, new_block)])] -- hunks matched by content, not by @@ numbers (agents get those wrong)."""
    files, cur, hunk = [], None, None
    for l in body.split("\n"):
        if l.startswith("--- "): continue
        if l.startswith("+++ "):
            p = l[4:].strip(); cur = (p[2:] if p.startswith("b/") else p, []); files.append(cur); hunk = None; continue
        if l.startswith("@@"):
            if cur is None: continue
            hunk = ([], []); cur[1].append(hunk); continue
        if cur is None: continue
        if hunk is None: hunk = ([], []); cur[1].append(hunk)
        tag, rest = (l[:1], l[1:]) if l[:1] in "+- " else (" ", l)
        if tag in " -": hunk[0].append(rest)
        if tag in " +": hunk[1].append(rest)
    return files


def inside(root, rel):
    p = (root / rel).resolve()
    return p if root.resolve() in p.parents else None


def apply_diff(root, body):
    changed = {}
    for path, hunks in parse_diff(body):
        f = inside(root, path)
        if f is None or not f.is_file(): return None, f"{path} not found"
        lines = changed.get(path, f.read_text(errors="replace")).split("\n")
        for old, new in hunks:
            strip = [x.rstrip() for x in old]
            hits = [k for k in range(len(lines) - len(old) + 1) if [x.rstrip() for x in lines[k:k + len(old)]] == strip]
            if len(hits) != 1: return None, f"{path}: hunk context found {len(hits)} times (want 1)"
            k = hits[0]; lines = lines[:k] + new + lines[k + len(old):]
        changed[path] = "\n".join(lines)
    return changed, None


def fill_tree(work, r, repo, snap):
    if snap:
        tree = pathlib.Path(snap) / str(r["pr"]["number"])
        if not tree.is_dir(): raise RuntimeError(f"no snapshot tree {tree}")
        shutil.copytree(tree, work, symlinks=True, dirs_exist_ok=True)
        return
    p = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", r["pr"]["head_sha"]], capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"git archive {r['pr']['head_sha']} failed in {repo}: {p.stderr.decode(errors='replace').strip()} "
                           "(fetch the PR head first, or pass --snap)")
    with tarfile.open(fileobj=io.BytesIO(p.stdout)) as tf:
        for m in tf.getmembers():
            if inside(work, m.name) is None and m.name not in (".", "./"):
                raise RuntimeError(f"archive member escapes the work copy: {m.name}")
        tf.extractall(work, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))


def run_cmd(argv, work):
    try:
        pr = subprocess.run(argv, cwd=work, capture_output=True, text=True)
    except OSError as e:
        return False, f"not checked — command could not start: {e}"
    if pr.returncode == 0: return True, "typecheck ok"
    out = (pr.stdout + pr.stderr).strip()
    tail = out.splitlines()[-1][:TAIL_CHARS] if out else f"exit {pr.returncode}"
    return False, f"not checked — typecheck failed: {tail}"


def check(d, r, a, work):
    argv = shlex.split(a.cmd) if a.cmd else None
    note = a.note or "no typecheck command given"
    for l in a.link:
        rel, src = l.split("=", 1)
        dst = inside(work, rel)
        if dst is None: raise RuntimeError(f"--link {rel} escapes the work copy")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists(): dst.symlink_to(src)
    log = {}
    for i in r["items"]:
        ch = i["change"]
        if ch["type"] not in ("suggestion", "diff"): continue
        if ch["type"] == "suggestion":
            p = i["where"]["path"]; f = inside(work, p) if p else None
            new = apply_suggestion(f.read_text(errors="replace"), i) if f is not None and f.is_file() else None
            changed, err = ({p: new}, None) if new is not None else (None, f"{p} L{i['where']['line']} not found")
        else:
            changed, err = apply_diff(work, ch["body"])
        h = hashlib.sha256(ch["body"].encode()).hexdigest()
        if err:
            res, ok = f"not checked — does not apply ({err})", False
        else:
            saved = {p: (work / p).read_text(errors="replace") for p in changed}
            for p, t in changed.items(): (work / p).write_text(t)
            if argv: ok, res = run_cmd(argv, work)
            else: ok, res = True, f"applies cleanly — typecheck not run ({note})"
            for p, t in saved.items(): (work / p).write_text(t)
        log[i["id"]] = {"sha256": h, "result": res, "cmd": a.cmd}
        print(f"{i['id']:16} {ch['type']:10} {res}")
        if a.write:
            ch["checked"] = res
            if not ok: ch["type"] = "pseudo"; log[i["id"]]["downgraded"] = True
    return log


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pr_suggest.py", description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="PR folder or its review.json")
    ap.add_argument("--repo", required=True, help="local clone holding pr.head_sha")
    ap.add_argument("--snap", help="pr_snapshot.py --dest dir; its <pr>/ tree is used instead of git archive")
    ap.add_argument("--cmd", help="typecheck/lint command, run without a shell")
    ap.add_argument("--link", action="append", default=[], metavar="REL=ABS")
    ap.add_argument("--note", help="why no typecheck ran")
    ap.add_argument("--write", action="store_true", help="update review.json with the results")
    a = ap.parse_args(argv)
    d = pathlib.Path(a.target)
    if d.name == "review.json": d = d.parent
    if not (d / "review.json").is_file(): print(f"pr_suggest: no review.json in {d}", file=sys.stderr); return 2
    if any("=" not in l for l in a.link): print("pr_suggest: --link wants REL=ABS", file=sys.stderr); return 2
    r = json.loads((d / "review.json").read_text(encoding="utf-8"))
    try:
        with tempfile.TemporaryDirectory(prefix="pr-suggest-") as tmp:
            work = pathlib.Path(tmp) / "head"
            work.mkdir()
            fill_tree(work, r, a.repo, a.snap)
            log = check(d, r, a, work)
    except RuntimeError as e:
        print(f"pr_suggest: {e}", file=sys.stderr); return 1
    (d / "suggestion-checks.json").write_text(json.dumps(log, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if a.write: (d / "review.json").write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Count which key points from a guide's inventory the built guide actually covers.

The accuracy log's "Key points in source: N · covered: N" line used to be written from
memory, so it always matched. This script computes it from markup instead:

  inventory.json  {"source": "...", "key_points": [
                     {"id": "kp-1", "text": "...", "label": "From source", "page": "intro"},
                     {"id": "kp-9", "text": "...", "excluded": "off-topic tangent"}]}
                  (a bare list of key points is also accepted)
  HTML / JSX      data-kp="kp-1"  or  data-kp="kp-1 kp-2"
  Markdown        <!-- kp:kp-1 -->  or  <!-- kp:kp-1,kp-2 -->

A key point is covered when its id is tagged anywhere in the guide. An item with an
"excluded" reason counts as intentionally excluded and must NOT be tagged.
Files named accuracy-log.md and inventory.json are never scanned.

Usage: coverage_check.py <inventory.json> <guide-file-or-dir> [--json]
Exit: 0 every key point covered or excluded; 1 missing, unknown or excluded-but-tagged
ids; 2 bad input (unreadable inventory, duplicate ids, no guide files).
Python 3.9+, stdlib only.
"""
import argparse
import json
import pathlib
import re
import sys

GUIDE_EXT = {".html", ".htm", ".md", ".mdx", ".jsx", ".tsx", ".js"}
SKIP_NAMES = {"accuracy-log.md", "inventory.json"}
ID_RX = re.compile(r"^[A-Za-z0-9_.:-]+$")
MD_TAG_RX = re.compile(r"<!--\s*kp:\s*([^>]*?)\s*-->")
HTML_COMMENT_RX = re.compile(r"<!--.*?-->", re.S)
ATTR_RX = re.compile(r"""data-kp\s*=\s*(?:"([^"]*)"|'([^']*)'|\{\s*["'`]([^"'`]*)["'`]\s*\})""")


def fail(msg):
    print(f"coverage_check: {msg}", file=sys.stderr)
    sys.exit(2)


def load_inventory(path):
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        fail(f"cannot read inventory {path}: {e}")
    items = data.get("key_points") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        fail(f"{path}: expected a non-empty 'key_points' list")
    seen, out = set(), []
    for i, kp in enumerate(items):
        kid = kp.get("id") if isinstance(kp, dict) else None
        if not isinstance(kid, str) or not ID_RX.match(kid):
            fail(f"{path}: key point #{i + 1} has no valid 'id' (letters, digits, - _ . :)")
        if kid in seen:
            fail(f"{path}: duplicate key point id '{kid}'")
        seen.add(kid)
        out.append(kp)
    return out


def guide_files(target):
    p = pathlib.Path(target)
    if p.is_file():
        return [p]
    if p.is_dir():
        return sorted(f for f in p.rglob("*")
                      if f.is_file() and f.suffix.lower() in GUIDE_EXT
                      and f.name not in SKIP_NAMES
                      and "node_modules" not in f.parts)
    fail(f"guide path not found: {target}")


def split_ids(raw):
    return [t for t in re.split(r"[\s,]+", raw.strip()) if t]


def tags_in(text):
    """Return every kp id tagged in one file's text."""
    found = []
    for m in MD_TAG_RX.finditer(text):
        found += split_ids(m.group(1))
    # data-kp written inside an ordinary HTML comment is documentation, not coverage.
    body = HTML_COMMENT_RX.sub("", text)
    for m in ATTR_RX.finditer(body):
        found += split_ids(next(g for g in m.groups() if g is not None))
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("inventory")
    ap.add_argument("guide", help="a guide file, or a directory scanned recursively")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    items = load_inventory(a.inventory)
    files = guide_files(a.guide)
    if not files:
        fail(f"no guide files ({', '.join(sorted(GUIDE_EXT))}) under {a.guide}")

    where = {}
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            fail(f"cannot read {f}: {e}")
        for kid in tags_in(text):
            where.setdefault(kid, set()).add(str(f))

    known = {kp["id"] for kp in items}
    excluded = [kp["id"] for kp in items if kp.get("excluded")]
    included = [kp["id"] for kp in items if not kp.get("excluded")]
    covered = [k for k in included if k in where]
    missing = [k for k in included if k not in where]
    tagged_excluded = [k for k in excluded if k in where]
    unknown = sorted(k for k in where if k not in known)

    result = {"key_points": len(items), "covered": len(covered),
              "excluded": len(excluded), "missing": missing,
              "unknown_ids": unknown, "excluded_but_tagged": tagged_excluded,
              "files_scanned": len(files)}
    ok = not (missing or unknown or tagged_excluded)
    if a.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Key points in source: {len(items)} · covered: {len(covered)} · "
              f"intentionally excluded: {len(excluded)} · missing: {len(missing)}")
        texts = {kp["id"]: str(kp.get("text", "")) for kp in items}
        for k in missing:
            print(f"  MISSING  {k}  {texts[k][:80]}")
        for k in unknown:
            print(f"  UNKNOWN  {k}  tagged in {', '.join(sorted(where[k]))} but not in the inventory")
        for k in tagged_excluded:
            print(f"  EXCLUDED-BUT-TAGGED  {k}  marked excluded in the inventory")
        print(f"coverage_check: {len(files)} file(s) scanned -> {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

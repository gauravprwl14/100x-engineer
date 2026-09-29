#!/usr/bin/env python3
"""Compare a spec's mermaid sequence diagram against the implementation.

The gap this closes: a sequence diagram is drawn once, the code then evolves, and
nothing notices. Worse for agent-written code, where the diagram is often the only
place the intended design was ever stated.

This is a NAME-LEVEL check, deliberately. It does not verify behaviour — it verifies
that every participant and every message in the diagram has a plausible counterpart
in the code, and that the code has no major collaborator the diagram never mentions.
It reports both directions, because drift runs both ways.

    design_drift.py specs/login/spec.md src/auth
    design_drift.py specs/login/spec.md src/auth --json

Exit 1 if anything in the diagram has no counterpart in the code.
Python stdlib only.
"""
import argparse, json, pathlib, re, sys

PARTICIPANT = re.compile(
    r"^\s*(?:actor|participant)\s+(\w+)(?:\s+as\s+(.+?))?\s*$", re.M)
MESSAGE = re.compile(
    r"^\s*(\w+)\s*(?:-->>|->>|-->|->|-x|--x)\s*(\w+)\s*:\s*(.+?)\s*$", re.M)
CODE_EXT = {".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".java", ".kt", ".swift",
            ".dart", ".rb", ".cs", ".rs"}
SKIP_DIRS = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__",
             ".next", "coverage", ".turbo"}


def extract_diagram(spec_text):
    blocks = re.findall(r"```mermaid\s*\n(.*?)```", spec_text, re.S)
    for b in blocks:
        if "sequenceDiagram" in b:
            return b
    return None


CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def norm(s):
    """Reduce a label to comparable tokens, splitting camelCase as well as
    punctuation. 'PasswordHasher' -> ['password','hasher'] so a partial match on
    'password' alone no longer counts as present."""
    s = CAMEL.sub(" ", s)
    return [w for w in re.split(r"[^a-z0-9]+", s.lower()) if len(w) > 2]


def present(tokens, *haystacks):
    """A label counts as implemented only when MOST of its significant tokens appear.
    `any()` was too lenient: 'verify(password, hash)' matched code containing only
    'password', hiding a missing verification step -- a real false negative."""
    if not tokens:
        return True
    hits = sum(1 for t in tokens if any(t in h for h in haystacks))
    return hits * 2 >= len(tokens) + (1 if len(tokens) > 1 else 0)


LINE_COMMENT = re.compile(r"(?m)^\s*(?://|#).*$")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/|\"\"\".*?\"\"\"|'''.*?'''", re.S)
TRAILING_COMMENT = re.compile(r"(?m)\s+(?://|#)\s.*$")


def strip_comments(text):
    """Comments must not count as implementation.

    Found the hard way: a source comment reading "omits the PasswordHasher verify
    step" made both `PasswordHasher` and `verify` look implemented. A diagram element
    is only present if real code references it.
    """
    text = BLOCK_COMMENT.sub(" ", text)
    text = LINE_COMMENT.sub(" ", text)
    return TRAILING_COMMENT.sub(" ", text)


def read_code(root):
    files, blob = [], []
    for p in sorted(pathlib.Path(root).rglob("*")):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.is_file() and p.suffix in CODE_EXT:
            try:
                blob.append(strip_comments(p.read_text(errors="replace")))
                files.append(p)
            except OSError:
                pass
    return files, "\n".join(blob)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("code_dir")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--external", default=None,
                    help="comma-separated participant aliases that live outside this "
                         "code path (also settable in the diagram via `%% external: C`)")
    a = ap.parse_args()

    spec_p = pathlib.Path(a.spec)
    if not spec_p.exists():
        print(f"no spec at {a.spec}", file=sys.stderr); return 2
    diagram = extract_diagram(spec_p.read_text())
    if not diagram:
        print("no mermaid sequenceDiagram found in the spec", file=sys.stderr); return 2

    # Participants that live outside the scanned code can be declared in the diagram
    # itself with `%% external: C, U`, so the exclusion travels with the design rather
    # than living in a command line someone forgets to pass.
    external = set()
    for m in re.finditer(r"%%\s*external\s*:\s*(.+)", diagram):
        external |= {x.strip() for x in m.group(1).split(",") if x.strip()}
    if a.external:
        external |= {x.strip() for x in a.external.split(",") if x.strip()}

    parts, actors = {}, set()
    for m in PARTICIPANT.finditer(diagram):
        alias, label = m.group(1), (m.group(2) or m.group(1)).strip()
        parts[alias] = label
        if m.group(0).lstrip().startswith("actor") or alias in external:
            actors.add(alias)
    msgs = [(m.group(1), m.group(2), m.group(3)) for m in MESSAGE.finditer(diagram)]

    code_root = pathlib.Path(a.code_dir)
    if not code_root.exists():
        print(f"code path {a.code_dir} does not exist — nothing implemented yet")
        print(f"diagram declares {len(parts)} participants and {len(msgs)} messages; "
              f"all are unimplemented")
        return 1
    files, code = read_code(code_root)
    code_l = code.lower()
    names = " ".join(f.stem.lower() for f in files)

    missing_parts, missing_msgs = [], []
    for alias, label in parts.items():
        if alias in actors:
            continue          # an `actor` is external by declaration; absent by design
        toks = norm(label) or [alias.lower()]
        if not present(toks, code_l, names):
            missing_parts.append((alias, label))

    for src, dst, text in msgs:
        toks = norm(text)
        if not toks:
            continue
        if src in actors or dst in actors:
            continue          # user-facing interactions are not backend symbols
        if not present(toks, code_l):
            missing_msgs.append((src, dst, text))

    # reverse direction: prominent code collaborators the diagram never mentions
    diagram_tokens = set()
    for label in parts.values():
        diagram_tokens |= set(norm(label))
    for _, _, t in msgs:
        diagram_tokens |= set(norm(t))
    CLASSY = re.compile(r"\b(?:class|interface)\s+([A-Z]\w{3,})")
    code_syms = {}
    for m in CLASSY.finditer(code):
        code_syms[m.group(1)] = code_syms.get(m.group(1), 0) + 1
    undocumented = [s for s in code_syms
                    if not any(t in s.lower() for t in diagram_tokens)]

    result = {
        "participants": len(parts), "messages": len(msgs),
        "code_files": len(files),
        "missing_participants": [{"alias": a_, "label": l} for a_, l in missing_parts],
        "missing_messages": [{"from": s, "to": d, "text": t} for s, d, t in missing_msgs],
        "undocumented_symbols": sorted(undocumented)[:20],
    }
    if a.json:
        print(json.dumps(result, indent=2))
        return 1 if (missing_parts or missing_msgs) else 0

    print(f"design_drift: {spec_p.name} vs {a.code_dir}")
    print(f"  diagram: {len(parts)} participants ({len(actors)} external actor(s) "
          f"excluded), {len(msgs)} messages")
    print(f"  code   : {len(files)} files")
    if missing_parts:
        print(f"\n  [DRIFT] {len(missing_parts)} participant(s) in the diagram with no "
              f"counterpart in the code:")
        for al, lb in missing_parts:
            print(f"      {al} ({lb})")
    if missing_msgs:
        print(f"\n  [DRIFT] {len(missing_msgs)} message(s) in the diagram not found in "
              f"the code:")
        for s, d, t in missing_msgs[:12]:
            print(f"      {s} -> {d}: {t}")
        if len(missing_msgs) > 12:
            print(f"      ... {len(missing_msgs)-12} more")
    if undocumented:
        print(f"\n  [INFO] {len(undocumented)} class/interface(s) in the code the diagram "
              f"never mentions — either fine, or the design moved:")
        for s in sorted(undocumented)[:12]:
            print(f"      {s}")
    if not missing_parts and not missing_msgs:
        print("\n  no drift: every participant and message has a counterpart in the code")
        return 0
    print(f"\nThis is a name-level check. A match does not prove the behaviour is right; "
          f"a miss proves the diagram and the code disagree.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

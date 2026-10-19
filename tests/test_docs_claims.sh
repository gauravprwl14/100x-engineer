#!/usr/bin/env bash
# Every count README.md and AGENTS.md state about this repo must match the repo. A
# stale "29 skills" or "68 assertions" is the claim-without-evidence this plugin exists
# to reject, so the numbers are checked against the files they count.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %-60s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %-60s\n' "$1"; [ -s "$TMP/out" ] && sed 's/^/       /' "$TMP/out" | head -6; }

# check <dir holding README.md and AGENTS.md>: reality always comes from $ROOT, the
# claims from <dir>, so a mutated copy can be checked against the real repo.
check() {
  python3 - "$ROOT" "$1" <<'PY'
import pathlib, re, subprocess, sys
root, docs = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
errs = []

def listed(*args):
    out = subprocess.run([str(root / "bin" / "100x"), "list", *args],
                         capture_output=True, text=True).stdout
    return [l.strip() for l in out.splitlines() if l.startswith("  ")]
# "tools" counts every tool (`100x list --all`); `100x list` hides the maintainer ones.
tools = listed("--all")
maintainer = sorted(set(tools) - set(listed()))
real = {
    "skills": len(list(root.glob("skills/*/SKILL.md"))),
    "agents": len(list(root.glob("agents/*.md"))),
    "tools": len(tools),
    "maintainer tools": len(maintainer),
    "test suites": len(list(root.glob("tests/test_*.sh"))),
}
readme = (docs / "README.md").read_text()
agents_md = (docs / "AGENTS.md").read_text()

# The stable sentence forms: "**40 skills**" in both files; README also says
# "the 40 skills", "the 38 command-line tools", "the 5 maintainer tools" and
# "# 37 test suites".
forms = {
    "README.md": (readme, {"skills": [r"\*\*(\d+) skills\*\*", r"the (\d+) skills"],
                           "agents": [r"\*\*(\d+) agents\*\*", r"the (\d+) specialists"],
                           "tools": [r"\*\*(\d+) tools\*\*", r"the (\d+) command-line tools"],
                           "maintainer tools": [r"the (\d+) maintainer tools"],
                           "test suites": [r"# (\d+) test suites"]}),
    "AGENTS.md": (agents_md, {k: [r"\*\*(\d+) " + k + r"\*\*"] for k in real
                              if k != "maintainer tools"}),
}
for fname, (text, pats) in forms.items():
    for what, rxs in pats.items():
        for rx in rxs:
            found = [int(n) for n in re.findall(rx, text)]
            if not found:
                errs.append(f"{fname}: no claim matching /{rx}/ -- keep the stable form")
            for n in found:
                if n != real[what]:
                    errs.append(f"{fname}: says {n} {what}, the repo has {real[what]}")

# README's phase table must agree with the generated skills/INDEX.md, row by row.
idx = (root / "skills" / "INDEX.md").read_text()
want = {}
for m in re.finditer(r"^\| (\d [a-z ]+?) \| \[", idx, re.M):
    want[m.group(1)] = want.get(m.group(1), 0) + 1
got = {m.group(1): int(m.group(2))
       for m in re.finditer(r"^\| (\d [a-z ]+?) \| (\d+) \|", readme, re.M)}
if got != want:
    errs.append(f"README.md skills-by-phase {got} != skills/INDEX.md {want}")
if sum(got.values()) != real["skills"]:
    errs.append(f"README.md phase counts sum to {sum(got.values())}, not {real['skills']}")

# Every tool `100x list` prints is named in README's tools section.
named = set(re.findall(r"`([a-z][a-z0-9_]+)`", readme.split("## Tools", 1)[-1].split("\n## ", 1)[0]))
missing = [t for t in tools if t not in named]
if missing:
    errs.append(f"README.md tools table is missing: {', '.join(missing)}")
# ...and the maintainer row names exactly the tools `100x list` hides.
row = re.search(r"^\| maintainer only[^|]*\|([^\n]*)\|$", readme, re.M)
in_row = sorted(re.findall(r"`([a-z][a-z0-9_]+)`", row.group(1))) if row else None
if in_row != maintainer:
    errs.append(f"README.md 'maintainer only' tools row {in_row} != hidden tools {maintainer}")

# Assertion totals go stale on every new test, so neither file states one, and the
# prove-it section states no suite count either (the checked sentence above does).
for fname, text in (("README.md", readme), ("AGENTS.md", agents_md)):
    for m in re.finditer(r"\b\d+ assertions\b", text):
        errs.append(f"{fname}: states an assertion total ({m.group(0)!r})")
prove = agents_md.split("## Prove-it command", 1)[-1].split("\n## ", 1)[0]
for m in re.finditer(r"\b\d+\s+(?:suites|test suites)\b|\(\d+ [a-z]+\)", prove):
    errs.append(f"AGENTS.md prove-it section states a count ({m.group(0)!r})")

for e in errs:
    print(e)
sys.exit(1 if errs else 0)
PY
}

check "$ROOT" >"$TMP/out" 2>&1 && ok "README.md and AGENTS.md counts match the repo" \
  || bad "README.md or AGENTS.md states a stale count"

# --- detection: each mutated copy must fail ---
mutate() {  # mutate <label> <file> <python expression over t>
  local d="$TMP/m"; rm -rf "$d"; mkdir -p "$d"
  cp "$ROOT/README.md" "$ROOT/AGENTS.md" "$d/"
  python3 -c "import pathlib,re,sys; p=pathlib.Path(sys.argv[1]); t=p.read_text(); n=$3; assert n!=t, 'mutation did not apply'; p.write_text(n)" "$d/$2" \
    || { bad "$1: mutation did not apply"; return; }
  if check "$d" >"$TMP/out" 2>&1; then bad "$1: not detected"; else ok "$1: detected"; fi
}
mutate "README wrong skill count"     README.md 're.sub(r"\*\*(\d+) skills\*\*", lambda m: "**%d skills**" % (int(m.group(1))+1), t, count=1)'
mutate "AGENTS.md wrong agent count"  AGENTS.md 're.sub(r"\*\*(\d+) agents\*\*", lambda m: "**%d agents**" % (int(m.group(1))-1), t, count=1)'
mutate "AGENTS.md wrong suite count"  AGENTS.md 're.sub(r"\*\*(\d+) test suites\*\*", lambda m: "**%d test suites**" % (int(m.group(1))+3), t, count=1)'
mutate "README wrong tool count"      README.md 're.sub(r"the (\d+) command-line tools", lambda m: "the %d command-line tools" % (int(m.group(1))+2), t, count=1)'
mutate "README drops the skill claim" README.md 're.sub(r"\*\*(\d+) skills\*\*", "many skills", t)'
mutate "README phase count off by one" README.md 're.sub(r"^\| 4 when broken \| (\d+) \|", lambda m: "| 4 when broken | %d |" % (int(m.group(1))+1), t, count=1, flags=re.M)'
mutate "README tool missing from table" README.md 't.replace("`vet_dep`, ", "", 1)'
mutate "README wrong maintainer count" README.md 're.sub(r"the (\d+) maintainer tools", lambda m: "the %d maintainer tools" % (int(m.group(1))+1), t, count=1)'
mutate "README maintainer row drifts" README.md 're.sub(r"(^\| maintainer only[^|]*\|[^\n]*?)`run_evals`, ", r"\1", t, count=1, flags=re.M)'
mutate "AGENTS.md stale assertion total" AGENTS.md 't.replace("## Prove-it command\n", "## Prove-it command\n\nFour suites (68 assertions).\n", 1)'

echo
echo "docs-claims: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]

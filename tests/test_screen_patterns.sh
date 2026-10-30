#!/usr/bin/env bash
# Regression suite for the screen-pattern checklists: scripts/data/edge_cases_ui.json
# (screen-behaviour families and role templates), scripts/data/screen_patterns.json
# (generic screen names -> families), a project's own <records root>/screen_patterns.json
# layered on top, and the plan_feature surfaces that use them (`new --screens/--roles`,
# `cases`, the audit's role rows).
#
# Each detection is paired with an input that must NOT be flagged: the validators
# reject a malformed fixture and pass the real file, an unknown screen is refused and
# every real name is accepted, and a spec created without the new flags is the one
# the pre-feature code wrote, audit included.
# Run: bash tests/test_screen_patterns.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PF="$ROOT/scripts/plan_feature.py"
UI="$ROOT/scripts/data/edge_cases_ui.json"
SP="$ROOT/scripts/data/screen_patterns.json"
# The last main commit before this feature: the spec a flag-less `new` writes must be
# byte-identical to what this ref writes (spec E10).
OLD_REF="${SCREEN_PATTERNS_OLD_REF:-3e3baca}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
OUT="$TMP/out"; ERR="$TMP/err"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok   %-66s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %-66s\n' "$1"
         for f in "$OUT" "$ERR"; do [ -s "$f" ] && sed 's/^/       /' "$f" | head -8; done; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has()  { grep -qF -- "$2" "$1" && ok "reports: $2" || bad "does NOT report: $2"; }
no()   { grep -qF -- "$2" "$1" && bad "false positive: $2" || ok "absent (correct): $2"; }
pf()   { python3 "$PF" "$@" >"$OUT" 2>"$ERR"; }

# ---------- validators, written once and run on the real files and on bad fixtures ----------
cat > "$TMP/check_ui.py" <<'PY'
"""Shape of edge_cases_ui.json (AC-1) and its separation from the other two (AC-12)."""
import json, pathlib, re, sys
path, data_dir = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
FAMILIES = ["settings", "destructive-action", "form", "list-table", "detail-view",
            "auth-screens", "scheduling", "checkout", "money-transfer"]
d = json.loads(path.read_text())
errs = []
kinds = [k for k in d if not k.startswith("_")]
if sorted(kinds) != sorted(FAMILIES):
    errs.append(f"families {sorted(kinds)} != {sorted(FAMILIES)}")
def well_formed(e):
    return isinstance(e, list) and len(e) == 3 and all(isinstance(x, str) and x.strip() for x in e)
for k in kinds:
    v = d[k]
    if not isinstance(v, list) or not 6 <= len(v) <= 10:
        errs.append(f"{k}: {len(v) if isinstance(v, list) else type(v).__name__} entries, want 6-10")
        continue
    errs += [f"{k}: malformed entry {e!r}" for e in v if not well_formed(e)]
roles = d.get("_roles", [])
if len(roles) != 3 or not all(well_formed(t) for t in roles):
    errs.append(f"_roles: want exactly 3 well-formed templates, got {len(roles)}")
for t in roles:
    if "{role}" not in t[0]:
        errs.append(f"_roles: no {{role}} in what {t[0]!r}")
    for cell in t:
        other = set(re.findall(r"\{[^}]*\}", cell)) - {"{role}"}
        if other:
            errs.append(f"_roles: placeholder(s) other than {{role}}: {sorted(other)}")
others = {}
for f in ("edge_cases.json", "edge_cases_infra.json"):
    others[f] = json.loads((data_dir / f).read_text())
for f, o in others.items():
    clash = set(kinds) & {k for k in o if not k.startswith("_")}
    if clash:
        errs.append(f"kind(s) also in {f}: {sorted(clash)}")
seen = {}
for f, o in [*others.items(), (path.name, d)]:
    for k, v in o.items():
        if k.startswith("_") or not isinstance(v, list):
            continue
        for e in v:
            if isinstance(e, list) and e and e[0] in seen and seen[e[0]] != (f, k):
                errs.append(f"'what' repeated: {e[0][:50]!r} in {seen[e[0]]} and {(f, k)}")
            elif isinstance(e, list) and e:
                seen[e[0]] = (f, k)
if errs:
    print("\n".join(errs)); sys.exit(1)
print(f"ui catalogue OK: " + ", ".join(f"{k}={len(d[k])}" for k in kinds))
PY

cat > "$TMP/check_sp.py" <<'PY'
"""A screen_patterns.json against the contract's shape rules (AC-5)."""
import json, pathlib, sys, unicodedata
path, data_dir = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
def norm(s):
    s = unicodedata.normalize("NFKC", s).casefold().replace("&", " and ")
    return " ".join(s.split())
kinds, planned = set(), set()
for f in ("edge_cases.json", "edge_cases_infra.json", "edge_cases_ui.json"):
    o = json.loads((data_dir / f).read_text())
    kinds |= {k for k in o if not k.startswith("_")}
    planned |= set(o.get("_planned", []))
pats = json.loads(path.read_text())["patterns"]
errs = []
if not pats:
    errs.append("no patterns")
seen = {}
for p in pats:
    for n in [p["name"], *p.get("aliases", [])]:
        if "," in n or "|" in n:
            errs.append(f"{p['name']}: name or alias {n!r} contains ',' or '|'")
        k = norm(n)
        if k in seen:
            errs.append(f"normalised {k!r} is in both {seen[k]['name']!r} and {p['name']!r}")
        seen[k] = p
    fam = p.get("families") or []
    if fam in (["baseline"], ["none"]):
        continue
    if not fam:
        errs.append(f"{p['name']}: no families")
    bad = [f for f in fam if f not in kinds and f not in planned]
    if bad:
        errs.append(f"{p['name']}: unknown families {bad}")
    if set(fam) & {"checkout", "money-transfer", "subscription"} and "payment" not in fam:
        errs.append(f"{p['name']}: lists {fam} without payment")
    if "auth-screens" in fam and "auth" not in fam:
        errs.append(f"{p['name']}: lists auth-screens without auth")
if errs:
    print("\n".join(errs)); sys.exit(1)
print(f"screen patterns OK: {len(pats)} patterns, {len(seen)} names and aliases")
PY

echo "# catalogues"
python3 "$TMP/check_ui.py" "$UI" "$ROOT/scripts/data" >"$OUT" 2>&1
rc_is 0 $? "ui catalogue: 9 families, 6-10 well-formed entries, 3 role templates"
python3 "$TMP/check_sp.py" "$SP" "$ROOT/scripts/data" >"$OUT" 2>&1
rc_is 0 $? "screen_patterns.json: meets the contract shape rules"

# Each validator must reject the defect it exists for (malformed-input edge case E4).
mkdir -p "$TMP/bad"
cp "$ROOT/scripts/data/edge_cases.json" "$ROOT/scripts/data/edge_cases_infra.json" "$TMP/bad/"
python3 - "$UI" "$TMP/bad/edge_cases_ui.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
d["settings"] = d["settings"][:5]                          # below 6 entries
d["form"][0] = [d["form"][0][0], "", d["form"][0][2]]      # empty cell
d["_roles"][0][0] = "Role: no placeholder"                 # {role} missing from what
d["list-table"].append(list(json.load(open(sys.argv[1].replace("_ui", "")))["universal"][0]))
json.dump(d, open(sys.argv[2], "w"))
PY
python3 "$TMP/check_ui.py" "$TMP/bad/edge_cases_ui.json" "$TMP/bad" >"$OUT" 2>&1
rc_is 1 $? "ui validator: rejects a malformed catalogue"
has "$OUT" "settings: 5 entries, want 6-10"
has "$OUT" "form: malformed entry"
has "$OUT" "_roles: no {role} in what"
has "$OUT" "'what' repeated"
python3 - "$UI" "$TMP/bad/clash.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d["payment"] = d.pop("checkout")
json.dump(d, open(sys.argv[2], "w"))
PY
python3 "$TMP/check_ui.py" "$TMP/bad/clash.json" "$TMP/bad" >"$OUT" 2>&1
has "$OUT" "kind(s) also in edge_cases.json: ['payment']"

cp "$UI" "$TMP/bad/edge_cases_ui.json"
python3 - "$SP" "$TMP/bad/sp.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); p = d["patterns"]
cart = next(x for x in p if x["name"] == "Cart")
cart["families"] = ["checkout"]                            # checkout without payment
fp = next(x for x in p if x["name"] == "Password reset")
fp["families"] = ["auth-screens"]                          # auth-screens without auth
dl = next(x for x in p if x["name"] == "Delete")
dl["aliases"] = dl.get("aliases", []) + ["SETTINGS"]       # collides after casefold
p[4]["aliases"] = p[4].get("aliases", []) + ["a, b"]       # comma in an alias
p[5]["families"] = ["not-a-family"]
json.dump(d, open(sys.argv[2], "w"))
PY
python3 "$TMP/check_sp.py" "$TMP/bad/sp.json" "$TMP/bad" >"$OUT" 2>&1
rc_is 1 $? "pattern validator: rejects a broken map"
has "$OUT" "Cart: lists ['checkout'] without payment"
has "$OUT" "Password reset: lists auth-screens without auth"
has "$OUT" "normalised 'settings' is in both"
has "$OUT" "contains ',' or '|'"
has "$OUT" "unknown families ['not-a-family']"

python3 - "$ROOT" >"$OUT" 2>&1 <<'PY'
import json, sys
root = sys.argv[1]; sys.path.insert(0, root + "/scripts")
import baseline, plan_feature as pf
ui = {k for k in json.load(open(root + "/scripts/data/edge_cases_ui.json")) if not k.startswith("_")}
missing_b, missing_p = ui - baseline.KNOWN_KINDS, ui - set(pf.KINDS)
assert not missing_b, f"baseline.KNOWN_KINDS lacks {sorted(missing_b)}"
assert not missing_p, f"plan_feature.KINDS lacks {sorted(missing_p)}"
assert {"universal", "payment", "cache"} <= set(pf.KINDS), "lost a core or infra kind"
assert not any(k.startswith("_") for k in pf.KINDS), "a _ key became a kind"
print("kinds OK")
PY
rc_is 0 $? "KNOWN_KINDS and plan_feature KINDS include the UI kinds, keep the rest"

# ---------- plan_feature in a consumer repo ----------
CONS="$TMP/consumer"; mkdir -p "$CONS"; cd "$CONS"
git init -q; git config user.email e@e; git config user.name e
git commit -q --allow-empty -m init
SPECS="$CONS/docs/engineering/specs"

echo "# new --kind settings (AC-1)"
pf new s1 --kind settings --tier small
rc_is 0 $? "new --kind settings succeeds"
python3 - "$UI" "$SPECS/s1/spec.md" >"$OUT" 2>&1 <<'PY'
import json, sys
want = json.load(open(sys.argv[1]))["settings"]
text = open(sys.argv[2]).read()
rows = [l.split(" | ") for l in text.splitlines() if l.startswith("| E")]
seeded = {r[2].replace("\\|", "|") for r in rows if r[1] == "settings"}
gone = [w for w, _, _ in want if w not in seeded]
assert not gone, f"settings entries not seeded with source settings: {gone}"
print(f"all {len(want)} settings entries seeded")
PY
rc_is 0 $? "every settings entry is a §7 row with source settings"

echo "# new --screens (AC-2, AC-3)"
pf new s2 --screens "settings, Shopping Cart" --tier small
rc_is 0 $? "new --screens resolves two names"
has "$SPECS/s2/spec.md" "| kinds | settings, form, checkout, payment |"
has "$SPECS/s2/spec.md" "| screens | Settings, Cart |"
has "$SPECS/s2/spec.md" "| risk | elevated |"
has "$ERR" "risk raised to elevated by kind payment"
no "$OUT" "risk raised to"                       # a diagnostic, so stderr only
no "$SPECS/s2/spec.md" "| roles |"               # omitted without --roles
grep -A1 "^| kinds |" "$SPECS/s2/spec.md" | grep -q "^| screens |" \
  && ok "screens row sits right after kinds" || bad "screens row is not right after kinds"

# Normalisation: case, extra spaces, '&' vs 'and', NFKC full-width letters (E8).
pf new s3 --screens "  SETTINGS ,shopping   CART, filter & sort,Archive  &  Trash" --tier small
rc_is 0 $? "names match after casefold, collapsed spaces and & -> and"
has "$SPECS/s3/spec.md" "| screens | Settings, Cart, Filter and sort, Archive and trash |"
pf new s4 --screens "$(printf '\xef\xbc\xb3\xef\xbd\x85\xef\xbd\x94\xef\xbd\x94\xef\xbd\x89\xef\xbd\x8e\xef\xbd\x87\xef\xbd\x93')" --tier small
rc_is 0 $? "full-width 'Ｓｅｔｔｉｎｇｓ' resolves through NFKC"
pf new s5 --screens "preferences, Settings" --tier small
has "$SPECS/s5/spec.md" "| screens | Settings |"   # alias + name: one screen

pf new u1 --screens "shoping cartt, Settings" --tier small
rc_is 2 $? "unknown screen exits 2"
has "$ERR" "unknown screen 'shoping cartt'; closest: "
python3 - "$ERR" >"$OUT" 2>&1 <<'PY'
import sys
line = next(l for l in open(sys.argv[1]) if l.startswith("unknown screen"))
names = line.split("closest: ", 1)[1].strip().split(", ")
assert 1 <= len(names) <= 3, names
assert "Cart" in names, names
print(names)
PY
rc_is 0 $? "closest lists 1-3 names, the near miss included"
[ ! -e "$SPECS/u1" ] && ok "nothing written for an unknown screen" || bad "wrote a spec for an unknown screen"
pf new u2 --screens "setting" --tier small
rc_is 2 $? "a near-miss is refused, not fuzzily accepted"
pf new u3 --screens "" --tier small
rc_is 2 $? "an empty --screens exits 2"
pf new u4 --screens " , ," --tier small
rc_is 2 $? "a --screens of only separators exits 2"

echo "# planned, baseline and none screens (AC-4)"
pf new s6 --screens "favorite, System states, Filter and sort" --tier small
rc_is 0 $? "unchecked screens still succeed"
has "$ERR" "not yet checked: Like and follow (social-actions)"
has "$ERR" "not yet checked: System states (baseline)"
has "$ERR" "not yet checked: Filter and sort (search-filter-ui)"
has "$SPECS/s6/spec.md" "| kinds | list-table |"       # the built family of the mixed one
no "$ERR" "not yet checked: Settings"
pf new s7 --screens "Settings" --tier small
no "$ERR" "not yet checked"                            # a fully built screen is not flagged
no "$ERR" "risk raised"                                # settings,form imply no risk
pf new s8 --screens "System states" --tier small
has "$SPECS/s8/spec.md" "| kinds | universal |"        # nothing built: the default kind

python3 -c "import json,sys; print(', '.join(p['name'] for p in json.load(open(sys.argv[1]))['patterns']))" \
  "$SP" > "$TMP/all_names"
pf new all --screens "$(cat "$TMP/all_names")" --tier small
rc_is 0 $? "every plugin name resolves in one --screens (no valid name rejected)"
python3 -c "import json,sys; print(', '.join(a for p in json.load(open(sys.argv[1]))['patterns'] for a in p.get('aliases', [])))" \
  "$SP" > "$TMP/all_aliases"
pf new alias --screens "$(cat "$TMP/all_aliases")" --tier small
rc_is 0 $? "every alias resolves"

echo "# new --roles (AC-7)"
pf new r1 --kind settings --roles admin,viewer --tier small
rc_is 0 $? "new --roles admin,viewer succeeds"
has "$SPECS/r1/spec.md" "| roles | admin, viewer |"
python3 - "$SPECS/r1/spec.md" >"$OUT" 2>&1 <<'PY'
import sys
rows = [l.split(" | ") for l in open(sys.argv[1]).read().splitlines() if l.startswith("| E")]
src = [r[1] for r in rows]
roles = [i for i, s in enumerate(src) if s.startswith("role:")]
assert src[roles[0]:] == ["role:admin"] * 3 + ["role:viewer"] * 3, src[roles[0]:]
assert roles == list(range(len(src) - 6, len(src))), "role rows are not after the family rows"
assert all("Role viewer:" in rows[i][2] for i in roles[3:]), "role name missing from what"
assert all("{role}" not in "|".join(r) for r in rows), "an unreplaced {role}"
print("6 role rows, after the family rows, in --roles order")
PY
rc_is 0 $? "3 rows per role, source role:<name>, after family rows, in order"
has "$SPECS/r1/spec.md" "roles: admin, viewer."

# The audit re-expands roles: deleting one role row is caught, keeping all is not.
python3 "$PF" audit "$SPECS/r1" >"$OUT" 2>&1
no "$OUT" "seeded edge case(s) deleted"
grep -v "Role viewer: controls it is not granted" "$SPECS/r1/spec.md" > "$TMP/r1" && cp "$TMP/r1" "$SPECS/r1/spec.md"
python3 "$PF" audit "$SPECS/r1" >"$OUT" 2>&1
rc_is 1 $? "audit fails once a role row is deleted"
has "$OUT" "1 seeded edge case(s) deleted from §7 (first: 'Role viewer: controls"
# Marking it covered with the seeded suggestion copied in is not evidence either.
pf new r2 --roles viewer --tier small
sed -i.bak 's#| E\([0-9]*\) | role:viewer | Role viewer: sees and can use every control the spec grants it | \(.*\) | TODO | _suggested:_ \(.*\) |#| E\1 | role:viewer | Role viewer: sees and can use every control the spec grants it | \2 | covered | \3 |#' "$SPECS/r2/spec.md"
python3 "$PF" audit "$SPECS/r2" >"$OUT" 2>&1
has "$OUT" "covered edge case(s) whose reference is the seeded suggestion"
sed -i.bak 's/^| roles | viewer |$/| roles | Viewer |/' "$SPECS/r2/spec.md"
python3 "$PF" audit "$SPECS/r2" >"$OUT" 2>&1
has "$OUT" "invalid role name(s) in the header: Viewer"

for r in "Admin" "a|b" "1x" "a b" "-x" "$(printf 'a%.0s' $(seq 33))"; do
  pf new badrole --roles "admin,$r" --tier small
  [ $? -eq 2 ] && ok "role '${r:0:12}' exits 2" || bad "role '${r:0:12}' was accepted"
done
pf new badrole --roles "" --tier small
rc_is 2 $? "an empty --roles exits 2"
[ ! -e "$SPECS/badrole" ] && ok "nothing written for a bad role" || bad "wrote a spec for a bad role"
pf new r3 --roles "$(printf 'a%.0s' $(seq 32)),ops-2,qa" --tier small
rc_is 0 $? "a 32-char role, digits and '-' are accepted (boundary)"

echo "# a spec without the new flags is unchanged (E10)"
if git -C "$ROOT" cat-file -e "$OLD_REF^{commit}" 2>/dev/null; then
  mkdir -p "$TMP/old" && git -C "$ROOT" archive "$OLD_REF" scripts | tar -x -C "$TMP/old"
  for v in old new; do
    mkdir -p "$TMP/$v-repo" && cd "$TMP/$v-repo" && git init -q && git commit -q --allow-empty -m i
    script="$PF"; [ "$v" = old ] && script="$TMP/old/scripts/plan_feature.py"
    python3 "$script" new same --kind crud,payment --work api,web-ui --tier small --stack nestjs >"$TMP/$v.stdout" 2>&1
    python3 "$script" new plain --tier small >>"$TMP/$v.stdout" 2>&1
    python3 "$script" audit docs/engineering/specs/same >"$TMP/$v.audit" 2>&1
  done
  cd "$CONS"
  diff "$TMP/old-repo/docs/engineering/specs/same/spec.md" "$TMP/new-repo/docs/engineering/specs/same/spec.md" >"$OUT" \
    && ok "flag-less new writes the spec $OLD_REF writes" || bad "flag-less spec differs from $OLD_REF"
  diff "$TMP/old-repo/docs/engineering/specs/plain/spec.md" "$TMP/new-repo/docs/engineering/specs/plain/spec.md" >"$OUT" \
    && ok "default-kind new writes the spec $OLD_REF writes" || bad "default-kind spec differs from $OLD_REF"
  diff "$TMP/old.stdout" "$TMP/new.stdout" >"$OUT" && ok "flag-less new prints what $OLD_REF prints" \
    || bad "flag-less new output differs from $OLD_REF"
  diff "$TMP/old.audit" "$TMP/new.audit" >"$OUT" && ok "a flag-less spec audits as it did at $OLD_REF" \
    || bad "flag-less audit differs from $OLD_REF"
else
  echo "  skip golden diff: $OLD_REF not in this clone (set SCREEN_PATTERNS_OLD_REF)"
fi
pf new hdr --kind crud --tier small
python3 - "$SPECS/hdr/spec.md" >"$OUT" 2>&1 <<'PY'
import sys
head = open(sys.argv[1]).read().split("\n\n")[1].splitlines()
want = ["| field | value |", "|---|---|", "| feature | hdr |", "| kinds | crud |",
        "| stack | unspecified |", "| prd | none |"]
assert head[:6] == want, head
print("header unchanged")
PY
rc_is 0 $? "header without --screens/--roles has no screens or roles row"

echo "# cases (AC-6)"
EMPTY="$TMP/not-a-repo"; mkdir -p "$EMPTY"; cd "$EMPTY"
pf cases --kind settings
rc_is 0 $? "cases --kind settings, outside a git repo"
has "$OUT" "| # | source | edge case | why it gets missed | test |"
has "$OUT" "| C1 | settings | A destructive or irreversible setting (delete workspace, revoke keys, disable SSO, downgrade plan) applies on one click |"
no "$OUT" "| E1 |"                                 # checklist-local ids, never a spec's E<n>
no "$OUT" "| universal |"
no "$OUT" "_suggested:_"
[ "$(grep -c '^| C' "$OUT")" -eq "$(python3 -c "import json;print(len(json.load(open('$UI'))['settings']))")" ] \
  && ok "one row per settings entry" || bad "row count differs from the settings family"
pf cases --screens delete
rc_is 0 $? "cases --screens delete (an alias)"
has "$OUT" "| C1 | destructive-action |"
pf cases --screens delete --roles viewer --json
rc_is 0 $? "cases --json --roles viewer"
python3 - "$OUT" "$UI" >"$TMP/j" 2>&1 <<'PY'
import json, sys
rows = json.load(open(sys.argv[1]))
n = len(json.load(open(sys.argv[2]))["destructive-action"])
assert isinstance(rows, list) and len(rows) == n + 3, len(rows)
assert all(set(r) == {"id", "source", "what", "why", "test"} for r in rows)
assert [r["id"] for r in rows] == [f"C{i}" for i in range(1, n + 4)]
assert [r["source"] for r in rows[-3:]] == ["role:viewer"] * 3
assert rows[-1]["what"].startswith("Role viewer:")
print("json OK")
PY
[ $? -eq 0 ] && ok "json: list of {id, source, what, why, test}, role rows last" || { cp "$TMP/j" "$OUT"; bad "json shape"; }
pf cases --screens "favorite" --json
python3 -c "import json,sys; assert json.load(open(sys.argv[1])) == []" "$OUT" \
  && ok "unchecked screen: stdout stays valid JSON (an empty list)" || bad "notes leaked into JSON stdout"
has "$ERR" "not yet checked: Like and follow (social-actions)"
pf cases --screens "cart"
has "$ERR" "risk raised to elevated by kind payment"
pf cases --kind universal,settings
has "$OUT" "| C1 | universal |"
pf cases --roles viewer
rc_is 2 $? "cases without --kind or --screens exits 2"
pf cases --screens nope
rc_is 2 $? "cases with an unknown screen exits 2"
has "$ERR" "unknown screen 'nope'"
pf cases --kind settings --roles "Bad"
rc_is 2 $? "cases with a bad role exits 2"
[ -z "$(ls -A "$EMPTY")" ] && ok "cases wrote nothing" || bad "cases wrote files: $(ls -A "$EMPTY")"
cd "$CONS"
before="$(git status --porcelain | md5sum 2>/dev/null || git status --porcelain | md5)"
pf cases --kind settings --screens delete
after="$(git status --porcelain | md5sum 2>/dev/null || git status --porcelain | md5)"
[ "$before" = "$after" ] && ok "cases changes nothing inside a repo" || bad "cases changed the repo"


echo "# a project's own screen map (records root)"
PROJ="$TMP/project"; mkdir -p "$PROJ/docs/engineering"; cd "$PROJ"
git init -q; git commit -q --allow-empty -m init
cat > docs/engineering/screen_patterns.json <<'JSON'
{"patterns": [
  {"name": "Team & Billing Settings", "aliases": ["prefs page"], "families": ["settings", "form"]},
  {"name": "Workspace removal", "aliases": ["delete"], "families": ["destructive-action", "settings"]},
  {"name": "Ads", "aliases": [], "families": ["none"]}
]}
JSON
pf new p1 --screens "team & billing settings, ads" --tier small
rc_is 0 $? "a project-only name resolves"
has "docs/engineering/specs/p1/spec.md" "| screens | Team & Billing Settings, Ads |"
has "docs/engineering/specs/p1/spec.md" "| kinds | settings, form |"
has "$ERR" "not yet checked: Ads (none)"
pf new p2 --screens "delete" --tier small
has "docs/engineering/specs/p2/spec.md" "| screens | Workspace removal |"   # project wins the clash
has "docs/engineering/specs/p2/spec.md" "| kinds | destructive-action, settings |"
pf new p3 --screens "remove, cart" --tier small
rc_is 0 $? "plugin names outside the clash still resolve beside a project map"
has "docs/engineering/specs/p3/spec.md" "| screens | Delete, Cart |"
pf cases --screens "prefs page" --json
rc_is 0 $? "cases reads the project map too"
python3 -c "import json,sys; assert json.load(open(sys.argv[1]))[0]['source'] == 'settings'" "$OUT" \
  && ok "cases: project screen yields its families' rows" || bad "cases ignored the project map"
pf cases --screens "delete"
has "$OUT" "| settings |"                       # Workspace removal includes settings; plugin Delete does not

# The records root moves with .100x.json, and the project map moves with it.
CFG="$TMP/cfgproj"; mkdir -p "$CFG/eng"; cd "$CFG"
git init -q; git commit -q --allow-empty -m init
echo '{"root": "eng"}' > .100x.json
echo '{"patterns": [{"name": "Team roster", "aliases": [], "families": ["list-table"]}]}' > eng/screen_patterns.json
pf cases --screens "team roster"
rc_is 0 $? "project map found under a configured records root"
has "$OUT" "| C1 | list-table |"

cd "$PROJ"
for bad_doc in '{not json' '{"patterns": "x"}' \
  '{"patterns": [{"name": "Pay", "aliases": [], "families": ["checkout"]}]}' \
  '{"patterns": [{"name": "A|B", "aliases": [], "families": ["form"]}]}' \
  '{"patterns": [{"name": "X", "aliases": ["y", "Y"], "families": ["form"]}]}' \
  '{"patterns": [{"name": "X", "aliases": "y", "families": ["form"]}]}' \
  '{"patterns": [{"name": "X", "aliases": [], "families": ["nope"]}]}' \
  '{"patterns": [{"name": "X", "aliases": [], "families": []}]}' \
  '{"patterns": [{"name": "X", "aliases": [], "families": [["settings"]]}]}' \
  '{"patterns": [{"name": "X\nY", "aliases": [], "families": ["form"]}]}' \
  '{"patterns": [{"name": "X", "aliases": ["a\tb"], "families": ["form"]}]}'; do
  printf '%s' "$bad_doc" > docs/engineering/screen_patterns.json
  pf cases --screens settings
  rc=$?
  if [ "$rc" -eq 2 ] && grep -q "malformed screen map docs/engineering/screen_patterns.json" "$ERR"; then
    ok "bad project map exits 2 naming the file: ${bad_doc:0:40}"
  else
    bad "bad project map not refused (rc=$rc): ${bad_doc:0:40}"
  fi
done
pf new p4 --screens settings --tier small
rc_is 2 $? "new --screens refuses a bad project map too"
[ ! -e docs/engineering/specs/p4 ] && ok "nothing written with a bad project map" || bad "wrote a spec with a bad map"
pf new p5 --kind settings --tier small
rc_is 0 $? "a bad project map does not affect new without --screens"
cd "$CONS"
python3 "$PF" --help >"$OUT" 2>&1 && grep -q "cases" "$OUT" && ok "--help lists cases" || bad "--help lacks cases"
python3 "$PF" new --help >"$OUT" 2>&1 && grep -q -- "--screens" "$OUT" && grep -q -- "--roles" "$OUT" \
  && ok "new --help documents --screens and --roles" || bad "new --help lacks the flags"

echo "# AC-9: every instruction file that owes the checklist names the command"
cd "$ROOT"
for f in skills/ui-baseline/SKILL.md skills/diff-review/SKILL.md \
         skills/feature-planning/SKILL.md skills/qa-strategy/SKILL.md \
         agents/qa-engineer.md agents/code-reviewer.md agents/frontend-engineer.md \
         skills/pr-review/references/reviewer-prompt.md; do
  grep -q "plan_feature cases" "$f" && ok "$f names plan_feature cases" \
    || bad "$f lost its plan_feature cases pointer"
done

cd "$ROOT"
echo
echo "screen-patterns: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]

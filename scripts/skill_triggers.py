#!/usr/bin/env python3
"""Score whether the right skill would load for a given task prompt.

The dominant skill failure mode is not a bad body -- it is a description that does not
discriminate, so the skill never loads and its context cost buys nothing. Descriptions
are usually written once, by hand, and never tested.

This ranks every skill's description against a fixture of realistic prompts by lexical
overlap. That is an APPROXIMATION of the model's choice, not a simulation of it. Its
value is narrower and still real: when two descriptions score identically for a prompt,
they are not separable on the words alone, and the model has no more to go on than this
does.

    skill_triggers.py                    # score skills/ against evals/triggers.json
    skill_triggers.py --from-git HEAD    # score the committed version (for before/after)
    skill_triggers.py --show-overlap     # which description pairs are least separable
    skill_triggers.py --truncate 100     # only the first 100 chars of each description
    skill_triggers.py --name-only        # skill names alone, every description dropped
    skill_triggers.py --distractors evals/ecc_distractors.json   # compete with other plugins
    skill_triggers.py --all-modes        # every mode above, one table, both gates
    skill_triggers.py --json

Why the realism modes exist: installed beside a ~250-skill plugin, the harness listed many of
this plugin's skills NAME-ONLY -- descriptions dropped once the listing budget ran out -- and
truncates any one description at 1,536 chars. A description that only discriminates in its
second sentence, or only against this plugin's own skills, does not route in that session.

Exit 1 if top-3 recall is below the floor or any skill never makes a shortlist; with
--all-modes, unless full mode AND truncate-100-with-distractors both clear the floor.
Python stdlib only.
"""
import argparse, json, math, pathlib, re, subprocess, sys, collections

PLUGIN = pathlib.Path(__file__).resolve().parent.parent
FIXTURE = PLUGIN / "evals" / "triggers.json"
DISTRACTORS = PLUGIN / "evals" / "ecc_distractors.json"
# Skills merged in the v0.2 consolidation. Applied only to --from-git, so a pre-merge
# catalogue is scored against today's fixture: any of the old skills reaching the shortlist
# counts for the skill it became, which is the fairest before/after available.
ALIASES = {
    "typescript-verification": "language-verification",
    "python-verification": "language-verification",
    "go-verification": "language-verification",
    "decision-log": "decision-records", "engineering-ledger": "decision-records",
    "scoped-review": "diff-review", "reviewing-others-code": "diff-review",
}
GATE_TRUNCATE = 100
# What this proxy can and cannot assert.
#
# Lexical overlap is a bag-of-words stand-in for a semantic decision. Across four
# honest attempts to improve it -- negation handling, scoring the skill name, and two
# rounds of description rewrites -- top-1 moved between 55% and 66% while top-3 stayed
# at 83-86%. Each change traded one case for another. That is the signature of a metric
# at its ceiling, not of a catalogue that keeps failing.
#
# So the gate is on TOP-3: "the right skill is in the shortlist" is a claim this proxy
# can support. Top-1 is reported as a diagnostic, not gated, because a bag-of-words
# scorer cannot rank two semantically adjacent descriptions the way a model reading
# both in full will.
#
# Measuring actual routing needs an LLM-judged eval. research/20-findings-ecosystem-
# skills.md records that the most sophisticated eval framework surveyed states its own
# LLM-judge layer is "experimental, not validated against human labels" -- so that
# would be a weaker claim than this one, not a stronger one.
TOP3_FLOOR = 0.85
TOP1_DIAGNOSTIC = 0.60     # reported, not gated; a fall below this is worth reading

STOP = set("""a an the and or but if when while for to of in on at by with from into
this that these those it its is are was were be been being do does did use used using
you your we our they their i me my not no non very more most such as than then there
here what which who whom whose how why where all any both each few other some only own
same so too can will just should now use when also about after before during between
per via etc eg ie vs""".split())
TOKEN = re.compile(r"[a-z][a-z0-9+#.-]{1,}")


# NOT DONE: stemming. Collapsing "choose"/"choice"/"chosen" into one token was tried
# and measurably hurt: top-3 fell 86% -> 79%, top-1 62% -> 59%. Stemming raises recall
# on sparse matches and lowers DISCRIMINATION, because more descriptions then share
# terms and the idf weighting flattens. Recorded so nobody re-tries it hopefully.

def toks(text):
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP and len(t) > 2]


def load_skills(from_git=None, root=PLUGIN):
    out = {}
    if from_git:
        names = subprocess.run(["git", "ls-tree", "-r", "--name-only", from_git],
                               cwd=root, capture_output=True, text=True).stdout.split()
        paths = [n for n in names if re.match(r"skills/[^/]+/SKILL\.md$", n)]
        for p in paths:
            body = subprocess.run(["git", "show", f"{from_git}:{p}"], cwd=root,
                                  capture_output=True, text=True).stdout
            out[p.split("/")[1]] = body
    else:
        for p in sorted((root / "skills").glob("*/SKILL.md")):
            out[p.parent.name] = p.read_text(errors="replace")
    descs = {}
    for name, body in out.items():
        descs[name] = extract_description(body)
    return descs


def extract_description(body):
    """Line-based, because a regex anchored with re.M cannot span a YAML block scalar.

    A `description: >` value continues across every following indented line; an
    earlier regex here captured just the ">" and scored every prompt at zero, which
    made the whole measurement silently meaningless rather than visibly broken.
    """
    lines = body.splitlines()
    for i, l in enumerate(lines):
        if not l.startswith("description:"):
            continue
        inline = l.split(":", 1)[1].strip()
        if inline and inline not in (">", "|", ">-", "|-", ">+", "|+"):
            return inline
        buf = []
        for nxt in lines[i + 1:]:
            if nxt.strip() == "---" or (nxt and not nxt[0].isspace()):
                break
            buf.append(nxt.strip())
        return " ".join(x for x in buf if x)
    return ""


NEG_CLAUSE = re.compile(
    r"(?:\bnot for\b|\bnot\s+(?:when|used for)\b|\bdo not use\b|\brather than\b)"
    r"[^.;]*[.;]?", re.I)


def split_polarity(desc):
    """Separate a description into what it claims and what it disclaims.

    Descriptions now carry negative signals like "Not for framework code (→
    stack-reviewer)". Those help a model that understands negation and actively
    mislead a bag-of-words scorer, which counts the disclaimed language as a match. A
    term inside a negative clause must subtract, not add -- that is the whole point of
    writing it.
    """
    neg = " ".join(NEG_CLAUSE.findall(desc))
    pos = NEG_CLAUSE.sub(" ", desc)
    return pos, neg


def score(prompt_toks, pos_toks, neg_toks, idf):
    """Weighted overlap, minus the weight of anything the description disclaims."""
    pset, nset = set(pos_toks), set(neg_toks) - set(pos_toks)
    q = set(prompt_toks)
    gain = sum(idf.get(t, 1.0) for t in q if t in pset)
    loss = sum(idf.get(t, 1.0) for t in q if t in nset)
    return gain - loss


def load_distractors(path):
    """Competitor skills from another plugin: {name: description}. Synthetic by design."""
    data = json.loads(pathlib.Path(path).read_text())
    return {s["name"]: s["description"] for s in data["skills"]}


def evaluate(descs, cases, plugin, truncate=None, name_only=False, aliases=None):
    """Rank every candidate for every case.

    `descs` may include distractors; `plugin` is this plugin's skill names, the only ones
    that can be reported as never shortlisted. Truncation applies to every candidate,
    because a listing budget cuts other plugins' descriptions as well as ours.
    """
    aliases = aliases or {}
    cand = {}
    for n, d in descs.items():
        d = "" if name_only else (d[:truncate] if truncate else d)
        pos, neg = split_polarity(d)
        # The skill NAME is part of what the harness shows the model, alongside the
        # description; a skill called `diff-review` carries "review" either way.
        cand[n] = (toks(n.replace("-", " ").replace(":", " ")) + toks(pos), toks(neg))
    df = collections.Counter()
    for tl, _ in cand.values():
        for t in set(tl):
            df[t] += 1
    N = len(cand)
    idf = {t: math.log(1 + N / c) for t, c in df.items()}   # rare terms discriminate
    show = lambda n: aliases.get(n, n)
    rows, wins, shortlisted = [], collections.Counter(), collections.Counter()
    top1 = top3 = rejviol = 0
    for c in cases:
        pt = toks(c["prompt"])
        ranked = sorted(((score(pt, cand[n][0], cand[n][1], idf), n) for n in cand),
                        reverse=True)
        names, seen = [], set()
        for _, n in ranked:          # an alias collapses several old skills into one
            if show(n) not in seen:
                seen.add(show(n)); names.append(show(n))
        exp = c["expect"] if isinstance(c["expect"], list) else [c["expect"]]
        ranks = [names.index(e) + 1 for e in exp if e in names]
        r1, r3 = names[0] in exp, bool(ranks) and min(ranks) <= 3
        top1 += r1; top3 += r3
        wins[names[0]] += 1
        for n in names[:3]:
            shortlisted[n] += 1
        viol = [r for r in c.get("reject", []) if show(r) == names[0] and show(r) not in exp]
        rejviol += bool(viol)
        rows.append({"prompt": c["prompt"], "expect": "/".join(exp), "top3": names[:3],
                     "rank": min(ranks) if ranks else None,
                     "top1": r1, "top3_hit": r3, "reject_violation": viol,
                     "scores": {show(n): round(s, 2) for s, n in ranked[:3]}})
    plugin_shown = {show(n) for n in plugin}
    # A skill absent from every shortlist is dead weight: it can never be chosen.
    never = sorted(plugin_shown - set(shortlisted))
    return {"top1": top1 / len(cases), "top3": top3 / len(cases), "n": len(cases),
            "top1_n": top1, "top3_n": top3, "reject_violations": rejviol,
            "never_wins": never,
            "distractor_top1": sum(v for k, v in wins.items() if k not in plugin_shown),
            "cases": rows, "idf": idf, "cand": cand}


def report(res, pool, label, show_overlap):
    rows = res["cases"]
    print(f"skill_triggers{label}: {len(pool)} candidates, {res['n']} prompts\n")
    print(f"{'prompt':52s} {'expected':24s} rank  top-1")
    print("-" * 94)
    for r in rows:
        mark = "ok" if r["top1"] else ("t3" if r["top3_hit"] else "MISS")
        print(f"{r['prompt'][:52]:52s} {r['expect'][:24]:24s} "
              f"{str(r['rank'] or '-'):>4s}  {mark}")
    print("-" * 94)
    print(f"top-3 recall   : {res['top3_n']}/{res['n']}  ({100*res['top3']:.0f}%)   GATE, "
          f"floor {100*TOP3_FLOOR:.0f}%")
    print(f"top-1 accuracy : {res['top1_n']}/{res['n']}  ({100*res['top1']:.0f}%)   "
          f"diagnostic only (see the note in this file on why top-1 is not gated)")
    print(f"reject in top-1: {res['reject_violations']}  (a neighbour outranking the right skill)")
    print(f"distractor won : {res['distractor_top1']}  (another plugin's skill ranked first)")
    if res["never_wins"]:
        print(f"\nnever shortlisted ({len(res['never_wins'])}) — either the fixture lacks a "
              f"case for it, or its description does not discriminate:")
        for n in res["never_wins"]:
            print(f"  {n}")
    misses = [r for r in rows if not r["top3_hit"]]
    if misses:
        print(f"\noutside the top 3 ({len(misses)}):")
        for r in misses:
            print(f"  {r['prompt'][:60]}")
            print(f"     wanted {r['expect']} (rank {r['rank']}), got {r['top3']}")
            print(f"     scores {r['scores']}")
    if show_overlap:
        idf, cand = res["idf"], res["cand"]
        print("\nleast separable description pairs (shared weighted terms):")
        pairs = []
        for i, x in enumerate(sorted(cand)):
            for y in sorted(cand)[i+1:]:
                sh = set(cand[x][0]) & set(cand[y][0])
                pairs.append((sum(idf.get(t, 1) for t in sh), x, y, len(sh)))
        for s, x, y, n in sorted(pairs, reverse=True)[:8]:
            print(f"  {s:6.1f}  {x} <-> {y}  ({n} shared terms)")
    print("\nLexical overlap only. It cannot tell you the model will choose correctly; "
          "it can tell you two descriptions are indistinguishable on words alone.")


def all_modes(descs, cases, plugin, aliases, dpath, n, as_json, label):
    distract = load_distractors(dpath)
    modes = [("full", None, False, False), ("full+distractors", None, False, True),
             (f"truncate{n}", n, False, False), (f"truncate{n}+distractors", n, False, True),
             ("name-only", None, True, False), ("name-only+distractors", None, True, True)]
    gated = {"full", f"truncate{n}+distractors"}
    out, ok = {}, True
    for name, tr, no, dis in modes:
        r = evaluate({**descs, **distract} if dis else descs, cases, plugin, tr, no, aliases)
        passed = r["top3"] >= TOP3_FLOOR and (name != "full" or not r["never_wins"])
        if name in gated:
            ok = ok and passed
        out[name] = {k: r[k] for k in ("top1", "top3", "reject_violations", "never_wins",
                                      "distractor_top1")}
        out[name].update(gated=name in gated, passed=passed,
                         misses=[f"{c['prompt']} -> {c['top3']}" for c in r["cases"]
                                 if not c["top3_hit"]])
    if as_json:
        print(json.dumps({"modes": out, "pass": ok}, indent=2))
        return 0 if ok else 1
    print(f"skill_triggers{label}: {len(descs)} skills, {len(distract)} distractors "
          f"({pathlib.Path(dpath).name}), {len(cases)} prompts\n")
    print(f"{'mode':26s} {'top-3':>6s} {'top-1':>6s} {'reject':>6s} {'distr':>6s} "
          f"{'never':>6s}  gate")
    print("-" * 72)
    for name, r in out.items():
        g = ("PASS" if r["passed"] else "FAIL") if r["gated"] else "-"
        print(f"{name:26s} {100*r['top3']:5.0f}% {100*r['top1']:5.0f}% "
              f"{r['reject_violations']:6d} {r['distractor_top1']:6d} "
              f"{len(r['never_wins']):6d}  {g}")
    print("-" * 72)
    print(f"gate: top-3 >= {100*TOP3_FLOOR:.0f}% in full mode (every skill shortlisted) AND "
          f"in truncate{n}+distractors -> {'PASS' if ok else 'FAIL'}")
    print("distr = prompts where another plugin's skill ranked first")
    for name, r in out.items():
        if r["gated"] and r["misses"]:
            print(f"\n{name} misses:")
            for m in r["misses"]:
                print(f"  {m}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-git", default=None)
    ap.add_argument("--root", default=str(PLUGIN), help="plugin root holding skills/")
    ap.add_argument("--fixture", default=None, help="default: <root>/evals/triggers.json")
    ap.add_argument("--truncate", type=int, default=None, metavar="N",
                    help="score only the first N chars of every description")
    ap.add_argument("--name-only", action="store_true",
                    help="score skill names alone, as a listing that dropped descriptions")
    ap.add_argument("--distractors", default=None, metavar="FILE",
                    help="add another plugin's skills as competitors")
    ap.add_argument("--all-modes", action="store_true",
                    help="full, truncated and name-only, each with and without distractors; "
                         "gates full and truncate-with-distractors")
    ap.add_argument("--show-overlap", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    root = pathlib.Path(a.root).resolve()
    descs = load_skills(a.from_git, root)
    if not descs:
        print("no skills found", file=sys.stderr); return 2
    cases = json.loads(pathlib.Path(a.fixture or root / "evals" / "triggers.json")
                       .read_text())["cases"]
    aliases = ALIASES if a.from_git else {}
    plugin = set(descs)
    label = f" ({a.from_git})" if a.from_git else ""

    if a.all_modes:
        return all_modes(descs, cases, plugin, aliases, a.distractors or DISTRACTORS,
                         a.truncate or GATE_TRUNCATE, a.json, label)

    pool = {**descs, **load_distractors(a.distractors)} if a.distractors else descs
    res = evaluate(pool, cases, plugin, a.truncate, a.name_only, aliases)
    ok = res["top3"] >= TOP3_FLOOR and not res["never_wins"]
    if a.json:
        print(json.dumps({k: res[k] for k in ("top1", "top3", "reject_violations",
                                              "never_wins", "distractor_top1", "cases")},
                         indent=2))
        return 0 if ok else 1
    mode = "".join([f" truncate={a.truncate}" if a.truncate else "",
                    " name-only" if a.name_only else "",
                    " +distractors" if a.distractors else ""])
    report(res, pool, label + mode, a.show_overlap)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

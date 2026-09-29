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
    skill_triggers.py --json

Exit 1 if top-1 accuracy is below the floor or any skill never wins a prompt.
Python stdlib only.
"""
import argparse, json, math, pathlib, re, subprocess, sys, collections

PLUGIN = pathlib.Path(__file__).resolve().parent.parent
FIXTURE = PLUGIN / "evals" / "triggers.json"
TOP1_FLOOR = 0.70          # below this the catalogue is not reliably routable

STOP = set("""a an the and or but if when while for to of in on at by with from into
this that these those it its is are was were be been being do does did use used using
you your we our they their i me my not no non very more most such as than then there
here what which who whom whose how why where all any both each few other some only own
same so too can will just should now use when also about after before during between
per via etc eg ie vs""".split())
TOKEN = re.compile(r"[a-z][a-z0-9+#.-]{1,}")


def toks(text):
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP and len(t) > 2]


def load_skills(from_git=None):
    out = {}
    if from_git:
        names = subprocess.run(["git", "ls-tree", "-r", "--name-only", from_git],
                               cwd=PLUGIN, capture_output=True, text=True).stdout.split()
        paths = [n for n in names if re.match(r"skills/[^/]+/SKILL\.md$", n)]
        for p in paths:
            body = subprocess.run(["git", "show", f"{from_git}:{p}"], cwd=PLUGIN,
                                  capture_output=True, text=True).stdout
            out[p.split("/")[1]] = body
    else:
        for p in sorted((PLUGIN / "skills").glob("*/SKILL.md")):
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


def score(prompt_toks, desc_toks, idf):
    """Weighted overlap: a term shared with few descriptions discriminates more than one
    shared with all of them."""
    dset = set(desc_toks)
    return sum(idf.get(t, 1.0) for t in set(prompt_toks) if t in dset)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-git", default=None)
    ap.add_argument("--show-overlap", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    descs = load_skills(a.from_git)
    if not descs:
        print("no skills found", file=sys.stderr); return 2
    dtoks = {n: toks(d) for n, d in descs.items()}

    # idf over descriptions: rare terms carry the discrimination
    df = collections.Counter()
    for tl in dtoks.values():
        for t in set(tl):
            df[t] += 1
    N = len(dtoks)
    idf = {t: math.log(1 + N / c) for t, c in df.items()}

    cases = json.loads(FIXTURE.read_text())["cases"]
    rows, wins = [], collections.Counter()
    top1 = top3 = rejviol = 0
    for c in cases:
        pt = toks(c["prompt"])
        ranked = sorted(((score(pt, dtoks[n], idf), n) for n in dtoks), reverse=True)
        names = [n for _, n in ranked]
        exp = c["expect"]
        r1 = names[0] == exp
        r3 = exp in names[:3]
        top1 += r1; top3 += r3
        wins[names[0]] += 1
        viol = [r for r in c.get("reject", []) if r in names[:1] and r != exp]
        rejviol += bool(viol)
        rows.append({"prompt": c["prompt"], "expect": exp, "top3": names[:3],
                     "rank": (names.index(exp) + 1) if exp in names else None,
                     "top1": r1, "top3_hit": r3, "reject_violation": viol,
                     "scores": {n: round(s, 2) for s, n in ranked[:3]}})

    never = sorted(set(dtoks) - set(wins))
    acc1, acc3 = top1 / len(cases), top3 / len(cases)

    if a.json:
        print(json.dumps({"top1": acc1, "top3": acc3, "reject_violations": rejviol,
                          "never_wins": never, "cases": rows}, indent=2))
        return 0 if (acc1 >= TOP1_FLOOR and not never) else 1

    label = f" ({a.from_git})" if a.from_git else ""
    print(f"skill_triggers{label}: {len(descs)} skills, {len(cases)} prompts\n")
    print(f"{'prompt':52s} {'expected':24s} rank  top-1")
    print("-" * 94)
    for r in rows:
        mark = "ok" if r["top1"] else ("t3" if r["top3_hit"] else "MISS")
        print(f"{r['prompt'][:52]:52s} {r['expect'][:24]:24s} "
              f"{str(r['rank'] or '-'):>4s}  {mark}")
    print("-" * 94)
    print(f"top-1 accuracy : {top1}/{len(cases)}  ({100*acc1:.0f}%)   floor {100*TOP1_FLOOR:.0f}%")
    print(f"top-3 recall   : {top3}/{len(cases)}  ({100*acc3:.0f}%)")
    print(f"reject in top-1: {rejviol}  (a neighbour outranking the right skill)")
    if never:
        print(f"\nnever wins a prompt ({len(never)}) — either the fixture lacks a case for "
              f"it, or its description does not discriminate:")
        for n in never:
            print(f"  {n}")
    misses = [r for r in rows if not r["top1"]]
    if misses:
        print(f"\nmisrouted ({len(misses)}):")
        for r in misses:
            print(f"  {r['prompt'][:60]}")
            print(f"     wanted {r['expect']} (rank {r['rank']}), got {r['top3'][0]}")
            print(f"     scores {r['scores']}")
    if a.show_overlap:
        print("\nleast separable description pairs (shared weighted terms):")
        pairs = []
        for i, x in enumerate(sorted(dtoks)):
            for y in sorted(dtoks)[i+1:]:
                sh = set(dtoks[x]) & set(dtoks[y])
                pairs.append((sum(idf.get(t, 1) for t in sh), x, y, len(sh)))
        for s, x, y, n in sorted(pairs, reverse=True)[:8]:
            print(f"  {s:6.1f}  {x} <-> {y}  ({n} shared terms)")
    print("\nLexical overlap only. It cannot tell you the model will choose correctly; "
          "it can tell you two descriptions are indistinguishable on words alone.")
    return 0 if (acc1 >= TOP1_FLOOR and not never) else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Flag claims about code that carry no evidence label and no file:line citation.

An inferred claim reads exactly like a verified one, which is why it is the most
expensive kind of wrong: nothing in its phrasing invites checking. This finds
claim-shaped sentences in a document and reports the ones with no provenance.

Heuristic by construction: it matches assertive sentences about code, so it will flag
prose that is fine and miss claims phrased as questions. It narrows what a reader must
check; it does not judge truth. Labels are defined in reviewers/_evidence-labels.md.

    check_claims.py docs/comprehension-auth.md
    check_claims.py rca/ --min-ratio 0.5
    check_claims.py research/30-findings-js-verification.md --json

Exit 1 if the labelled-or-cited ratio falls below --min-ratio.
Python stdlib only.
"""
import argparse, json, pathlib, re, sys

LABELS = ("Verified", "Inferred", "Illustrative", "Added", "Corrected", "Uncertain",
          "SOURCE: original")
LABEL_RX = re.compile("|".join(re.escape(l) for l in LABELS))
# a file:line, or owner/repo:path, counts as provenance
CITE_RX = re.compile(r"[\w./-]+\.[a-z]{1,4}:\d+|[\w.-]+/[\w.-]+[:@][\w./-]+|`[^`]+:\d+`")
# assertive sentences about code/behaviour
CLAIM_RX = re.compile(
    r"\b(is|are|was|were|has|have|does|do|uses|calls|returns|throws|stores|"
    r"defaults? to|runs|blocks|enforces|validates|caches|retries|expires)\b", re.I)
SKIP_RX = re.compile(r"^\s*(#{1,6}\s|>\s|\||```|-{3,}|\d+\.\s*$|$)")


def analyse(path):
    text = path.read_text(errors="replace")
    lines, fence = text.splitlines(), False
    claims, ok = [], []
    for i, l in enumerate(lines, 1):
        if l.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence or SKIP_RX.match(l) or len(l.strip()) < 25:
            continue
        if not CLAIM_RX.search(l):
            continue
        # a claim is covered if it, or the line after it, carries a label or citation
        window = l + " " + (lines[i] if i < len(lines) else "")
        if LABEL_RX.search(window) or CITE_RX.search(window):
            ok.append((i, l.strip()))
        else:
            claims.append((i, l.strip()))
    return claims, ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--min-ratio", type=float, default=0.5)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    p = pathlib.Path(a.path)
    files = sorted(p.rglob("*.md")) if p.is_dir() else [p]
    files = [f for f in files if f.is_file() and f.name != "INDEX.md"]
    if not files:
        print(f"no markdown found at {a.path}"); return 0

    results, tot_c, tot_ok = [], 0, 0
    for f in files:
        unl, cited = analyse(f)
        tot_c += len(unl); tot_ok += len(cited)
        results.append({"file": str(f), "unlabelled": len(unl), "covered": len(cited),
                        "examples": [{"line": n, "text": t[:110]} for n, t in unl[:5]]})
    total = tot_c + tot_ok
    ratio = (tot_ok / total) if total else 1.0

    if a.json:
        print(json.dumps({"ratio": round(ratio, 3), "covered": tot_ok,
                          "unlabelled": tot_c, "files": results}, indent=2))
        return 0 if ratio >= a.min_ratio else 1

    print(f"check_claims: {len(files)} file(s), {total} claim-shaped line(s)")
    print(f"  with a label or citation : {tot_ok}")
    print(f"  with neither             : {tot_c}")
    print(f"  ratio {ratio:.0%} (floor {a.min_ratio:.0%})\n")
    for r in sorted(results, key=lambda x: -x["unlabelled"])[:8]:
        if not r["unlabelled"]:
            continue
        print(f"  {r['file']}  ({r['unlabelled']} unlabelled)")
        for e in r["examples"]:
            print(f"     {e['line']:>5}: {e['text']}")
    print("\nLabels: " + ", ".join(LABELS[:6]) +
          " — see reviewers/_evidence-labels.md.\nHeuristic: it flags assertive prose, "
          "so some hits are fine. It narrows what to check, it does not judge truth.")
    return 0 if ratio >= a.min_ratio else 1


if __name__ == "__main__":
    sys.exit(main())

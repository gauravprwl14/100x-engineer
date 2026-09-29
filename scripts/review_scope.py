#!/usr/bin/env python3
"""Emit the review questions that mechanical checks cannot answer, scoped to this diff.

Both research passes reached the same conclusion: tools settle roughly the objectively
checkable part — dead code, cycles, unused deps, complexity, byte budgets, API-surface
diffs, assertion-free tests — and a short list of defect classes has no mechanical
coverage in any production repo surveyed. The right architecture is therefore to let
the tools narrow the surface, then route what is left to a reviewer asked ONLY those
questions, rather than asked to re-derive what the tools already decided.

This produces that scoped checklist, so "review it" becomes a finite list of answerable
questions attached to specific files.

    review_scope.py                        # vs HEAD
    review_scope.py --base origin/main
    review_scope.py --json

Every question must be answered yes / no / n-a. Silence is not a pass.
Python stdlib only.
"""
import argparse, json, re, subprocess, sys, pathlib

# (id, question, applies-to predicate key, what a "no" means)
QUESTIONS = [
 ("R1", "Is every new abstraction (interface, base class, wrapper, factory) used by "
        "more than one caller, or is it speculative?", "abstraction",
  "delete it and inline the single use; add the seam when the second caller exists"),
 ("R2", "Does any added logic duplicate logic that already exists elsewhere under a "
        "different name? (copy-paste detectors miss this when variables are renamed)",
  "logic", "extract or reuse the existing implementation"),
 ("R3", "Does every added comment explain WHY rather than restate WHAT the code does?",
  "comment", "delete the comment or the code it narrates"),
 ("R4", "Was each added dependency checked against the standard library and the "
        "existing dependency list first?", "dependency",
  "remove it and use what is already present"),
 ("R5", "Do the added tests assert the INTENDED behaviour, not merely the behaviour the "
        "implementation happens to have? (a test written from the code locks the bug in)",
  "test", "derive the expectation from the spec, then check the code against it"),
 ("R6", "For every data access added, is authorization checked against the CALLER, not "
        "just the record id?", "authz",
  "add the ownership/tenant check and a negative test for it"),
 ("R7", "For every check-then-act sequence (exists? then insert / read then write), is "
        "the race handled by a constraint, lock, or atomic operation?", "race",
  "enforce it in the database or use an atomic operation"),
 ("R8", "Does every new file earn its existence, or should this have been an edit to an "
        "existing module?", "newfile",
  "fold it into the existing module"),
 ("R9", "Are the edge cases marked `accepted` or `deferred` in the spec still the right "
        "call given what the implementation revealed?", "spec",
  "reopen the spec row and change its status"),
]

PRED = {
 "abstraction": re.compile(r"^\+.*\b(interface|abstract class|class \w+\(ABC\)|"
                           r"type \w+ interface|Protocol\)|Factory|Wrapper|Adapter)\b"),
 "logic":       re.compile(r"^\+.*\b(for |while |if |def |func |function |=> ?\{)"),
 "comment":     re.compile(r"^\+\s*(//|#|\*)\s*\w"),
 "dependency":  None,   # file-name based
 "test":        None,
 "authz":       re.compile(r"^\+.*\b(find|findOne|findById|get|select|query|fetch|"
                           r"delete|update)\w*\s*\("),
 "race":        re.compile(r"^\+.*\b(exists|findBy|findOne|count|get)\w*\s*\("),
 "newfile":     None,
 "spec":        None,
}
DEP_FILES = re.compile(r"(package\.json|requirements.*\.txt|pyproject\.toml|go\.mod|"
                       r"Gemfile|composer\.json|Cargo\.toml|pubspec\.yaml)$")
TEST_FILE = re.compile(r"(^|/)(tests?|spec|__tests__)/|[._](test|spec)\.|_test\.(go|py)$", re.I)
CODE_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".py", ".go", ".java", ".kt",
            ".swift", ".dart", ".rb", ".cs", ".rs", ".php"}
# Fixtures and generated artifacts are not the author's code under review.
NOISE = re.compile(r"(^|/)(evals/seeded|node_modules|dist|build|\.git)/|"
                   r"(^|/)(INDEX\.md)$")


def is_code(f):
    return pathlib.Path(f).suffix in CODE_EXT and not NOISE.search(f)


def sh(args):
    r = subprocess.run(args, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    rng = [a.base] if a.base else ["HEAD"]

    status = sh(["git", "diff", "--name-status", "--diff-filter=AMR"] + rng)
    added, modified = [], []
    for line in status.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        (added if parts[0].startswith("A") else modified).append(parts[-1])
    for p in sh(["git", "ls-files", "--others", "--exclude-standard"]).splitlines():
        if p and p not in added:
            added.append(p)
    files = added + modified
    if not files:
        print("review_scope: no changes to review")
        return 0

    # Added lines attributed PER FILE, so each question names only the files that
    # actually contain a matching line. A blanket file list is noise, and a reviewer
    # handed noise stops reading.
    per_file = {}
    cur = None
    for l in sh(["git", "diff", "--unified=0"] + rng).splitlines():
        if l.startswith("+++ b/"):
            cur = l[6:]
            per_file.setdefault(cur, [])
        elif l.startswith("+") and not l.startswith("+++") and cur:
            per_file[cur].append(l)
    for p_ in added:
        try:
            per_file.setdefault(p_, [])
            per_file[p_] += ["+" + x for x in
                             pathlib.Path(p_).read_text(errors="replace").splitlines()]
        except OSError:
            pass
    files = [f for f in files if not NOISE.search(f)]

    # which questions are in scope, and on which files
    scope = {}
    for qid, q, key, remedy in QUESTIONS:
        hits = []
        if key == "dependency":
            hits = [f for f in files if DEP_FILES.search(f)]
        elif key == "test":
            hits = [f for f in files if TEST_FILE.search(f) and is_code(f)]
        elif key == "newfile":
            hits = [f for f in added if is_code(f) and not TEST_FILE.search(f)]
        elif key == "spec":
            hits = [f for f in files if f.endswith("/spec.md") and not NOISE.search(f)]
        else:
            rx = PRED[key]
            hits = [f for f, lines in per_file.items()
                    if is_code(f) and not TEST_FILE.search(f)
                    and rx and any(rx.search(l) for l in lines)]
        if hits:
            scope[qid] = {"question": q, "remedy_if_no": remedy, "files": hits[:12]}

    if a.json:
        print(json.dumps({"changed": len(files), "in_scope": scope}, indent=2))
        return 0

    print(f"# Scoped review — {len(files)} changed file(s), {len(scope)} question(s) in scope\n")
    print("Mechanical checks have already run. These are the defect classes no tool in "
          "this plugin, or in any production repo surveyed, detects. Answer each one "
          "explicitly: `yes`, `no`, or `n-a` with a reason. An unanswered question is "
          "not a pass.\n")
    print("| id | answer | question | if the answer is no |")
    print("|---|---|---|---|")
    for qid in [q[0] for q in QUESTIONS]:
        if qid in scope:
            s = scope[qid]
            print(f"| {qid} | ` ` | {s['question']} | {s['remedy_if_no']} |")
    print("\n## Files per question\n")
    for qid, s in scope.items():
        print(f"- **{qid}**: {', '.join(s['files'])}")
    print("\nRun the mechanical checks first so this review is not spent on what they "
          "already settle:\n")
    print("```bash\npython3 scripts/bloat_check.py --base " + (a.base or "HEAD") +
          "\npython3 scripts/decide.py verify && python3 scripts/decide.py drift\n```")
    return 0


if __name__ == "__main__":
    sys.exit(main())

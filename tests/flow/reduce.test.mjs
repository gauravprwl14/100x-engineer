// The player's JS reducer must produce exactly what scripts/flow.py reduce produces:
// tests/flow/states.json is that output for every case. Run: node --test tests/flow/
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..", "..");
const require = createRequire(import.meta.url);
const { reduceScenario, ReduceError, parseAt, splitTerms, outlineHits, stepSnippets, effectiveSteps, heroSummary, worstIssue, confidenceOf } = require(path.join(root, "skills/explain/assets/flow-player.js"));
const golden = JSON.parse(readFileSync(path.join(here, "states.json"), "utf8"));
const load = file => JSON.parse(readFileSync(path.join(root, file), "utf8"));

for (const c of golden.cases) {
  const doc = load(c.file);
  for (const [sid, states] of Object.entries(c.scenarios)) {
    test(`${c.file} ${sid}: JS states equal flow.py's`, () => {
      assert.deepEqual(reduceScenario(doc, sid), states);
    });
  }
}

test("the golden cases use every action in the vocabulary", () => {
  const vocab = ["send", "reply", "enqueue", "pickup", "free", "cache.get", "cache.set", "cache.set-if-fresh",
    "cache.del", "cache.expire", "mark-stale", "db.read", "db.write", "wait", "counter", "fail", "note"];
  const used = new Set();
  for (const c of golden.cases) for (const s of load(c.file).scenarios) for (const st of s.steps) for (const a of st.do) used.add(a[0]);
  assert.deepEqual(vocab.filter(a => !used.has(a)), []);
});

const mini = steps => ({
  schema: 1, title: "t", subject: { kind: "concept", lede: "l" },
  nodes: [{ id: "api", role: "service", label: "API" }, { id: "c", role: "cache", label: "C" },
          { id: "db", role: "store", label: "DB" }, { id: "q", role: "queue", label: "Q" },
          { id: "w", role: "worker", label: "W" }],
  initial: { stores: { db: { k: "v1" } } },
  scenarios: [{ id: "s", kind: "race", title: "s", steps: steps.map(d => ({ t: "x", do: d, tag: "inferred" })) }],
});

test("set-if-fresh writes when the store still holds the value read", () => {
  const [st] = reduceScenario(mini([[["db.read", "db", "k"], ["cache.set-if-fresh", "c", "key", "$read"]]]), "s");
  assert.deepEqual(st.caches.c.key, { v: "v1", stale: false, src: ["db", "k"] });
  assert.deepEqual([st.skipped, st.hazards], [[], []]);
});

test("set-if-fresh skips, without a hazard, when a write landed after the read", () => {
  const sts = reduceScenario(mini([[["db.read", "db", "k"]], [["db.write", "db", "k", "v2"]], [["cache.set-if-fresh", "c", "key", "$read"]]]), "s");
  const last = sts[2];
  assert.equal(Object.hasOwn(last.caches.c, "key"), false);
  assert.deepEqual(last.skipped, [{ cache: "c", key: "key", store: "db", store_key: "k", read: "v1", current: "v2" }]);
  assert.deepEqual(last.hazards, []);
});

test("plain cache.set in the same race raises stale-writeback", () => {
  const sts = reduceScenario(mini([[["db.read", "db", "k"]], [["db.write", "db", "k", "v2"]], [["cache.set", "c", "key", "$read"]]]), "s");
  assert.equal(sts[2].hazards[0].kind, "stale-writeback");
});

test("an unbound $var is a ReduceError naming the step", () => {
  assert.throws(() => reduceScenario(mini([[["cache.set-if-fresh", "c", "key", "$nope"]]]), "s"),
    e => e instanceof ReduceError && /scenario s step 0: cache\.set-if-fresh: variable '\$nope' is unbound/.test(e.message));
});

test("pickup from an empty queue is a ReduceError", () => {
  assert.throws(() => reduceScenario(mini([[["pickup", "q", "w"]]]), "s"), ReduceError);
});

test("a key named __proto__ stays an ordinary key", () => {
  const [st] = reduceScenario(mini([[["db.write", "db", "__proto__", "x"]]]), "s");
  assert.equal(Object.getPrototypeOf(st.stores.db), Object.prototype);
  assert.equal(Object.getOwnPropertyDescriptor(st.stores.db, "__proto__").value, "x");
});

test("an evidence path may hold @: only a trailing @<7-40 hex> is the revision", () => {
  assert.deepEqual(parseAt("packages/@scope/x.ts:12@abc1234"), { path: "packages/@scope/x.ts", line: "12", rev: "abc1234" });
  assert.deepEqual(parseAt("packages/@scope/x.ts:12"), { path: "packages/@scope/x.ts", line: "12", rev: null });
  assert.equal(parseAt("x.ts:12@abc123"), null); // six hex is not a revision
  assert.equal(parseAt("x.ts:0"), null);
});

test("parseAt matches flow.py AT_RX on the same inputs", () => {
  const cases = ["src/a.js:3", "src/a.js:3@abc1234", "packages/@scope/x.ts:12@abc1234", "@s/x.ts:1", "a@b:2@" + "f".repeat(40),
    "x.ts:12@abc123", "x.ts:0", "x.ts", ":3", "a:b:3", "x.ts:3@ABC1234", "x.ts:3@" + "a".repeat(41)];
  const py = "import json,sys; sys.path.insert(0, sys.argv[1]); import flow\n" +
    "print(json.dumps([(lambda m: m and {'path': m['path'], 'line': m['line'], 'rev': m['rev']})(flow.AT_RX.match(c)) for c in json.loads(sys.argv[2])]))";
  const want = JSON.parse(execFileSync("python3", ["-c", py, path.join(root, "scripts"), JSON.stringify(cases)], { encoding: "utf8" }));
  assert.deepEqual(cases.map(parseAt), want);
});

test("splitTerms wraps whole-word terms in any case and leaves part-words alone", () => {
  const terms = [{ term: "TTL" }, { term: "cache" }, { term: "Promise.all" }];
  assert.deepEqual(splitTerms("The Cache TTL ends; caches and recache stay.", terms),
    ["The ", { term: "Cache", i: 1 }, " ", { term: "TTL", i: 0 }, " ends; caches and recache stay."]);
  assert.deepEqual(splitTerms("Promise.all(x)", terms), [{ term: "Promise.all", i: 2 }, "(x)"]);
  assert.deepEqual(splitTerms("no glossary", []), ["no glossary"]);
});

test("splitTerms prefers the longest term and matches next to CJK text", () => {
  const terms = [{ term: "cache" }, { term: "cache key" }];
  assert.deepEqual(splitTerms("キャッシュのcache keyを消す", terms), ["キャッシュの", { term: "cache key", i: 1 }, "を消す"]);
});

test("outlineHits lights a line by step identity, so a fix's inherited step matches the issue's line", () => {
  const doc = load("skills/explain/assets/examples/stale-writeback.json");
  const sc = {}; for (const s of doc.scenarios) sc[s.id] = s;
  const entries = {}; for (const id of Object.keys(sc)) entries[id] = effectiveSteps(id, sc);
  const outline = [{ scenario: "race", lines: [{ code: "a", steps: [1] }, { code: "b", steps: [5] }, { code: "c" }] }];
  assert.deepEqual(outlineHits(outline, entries, "race", 1), [{ o: 0, l: 0 }]);
  assert.deepEqual(outlineHits(outline, entries, "fix-set-if-fresh", 1), [{ o: 0, l: 0 }]); // inherited from race
  assert.deepEqual(outlineHits(outline, entries, "fix-set-if-fresh", 5), []); // the fix's own step, not race's step 5
  assert.deepEqual(outlineHits(outline, entries, "race", 99), []);
});

test("stepSnippets keeps well-formed snippets for the step's evidence and skips the rest", () => {
  const good = { path: "src/a.js", sha: "abc1234", start: 3, lines: ["x", "y"], hl: 4 };
  const snippets = { e1: good, e2: { path: "src/b.js", start: 0, lines: ["z"], hl: 1 }, e3: { path: "c", start: 1, lines: [], hl: 1 } };
  assert.deepEqual(stepSnippets({ ev: ["e1", "e2", "e3", "e4"] }, snippets), [Object.assign({ ev: "e1" }, good)]);
  assert.deepEqual(stepSnippets({ ev: ["e1"] }, {}), []);
  assert.deepEqual(stepSnippets({ ev: ["e1"] }, null), []);
  assert.deepEqual(stepSnippets({}, snippets), []);
});

const pr = extra => Object.assign({
  subject: { kind: "pr", lede: "The lede." }, context: { purpose: "The purpose." },
  outline: [{ title: "run(x)", lines: [] }],
  scenarios: [{ id: "a", severity: "medium", title: "A" }, { id: "b", severity: "high", title: "B" }, { id: "c", severity: "high", title: "C" }],
}, extra);

test("heroSummary: tldr's what is the headline, so no What card repeats it; how and watch out are cards", () => {
  const s = heroSummary(pr({ tldr: { what: "W", how: { en: "H", ja: "ほ" }, watch_out: "O" } }));
  assert.deepEqual([s.purpose, s.what, s.how, s.watch, s.lede], ["W", null, { en: "H", ja: "ほ" }, { text: "O" }, "The lede."]);
});

test("heroSummary without tldr: no card repeats the purpose, how falls back to the outline, watch to the worst issue", () => {
  const s = heroSummary(pr({}));
  assert.equal(s.what, null); // its first text, context.purpose, is the big sentence already
  assert.deepEqual(s.how, { code: "run(x)" });
  assert.deepEqual(s.watch, { issue: "b", severity: "high" }); // first of the two highs
  assert.equal(s.lede, "The lede."); // used by no card, so it stays as detail
});

test("heroSummary with only a lede: it is the purpose and no card or detail repeats it", () => {
  const s = heroSummary({ subject: { kind: "plan", lede: "Only." }, scenarios: [{ id: "a", title: "A" }] });
  assert.deepEqual([s.purpose, s.what, s.how, s.watch, s.lede], ["Only.", null, null, null, null]);
});

test("worstIssue ranks critical over high and ignores scenarios with no severity", () => {
  assert.equal(worstIssue({ scenarios: [{ id: "x" }, { id: "h", severity: "high" }, { id: "k", severity: "critical" }] }).id, "k");
  assert.equal(worstIssue({ scenarios: [{ id: "x" }] }), null);
});

test("confidenceOf counts a step verified only when it cites evidence and is not tagged inferred", () => {
  const doc = { scenarios: [{ steps: [{ ev: ["e"] }, { ev: [] }, { ev: ["e"], tag: "inferred" }] }, { steps: [{ ev: ["f"] }] }] };
  assert.deepEqual(confidenceOf(doc), { verified: 2, total: 4 });
  assert.deepEqual(confidenceOf({ scenarios: [] }), { verified: 0, total: 0 });
});

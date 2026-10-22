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
const { reduceScenario, ReduceError, parseAt } = require(path.join(root, "skills/explain/assets/flow-player.js"));
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

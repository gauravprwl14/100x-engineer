// node --test tests/flow/system.test.mjs
// The system map's layout, routing and markup (skills/explain/assets/system-map.js) against 300
// random subjects, so "it draws any subject" is tested and not assumed, plus the cases a fixed
// layout gets wrong: a link that must pass boxes it does not connect, labels wider than the gap,
// text that is not ours (escaping), text without spaces (Japanese), and one column on a phone.
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SM = createRequire(import.meta.url)(join(HERE, "..", "..", "skills", "explain", "assets", "system-map.js"));
const tx = s => (typeof s === "string" ? s : s.en);
const draw = (sys, narrow = false) => { const L = SM.layout(sys, { tx, narrow }), R = SM.route(sys, L, { tx }); return { L, R, S: SM.stats(L, R) }; };

// a small seeded generator, so a failure names its seed and replays
function rng(seed) { let a = seed >>> 0; return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const WORDS = ["Gateway", "Ledger", "Reader", "Queue", "Planner", "Cache", "Auditor", "Mailer", "Billing", "Index", "Console", "Worker", "Vault", "Router", "Scheduler"];
const SUBS = [undefined, "does the work", "keeps a copy for a while, then lets it go", "outside our control", "reads and writes in order"];
function subject(seed) {
  const r = rng(seed), pick = a => a[Math.floor(r() * a.length)];
  let n = 0;
  const make = depth => {
    const count = 1 + Math.floor(r() * 4), items = [];
    for (let i = 0; i < count; i++) {
      const id = "n" + n++;
      if (depth < 2 && r() < 0.4) items.push({ id, label: pick(WORDS) + " group", sub: r() < 0.3 ? "a set of parts" : undefined, cols: 1 + Math.floor(r() * 3), items: make(depth + 1) });
      else items.push({ id, label: pick(WORDS) + " " + id, sub: pick(SUBS), kind: pick([undefined, "actor", "data", "external"]) });
    }
    return items;
  };
  const items = make(0), parent = {}, ids = [];
  (function walk(list, up) { for (const x of list) { ids.push(x.id); parent[x.id] = up; if (x.items) walk(x.items, x.id); } })(items, null);
  const anc = id => { const out = new Set(); for (let p = parent[id]; p; p = parent[p]) out.add(p); return out; };
  const links = [], steps = 1 + Math.floor(r() * 5);
  for (let k = 0, tries = 0; k < 3 + Math.floor(r() * 14) && tries < 200; tries++) {
    const a = pick(ids), b = pick(ids);
    if (a === b || anc(a).has(b) || anc(b).has(a)) continue;
    links.push({ from: a, to: b, label: r() < 0.8 ? pick(["read", "writes the record", "asks", "notifies", "if it is down: wait", "sync"]) : undefined, style: pick(SM.STYLES), n: r() < 0.5 ? 1 + Math.floor(r() * steps) : undefined, tag: "inferred" });
    k++;
  }
  return { items, links, cols: 1 + Math.floor(r() * 3) };
}
const inside = (inner, outer) => inner.x >= outer.x && inner.y >= outer.y && inner.x + inner.w <= outer.x + outer.w && inner.y + inner.h <= outer.y + outer.h;

test("300 random subjects: no overlaps, every child inside its group, everything finite and inside the canvas", () => {
  for (let seed = 1; seed <= 300; seed++) {
    const sys = subject(seed), { L, S } = draw(sys);
    const where = `seed ${seed}`;
    assert.equal(S.overlaps, 0, `${where}: boxes overlap`);
    assert.equal(S.outside, 0, `${where}: a child sticks out of its group`);
    for (const b of Object.values(L.boxes)) {
      assert.ok([b.x, b.y, b.w, b.h].every(Number.isFinite), `${where}: ${b.id} not finite`);
      assert.ok(b.x >= 0 && b.y >= 0 && b.x + b.w <= L.W + 0.5 && b.y + b.h <= L.H + 0.5, `${where}: ${b.id} outside the canvas`);
      if (b.parent) assert.ok(inside(b, L.boxes[b.parent]), `${where}: ${b.id} outside ${b.parent}`);
    }
  }
});

test("300 random subjects: same input, same picture (layout, routes and markup)", () => {
  for (let seed = 1; seed <= 300; seed++) {
    const sys = subject(seed), a = draw(sys), b = draw(sys);
    assert.equal(JSON.stringify(a.L), JSON.stringify(b.L), `seed ${seed}: layout differs`);
    assert.equal(SM.svg(sys, a.L, a.R, { tx, id: "x" }), SM.svg(sys, b.L, b.R, { tx, id: "x" }), `seed ${seed}: markup differs`);
  }
});

test("300 random subjects: each route leaves and enters its boxes on the border", () => {
  const onBorder = (p, b) => {
    const dx = Math.min(Math.abs(p[0] - b.x), Math.abs(p[0] - (b.x + b.w))), dy = Math.min(Math.abs(p[1] - b.y), Math.abs(p[1] - (b.y + b.h)));
    const within = p[0] >= b.x - 1 && p[0] <= b.x + b.w + 1 && p[1] >= b.y - 1 && p[1] <= b.y + b.h + 1;
    return within && Math.min(dx, dy) <= 1;
  };
  for (let seed = 1; seed <= 300; seed++) {
    const sys = subject(seed), { L, R } = draw(sys);
    for (const r of R.routes) {
      assert.ok(onBorder(r.pts[0], L.boxes[r.from]), `seed ${seed}: ${r.from} -> ${r.to} does not start on ${r.from}`);
      assert.ok(onBorder(r.pts[r.pts.length - 1], L.boxes[r.to]), `seed ${seed}: ${r.from} -> ${r.to} does not end on ${r.to}`);
    }
  }
});

test("a label that found a free spot never overlaps anything: overlaps only come from the counted fallback", () => {
  for (let seed = 1; seed <= 300; seed++) {
    const { S } = draw(subject(seed));
    if (S.crowded === 0) assert.equal(S.tagOverlaps, 0, `seed ${seed}: crowded 0 but ${S.tagOverlaps} label overlap(s)`);
  }
});

test("a link between the first and last box of one column goes around the boxes between, not through them", () => {
  const col = ["a", "b", "c", "d"].map(id => ({ id, label: id.toUpperCase() + " part" }));
  const sys = { cols: 1, items: [{ id: "g", label: "Stack", cols: 1, items: col }], links: [{ from: "a", to: "d", label: "skips two", tag: "inferred" }] };
  const { S } = draw(sys);
  assert.equal(S.through, 0);
});

test("two links between the same pair do not sit on each other", () => {
  const sys = { items: [{ id: "x", label: "X part" }, { id: "y", label: "Y part" }], links: [{ from: "x", to: "y", label: "one", tag: "inferred" }, { from: "x", to: "y", label: "two", tag: "inferred" }] };
  const { R, S } = draw(sys);
  assert.notEqual(R.routes[0].d, R.routes[1].d);
  assert.equal(S.tagOverlaps, 0);
});

test("the gap between groups grows with the widest label that has to cross it", () => {
  const mk = label => ({ items: [{ id: "g1", label: "Left", items: [{ id: "a", label: "A part" }] }, { id: "g2", label: "Right", items: [{ id: "b", label: "B part" }] }],
                         links: [{ from: "a", to: "b", label, tag: "inferred" }] });
  const gap = sys => { const { L } = draw(sys); return L.boxes.g2.x - (L.boxes.g1.x + L.boxes.g1.w); };
  assert.ok(gap(mk("a much longer label for the link")) > gap(mk("ok")), "a long label gets a wider gap");
});

test("markup escapes text that is not ours", () => {
  const evil = '<img src=x onerror=alert(1)> & "quoted"';
  const sys = { items: [{ id: "a", label: evil, sub: evil }, { id: "g", label: evil, items: [{ id: "b", label: "B part" }] }], links: [{ from: "a", to: "b", label: evil, n: 1, tag: "inferred" }] };
  const { L, R } = draw(sys), out = SM.svg(sys, L, R, { tx, id: "x", title: evil });
  assert.ok(!/<img/i.test(out) && !/onerror=alert\(1\)>/.test(out.replace(/&lt;img[^>]*&gt;/g, "")), "no raw tag survives");
  assert.ok(out.includes("&lt;img"), "it is shown as text");
});

test("a part with no subtitle never prints the word undefined", () => {
  const sys = { items: [{ id: "a", label: "Alpha" }, { id: "b", label: "Beta" }], links: [{ from: "a", to: "b", tag: "inferred" }] };
  const { L, R } = draw(sys);
  assert.ok(!/undefined/.test(SM.svg(sys, L, R, { id: "x" })), "default text function");
});

test("text without spaces (Japanese) wraps into at most two lines and stays inside its box", () => {
  const sub = "これは長い説明文でスペースがなくても折り返されることを確かめるための文章です。もっと長くしてみます。";
  const lines = SM.wrap(sub, SM.K.subPx, SM.K.partMaxW - 2 * SM.K.partPad, SM.K.maxSubLines);
  assert.ok(lines.length >= 1 && lines.length <= 2);
  for (const l of lines) assert.ok(SM.textW(l, SM.K.subPx) <= SM.K.partMaxW - 2 * SM.K.partPad + 1, "a line is wider than the box");
});

test("narrow (a phone) is one column at every level and no wider than the wide layout", () => {
  for (let seed = 1; seed <= 60; seed++) {
    const sys = subject(seed), wide = draw(sys), narrow = draw(sys, true);
    assert.ok(narrow.L.W <= wide.L.W + 0.5, `seed ${seed}: narrow ${narrow.L.W} wider than wide ${wide.L.W}`);
    const top = Object.values(narrow.L.boxes).filter(b => !b.parent);
    assert.equal(new Set(top.map(b => b.y)).size, top.length, `seed ${seed}: two top-level boxes share a row`);
  }
});

test("every committed fixture draws with no overlap, no child outside its group, and no label clash", () => {
  const dir = join(HERE, "system"), files = [...readdirSync(dir).filter(n => n.endsWith(".json") && n !== "bench-cases.json").map(n => join(dir, n)),
    ...readdirSync(join(dir, "ab")).map(n => join(dir, "ab", n))];
  for (const f of files) {
    const { S } = draw(JSON.parse(readFileSync(f, "utf8")).system);
    assert.equal(S.overlaps, 0, `${f}: overlaps`); assert.equal(S.outside, 0, `${f}: outside`); assert.equal(S.tagOverlaps, 0, `${f}: label clashes`);
  }
});

test("the engine file knows no subject: no product, team or project name is written into it", () => {
  const src = readFileSync(join(HERE, "..", "..", "skills", "explain", "assets", "system-map.js"), "utf8");
  for (const word of ["100x", "tunag", "stmn", "grok", "claude", "codex", "gemini", "t3 code", "opus", "notes", "cache", "plugin"]) {
    assert.ok(!src.toLowerCase().includes(word), `system-map.js mentions "${word}"`);
  }
});

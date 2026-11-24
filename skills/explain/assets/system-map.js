/* System map: the one-picture overview of any subject (a system, a module, a PR, a concept, a
   process). Pure functions, no DOM and no network, so the same code draws the page and is tested in
   node (tests/flow/system.test.mjs). The agent supplies a tree of groups and parts plus labelled
   links; nothing here knows what a subject is called.

     layout(sys, {tx, narrow})  -> L   boxes by id: {x, y, w, h, kind, depth, parent, lines}
     route(sys, L, {tx})        -> R   {routes, tags, crowded}: an orthogonal path per link
     svg(sys, L, R, {tx, id, title}) -> markup string
     stats(L, R)                -> overlaps, outside, through, crowded, minFont (what the bench reads)

   build() prepends this file to the player, so SystemMap is a global of the page script. */
const SystemMap = (function () {
const K = {
  partMinW: 112, partMaxW: 240, partPad: 12, labelPx: 12.5, subPx: 10.5, lineH: 12, partBase: 34, maxSubLines: 2,
  gap: 30, gapMax: 150, gapSlack: 12, groupPad: 14, groupHead: 28, groupPx: 12, outer: 16, topCols: 3,
  corner: 6, portInset: 4, offStep: 17, tagPx: 10.5, tagH: 16, tagPad: 5, badgeR: 8, tagTries: [0.5, 0.45, 0.55, 0.4, 0.6, 0.35, 0.65, 0.3, 0.7, 0.25, 0.75, 0.2, 0.8, 0.15, 0.85, 0.1, 0.9],
  midTries: 5, through: 1000, bend: 30, detour: 12,
};
const STYLES = ["call", "data", "async", "watch", "risk"];

const cjk = ch => ch.codePointAt(0) > 0x2e80;
function textW(s, px) { let w = 0; for (const ch of String(s)) w += cjk(ch) ? px : px * 0.58; return w; }
function clip(s, maxW, px) {
  s = String(s);
  if (textW(s, px) <= maxW) return s;
  let out = "";
  for (const ch of s) { if (textW(out + ch + "…", px) > maxW) break; out += ch; }
  return out + "…";
}
// Greedy wrap at spaces (any character for text without spaces), at most `most` lines, the last clipped.
function wrap(s, px, maxW, most) {
  s = String(s || "").trim();
  if (!s) return [];
  const words = s.split(/(\s+)/).filter(x => x !== ""), lines = [];
  let cur = "";
  for (const w of words) {
    if (textW(cur + w, px) <= maxW || !cur.trim()) { cur += w; continue; }
    lines.push(cur.trim()); cur = w.trimStart();
  }
  if (cur.trim()) lines.push(cur.trim());
  const fit = lines.flatMap(l => { // a word wider than the line breaks by characters
    if (textW(l, px) <= maxW) return [l];
    const parts = []; let c = "";
    for (const ch of l) { if (textW(c + ch, px) > maxW && c) { parts.push(c); c = ""; } c += ch; }
    if (c) parts.push(c);
    return parts;
  });
  if (fit.length <= most) return fit;
  const keep = fit.slice(0, most);
  keep[most - 1] = clip(fit.slice(most - 1).join(" "), maxW, px);
  return keep;
}
const isGroup = n => Array.isArray(n.items);
const idOf = n => n.id;

/* ---- layout: a grid per group, each child centred in its cell ---- */
function layout(sys, opts) { return layoutOnce(sys, opts, Infinity, Infinity); }
// The same subject drawn with fewer columns: capTop limits the columns of the top level, capInner those of every group.
function layoutOnce(sys, opts, capTop, capInner) {
  const tx = (opts && opts.tx) || String, narrow = !!(opts && opts.narrow);
  const boxes = {}, order = [];
  // A link between two cells of a group draws its label in the gap between them, so that gap is as
  // wide as the widest label crossing it: the layout follows the subject's own words.
  const par = {};
  (function walk(items, up) { for (const n of items) { par[n.id] = up; if (isGroup(n)) walk(n.items, n.id); } })(sys.items, null);
  const chain = id => { const c = []; for (let p = par[id]; p !== null && p !== undefined; p = par[p]) c.push(p); c.push(null); return c; };
  const corridor = {};
  for (const l of sys.links || []) {
    if (!(l.from in par) || !(l.to in par)) continue;
    const cb = chain(l.to), at = chain(l.from).find(x => cb.includes(x));
    const w = tagWidth(l, tx);
    corridor[at] = Math.max(corridor[at] || 0, w);
  }
  const gapOf = at => Math.min(K.gapMax, Math.max(K.gap, Math.ceil((corridor[at] || 0) + K.gapSlack)));

  function measure(n, depth) {
    if (!isGroup(n)) {
      const label = tx(n.label), subLines = wrap(n.sub ? tx(n.sub) : "", K.subPx, K.partMaxW - 2 * K.partPad, K.maxSubLines);
      const w = Math.min(K.partMaxW, Math.max(K.partMinW, textW(label, K.labelPx) + 2 * K.partPad,
        ...subLines.map(l => textW(l, K.subPx) + 2 * K.partPad)));
      return { n, kind: "part", depth, w: Math.ceil(w), h: K.partBase + K.lineH * subLines.length, subLines };
    }
    const kids = n.items.map(c => measure(c, depth + 1));
    const cols = narrow ? 1 : Math.max(1, Math.min(n.cols || Math.min(kids.length, K.topCols), kids.length, capInner));
    const g = grid(kids, cols, gapOf(n.id));
    const head = textW(tx(n.label), K.groupPx) + 2 * K.groupPad;
    const w = Math.ceil(Math.max(g.w + 2 * K.groupPad, head));
    return { n, kind: "group", depth, kids, g, w, h: K.groupHead + g.h + K.groupPad, innerX: Math.floor((w - g.w) / 2) };
  }
  function grid(kids, cols, gap) {
    const rows = [];
    for (let i = 0; i < kids.length; i += cols) rows.push(kids.slice(i, i + cols));
    const colW = Array.from({ length: cols }, (_, c) => Math.max(0, ...rows.map(r => (r[c] ? r[c].w : 0))));
    const rowH = rows.map(r => Math.max(...r.map(k => k.h)));
    const w = colW.reduce((a, b) => a + b, 0) + gap * (cols - 1);
    const h = rowH.reduce((a, b) => a + b, 0) + Math.max(K.gap, Math.min(gap, 60)) * (rows.length - 1);
    return { rows, colW, rowH, w, h, cols, gap, rowGap: Math.max(K.gap, Math.min(gap, 60)) };
  }
  function place(m, x, y, parent) {
    const id = idOf(m.n);
    boxes[id] = { id, kind: m.kind, depth: m.depth, parent, x, y, w: m.w, h: m.h,
                  lines: m.subLines || [], subLines: m.subLines || [] };
    order.push(id);
    if (m.kind === "part") return;
    let cy = y + K.groupHead;
    m.g.rows.forEach((row, r) => {
      let cx = x + m.innerX;
      row.forEach((k, c) => {
        place(k, cx + Math.floor((m.g.colW[c] - k.w) / 2), cy + Math.floor((m.g.rowH[r] - k.h) / 2), id);
        cx += m.g.colW[c] + m.g.gap;
      });
      cy += m.g.rowH[r] + m.g.rowGap;
    });
  }
  const top = sys.items.map(n => measure(n, 0));
  const cols = narrow ? 1 : Math.max(1, Math.min(sys.cols || Math.min(top.length, K.topCols), top.length, capTop));
  const g = grid(top, cols, gapOf(null));
  let cy = K.outer;
  g.rows.forEach((row, r) => {
    let cx = K.outer;
    row.forEach((k, c) => { place(k, cx + Math.floor((g.colW[c] - k.w) / 2), cy + Math.floor((g.rowH[r] - k.h) / 2), null); cx += g.colW[c] + g.gap; });
    cy += g.rowH[r] + g.rowGap;
  });
  return { boxes, order, W: g.w + 2 * K.outer, H: g.h + 2 * K.outer, narrow };
}

/* ---- routing: straight, elbow or L, the one that crosses fewest other parts ---- */
const inside = (L, id, anc) => { for (let p = L.boxes[id]; p; p = p.parent && L.boxes[p.parent]) if (p.id === anc) return true; return false; };

// Liang-Barsky: does the segment pass through the open interior of the rectangle?
function segHits(a, b, r) {
  const x0 = r.x + 1, y0 = r.y + 1, x1 = r.x + r.w - 1, y1 = r.y + r.h - 1;
  let t0 = 0, t1 = 1;
  const dx = b[0] - a[0], dy = b[1] - a[1];
  for (const [p, q] of [[-dx, a[0] - x0], [dx, x1 - a[0]], [-dy, a[1] - y0], [dy, y1 - a[1]]]) {
    if (p === 0) { if (q < 0) return false; continue; }
    const t = q / p;
    if (p < 0) { if (t > t1) return false; if (t > t0) t0 = t; } else { if (t < t0) return false; if (t < t1) t1 = t; }
  }
  return t0 < t1;
}
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const cx = b => b.x + b.w / 2, cy = b => b.y + b.h / 2;
function borderPoint(b, tx, ty) { // where the line from b's centre toward (tx, ty) leaves b
  const dx = tx - cx(b), dy = ty - cy(b);
  if (dx === 0 && dy === 0) return [cx(b), b.y];
  const s = Math.min(dx ? (b.w / 2) / Math.abs(dx) : Infinity, dy ? (b.h / 2) / Math.abs(dy) : Infinity);
  return [cx(b) + dx * s, cy(b) + dy * s];
}
const dedupe = pts => pts.filter((p, i) => i === 0 || Math.abs(p[0] - pts[i - 1][0]) > 0.01 || Math.abs(p[1] - pts[i - 1][1]) > 0.01);
function lengthOf(pts) { let l = 0; for (let i = 1; i < pts.length; i++) l += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); return l; }

// the nearest point of b's border to p, so a sideways shift never leaves a port off its box
function snap(b, p) {
  const x = clamp(p[0], b.x, b.x + b.w), y = clamp(p[1], b.y, b.y + b.h);
  if (x <= b.x || x >= b.x + b.w || y <= b.y || y >= b.y + b.h) return [x, y];
  const d = [x - b.x, b.x + b.w - x, y - b.y, b.y + b.h - y], m = Math.min(...d);
  return m === d[0] ? [b.x, y] : m === d[1] ? [b.x + b.w, y] : m === d[2] ? [x, b.y] : [x, b.y + b.h];
}
function candidates(A, B, off, others) {
  const out = [];
  const ay = clamp(cy(A) + off, A.y + K.portInset, A.y + A.h - K.portInset), by = clamp(cy(B) + off, B.y + K.portInset, B.y + B.h - K.portInset);
  const ax = clamp(cx(A) + off, A.x + K.portInset, A.x + A.w - K.portInset), bx = clamp(cx(B) + off, B.x + K.portInset, B.x + B.w - K.portInset);
  // straight, centre to centre, shifted sideways by off
  const s = borderPoint(A, cx(B), cy(B)), e = borderPoint(B, cx(A), cy(A));
  const nx = -(e[1] - s[1]), ny = e[0] - s[0], nl = Math.hypot(nx, ny) || 1;
  out.push([snap(A, [s[0] + nx / nl * off, s[1] + ny / nl * off]), snap(B, [e[0] + nx / nl * off, e[1] + ny / nl * off])]);
  const left = A.x + A.w <= B.x, right = B.x + B.w <= A.x, above = A.y + A.h <= B.y, below = B.y + B.h <= A.y;
  if (left || right) { // horizontal, vertical, horizontal
    const x0 = left ? A.x + A.w : A.x, x1 = left ? B.x : B.x + B.w, lo = Math.min(x0, x1) + 6, hi = Math.max(x0, x1) - 6;
    for (let i = 0; i < K.midTries; i++) {
      const mx = hi <= lo ? (x0 + x1) / 2 : lo + (hi - lo) * (i + 0.5) / K.midTries + off;
      out.push([[x0, ay], [mx, ay], [mx, by], [x1, by]]);
    }
  }
  if (above || below) { // vertical, horizontal, vertical
    const y0 = above ? A.y + A.h : A.y, y1 = above ? B.y : B.y + B.h, lo = Math.min(y0, y1) + 6, hi = Math.max(y0, y1) - 6;
    for (let i = 0; i < K.midTries; i++) {
      const my = hi <= lo ? (y0 + y1) / 2 : lo + (hi - lo) * (i + 0.5) / K.midTries + off;
      out.push([[ax, y0], [ax, my], [bx, my], [bx, y1]]);
    }
  }
  if (!(left || right)) { // same column: go out to the side, past every box between, and back in
    const y0 = Math.min(A.y, B.y), y1 = Math.max(A.y + A.h, B.y + B.h), xa = Math.min(A.x, B.x), xb = Math.max(A.x + A.w, B.x + B.w),
      span = others.filter(p => p.y < y1 && p.y + p.h > y0 && p.x < xb && p.x + p.w > xa); // only the boxes in the way
    for (const side of [1, -1]) {
      const edge = side > 0 ? Math.max(A.x + A.w, B.x + B.w, ...span.map(p => p.x + p.w)) + K.detour + off
                            : Math.min(A.x, B.x, ...span.map(p => p.x)) - K.detour + off;
      out.push([[side > 0 ? A.x + A.w : A.x, ay], [edge, ay], [edge, by], [side > 0 ? B.x + B.w : B.x, by]]);
    }
  }
  if (!(above || below)) { // same row: out over or under
    const x0 = Math.min(A.x, B.x), x1 = Math.max(A.x + A.w, B.x + B.w), ya = Math.min(A.y, B.y), yb = Math.max(A.y + A.h, B.y + B.h),
      span = others.filter(p => p.x < x1 && p.x + p.w > x0 && p.y < yb && p.y + p.h > ya);
    for (const side of [1, -1]) {
      const edge = side > 0 ? Math.max(A.y + A.h, B.y + B.h, ...span.map(p => p.y + p.h)) + K.detour + off
                            : Math.min(A.y, B.y, ...span.map(p => p.y)) - K.detour + off;
      out.push([[ax, side > 0 ? A.y + A.h : A.y], [ax, edge], [bx, edge], [bx, side > 0 ? B.y + B.h : B.y]]);
    }
  }
  if ((left || right) && (above || below)) { // one bend
    out.push([[left ? A.x + A.w : A.x, ay], [bx, ay], [bx, above ? B.y : B.y + B.h]]);
    out.push([[ax, above ? A.y + A.h : A.y], [ax, by], [left ? B.x : B.x + B.w, by]]);
  }
  return out;
}

function route(sys, L, opts) {
  const tx = (opts && opts.tx) || String;
  const parts = Object.values(L.boxes).filter(b => b.kind === "part");
  const pair = {}, seen = {};
  for (const l of sys.links) { const k = [l.from, l.to].sort().join("|"); pair[k] = (pair[k] || 0) + 1; }
  const routes = [];
  for (const l of sys.links) {
    const A = L.boxes[l.from], B = L.boxes[l.to];
    if (!A || !B) continue;
    const k = [l.from, l.to].sort().join("|"), nth = seen[k] || 0;
    seen[k] = nth + 1;
    const off = (nth - (pair[k] - 1) / 2) * K.offStep;
    const obstacles = parts.filter(p => p.id !== l.from && p.id !== l.to && !inside(L, p.id, l.from) && !inside(L, p.id, l.to));
    let best = null;
    for (const pts0 of candidates(A, B, off, obstacles)) {
      const pts = dedupe(pts0);
      let through = 0;
      for (const p of obstacles) for (let i = 1; i < pts.length; i++) if (segHits(pts[i - 1], pts[i], p)) { through++; break; }
      const score = through * K.through + (pts.length - 2) * K.bend + lengthOf(pts);
      if (!best || score < best.score) best = { pts, through, score };
    }
    routes.push({ link: l, from: l.from, to: l.to, pts: best.pts, through: best.through, d: roundPath(best.pts, K.corner) });
  }
  const tags = placeTags(routes, parts, tx);
  return { routes, tags: tags.tags, crowded: tags.crowded, bounds: boundsOf(L, routes, tags.tags) };
}
// Everything drawn: the boxes, every route and every label. A label beside a line on the outside of the
// picture may hang past the boxes' canvas, so the viewBox is this and not the canvas.
function boundsOf(L, routes, tags) {
  let x0 = 0, y0 = 0, x1 = L.W, y1 = L.H;
  for (const r of routes) for (const p of r.pts) { x0 = Math.min(x0, p[0]); y0 = Math.min(y0, p[1]); x1 = Math.max(x1, p[0]); y1 = Math.max(y1, p[1]); }
  for (const t of tags) { x0 = Math.min(x0, t.box.x); y0 = Math.min(y0, t.box.y); x1 = Math.max(x1, t.box.x + t.box.w); y1 = Math.max(y1, t.box.y + t.box.h); }
  x0 = Math.floor(x0 - (x0 < 0 ? 4 : 0)); y0 = Math.floor(y0 - (y0 < 0 ? 4 : 0)); x1 = Math.ceil(x1 + (x1 > L.W ? 4 : 0)); y1 = Math.ceil(y1 + (y1 > L.H ? 4 : 0));
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
}
// How untidy a drawing is: links through parts they do not join, then the total length of every link and its bends.
const cost = c => c.R.routes.reduce((a, r) => a + r.through * K.through + (r.pts.length - 2) * K.bend + lengthOf(r.pts), 0);
// Draw the subject in the way that fits `fitW` (the widest picture whose text stays readable at the page's width)
// with the least tangle of links; if none fits, the narrowest one.
function arrange(sys, opts) {
  const tx = (opts && opts.tx) || String, fitW = opts && opts.fitW, narrow = !!(opts && opts.narrow);
  const draw = (a, b) => { const L = layoutOnce(sys, opts, a, b); return { L, R: route(sys, L, { tx }) }; };
  let best = draw(Infinity, Infinity);
  if (!fitW || narrow || best.R.bounds.w <= fitW) return best;
  let ok = null, narrowest = best;
  for (const a of [Infinity, 3, 2, 1]) for (const b of [Infinity, 2, 1]) {
    const c = draw(a, b), w = c.R.bounds.w;
    if (w < narrowest.R.bounds.w) narrowest = c;
    if (w <= fitW && (!ok || cost(c) < cost(ok))) ok = c;
  }
  return ok || narrowest;
}
function roundPath(pts, r) {
  const f = n => Math.round(n * 10) / 10;
  if (pts.length < 3) return "M" + pts.map(p => f(p[0]) + " " + f(p[1])).join(" L");
  let d = "M" + f(pts[0][0]) + " " + f(pts[0][1]);
  for (let i = 1; i < pts.length - 1; i++) {
    const a = pts[i - 1], b = pts[i], c = pts[i + 1];
    const l1 = Math.hypot(b[0] - a[0], b[1] - a[1]), l2 = Math.hypot(c[0] - b[0], c[1] - b[1]), rr = Math.min(r, l1 / 2, l2 / 2);
    const p1 = [b[0] - (b[0] - a[0]) / l1 * rr, b[1] - (b[1] - a[1]) / l1 * rr], p2 = [b[0] + (c[0] - b[0]) / l2 * rr, b[1] + (c[1] - b[1]) / l2 * rr];
    d += ` L${f(p1[0])} ${f(p1[1])} Q${f(b[0])} ${f(b[1])} ${f(p2[0])} ${f(p2[1])}`;
  }
  const z = pts[pts.length - 1];
  return d + ` L${f(z[0])} ${f(z[1])}`;
}
function pointAt(pts, t) {
  const total = lengthOf(pts); let want = total * t;
  for (let i = 1; i < pts.length; i++) {
    const seg = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
    if (want <= seg || i === pts.length - 1) { const u = seg ? want / seg : 0; return [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * u, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * u]; }
    want -= seg;
  }
  return pts[0];
}
function tagWidth(l, tx) { return Math.ceil((l.label ? textW(tx(l.label), K.tagPx) + 2 * K.tagPad : 0) + (l.n ? 2 * K.badgeR + (l.label ? 3 : 0) : 0)); }
const hit = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

// A tag is the journey badge and/or the label of a link; it sits on the path where it touches no part and no other tag.
function placeTags(routes, parts, tx) {
  const placed = [], tags = []; let crowded = 0;
  for (const r of routes) {
    const l = r.link, text = l.label ? tx(l.label) : "";
    if (!text && !l.n) continue;
    const w = tagWidth(l, tx), h = K.tagH;
    let spot = null;
    for (const t of K.tagTries) {
      const [px, py] = pointAt(r.pts, t), box = { x: px - w / 2, y: py - h / 2, w, h };
      if (!parts.some(p => hit(box, p)) && !placed.some(o => hit(box, o))) { spot = box; break; }
    }
    // second choice: beside the line, nudged across it by up to three tag heights
    for (let k = 1; !spot && k <= 3; k++) for (const t of K.tagTries) for (const sign of [-1, 1]) {
      if (spot) break;
      const [px, py] = pointAt(r.pts, t), [ax, ay] = pointAt(r.pts, Math.max(0, t - 0.02)), [bx, by] = pointAt(r.pts, Math.min(1, t + 0.02));
      const horizontal = Math.abs(bx - ax) >= Math.abs(by - ay), d = sign * k * (h + 2);
      const box = horizontal ? { x: px - w / 2, y: py - h / 2 + d, w, h } : { x: px - w / 2 + sign * k * (w / 2 + 6), y: py - h / 2, w, h };
      if (!parts.some(q => hit(box, q)) && !placed.some(o => hit(box, o))) spot = box;
    }
    if (!spot) { const [px, py] = pointAt(r.pts, 0.5); spot = { x: px - w / 2, y: py - h / 2, w, h }; crowded++; }
    placed.push(spot);
    tags.push({ link: l, text, box: spot, from: r.from, to: r.to });
  }
  return { tags, crowded };
}

/* ---- numbers the bench and the tests read ---- */
function stats(L, R) {
  const bs = Object.values(L.boxes);
  let overlaps = 0, outside = 0;
  for (let i = 0; i < bs.length; i++) for (let j = i + 1; j < bs.length; j++) {
    const a = bs[i], b = bs[j];
    const related = inside(L, a.id, b.id) || inside(L, b.id, a.id);
    if (!related && hit(a, b)) overlaps++;
  }
  for (const b of bs) if (b.parent) { const p = L.boxes[b.parent]; if (b.x < p.x || b.y < p.y || b.x + b.w > p.x + p.w || b.y + b.h > p.y + p.h) outside++; }
  let tagOverlaps = 0;
  const tg = R.tags.map(t => t.box);
  for (let i = 0; i < tg.length; i++) {
    for (let j = i + 1; j < tg.length; j++) if (hit(tg[i], tg[j])) tagOverlaps++;
    for (const b of bs) if (b.kind === "part" && hit(tg[i], b)) tagOverlaps++;
  }
  return { tagOverlaps, parts: bs.filter(b => b.kind === "part").length, groups: bs.filter(b => b.kind === "group").length,
           overlaps, outside, through: R.routes.reduce((a, r) => a + r.through, 0), crowded: R.crowded,
           links: R.routes.length, W: R.bounds.w, H: R.bounds.h, minFont: Math.min(K.subPx, K.tagPx, K.labelPx, K.groupPx) };
}

/* ---- markup ---- */
const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const esc = s => String(s).replace(/[&<>"']/g, c => ESC[c]);
const num = n => Math.round(n * 10) / 10;

function svg(sys, L, R, opts) {
  const tx = (opts && opts.tx) || String, id = (opts && opts.id) || "sm", title = (opts && opts.title) || "";
  const kinds = {};
  (function walk(items) { for (const n of items) { kinds[n.id] = n; if (isGroup(n)) walk(n.items); } })(sys.items);
  const out = [];
  const B = R.bounds || { x: 0, y: 0, w: L.W, h: L.H };
  out.push(`<svg class="sysmap${L.narrow ? " narrow" : ""}" xmlns="http://www.w3.org/2000/svg" viewBox="${B.x} ${B.y} ${B.w} ${B.h}" role="img" aria-labelledby="${id}-t" style="max-width:${B.w}px">`);
  out.push(`<title id="${id}-t">${esc(title)}</title><defs>`);
  for (const s of STYLES) out.push(`<marker id="${id}-ah-${s}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" class="sys-ah ah-${s}"/></marker>`);
  out.push("</defs>");
  for (const gid of L.order) { // outermost first, so a nested group paints over its parent
    const b = L.boxes[gid]; if (b.kind !== "group") continue;
    const n = kinds[gid], label = tx(n.label), sub = n.sub ? tx(n.sub) : "";
    const room = b.w - 2 * K.groupPad - textW(label, K.groupPx) - 10;
    out.push(`<g class="sys-group d${Math.min(b.depth, 3)}" data-group="${esc(gid)}"><title>${esc(label + (sub ? " — " + sub : ""))}</title>` +
      `<rect x="${num(b.x)}" y="${num(b.y)}" width="${b.w}" height="${b.h}" rx="12"/>` +
      `<text class="sys-gl" x="${num(b.x + K.groupPad)}" y="${num(b.y + 18)}">${esc(label)}</text>` +
      (sub && room > 40 ? `<text class="sys-gs" x="${num(b.x + b.w - K.groupPad)}" y="${num(b.y + 18)}" text-anchor="end">${esc(clip(sub, room, K.subPx))}</text>` : "") + "</g>");
  }
  out.push('<g class="sys-links">');
  for (const r of R.routes) {
    const l = r.link, style = STYLES.includes(l.style) ? l.style : "call";
    out.push(`<path class="sys-link st-${style}${l.tag === "inferred" || !(l.ev || []).length ? " inferred" : ""}" data-link="${esc(r.from)}|${esc(r.to)}"` +
      `${l.n ? ` data-n="${l.n}"` : ""} d="${r.d}" marker-end="url(#${id}-ah-${style})"/>`);
  }
  out.push("</g>");
  for (const pid of L.order) {
    const b = L.boxes[pid]; if (b.kind !== "part") continue;
    const n = kinds[pid], label = tx(n.label), sub = n.sub ? tx(n.sub) : "", kind = ["actor", "data", "external"].includes(n.kind) ? n.kind : "plain";
    out.push(`<g class="sys-part k-${kind}" data-part="${esc(pid)}"${b.parent ? ` data-parent="${esc(b.parent)}"` : ""}><title>${esc(label + (sub ? " — " + sub : ""))}</title>` +
      `<rect class="sys-box" x="${num(b.x)}" y="${num(b.y)}" width="${b.w}" height="${b.h}" rx="8"/>` +
      `<text class="sys-lbl-p" x="${num(b.x + b.w / 2)}" y="${num(b.y + 20)}" text-anchor="middle">${esc(clip(label, b.w - 2 * K.partPad, K.labelPx))}</text>` +
      b.subLines.map((ln, i) => `<text class="sys-sub" x="${num(b.x + b.w / 2)}" y="${num(b.y + 34 + K.lineH * i)}" text-anchor="middle">${esc(ln)}</text>`).join("") + "</g>");
  }
  out.push('<g class="sys-tags">');
  for (const t of R.tags) {
    const b = t.box, l = t.link, from = tx(kinds[t.from].label), to = tx(kinds[t.to].label);
    const tip = `${l.n ? l.n + ". " : ""}${t.text ? t.text + " " : ""}(${from} → ${to})`;
    const body = `<g class="sys-lbl" transform="translate(${num(b.x)},${num(b.y)})"${l.n ? ` data-n="${l.n}"` : ""}><title>${esc(tip)}</title>` +
      `<rect width="${b.w}" height="${b.h}" rx="${b.h / 2}"/>` +
      (l.n ? `<circle cx="${K.badgeR + 1}" cy="${b.h / 2}" r="${K.badgeR - 1}"/><text class="sys-n" x="${K.badgeR + 1}" y="${b.h / 2 + 3.6}" text-anchor="middle">${l.n}</text>` : "") +
      (t.text ? `<text class="sys-lbl-t" x="${l.n ? 2 * K.badgeR + 3 + K.tagPad : K.tagPad}" y="${b.h / 2 + 3.6}">${esc(t.text)}</text>` : "") + "</g>";
    out.push(l.n ? `<a class="sys-jump" href="#sys-j${l.n}" aria-label="${esc(tip)}">${body}</a>` : body);
  }
  out.push("</g></svg>");
  return out.join("");
}

return { layout, route, arrange, svg, stats, textW, wrap, STYLES, K, candidates };
})();
if (typeof module === "object" && module.exports) module.exports = SystemMap;

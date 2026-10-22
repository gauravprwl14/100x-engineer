/* 100x flow player: the reducer and both renderers (light step cards, heavy animated player)
   for a page written by `100x flow build`. Vanilla JS, no dependencies, no network. The
   scenario arrives as JSON in #flow-data; rendering is a function of the reduced state, so
   Back, deep links (#<scenario>.<step>) and the before/after toggle replay nothing by hand. */
(function () {
"use strict";

/* ============ reducer: mirrors scripts/flow.py reduce_scenario (tests/flow/states.json) ============ */

const TIME_UNITS_MS = { ms: 1, s: 1000, min: 60000, h: 3600000 };
const DEFAULT_READ_VAR = "read";
const ONE_PLACEHOLDER = /^\{\{\s*([^}]*?)\s*\}\}$/;
// flow.py AT_RX: a path may hold '@' (packages/@scope/x.ts); only a trailing @<7-40 hex> is the revision.
const AT_RX = /^([^:]+):([1-9][0-9]*)(?:@([0-9a-f]{7,40}))?$/;
function parseAt(at) {
  const m = typeof at === "string" ? AT_RX.exec(at) : null;
  return m ? { path: m[1], line: m[2], rev: m[3] || null } : null;
}

class ReduceError extends Error {}

const own = (o, k) => o != null && Object.prototype.hasOwnProperty.call(o, k);
const get = (o, k) => (own(o, k) ? o[k] : null);
const clone = x => JSON.parse(JSON.stringify(x));
const same = (a, b) => JSON.stringify(a === undefined ? null : a) === JSON.stringify(b === undefined ? null : b);
// Keys come from the scenario; defineProperty keeps a key such as "__proto__" an ordinary key.
function put(o, k, v) { Object.defineProperty(o, k, { value: v, enumerable: true, writable: true, configurable: true }); }

function scenarioIndex(doc) { const m = {}; for (const s of doc.scenarios) put(m, s.id, s); return m; }

function effectiveSteps(sid, scenarios, seen) {
  seen = seen || [];
  if (seen.includes(sid)) throw new ReduceError("branch cycle: " + seen.concat([sid]).join(" -> "));
  const s = scenarios[sid];
  const mine = s.steps.map((step, index) => ({ step, origin: sid, index }));
  if (!s.branch) return mine;
  const parent = effectiveSteps(s.branch.from, scenarios, seen.concat([sid]));
  if (s.branch.at > parent.length) {
    throw new ReduceError(`scenario ${sid}: branch.at ${s.branch.at} is past the ${parent.length} step(s) of ${s.branch.from}`);
  }
  return parent.slice(0, s.branch.at).concat(mine);
}

function initialState(doc) {
  const init = doc.initial || {}, caches0 = init.caches || {}, stores0 = init.stores || {};
  const st = { clock_ms: 0, queues: {}, workers: {}, caches: {}, stores: {}, vars: {}, counters: {}, failed: [] };
  for (const n of doc.nodes) {
    if (n.role === "queue") put(st.queues, n.id, []);
    else if (n.role === "worker") put(st.workers, n.id, new Array(n.slots || 1).fill(null));
    else if (n.role === "cache") {
      const c = {}, kv = get(caches0, n.id) || {};
      for (const k of Object.keys(kv)) put(c, k, { v: kv[k], stale: false, src: null });
      put(st.caches, n.id, c);
    } else if (n.role === "store") {
      const c = {}, kv = get(stores0, n.id) || {};
      for (const k of Object.keys(kv)) put(c, k, kv[k]);
      put(st.stores, n.id, c);
    }
  }
  return st;
}

function msOf(placeholder, numbers) {
  const n = numbers[ONE_PLACEHOLDER.exec(placeholder)[1]];
  return Math.round(n.v * TIME_UNITS_MS[n.unit]);
}

function boundVar(state, ref, action) {
  const v = get(state.vars, ref.slice(1));
  if (v === null) throw new ReduceError(`${action}: variable '${ref}' is unbound`);
  return v;
}

const isRef = v => typeof v === "string" && v.startsWith("$");

function applyAction(state, out, action, numbers) {
  const name = action[0], args = action.slice(1);
  const touch = id => { if (!out.active.includes(id)) out.active.push(id); };
  if (name === "send" || name === "reply") {
    touch(args[0]); touch(args[1]);
    out.messages.push({ kind: name, from: args[0], to: args[1], label: args.length > 2 ? args[2] : null });
    return;
  }
  if (name !== "wait" && name !== "counter" && name !== "note") touch(args[0]);
  switch (name) {
    case "enqueue": state.queues[args[0]].push(args[1]); break;
    case "pickup": {
      touch(args[1]);
      const q = state.queues[args[0]], slots = state.workers[args[1]], free = slots.indexOf(null);
      if (!q.length) throw new ReduceError(`pickup: queue '${args[0]}' is empty`);
      if (free < 0) throw new ReduceError(`pickup: worker '${args[1]}' has no free slot`);
      slots[free] = q.shift();
      break;
    }
    case "free": {
      const slots = state.workers[args[0]];
      const target = args.length > 1 ? args[1] : (slots.find(j => j !== null) ?? null);
      const at = target === null ? -1 : slots.indexOf(target);
      if (at < 0) throw new ReduceError(`free: worker '${args[0]}' holds no job` + (args.length > 1 ? ` '${args[1]}'` : ""));
      slots[at] = null;
      break;
    }
    case "cache.get": out.hit = own(state.caches[args[0]], args[1]) ? "hit" : "miss"; break;
    case "cache.set": {
      const cache = args[0], key = args[1];
      let value = args[2], src = null, stale = false;
      if (isRef(value)) { const v = boundVar(state, value, "cache.set"); value = v.v; src = v.src; }
      if (src !== null) {
        const current = get(state.stores[src[0]], src[1]);
        if (!same(current, value)) {
          stale = true;
          out.hazards.push({ kind: "stale-writeback", cache, key, store: src[0], store_key: src[1] });
        }
      }
      put(state.caches[cache], key, { v: value, stale, src });
      break;
    }
    case "cache.set-if-fresh": {
      const cache = args[0], key = args[1], v = boundVar(state, args[2], "cache.set-if-fresh");
      const current = get(state.stores[v.src[0]], v.src[1]);
      if (same(current, v.v)) put(state.caches[cache], key, { v: v.v, stale: false, src: v.src });
      else out.skipped.push({ cache, key, store: v.src[0], store_key: v.src[1], read: v.v, current });
      break;
    }
    case "cache.del": case "cache.expire": delete state.caches[args[0]][args[1]]; break;
    case "mark-stale": {
      const e = get(state.caches[args[0]], args[1]);
      if (e === null) throw new ReduceError(`mark-stale: cache '${args[0]}' has no key '${args[1]}'`);
      e.stale = true;
      break;
    }
    case "db.read":
      put(state.vars, args.length > 2 ? args[2] : DEFAULT_READ_VAR,
          { v: get(state.stores[args[0]], args[1]), src: [args[0], args[1]] });
      break;
    case "db.write": {
      const store = args[0], skey = args[1];
      let value = args[2];
      if (isRef(value)) value = boundVar(state, value, "db.write").v;
      put(state.stores[store], skey, value);
      for (const entries of Object.values(state.caches)) {
        for (const e of Object.values(entries)) {
          if (e.src && e.src[0] === store && e.src[1] === skey && !same(e.v, value)) e.stale = true;
        }
      }
      break;
    }
    case "wait": state.clock_ms += msOf(args[0], numbers); break;
    case "counter": put(state.counters, args[0], (get(state.counters, args[0]) || 0) + args[1]); break;
    case "fail":
      if (!state.failed.includes(args[0])) state.failed.push(args[0]);
      out.failures.push({ node: args[0], label: args.length > 1 ? args[1] : null });
      break;
    case "note": out.notes.push(args[0]); break;
    default: throw new ReduceError(`unknown action '${name}'`);
  }
}

const newOut = () => ({ active: [], messages: [], hit: null, failures: [], notes: [], hazards: [], skipped: [] });

function snapshot(i, entry, sid, state, out) {
  const s = clone(state), o = clone(out);
  return {
    step: i, origin: entry.origin, origin_step: entry.index, inherited: entry.origin !== sid,
    clock_ms: s.clock_ms, active: o.active, messages: o.messages, hit: o.hit,
    queues: s.queues, workers: s.workers, caches: s.caches, stores: s.stores, vars: s.vars,
    counters: s.counters, failed: s.failed, failures: o.failures, notes: o.notes,
    hazards: o.hazards, skipped: o.skipped,
  };
}

function reduceScenario(doc, sid) {
  const scenarios = scenarioIndex(doc), numbers = doc.numbers || {};
  const state = initialState(doc);
  return effectiveSteps(sid, scenarios).map((entry, i) => {
    const out = newOut();
    for (const a of entry.step.do) {
      try { applyAction(state, out, a, numbers); } catch (err) {
        if (err instanceof ReduceError) throw new ReduceError(`scenario ${entry.origin} step ${entry.index}: ${err.message}`);
        throw err;
      }
    }
    return snapshot(i, entry, sid, state, out);
  });
}

const API = { reduceScenario, effectiveSteps, initialState, applyAction, newOut, ReduceError, parseAt };
if (typeof module === "object" && module && module.exports) module.exports = API;
if (typeof document === "undefined") return;

/* ============ page context, text and numbers ============ */

const ROLES = ["client", "edge", "service", "queue", "worker", "cache", "store", "external"];
const ACTOR_ROLES = ["service", "edge", "worker"];
const NO_SPACE_UNITS = ["%", "×", "x"];
const NARROW_PX = 640;
const VIS = 3;
const HOLD_MS = 1400;
const TAG_FADE_FROM = 0.8; // a moving tag fades over the last fifth of its flight, as it lands
const WIDE_MAP_W = 1080;   // a map wider than this takes the full width; the step list moves below
const COMPARE_RUN_MS = 12000;
const PH = /\{\{\s*([^}]*?)\s*\}\}/g;
const STORE_KEYS = { lang: "flow-player-lang", theme: "flow-player-theme" };

const UI = {
  en: {
    play: "Play", pause: "Pause", back: "Back", next: "Next", replay: "Replay", speed: "Speed",
    scenarios: "Scenarios", compareTab: "On one clock", steps: "Steps",
    fixGroup: "Before or after the fix", before: "Before: the issue", after: a => `After: ${a.title}`,
    howto: "How to read this page", map: "Where it lives", mapLegend: "Map legend",
    stepOf: a => `${a.i} / ${a.n}`, inherited: a => `Same as “${a.title}” up to here`,
    afterStep: "After this step", noChange: "no change", moves: "What moves, in order",
    predict: "Predict before you look", reveal: "Reveal", answer: "Answer",
    hazard: a => `Hazard: stale write-back. ${a.cache}[${a.key}] now holds a value read from ${a.store}[${a.skey}] before a later write replaced it. Every read hits it until the entry expires.`,
    skipped: a => `Fill skipped: ${a.store}[${a.skey}] changed from ${a.read} to ${a.current} since the read, so ${a.cache}[${a.key}] is not written.`,
    failed: a => `${a.node} failed` + (a.label ? `: ${a.label}` : ""),
    clock: "Clock", waiting: "Jobs waiting", busy: "Slots busy", holds: "Held in memory",
    empty: "empty", busyOf: a => `${a.b} / ${a.n} busy`, running: "running", more: a => `+${a.n}`,
    hit: "HIT", miss: "MISS", stale: "stale", skippedTag: "skipped", failedBadge: "FAILED", context: "context",
    issues: "What can go wrong", fixedBy: "Fixed by", open: "Open: no fix shown yet", showFix: "Show the fix",
    showScenario: "Show this scenario", issueCol: "Issue", severityCol: "Severity", fixCol: "Fix",
    decision: "Decision", solves: "solves it", notSolves: "does not solve it", chosen: "Chosen",
    pros: "Pros", cons: "Cons", deciding: "Deciding factor", revisit: "Revisit when", source: "Source",
    numbers: "Numbers", nameCol: "Name", valueCol: "Value", tagCol: "Tag", backedCol: "Backed by",
    evidence: a => `Evidence (${a.n})`, idCol: "Id", whereCol: "Where", checkCol: "What was checked",
    anchorCheck: a => `“${a.anchor}” within two lines`, absenceCheck: a => `git grep /${a.pattern}/ finds ${a.hits}`,
    compareTitle: "The scenarios on one clock",
    compareLede: "Each bar is a step that takes time (a wait); its length is the time it adds. Dashed bars rest on estimated numbers or inferred steps. Counters below follow the playhead.",
    clockSteps: "Steps", timeAxisSteps: "No step waits, so the axis counts steps.",
    totalTime: "Total time", hazards: "Hazards", failures: "Failures", doneAt: a => `done at ${a.t}`,
    stepUnit: a => `step ${a.n}`,
    theme: a => `Theme: ${a.mode}`, themeAuto: "auto", themeLight: "light", themeDark: "dark",
    lang: "Language",
    kind: { happy: "happy path", edge: "edge case", failure: "failure", race: "race", load: "load", issue: "issue", fix: "fix" },
    severity: { low: "low", medium: "medium", high: "high", critical: "critical" },
    role: { client: "Clients", edge: "Edge", service: "Services", queue: "Queues", worker: "Workers", cache: "Caches", store: "Stores", external: "Outside services" },
    tag: { verified: "verified", "verified-absent": "verified absent", measured: "measured", estimated: "estimated", inferred: "inferred" },
    tagHelp: {
      verified: "Read in the code at the pinned commit; the checker found the cited token on that line.",
      "verified-absent": "Searched for and not there; the stated git grep hit count is the real one.",
      measured: "A number from a run, a log or a dashboard, named next to it.",
      estimated: "A number worked out from other numbers; its basis is stated.",
      inferred: "Deduced, not read. Drawn dashed.",
    },
    tagCount: {
      verified: a => `${a.n} cited line(s)`, "verified-absent": a => `${a.n} counted absence(s)`,
      measured: a => `${a.n} number(s)`, estimated: a => `${a.n} number(s)`, inferred: a => `${a.n} step(s)`,
    },
    legend: { req: "Request", res: "Response", job: "Job", slot: "Slot running a job", stale: "Stale cache entry", hazard: "Hazard", failed: "Failed", inferred: "Inferred step", context: "Outside the change", more: "More jobs, not drawn" },
    sameSteps: a => `Steps 1–${a.n} are the same as “${a.title}”.`, showSame: "Show those steps",
    footer: a => `Built by 100x flow build from scenario.json, tier ${a.tier}. explain.md beside this page has the same walkthrough as tables.`,
    fatal: "The walkthrough could not be drawn.", scenarioError: "This scenario cannot be replayed.",
    noScenario: "This page has no scenario to show.",
    arrow: { get: a => `get ${a.key} → ${a.r}`, set: a => `set ${a.key} = ${a.v}`, fresh: a => `set if fresh ${a.key}`, del: a => `del ${a.key}`, expire: a => `${a.key} expires`, read: a => `read ${a.key} → ${a.v}`, write: a => `write ${a.key} = ${a.v}` },
    change: {
      hit: a => `cache ${a.r}`, removed: a => `${a.c}[${a.key}] removed`, set: a => `${a.c}[${a.key}] = ${a.v}`, staleSuffix: " (stale)",
      queue: a => `${a.q}: ${a.n} waiting`, worker: a => `${a.w}: ${a.b}/${a.n} busy`, counter: a => `${a.name} = ${a.v}`,
      clock: a => `clock ${a.t}`, holds: a => `holds ${a.name} = ${a.v}`,
    },
    clockFmt: { ms: a => `${a.n} ms`, s: a => `${a.n} s`, ms2: a => `${a.m} min` + (a.s ? ` ${a.s} s` : ""), h: a => `${a.h} h` + (a.m ? ` ${a.m} min` : "") },
  },
  ja: {
    play: "再生", pause: "一時停止", back: "戻る", next: "次へ", replay: "最初から", speed: "速度",
    scenarios: "シナリオ", compareTab: "同じ時計で比較", steps: "ステップ",
    fixGroup: "修正前と修正後", before: "修正前: 問題", after: a => `修正後: ${a.title}`,
    howto: "このページの読み方", map: "どこにあるか", mapLegend: "図の凡例",
    stepOf: a => `${a.i} / ${a.n}`, inherited: a => `ここまでは「${a.title}」と同じ`,
    afterStep: "このステップの後", noChange: "変化なし", moves: "動くもの（順番どおり）",
    predict: "見る前に予想する", reveal: "答えを見る", answer: "答え",
    hazard: a => `ハザード: 古い値の書き戻し。${a.cache}[${a.key}] には、後の書き込みで置き換えられる前に ${a.store}[${a.skey}] から読んだ値が入っている。期限切れまで全ての読み取りがこれに当たる。`,
    skipped: a => `書き込みを省略: 読み取り後に ${a.store}[${a.skey}] が ${a.read} から ${a.current} に変わったので、${a.cache}[${a.key}] には書かない。`,
    failed: a => `${a.node} が失敗` + (a.label ? `: ${a.label}` : ""),
    clock: "時計", waiting: "待機中のジョブ", busy: "稼働中のスロット", holds: "メモリに保持",
    empty: "空", busyOf: a => `${a.b} / ${a.n} 稼働`, running: "実行中", more: a => `+${a.n}`,
    hit: "ヒット", miss: "ミス", stale: "古い", skippedTag: "省略", failedBadge: "失敗", context: "周辺",
    issues: "何が起こりうるか", fixedBy: "修正", open: "未解決: 修正はまだない", showFix: "修正を見る",
    showScenario: "このシナリオを見る", issueCol: "問題", severityCol: "深刻度", fixCol: "修正",
    decision: "判断", solves: "解決する", notSolves: "解決しない", chosen: "採用",
    pros: "利点", cons: "欠点", deciding: "決め手", revisit: "見直す条件", source: "出典",
    numbers: "数値", nameCol: "名前", valueCol: "値", tagCol: "根拠の種類", backedCol: "根拠",
    evidence: a => `根拠 (${a.n})`, idCol: "ID", whereCol: "場所", checkCol: "確認した内容",
    anchorCheck: a => `「${a.anchor}」が前後2行以内にある`, absenceCheck: a => `git grep /${a.pattern}/ の件数 ${a.hits}`,
    compareTitle: "シナリオを同じ時計で比較",
    compareLede: "各バーは時間のかかるステップ（待ち）で、長さはそのステップが足す時間。破線のバーは推定値か推測のステップに基づく。下のカウンターは再生位置に合わせて動く。",
    clockSteps: "ステップ", timeAxisSteps: "待ちのあるステップがないので、横軸はステップ数。",
    totalTime: "合計時間", hazards: "ハザード", failures: "失敗", doneAt: a => `${a.t} に完了`,
    stepUnit: a => `ステップ ${a.n}`,
    theme: a => `テーマ: ${a.mode}`, themeAuto: "自動", themeLight: "ライト", themeDark: "ダーク",
    lang: "言語",
    kind: { happy: "正常系", edge: "境界ケース", failure: "障害", race: "競合", load: "負荷", issue: "問題", fix: "修正" },
    severity: { low: "低", medium: "中", high: "高", critical: "致命的" },
    role: { client: "クライアント", edge: "エッジ", service: "サービス", queue: "キュー", worker: "ワーカー", cache: "キャッシュ", store: "ストア", external: "外部サービス" },
    tag: { verified: "コードで確認", "verified-absent": "不在を確認", measured: "実測", estimated: "推定", inferred: "推測" },
    tagHelp: {
      verified: "固定したコミットのコードで読んだ。チェッカーが該当行にトークンを確認した。",
      "verified-absent": "探して見つからなかった。記載の git grep 件数は実際の件数。",
      measured: "実行・ログ・ダッシュボードから得た数値。出所を併記。",
      estimated: "他の数値から算出した数値。根拠を併記。",
      inferred: "読んだのではなく推測した。破線で表示。",
    },
    tagCount: {
      verified: a => `引用行 ${a.n} 件`, "verified-absent": a => `不在の確認 ${a.n} 件`,
      measured: a => `数値 ${a.n} 件`, estimated: a => `数値 ${a.n} 件`, inferred: a => `ステップ ${a.n} 件`,
    },
    legend: { req: "リクエスト", res: "レスポンス", job: "ジョブ", slot: "ジョブ実行中のスロット", stale: "古いキャッシュ", hazard: "ハザード", failed: "失敗", inferred: "推測のステップ", context: "変更の外", more: "描画していないジョブ" },
    sameSteps: a => `ステップ 1–${a.n} は「${a.title}」と同じ。`, showSame: "そのステップを表示",
    footer: a => `100x flow build が scenario.json から生成（ティア ${a.tier}）。同じ内容の表は隣の explain.md にある。`,
    fatal: "ウォークスルーを描画できなかった。", scenarioError: "このシナリオは再生できない。",
    noScenario: "表示するシナリオがない。",
    arrow: { get: a => `get ${a.key} → ${a.r}`, set: a => `set ${a.key} = ${a.v}`, fresh: a => `変化なしなら set ${a.key}`, del: a => `del ${a.key}`, expire: a => `${a.key} 期限切れ`, read: a => `read ${a.key} → ${a.v}`, write: a => `write ${a.key} = ${a.v}` },
    change: {
      hit: a => `キャッシュ${a.r}`, removed: a => `${a.c}[${a.key}] 削除`, set: a => `${a.c}[${a.key}] = ${a.v}`, staleSuffix: "（古い）",
      queue: a => `${a.q}: ${a.n} 件待機`, worker: a => `${a.w}: ${a.b}/${a.n} 稼働`, counter: a => `${a.name} = ${a.v}`,
      clock: a => `時計 ${a.t}`, holds: a => `${a.name} = ${a.v} を保持`,
    },
    clockFmt: { ms: a => `${a.n} ミリ秒`, s: a => `${a.n} 秒`, ms2: a => `${a.m} 分` + (a.s ? ` ${a.s} 秒` : ""), h: a => `${a.h} 時間` + (a.m ? ` ${a.m} 分` : "") },
  },
};

let P = null; // page context, set once by boot()

function ui(path, args) {
  const pick = dict => path.split(".").reduce((o, k) => (o && own(o, k) ? o[k] : undefined), dict);
  let t = pick(UI[P ? P.lang : "en"]);
  if (t === undefined) t = pick(UI.en);
  if (t === undefined) return path;
  return typeof t === "function" ? t(args || {}) : t;
}
const locale = () => (P && P.lang === "ja" ? "ja-JP" : "en-US");
const fmtInt = n => new Intl.NumberFormat(locale(), { maximumFractionDigits: 0 }).format(n);
function fmtNumber(n) {
  const unit = n.unit || "";
  return new Intl.NumberFormat(locale(), { maximumFractionDigits: 3 }).format(n.v) + (NO_SPACE_UNITS.includes(unit) ? "" : " ") + unit;
}
function fmtClock(ms) {
  ms = Math.round(ms);
  const f = (k, a) => ui("clockFmt." + k, a);
  if (ms < 1000) return f("ms", { n: fmtInt(ms) });
  if (ms < TIME_UNITS_MS.min) return f("s", { n: new Intl.NumberFormat(locale(), { maximumFractionDigits: 1 }).format(ms / 1000) });
  const { s: S, min: MIN, h: H } = TIME_UNITS_MS;
  if (ms < H) return f("ms2", { m: Math.floor(ms / MIN), s: Math.round((ms % MIN) / S) });
  return f("h", { h: Math.floor(ms / H), m: Math.round((ms % H) / MIN) });
}
function raw(text) {
  if (text == null) return "";
  if (typeof text === "string") return text;
  return P.lang === "ja" && text.ja ? text.ja : text.en;
}
const tx = text => raw(text).replace(PH, (m, name) => (own(P.numbers, name) ? fmtNumber(P.numbers[name]) : m));
function valueText(v) { return v === null || v === undefined ? "null" : typeof v === "string" ? v : JSON.stringify(v); }
function backing(n) {
  if (n.tag === "verified" && n.ev) return evidenceLabel(n.ev);
  return raw(n.tag === "measured" ? n.source : n.basis);
}
// Prose with each {{number}} wrapped so its evidence tag shows inline.
function txNode(text) {
  const s = raw(text), frag = document.createDocumentFragment();
  let last = 0;
  s.replace(PH, (m, name, off) => {
    frag.append(s.slice(last, off));
    last = off + m.length;
    const n = get(P.numbers, name);
    frag.append(n ? h("span", { class: "numtag t-" + n.tag, title: ui("tag." + n.tag) + ": " + backing(n) }, fmtNumber(n)) : m);
    return m;
  });
  frag.append(s.slice(last));
  return frag;
}
function hasJa(doc) {
  let found = false;
  const walk = v => {
    if (found || v == null) return;
    if (Array.isArray(v)) v.forEach(walk);
    else if (typeof v === "object") { if (typeof v.ja === "string" && typeof v.en === "string") found = true; else Object.values(v).forEach(walk); }
  };
  walk(doc);
  return found;
}

/* ============ DOM and SVG helpers ============ */

const SVGNS = "http://www.w3.org/2000/svg";
function setAttrs(e, attrs) {
  for (const k in attrs || {}) {
    const v = attrs[k];
    if (v == null || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? "" : String(v));
  }
}
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  setAttrs(e, attrs);
  for (const k of kids.flat(Infinity)) if (k != null && k !== false) e.append(k instanceof Node ? k : String(k));
  return e;
}
function sv(tag, attrs, parent, text) {
  const e = document.createElementNS(SVGNS, tag);
  setAttrs(e, attrs);
  if (text != null) e.textContent = text;
  if (parent) parent.appendChild(e);
  return e;
}
const $ = id => document.getElementById(id);
const pad2 = n => String(n).padStart(2, "0");
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
function truncate(s, n) { s = String(s); return s.length > n ? s.slice(0, n - 1) + "…" : s; }
function textW(str, px) { let w = 0; for (const ch of String(str)) w += ch.codePointAt(0) > 0x2e80 ? px : px * 0.58; return w; }
const MONO_W = 6.7; // px per character of the 11px mono face used in boxes

/* ============ evidence ============ */

function evidenceAt(eid) {
  const e = get(P.doc.evidence || {}, eid);
  const at = e ? parseAt(e.at) : null;
  if (at && !at.rev) at.rev = (P.doc.subject || {}).sha || null;
  return at;
}
function evidenceLabel(eid) {
  const e = get(P.doc.evidence || {}, eid);
  if (!e) return eid;
  if (own(e, "absent")) return raw(e.absent);
  const at = evidenceAt(eid);
  return at ? `${at.path}:${at.line}` : eid;
}
function evidenceTag(eid) { const e = get(P.doc.evidence || {}, eid); return e && own(e, "absent") ? "verified-absent" : "verified"; }
function evidenceHref(eid) {
  const at = evidenceAt(eid), repo = String((P.doc.subject || {}).repo || "");
  if (!at || !at.rev || !/^https?:\/\//.test(repo)) return null;
  return `${repo.replace(/\/+$/, "")}/blob/${at.rev}/${at.path}#L${at.line}`;
}
function evidenceChip(eid) {
  const tag = evidenceTag(eid), e = get(P.doc.evidence || {}, eid) || {};
  const title = tag === "verified-absent" ? ui("absenceCheck", { pattern: e.git_grep, hits: e.hits }) : ui("anchorCheck", { anchor: e.anchor || "" });
  const href = evidenceHref(eid), label = evidenceLabel(eid);
  const body = [tag === "verified-absent" ? h("span", { class: "chip-k" }, ui("tag." + tag)) : null, h("code", null, label)];
  return href ? h("a", { class: "ev t-" + tag, href, target: "_blank", rel: "noopener", title }, body)
              : h("span", { class: "ev t-" + tag, title }, body);
}
function stepTag(step) { return step.tag === "inferred" || !(step.ev || []).length ? "inferred" : "verified"; }

/* ============ actors: who calls the cache, the store or the queue ============ */

function defaultActor(doc) {
  for (const r of ACTOR_ROLES) { const n = doc.nodes.find(x => x.role === r); if (n) return n.id; }
  return doc.nodes[0].id;
}
function nextActor(a, actor) {
  const role = id => (P.nodeById[id] || {}).role;
  if (a[0] === "send") return ACTOR_ROLES.includes(role(a[2])) ? a[2] : actor;
  if (a[0] === "reply") return ACTOR_ROLES.includes(role(a[2])) ? a[2] : a[1];
  if (a[0] === "pickup") return a[2];
  return actor;
}
// The actor before each effective step of a scenario.
function actorsFor(entries) {
  let actor = defaultActor(P.doc);
  return entries.map(e => { const before = actor; for (const a of e.step.do) actor = nextActor(a, actor); return before; });
}

/* ============ step arrows: what one step moves, derived from its actions ============ */

// Replays one step's actions from the state before it and returns every arrow it draws.
function stepArrows(prevState, entry, actor) {
  const state = clone(prevState), out = newOut(), arrows = [];
  const A = (from, to, kind, label) => {
    if (!from || !to || from === to) return;
    const last = arrows[arrows.length - 1];
    // Back-to-back identical moves (five pickups from one queue) are one numbered move.
    if (last && last.from === from && last.to === to && last.kind === kind) { last.label = last.label + ", " + label; last.times++; return; }
    arrows.push({ from, to, kind, label, times: 1 });
  };
  for (const a of entry.step.do) {
    const [name, x, y, z] = a;
    if (name === "send") A(x, y, "req", z != null ? tx(z) : "");
    else if (name === "reply") A(x, y, "res", z != null ? tx(z) : "");
    else if (name === "enqueue") A(actor, x, "job", y);
    else if (name === "pickup") A(x, y, "job", state.queues[x][0] || "");
    else if (name === "cache.get") A(actor, x, "data", ui("arrow.get", { key: y, r: own(state.caches[x], y) ? ui("hit") : ui("miss") }));
    else if (name === "cache.set") A(actor, x, "data", ui("arrow.set", { key: y, v: valueText(isRef(z) ? (get(state.vars, z.slice(1)) || {}).v : z) }));
    else if (name === "cache.set-if-fresh") A(actor, x, "data", ui("arrow.fresh", { key: y }));
    else if (name === "cache.del") A(actor, x, "data", ui("arrow.del", { key: y }));
    else if (name === "db.read") A(actor, x, "data", ui("arrow.read", { key: y, v: valueText(get(state.stores[x], y)) }));
    else if (name === "db.write") A(actor, x, "data", ui("arrow.write", { key: y, v: valueText(isRef(z) ? (get(state.vars, z.slice(1)) || {}).v : z) }));
    try { applyAction(state, out, a, P.numbers); } catch (e) { break; }
    actor = nextActor(a, actor);
  }
  return arrows;
}

/* ============ what one step changed (the light card's list, the heavy caption's line) ============ */

function changes(prev, cur) {
  const C = (k, a) => ui("change." + k, a), out = [];
  if (cur.hit) out.push(C("hit", { r: cur.hit === "hit" ? ui("hit") : ui("miss") }));
  for (const c of Object.keys(cur.caches)) {
    const before = prev.caches[c] || {}, after = cur.caches[c];
    const keys = Object.keys(before).concat(Object.keys(after).filter(k => !own(before, k)));
    for (const key of keys) {
      const a = get(before, key), b = get(after, key);
      if (same(a, b)) continue;
      out.push(b === null ? C("removed", { c, key }) : C("set", { c, key, v: valueText(b.v) }) + (b.stale ? C("staleSuffix") : ""));
    }
  }
  for (const st of Object.keys(cur.stores)) {
    const before = prev.stores[st] || {};
    for (const key of Object.keys(cur.stores[st])) {
      if (!own(before, key) || !same(before[key], cur.stores[st][key])) out.push(C("set", { c: st, key, v: valueText(cur.stores[st][key]) }));
    }
  }
  for (const name of Object.keys(cur.vars)) if (!same(get(prev.vars, name), cur.vars[name])) out.push(C("holds", { name, v: valueText(cur.vars[name].v) }));
  for (const q of Object.keys(cur.queues)) if (!same(prev.queues[q], cur.queues[q])) out.push(C("queue", { q: label(q), n: cur.queues[q].length }));
  for (const w of Object.keys(cur.workers)) {
    if (!same(prev.workers[w], cur.workers[w])) out.push(C("worker", { w: label(w), b: cur.workers[w].filter(j => j !== null).length, n: cur.workers[w].length }));
  }
  for (const name of Object.keys(cur.counters)) if (get(prev.counters, name) !== cur.counters[name]) out.push(C("counter", { name, v: fmtInt(cur.counters[name]) }));
  if (cur.clock_ms !== prev.clock_ms) out.push(C("clock", { t: fmtClock(cur.clock_ms) }));
  return out;
}
const label = id => tx((P.nodeById[id] || {}).label || id);

/* ============ layout: columns by role, rows by declaration order ============ */

const COMPACT_COLUMNS = 5; // more role columns than this and the gaps shrink so the map stays legible
const G = { pad: 20, top: 44, colGap: 84, colGapCompact: 52, rowGap: 22, narrowW: 360, narrowPad: 12, narrowGap: 12, rowH: 24, slot: 20, slotStep: 26, perRow: 6 };

// The widest content each box must hold across every state of every scenario.
function measureNeeds() {
  const need = { rows: {}, textW: {} };
  const bump = (id, rows, w) => { need.rows[id] = Math.max(need.rows[id] || 0, rows); need.textW[id] = Math.max(need.textW[id] || 0, w); };
  const all = [P.init].concat(...Object.values(P.states).filter(Array.isArray));
  for (const st of all) {
    for (const [c, kv] of Object.entries(st.caches)) {
      const ghosts = (st.skipped || []).filter(k => k.cache === c && !own(kv, k.key));
      let w = 0;
      for (const [k, e] of Object.entries(kv)) w = Math.max(w, (k.length + valueText(e.v).length) * MONO_W + 70);
      for (const g of ghosts) w = Math.max(w, (g.key.length + 12) * MONO_W + 40);
      bump(c, Object.keys(kv).length + ghosts.length, w);
    }
    for (const [s, kv] of Object.entries(st.stores)) {
      let w = 0;
      for (const [k, v] of Object.entries(kv)) w = Math.max(w, (k.length + valueText(v).length) * MONO_W + 44);
      bump(s, Object.keys(kv).length, w);
    }
  }
  return need;
}

const MAX_BOX_W = 300;
function nodeSize(n, need, fullW) {
  const lw = textW(tx(n.label), 13.5) + 28;
  if (n.role === "queue") return { w: fullW || Math.min(MAX_BOX_W, Math.max(214, lw)), h: 74 };
  if (n.role === "worker") {
    const k = n.slots || 1, per = Math.min(k, G.perRow), rows = Math.ceil(k / G.perRow);
    return { w: fullW || Math.min(MAX_BOX_W, Math.max(170, lw + 70, 24 + per * G.slotStep)), h: 36 + rows * G.slotStep + 18 };
  }
  if (n.role === "cache" || n.role === "store") {
    const rows = Math.max(1, need.rows[n.id] || 0);
    return { w: fullW || Math.min(MAX_BOX_W, Math.max(200, lw, need.textW[n.id] || 0)), h: 34 + rows * G.rowH + 8 };
  }
  const refW = n.ref ? textW(n.ref, 10.5) * 1.05 + 24 : 0;
  return { w: fullW || Math.min(220, Math.max(132, lw, refW)), h: n.ref ? 58 : 48 };
}

function layoutWide(need) {
  const cols = ROLES.map(r => P.doc.nodes.filter(n => n.role === r)).filter(c => c.length);
  const sizes = cols.map(c => c.map(n => nodeSize(n, need)));
  const colW = sizes.map(z => Math.max(...z.map(s => s.w)));
  const colH = sizes.map(z => z.reduce((a, s) => a + s.h, 0) + (z.length - 1) * G.rowGap);
  const maxH = Math.max(...colH), pos = {}, zones = [], extents = [];
  const gap = cols.length > COMPACT_COLUMNS ? G.colGapCompact : G.colGap;
  let x = G.pad;
  cols.forEach((c, ci) => {
    let y = G.top + (maxH - colH[ci]) / 2;
    zones.push({ x, y: 24, role: c[0].role });
    extents.push({ x0: x, x1: x + colW[ci] });
    c.forEach((n, ri) => {
      const z = sizes[ci][ri];
      pos[n.id] = { x: x + (colW[ci] - z.w) / 2, y, w: z.w, h: z.h, col: ci, row: ri, band: ci };
      y += z.h + G.rowGap;
    });
    x += colW[ci] + gap;
  });
  return { mode: "wide", W: x - gap + G.pad, H: G.top + maxH + G.pad, pos, zones, cols: extents };
}

function layoutNarrow(need) {
  const inner = G.narrowW - 2 * G.narrowPad, pos = {}, zones = [];
  let y = 6, band = 0;
  for (const r of ROLES) {
    const nodes = P.doc.nodes.filter(n => n.role === r);
    if (!nodes.length) continue;
    zones.push({ x: G.narrowPad, y: y + 14, role: r });
    y += 24;
    const boxy = ["queue", "worker", "cache", "store"].includes(r);
    for (let i = 0, row = 0; i < nodes.length; row++) {
      const pair = boxy ? [nodes[i]] : nodes.slice(i, i + 2);
      const w = pair.length === 2 ? (inner - 10) / 2 : inner;
      const sizes = pair.map(n => nodeSize(n, need, w));
      const hh = Math.max(...sizes.map(s => s.h));
      pair.forEach((n, k) => { pos[n.id] = { x: G.narrowPad + k * (w + 10), y, w, h: hh, col: k, row, band }; });
      y += hh + G.narrowGap;
      i += pair.length;
    }
    y += 6;
    band++;
  }
  return { mode: "narrow", W: G.narrowW, H: y, pos, zones };
}

// An edge keeps its curve unless the curve crosses a box it does not connect; then it is routed
// orthogonally: through the gutters beside its own columns and along a horizontal channel clear
// of every box in the columns between (wide), or down the side margin (narrow).
const EDGE_CLEAR = 8;       // px a routed channel keeps from the boxes it passes
const EDGE_CORNER = 10;     // corner radius of a routed edge
const CHANNEL_TOP = 30;     // highest channel: under the column labels, above every box
const CURVE_SAMPLES = 24;   // points per curve segment when testing it against the boxes
const SAME_PX = 0.5;        // points, or a bend, closer than this are one

function edgePath(A, B, L) {
  const d = curvePath(A, B, L.mode);
  if (!crossesBox(samplePath(d), L, A, B)) return d;
  if (L.mode !== "wide") return routeNarrow(A, B, L);
  return A.col === B.col ? d : routeWide(A, B, L);
}

function samplePath(d) {
  const tok = d.match(/[MLC]|-?[\d.]+(?:e-?\d+)?/g) || [], pts = [];
  let i = 0, cmd = "", cur = [0, 0];
  const num = () => +tok[i++];
  const pt = () => [num(), num()];
  while (i < tok.length) {
    if (/^[MLC]$/.test(tok[i])) cmd = tok[i++];
    if (cmd === "M") { cur = pt(); pts.push(cur); continue; }
    const c1 = cmd === "C" ? pt() : null, c2 = cmd === "C" ? pt() : null, end = pt();
    for (let k = 1; k <= CURVE_SAMPLES; k++) {
      const t = k / CURVE_SAMPLES, u = 1 - t;
      pts.push(c1 ? [0, 1].map(j => u * u * u * cur[j] + 3 * u * u * t * c1[j] + 3 * u * t * t * c2[j] + t * t * t * end[j])
                  : [cur[0] + (end[0] - cur[0]) * t, cur[1] + (end[1] - cur[1]) * t]);
    }
    cur = end;
  }
  return pts;
}

function crossesBox(pts, L, A, B) {
  return Object.values(L.pos).some(p => p !== A && p !== B &&
    pts.some(([x, y]) => x > p.x && x < p.x + p.w && y > p.y && y < p.y + p.h));
}

// The y nearest `want` in [lo, hi] that sits in no blocked interval.
function freeLine(blocked, want, lo, hi) {
  let best = null, at = lo;
  const consider = (a, b) => { if (b < a) return; const y = clamp(want, a, b); if (best === null || Math.abs(y - want) < Math.abs(best - want)) best = y; };
  for (const [a, b] of blocked.slice().sort((p, q) => p[0] - q[0])) { consider(at, a); at = Math.max(at, b); }
  consider(at, hi);
  return best === null ? lo : best;
}

function routeWide(A, B, L) {
  const dir = B.col > A.col ? 1 : -1, ay = A.y + A.h / 2, by = B.y + B.h / 2;
  const x1 = dir > 0 ? A.x + A.w : A.x, x2 = dir > 0 ? B.x : B.x + B.w;
  const gutter = c => (L.cols[c].x1 + L.cols[c + 1].x0) / 2; // between column c and c+1
  const gA = gutter(dir > 0 ? A.col : A.col - 1), gB = gutter(dir > 0 ? B.col - 1 : B.col);
  const lo = Math.min(A.col, B.col), hi = Math.max(A.col, B.col);
  const blocked = Object.values(L.pos).filter(p => p.col > lo && p.col < hi).map(p => [p.y - EDGE_CLEAR, p.y + p.h + EDGE_CLEAR]);
  const cy = freeLine(blocked, (ay + by) / 2, CHANNEL_TOP, L.H - EDGE_CLEAR);
  return roundedPath([[x1, ay], [gA, ay], [gA, cy], [gB, cy], [gB, by], [x2, by]], EDGE_CORNER);
}

function routeNarrow(A, B, L) {
  const down = B.y > A.y, s = down ? 1 : -1, ax = A.x + A.w / 2, bx = B.x + B.w / 2;
  const y1 = down ? A.y + A.h : A.y, y2 = down ? B.y : B.y + B.h, half = G.narrowGap / 2;
  const side = (ax + bx) / 2 < L.W / 2 ? G.narrowPad / 2 : L.W - G.narrowPad / 2;
  return roundedPath([[ax, y1], [ax, y1 + s * half], [side, y1 + s * half], [side, y2 - s * half], [bx, y2 - s * half], [bx, y2]], half);
}

function roundedPath(points, r) {
  const pts = [];
  for (const p of points) { const q = pts[pts.length - 1]; if (!q || Math.hypot(p[0] - q[0], p[1] - q[1]) > SAME_PX) pts.push(p); }
  const bend = (a, b, c) => Math.abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) > SAME_PX;
  const k = pts.filter((p, i) => i === 0 || i === pts.length - 1 || bend(pts[i - 1], p, pts[i + 1]));
  const f = v => Math.round(v * 10) / 10;
  let d = `M${f(k[0][0])} ${f(k[0][1])}`;
  for (let i = 1; i < k.length - 1; i++) {
    const [px, py] = k[i - 1], [x, y] = k[i], [nx, ny] = k[i + 1];
    const l1 = Math.hypot(x - px, y - py), l2 = Math.hypot(nx - x, ny - y), rr = Math.min(r, l1 / 2, l2 / 2);
    d += ` L${f(x - (x - px) / l1 * rr)} ${f(y - (y - py) / l1 * rr)} Q${f(x)} ${f(y)} ${f(x + (nx - x) / l2 * rr)} ${f(y + (ny - y) / l2 * rr)}`;
  }
  const z = k[k.length - 1];
  return d + ` L${f(z[0])} ${f(z[1])}`;
}

function curvePath(A, B, mode) {
  const ax = A.x + A.w / 2, ay = A.y + A.h / 2, bx = B.x + B.w / 2, by = B.y + B.h / 2;
  const bulgeRight = () => {
    const x1 = A.x + A.w, x2 = B.x + B.w, bx2 = Math.max(x1, x2) + 40;
    return `M${x1} ${ay} C${bx2} ${ay} ${bx2} ${by} ${x2} ${by}`;
  };
  if (mode === "wide") {
    if (A.col !== B.col) {
      const dir = bx > ax ? 1 : -1, x1 = dir > 0 ? A.x + A.w : A.x, x2 = dir > 0 ? B.x : B.x + B.w;
      const dx = Math.max(24, Math.abs(x2 - x1) / 2);
      return `M${x1} ${ay} C${x1 + dir * dx} ${ay} ${x2 - dir * dx} ${by} ${x2} ${by}`;
    }
    if (Math.abs(A.row - B.row) === 1) {
      const down = by > ay, y1 = down ? A.y + A.h : A.y, y2 = down ? B.y : B.y + B.h;
      return `M${ax} ${y1} L${bx} ${y2}`;
    }
    return bulgeRight();
  }
  if (A.band !== B.band) {
    const down = by > ay, y1 = down ? A.y + A.h : A.y, y2 = down ? B.y : B.y + B.h;
    const dy = Math.max(16, Math.abs(y2 - y1) / 2) * (down ? 1 : -1);
    return `M${ax} ${y1} C${ax} ${y1 + dy} ${bx} ${y2 - dy} ${bx} ${y2}`;
  }
  if (Math.abs(ay - by) < 2) {
    const dir = bx > ax ? 1 : -1, x1 = dir > 0 ? A.x + A.w : A.x, x2 = dir > 0 ? B.x : B.x + B.w;
    return `M${x1} ${ay} L${x2} ${by}`;
  }
  return bulgeRight();
}

// Every pair of nodes any scenario connects, so the map does not change between steps.
function collectEdges() {
  const pairs = new Map();
  const add = (a, b, kind) => {
    if (!a || !b || a === b) return;
    const key = [a, b].sort().join("|");
    if (!pairs.has(key) || pairs.get(key) === "data") pairs.set(key, kind);
  };
  for (const sid of P.order) {
    const entries = P.entries[sid];
    if (!entries) continue;
    let actor = defaultActor(P.doc);
    for (const e of entries) {
      for (const a of e.step.do) {
        const [name, x, y] = a;
        if (name === "send" || name === "reply") add(x, y, "msg");
        else if (name === "enqueue") add(actor, x, "feed");
        else if (name === "pickup") add(x, y, "feed");
        else if (/^(cache\.(get|set|set-if-fresh|del)|db\.(read|write))$/.test(name)) add(actor, x, "data");
        actor = nextActor(a, actor);
      }
    }
  }
  return pairs;
}

/* ============ the map: static frame once, then render(state) as often as needed ============ */

let mapSeq = 0;
function buildMap(host, opts) {
  const need = P.need, narrow = opts && opts.narrow;
  const L = narrow ? layoutNarrow(need) : layoutWide(need);
  const id = "m" + (++mapSeq);
  const svg = sv("svg", { viewBox: `0 0 ${L.W} ${L.H}`, class: "map " + L.mode, role: "img", "aria-labelledby": id + "-t" });
  svg.style.maxWidth = L.W + "px"; // never scale a map above its natural size
  host.replaceChildren(svg);
  const title = sv("title", { id: id + "-t" }, svg, "");
  const defs = sv("defs", null, svg);
  const hatch = sv("pattern", { id: id + "-hatch", width: 7, height: 7, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" }, defs);
  sv("rect", { width: 7, height: 7, class: "hatch-bg" }, hatch);
  sv("line", { x1: 0, y1: 0, x2: 0, y2: 7, class: "hatch-line" }, hatch);
  for (const k of ["req", "res", "job", "data"]) {
    const m = sv("marker", { id: `${id}-arr-${k}`, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" }, defs);
    sv("path", { d: "M0 0 L10 5 L0 10 z", class: "arrowhead " + k }, m);
  }
  for (const z of L.zones) sv("text", { class: "zone", x: z.x, y: z.y }, svg, ui("role." + z.role));
  const layers = {};
  for (const k of ["edges", "overlay", "nodes", "labels", "chips", "dots"]) layers[k] = sv("g", { class: "layer-" + k }, svg);
  const M = { svg, title, L, id, layers, nodes: {}, edgeKinds: collectEdges() };
  for (const [key, kind] of M.edgeKinds) {
    const [a, b] = key.split("|");
    if (L.pos[a] && L.pos[b]) sv("path", { class: "edge " + kind, "data-edge": key, d: edgePath(L.pos[a], L.pos[b], L) }, layers.edges);
  }
  for (const n of P.doc.nodes) {
    const p = L.pos[n.id];
    const g = sv("g", { class: `node r-${n.role}` + (n.outside_diff ? " ctx" : ""), "data-node": n.id }, layers.nodes);
    sv("title", null, g, tx(n.label) + (n.ref ? " · " + n.ref : ""));
    sv("rect", { class: "box", x: p.x, y: p.y, width: p.w, height: p.h, rx: 8 }, g);
    const body = ["queue", "worker", "cache", "store"].includes(n.role);
    if (body) {
      sv("text", { class: "lbl", x: p.x + 12, y: p.y + 20 }, g, truncate(tx(n.label), Math.floor((p.w - 90) / 7.6)));
    } else {
      const ly = n.ref ? p.y + p.h / 2 - 3 : p.y + p.h / 2 + 5;
      sv("text", { class: "lbl", x: p.x + p.w / 2, y: ly, "text-anchor": "middle" }, g, truncate(tx(n.label), Math.floor((p.w - 16) / 7.4)));
      if (n.ref) sv("text", { class: "sub", x: p.x + p.w / 2, y: ly + 16, "text-anchor": "middle" }, g, truncate(n.ref, Math.floor((p.w - 12) / 6.3)));
    }
    M.nodes[n.id] = { g, p, role: n.role, dyn: sv("g", { class: "dyn" }, g) };
  }
  return M;
}

function chipAt(parent, x, y, text, cls) {
  const g = sv("g", { class: "chip " + (cls || ""), transform: `translate(${x},${y})` }, parent);
  sv("rect", { width: 54, height: 22, rx: 5 }, g);
  sv("text", { x: 27, y: 15, "text-anchor": "middle" }, g, truncate(text, 8));
  sv("title", null, g, text);
  return g;
}
const qPos = (p, i) => [p.x + 10 + Math.min(i, VIS - 1) * 60, p.y + 34];
const slotPos = (p, k) => [p.x + 12 + (k % G.perRow) * G.slotStep, p.y + 32 + Math.floor(k / G.perRow) * G.slotStep];
const rowY = (p, i) => p.y + 30 + i * G.rowH;

// render = f(state). info: { active, inferred, hit: cacheId|null, hazards, skipped, failures, prev, pending }
function renderMap(M, state, info) {
  info = info || {};
  const active = info.active || [], hz = info.hazards || [], sk = info.skipped || [], pend = info.pending || {};
  for (const n of P.doc.nodes) {
    const N = M.nodes[n.id], p = N.p, d = N.dyn, on = active.includes(n.id);
    N.g.classList.toggle("on", on);
    N.g.classList.toggle("dash", on && !!info.inferred);
    N.g.classList.toggle("failed", state.failed.includes(n.id));
    d.replaceChildren();
    if (n.role === "queue") {
      const jobs = state.queues[n.id] || [];
      jobs.slice(0, VIS).forEach((j, i) => {
        const [x, y] = qPos(p, i), c = chipAt(d, x, y, j);
        if (pend.queue === n.id && pend.index === i) c.setAttribute("opacity", 0);
      });
      if (jobs.length > VIS) sv("text", { class: "more", x: p.x + p.w - 10, y: p.y + 50, "text-anchor": "end" }, d, ui("more", { n: jobs.length - VIS }));
      if (!jobs.length) sv("text", { class: "empty", x: p.x + 12, y: p.y + 50 }, d, ui("empty"));
      sv("text", { class: "meta", x: p.x + p.w - 10, y: p.y + 20, "text-anchor": "end" }, d, String(jobs.length));
    } else if (n.role === "worker") {
      const slots = state.workers[n.id] || [];
      slots.forEach((j, k) => {
        const [x, y] = slotPos(p, k), busy = j !== null && !(pend.worker === n.id && pend.slot === k);
        const r = sv("rect", { class: "slot" + (busy ? " busy" : ""), x, y, width: G.slot, height: G.slot, rx: 4 }, d);
        if (j !== null) sv("title", null, r, j);
      });
      const b = slots.filter(j => j !== null).length;
      sv("text", { class: "meta", x: p.x + p.w - 10, y: p.y + 20, "text-anchor": "end" }, d, ui("busyOf", { b, n: slots.length }));
      const run = slots.filter(j => j !== null);
      sv("text", { class: "sub", x: p.x + 12, y: p.y + p.h - 8 }, d, run.length ? truncate(ui("running") + ": " + run.join(", "), Math.floor((p.w - 20) / 6.3)) : "");
    } else if (n.role === "cache") {
      const kv = state.caches[n.id] || {}, keys = Object.keys(kv);
      keys.forEach((k, i) => cacheRow(M, d, p, i, k, kv[k], hz.some(x => x.cache === n.id && x.key === k)));
      sk.filter(x => x.cache === n.id && !own(kv, x.key)).forEach((x, i) => ghostRow(d, p, keys.length + i, x.key));
      if (!keys.length && !sk.some(x => x.cache === n.id)) sv("text", { class: "empty", x: p.x + 12, y: rowY(p, 0) + 15 }, d, ui("empty"));
      if (info.hit && info.hitCache === n.id) badge(d, p, info.hit === "hit" ? ui("hit") : ui("miss"), info.hit);
    } else if (n.role === "store") {
      const kv = state.stores[n.id] || {}, keys = Object.keys(kv), prev = info.prev ? info.prev.stores[n.id] || {} : kv;
      keys.forEach((k, i) => {
        const y = rowY(p, i), chg = !own(prev, k) || !same(prev[k], kv[k]);
        sv("rect", { class: "row" + (chg ? " chg" : ""), x: p.x + 8, y, width: p.w - 16, height: G.rowH - 4, rx: 4 }, d);
        sv("text", { class: "key", x: p.x + 14, y: y + 14 }, d, truncate(k, 22));
        sv("text", { class: "val", x: p.x + p.w - 14, y: y + 14, "text-anchor": "end" }, d, truncate(valueText(kv[k]), 18));
      });
      if (!keys.length) sv("text", { class: "empty", x: p.x + 12, y: rowY(p, 0) + 15 }, d, ui("empty"));
    }
    if (state.failed.includes(n.id)) {
      const f = (info.failures || []).find(x => x.node === n.id);
      badge(d, p, ui("failedBadge"), "failed");
      if (f && f.label && !["queue", "worker", "cache", "store"].includes(n.role)) {
        sv("text", { class: "faillbl", x: p.x + p.w / 2, y: p.y + p.h + 14, "text-anchor": "middle" }, d, truncate(tx(f.label), 30));
      }
    }
  }
  M.title.textContent = mapSummary(state, info);
}

function cacheRow(M, d, p, i, k, e, hazard) {
  const y = rowY(p, i), w = p.w - 16;
  sv("rect", { class: "row" + (e.stale ? " stale" : "") + (hazard ? " hazard" : ""), x: p.x + 8, y, width: w, height: G.rowH - 4, rx: 4 }, d);
  if (e.stale) sv("rect", { class: "hatch", x: p.x + 8, y, width: w, height: G.rowH - 4, rx: 4, fill: `url(#${M.id}-hatch)` }, d);
  sv("text", { class: "key", x: p.x + (hazard ? 30 : 14), y: y + 14 }, d, truncate(k, 18));
  const right = p.x + p.w - 14;
  sv("text", { class: "val", x: right, y: y + 14, "text-anchor": "end" }, d, truncate(valueText(e.v), 14));
  if (e.stale) sv("text", { class: "stale-tag", x: right - Math.min(14, valueText(e.v).length) * MONO_W - 8, y: y + 14, "text-anchor": "end" }, d, ui("stale"));
  if (hazard) {
    sv("circle", { class: "hz-mark", cx: p.x + 19, cy: y + 10, r: 8 }, d);
    sv("text", { class: "hz-mark-t", x: p.x + 19, y: y + 14, "text-anchor": "middle" }, d, "!");
  }
}
function ghostRow(d, p, i, key) {
  const y = rowY(p, i);
  sv("rect", { class: "row ghost", x: p.x + 8, y, width: p.w - 16, height: G.rowH - 4, rx: 4 }, d);
  sv("text", { class: "key", x: p.x + 14, y: y + 14 }, d, truncate(key, 18));
  sv("text", { class: "val skipped", x: p.x + p.w - 14, y: y + 14, "text-anchor": "end" }, d, ui("skippedTag"));
}
function badge(d, p, text, kind) {
  const w = textW(text, 10.5) + 14, x = p.x + p.w - w - 6, y = p.y - 9;
  sv("rect", { class: "badge " + kind, x, y, width: w, height: 18, rx: 9 }, d);
  sv("text", { class: "badge-t " + kind, x: x + w / 2, y: y + 13, "text-anchor": "middle" }, d, text);
}
function mapSummary(state, info) {
  const parts = [];
  if ((info.active || []).length) parts.push("Active: " + info.active.map(label).join(", ") + ".");
  for (const [c, kv] of Object.entries(state.caches)) parts.push(`${label(c)}: ` + (Object.keys(kv).map(k => `${k} = ${valueText(kv[k].v)}${kv[k].stale ? " (stale)" : ""}`).join(", ") || ui("empty")) + ".");
  for (const [s, kv] of Object.entries(state.stores)) parts.push(`${label(s)}: ` + (Object.keys(kv).map(k => `${k} = ${valueText(kv[k])}`).join(", ") || ui("empty")) + ".");
  for (const [q, jobs] of Object.entries(state.queues)) parts.push(`${label(q)}: ${jobs.length}.`);
  for (const [w, sl] of Object.entries(state.workers)) parts.push(`${label(w)}: ${ui("busyOf", { b: sl.filter(j => j !== null).length, n: sl.length })}.`);
  if (state.failed.length) parts.push(ui("failedBadge") + ": " + state.failed.map(label).join(", ") + ".");
  return parts.join(" ");
}

// Each arrow of a step gets a numbered badge at a point clear of every box and of the other
// badges; the labels go in a numbered list beside the map, so nothing overlaps.
const BADGE_R = 9;
const BADGE_TRIES = [0.5, 0.6, 0.7, 0.8, 0.4, 0.88, 0.3, 0.2, 0.12];
function insideBox(L, x, y) {
  return Object.values(L.pos).some(p => x > p.x - BADGE_R && x < p.x + p.w + BADGE_R && y > p.y - BADGE_R && y < p.y + p.h + BADGE_R);
}
function drawArrows(M, arrows) {
  const g = M.layers.overlay, tags = M.layers.labels, L = M.L, placed = [];
  g.replaceChildren();
  tags.replaceChildren();
  arrows.forEach((a, k) => {
    const A = L.pos[a.from], B = L.pos[a.to];
    if (!A || !B) return;
    const shift = a.kind === "res" ? 6 : a.kind === "data" ? -6 : 0;
    const tf = L.mode === "wide" ? `translate(0,${shift})` : `translate(${shift},0)`;
    const grp = sv("g", { class: "arrow " + a.kind, transform: tf }, g);
    const path = sv("path", { d: edgePath(A, B, L), "marker-end": `url(#${M.id}-arr-${a.kind})` }, grp);
    let pt = null;
    try {
      const len = path.getTotalLength();
      const pts = BADGE_TRIES.map(t => path.getPointAtLength(len * t));
      const free = q => !insideBox(L, q.x, q.y) && placed.every(o => Math.hypot(o.x - q.x, o.y - q.y) > 2 * BADGE_R + 2);
      pt = pts.find(free) || pts.find(q => !insideBox(L, q.x, q.y)) || pts[0];
    } catch (e) { pt = { x: (A.x + A.w / 2 + B.x + B.w / 2) / 2, y: (A.y + A.h / 2 + B.y + B.h / 2) / 2 }; }
    placed.push(pt);
    const b = sv("g", { class: "abadge " + a.kind, transform: tf }, tags);
    sv("circle", { cx: pt.x, cy: pt.y, r: BADGE_R }, b);
    sv("text", { x: pt.x, y: pt.y + 4, "text-anchor": "middle" }, b, String(k + 1));
    sv("title", null, b, `${k + 1}. ${a.label || ""} (${label(a.from)} → ${label(a.to)})`);
  });
}
function movesList(arrows) {
  if (!arrows.length) return null;
  return h("ol", { class: "moves", "aria-label": ui("moves") }, arrows.map((a, k) => h("li", { class: a.kind },
    h("span", { class: "mv-n", "aria-hidden": "true" }, String(k + 1)),
    h("span", { class: "mv-t" }, a.label ? h("code", null, a.label) : null,
      h("span", { class: "mv-ft" }, `${label(a.from)} → ${label(a.to)}` + (a.times > 1 ? ` ×${a.times}` : ""))))));
}

/* ============ shared page parts ============ */

function header() {
  const sub = P.doc.subject || {};
  const bits = [h("span", { class: "pill" }, sub.kind)];
  if (sub.repo) bits.push(h("code", null, sub.repo));
  if (sub.pr) bits.push(h("span", null, "#" + sub.pr));
  if (sub.sha) bits.push(h("code", { title: sub.sha }, sub.sha.slice(0, 12)));
  const tools = h("div", { class: "tools" });
  if (P.tier === "heavy" && P.hasJa) {
    const grp = h("div", { class: "seg", role: "group", "aria-label": ui("lang") });
    for (const [l, t] of [["en", "EN"], ["ja", "日本語"]]) {
      grp.append(h("button", { type: "button", "aria-pressed": String(P.lang === l), lang: l, onclick: () => setLang(l) }, t));
    }
    tools.append(grp);
  }
  tools.append(h("button", { type: "button", class: "btn", id: "theme-btn", onclick: cycleTheme }, ui("theme", { mode: ui("theme" + cap(P.theme)) })));
  return h("header", { class: "head" },
    h("div", { class: "top" }, h("h1", null, tx(P.doc.title)), tools),
    h("p", { class: "lede" }, txNode(sub.lede)),
    h("p", { class: "meta-line" }, bits));
}
const cap = s => s.charAt(0).toUpperCase() + s.slice(1);

function countTags() {
  const ev = Object.values(P.doc.evidence || {});
  const nums = Object.values(P.numbers);
  let inferred = 0;
  for (const s of P.doc.scenarios) for (const st of s.steps) if (stepTag(st) === "inferred") inferred++;
  return {
    verified: ev.filter(e => !own(e, "absent")).length, "verified-absent": ev.filter(e => own(e, "absent")).length,
    measured: nums.filter(n => n.tag === "measured").length, estimated: nums.filter(n => n.tag === "estimated").length, inferred,
  };
}
function howto() {
  const counts = countTags();
  return h("section", { class: "howto", "aria-label": ui("howto") },
    Object.keys(counts).map(t => h("div", { class: "how t-" + t },
      h("b", null, ui("tag." + t)), h("p", null, ui("tagHelp." + t)), h("span", { class: "count" }, ui("tagCount." + t, { n: counts[t] })))));
}

function mapLegend() {
  const roles = new Set(P.doc.nodes.map(n => n.role));
  const items = [["req", "dot req"], ["res", "dot res"]];
  if (roles.has("queue")) items.push(["job", "card"], ["more", "plus"]);
  if (roles.has("worker")) items.push(["slot", "sq"]);
  if (roles.has("cache")) items.push(["stale", "hatchsw"], ["hazard", "hz"]);
  items.push(["failed", "failsw"], ["inferred", "dashsw"]);
  if (P.doc.nodes.some(n => n.outside_diff)) items.push(["context", "ctxsw"]);
  return h("div", { class: "legend", "aria-label": ui("mapLegend") },
    items.map(([k, cls]) => h("span", null, cls === "plus" ? h("b", { class: "plus" }, "+N") : h("i", { class: cls, "aria-hidden": "true" }), ui("legend." + k))));
}

function issuesPanel(onShow) {
  const issues = P.doc.scenarios.filter(s => s.severity);
  if (!issues.length) return null;
  const rows = issues.map(s => h("tr", null,
    h("td", null, h("span", { class: "kind" }, ui("kind." + s.kind)), " ", onShow ? h("button", { type: "button", class: "link", onclick: () => onShow(s.id) }, tx(s.title)) : h("a", { href: "#sc-" + s.id }, tx(s.title))),
    h("td", null, h("span", { class: "sev s-" + s.severity }, ui("severity." + s.severity))),
    h("td", null, s.fixed_by ? s.fixed_by.map(f => {
      const fs = P.scen[f];
      return onShow ? h("button", { type: "button", class: "link", onclick: () => onShow(f) }, tx(fs ? fs.title : f)) : h("a", { href: "#sc-" + f }, tx(fs ? fs.title : f));
    }) : h("span", { class: "muted" }, ui("open")))));
  return h("section", { class: "panel" }, h("h2", null, ui("issues")),
    h("div", { class: "tbl" }, h("table", null,
      h("thead", null, h("tr", null, h("th", null, ui("issueCol")), h("th", null, ui("severityCol")), h("th", null, ui("fixCol")))),
      h("tbody", null, rows))));
}

function decisionPanel(onShow) {
  const d = P.doc.decision;
  if (!d) return null;
  const opts = d.options.map(o => {
    const chosen = o.id === d.chosen;
    return h("article", { class: "opt" + (chosen ? " chosen" : "") + (o.fit === "fail" ? " fails" : "") },
      h("div", { class: "opt-head" }, h("h3", null, tx(o.label)),
        h("span", { class: "fit f-" + o.fit }, o.fit === "pass" ? ui("solves") : ui("notSolves")),
        chosen ? h("span", { class: "chosen-b" }, ui("chosen")) : null),
      h("div", { class: "pc" },
        h("div", null, h("h4", null, ui("pros")), h("ul", { class: "pros" }, o.pros.map(x => h("li", null, txNode(x))))),
        h("div", null, h("h4", null, ui("cons")), h("ul", { class: "cons" }, o.cons.map(x => h("li", null, txNode(x)))))),
      o.scenario && P.scen[o.scenario] ? (onShow ? h("button", { type: "button", class: "link", onclick: () => onShow(o.scenario) }, ui("showScenario"))
        : h("a", { class: "link", href: "#sc-" + o.scenario }, ui("showScenario"))) : null);
  });
  return h("section", { class: "panel decision" }, h("h2", null, ui("decision")),
    h("div", { class: "opts" }, opts),
    h("dl", { class: "dec" },
      h("div", null, h("dt", null, ui("deciding")), h("dd", null, txNode(d.deciding_factor))),
      h("div", null, h("dt", null, ui("revisit")), h("dd", null, txNode(d.revisit_when))),
      h("div", null, h("dt", null, ui("source")), h("dd", null, h("code", null, d.source)))));
}

function numbersPanel() {
  const names = Object.keys(P.numbers);
  if (!names.length) return null;
  return h("section", { class: "panel" }, h("h2", null, ui("numbers")),
    h("div", { class: "tbl" }, h("table", null,
      h("thead", null, h("tr", null, h("th", null, ui("nameCol")), h("th", null, ui("valueCol")), h("th", null, ui("tagCol")), h("th", null, ui("backedCol")))),
      h("tbody", null, names.map(k => {
        const n = P.numbers[k];
        return h("tr", null, h("td", null, h("code", null, k)), h("td", { class: "n" }, fmtNumber(n)),
          h("td", null, h("span", { class: "tagchip t-" + n.tag }, ui("tag." + n.tag))),
          h("td", null, n.tag === "verified" && n.ev ? evidenceChip(n.ev) : raw(n.tag === "measured" ? n.source : n.basis)));
      })))));
}

function evidencePanel() {
  const ids = Object.keys(P.doc.evidence || {});
  if (!ids.length) return null;
  return h("details", { class: "panel ev-panel" }, h("summary", null, ui("evidence", { n: ids.length })),
    h("div", { class: "tbl" }, h("table", null,
      h("thead", null, h("tr", null, h("th", null, ui("idCol")), h("th", null, ui("whereCol")), h("th", null, ui("checkCol")))),
      h("tbody", null, ids.map(id => {
        const e = P.doc.evidence[id];
        const check = own(e, "absent") ? ui("absenceCheck", { pattern: e.git_grep, hits: e.hits }) + " · " + e.path : ui("anchorCheck", { anchor: e.anchor });
        return h("tr", null, h("td", null, h("code", null, id)), h("td", null, evidenceChip(id)), h("td", null, check));
      })))));
}

function footer() { return h("footer", { class: "foot" }, h("p", null, ui("footer", { tier: P.tier }))); }

function banners(st) {
  const out = [];
  for (const x of st.hazards) out.push(h("p", { class: "banner hazard", role: "note" }, h("b", null, "!"), " ", ui("hazard", { cache: label(x.cache), key: x.key, store: label(x.store), skey: x.store_key })));
  for (const x of st.skipped || []) out.push(h("p", { class: "banner skipped", role: "note" }, h("b", null, "✓"), " ", ui("skipped", { cache: label(x.cache), key: x.key, store: label(x.store), skey: x.store_key, read: valueText(x.read), current: valueText(x.current) })));
  for (const f of st.failures) out.push(h("p", { class: "banner failure", role: "note" }, h("b", null, "×"), " ", ui("failed", { node: label(f.node), label: f.label ? tx(f.label) : "" })));
  for (const n of st.notes) out.push(h("p", { class: "banner note" }, txNode(n)));
  return out;
}

function stepChips(step) {
  const tag = stepTag(step);
  return h("p", { class: "chips" },
    h("span", { class: "tagchip t-" + tag }, ui("tag." + tag)),
    (step.ev || []).map(evidenceChip));
}

/* ============ light tier: one static card per step ============ */

function renderLight(app) {
  const narrow = innerWidth < NARROW_PX;
  app.replaceChildren(header(), howto());
  const mapHost = h("figure", { class: "mapfig" });
  const overview = h("section", { class: "panel", id: "flow-main", tabindex: "-1" }, h("h2", null, ui("map")), mapHost, mapLegend());
  app.append(overview);
  const M0 = buildMap(mapHost, { narrow });
  renderMap(M0, P.init, {});
  const issues = issuesPanel(null);
  if (issues) app.append(issues);
  for (const sid of P.order) app.append(lightScenario(sid, narrow));
  for (const x of [decisionPanel(null), numbersPanel(), evidencePanel(), footer()]) if (x) app.append(x);
  // Cards are drawn after they are in the document: arrow labels need path lengths.
  for (const job of P.pendingCards.splice(0)) job();
  // The cards did not exist when the browser looked for the #<scenario>.<step> target.
  let target = null;
  try { target = location.hash.length > 1 ? $(decodeURIComponent(location.hash.slice(1))) : null; } catch (e) { /* fail-open: a malformed %-escape in the hash links nowhere */ }
  if (target) {
    if (target.hidden) { const more = target.parentElement.querySelector(".same button"); if (more) more.click(); }
    target.scrollIntoView({ block: "start" });
  }
}

function lightScenario(sid, narrow) {
  const s = P.scen[sid], sts = P.states[sid];
  const sec = h("section", { class: "scenario", id: "sc-" + sid, "aria-labelledby": "sch-" + sid });
  const badges = [h("span", { class: "kind" }, ui("kind." + s.kind))];
  if (s.severity) badges.push(h("span", { class: "sev s-" + s.severity }, ui("severity." + s.severity)));
  sec.append(h("div", { class: "sc-head" }, h("h2", { id: "sch-" + sid }, tx(s.title)), badges));
  if (!Array.isArray(sts)) { sec.append(errorBox(ui("scenarioError"), sts && sts.error)); return sec; }
  const fixLine = [];
  if (s.fixed_by) fixLine.push(ui("fixedBy") + ": ", s.fixed_by.map((f, i) => [i ? ", " : "", h("a", { href: "#sc-" + f }, tx((P.scen[f] || {}).title || f))]));
  else if (s.severity && s.open) fixLine.push(ui("open"));
  if (fixLine.length) sec.append(h("p", { class: "fixline" }, fixLine));
  const ol = h("ol", { class: "cards" });
  const inheritedN = sts.filter(x => x.inherited).length;
  if (inheritedN) {
    const from = s.branch.from, more = h("button", { type: "button", class: "link", "aria-expanded": "false" }, ui("showSame"));
    const note = h("li", { class: "same" }, h("p", null, ui("sameSteps", { n: inheritedN, title: tx(P.scen[from].title) }), " ", more));
    ol.append(note);
    const hidden = [];
    more.addEventListener("click", () => {
      const open = more.getAttribute("aria-expanded") !== "true";
      more.setAttribute("aria-expanded", String(open));
      hidden.forEach(li => { li.hidden = !open; });
    });
    sts.forEach((st, i) => { if (st.inherited) { const li = lightCard(sid, i, narrow); li.hidden = true; hidden.push(li); ol.append(li); } });
    sts.forEach((st, i) => { if (!st.inherited) ol.append(lightCard(sid, i, narrow)); });
  } else {
    sts.forEach((st, i) => ol.append(lightCard(sid, i, narrow)));
  }
  sec.append(ol);
  return sec;
}

function lightCard(sid, i, narrow) {
  const sts = P.states[sid], st = sts[i], entry = P.entries[sid][i], step = entry.step;
  const prev = i ? sts[i - 1] : P.init, tag = stepTag(step);
  const ch = changes(prev, st);
  const arrows = stepArrows(prev, entry, P.actors[sid][i]);
  const text = h("div", { class: "card-text" },
    h("div", { class: "card-head" }, h("span", { class: "num" }, pad2(i + 1)), h("h3", null, tx(step.t)),
      step.time ? h("span", { class: "time" }, tx(step.time)) : null),
    step.d ? h("p", { class: "d" }, txNode(step.d)) : null,
    stepChips(step), banners(st), movesList(arrows),
    h("div", { class: "after" }, h("span", { class: "after-k" }, ui("afterStep")),
      ch.length ? h("ul", null, ch.map(c => h("li", null, h("code", null, c)))) : h("span", { class: "muted" }, ui("noChange"))));
  const fig = h("figure", { class: "card-map" });
  const li = h("li", { class: "card" + (tag === "inferred" ? " inferred" : "") + (st.hazards.length ? " has-hazard" : ""), id: `${sid}.${i}`, "data-step": String(i) }, text, fig);
  if (!narrow && P.wideMap) li.classList.add("stack");
  P.pendingCards.push(() => {
    const M = buildMap(fig, { narrow });
    renderMap(M, st, { active: st.active, inferred: tag === "inferred", hit: st.hit, hitCache: lastGetCache(step), hazards: st.hazards, skipped: st.skipped, failures: st.failures, prev });
    drawArrows(M, arrows);
  });
  return li;
}

function lastGetCache(step) {
  let c = null;
  for (const a of step.do) if (a[0] === "cache.get") c = a[1];
  return c;
}

function errorBox(title, detail) {
  return h("div", { class: "errorbox", role: "alert" }, h("b", null, title), detail ? h("code", null, detail) : null);
}

/* ============ heavy tier: the animated player ============ */

const CANCEL = { cancel: true };
const PL = { sid: null, i: 0, playing: false, tk: { off: false }, revealed: new Set(), wasAuto: false, M: null, rafs: new Set() };
const reduced = () => P.reducedMotion;
const speed = () => +(($("speed") || {}).value || 1);
// One animation frame: requestAnimationFrame, or a timer when frames are not produced
// (headless browsers, some embedded viewers); whichever fires first wins.
const FRAME_FALLBACK_MS = 32;
function nextFrame(cb) {
  let done = false;
  const run = t => { if (done) return; done = true; cancelAnimationFrame(raf); clearTimeout(tm); cb(t === undefined ? performance.now() : t); };
  const raf = requestAnimationFrame(run), tm = setTimeout(run, FRAME_FALLBACK_MS);
  return () => { done = true; cancelAnimationFrame(raf); clearTimeout(tm); };
}
const ease = t => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);

function tween(ms, fn) {
  const tk = PL.tk;
  if (tk.off) { const p = Promise.reject(CANCEL); p.catch(() => {}); return p; }
  if (reduced() || !ms) { fn(1); return Promise.resolve(); }
  ms /= speed();
  const p = new Promise((res, rej) => {
    const t0 = performance.now();
    (function f() {
      if (tk.off) return rej(CANCEL);
      const t = Math.min(1, (performance.now() - t0) / ms);
      fn(ease(t));
      t < 1 ? nextFrame(f) : res();
    })();
  });
  p.catch(() => {});
  return p;
}
function hold(ms) {
  const tk = PL.tk;
  if (tk.off) { const p = Promise.reject(CANCEL); p.catch(() => {}); return p; }
  const p = new Promise((res, rej) => {
    const t0 = performance.now(), dur = ms / speed();
    (function f() { if (tk.off) return rej(CANCEL); performance.now() - t0 >= dur ? res() : nextFrame(f); })();
  });
  p.catch(() => {});
  return p;
}
function cancel() {
  PL.tk.off = true;
  PL.tk = { off: false };
  setPlaying(false);
  if (PL.M) { PL.M.layers.dots.replaceChildren(); PL.M.layers.chips.replaceChildren(); }
}
function setPlaying(on) {
  PL.playing = on;
  const b = $("play");
  if (b) { b.textContent = on ? ui("pause") : ui("play"); b.setAttribute("aria-pressed", String(on)); }
}

function pulse(id) {
  const N = PL.M && PL.M.nodes[id];
  if (!N || reduced()) return;
  N.g.classList.remove("pulse");
  void N.g.getBBox();
  N.g.classList.add("pulse");
}

async function flyPath(d, kind, tag) {
  const M = PL.M;
  const guide = sv("path", { d, class: "guide" }, M.layers.dots);
  const len = guide.getTotalLength();
  const dot = sv("circle", { class: "dot " + kind, r: 6.5 }, M.layers.dots);
  const lab = tag ? sv("text", { class: "atag " + kind, "text-anchor": "middle" }, M.layers.dots, truncate(tag, 28)) : null;
  const at = t => { const pt = guide.getPointAtLength(len * t); dot.setAttribute("cx", pt.x); dot.setAttribute("cy", pt.y); if (lab) { lab.setAttribute("x", pt.x); lab.setAttribute("y", pt.y - 12); lab.setAttribute("opacity", t < TAG_FADE_FROM ? 1 : (1 - t) / (1 - TAG_FADE_FROM)); } };
  at(0);
  try { await tween(Math.max(360, len * 2.4), at); } finally { guide.remove(); dot.remove(); if (lab) lab.remove(); }
}
async function fly(from, to, kind, tag) {
  const L = PL.M.L;
  if (!from || !to || from === to || !L.pos[from] || !L.pos[to]) return;
  await flyPath(edgePath(L.pos[from], L.pos[to], L), kind, tag);
  pulse(to);
}
async function flyChip(from, to, text) {
  const c = chipAt(PL.M.layers.chips, from[0], from[1], text, "flying");
  try {
    await tween(560, e => c.setAttribute("transform", `translate(${from[0] + (to[0] - from[0]) * e},${from[1] + (to[1] - from[1]) * e})`));
  } finally { c.remove(); }
}
const centerOf = id => { const p = PL.M.L.pos[id]; return [p.x + p.w / 2 - 27, p.y + p.h / 2 - 11]; };

function liveInfo(out, extra) {
  return Object.assign({ active: out.active, hazards: out.hazards, skipped: out.skipped, failures: out.failures, inferred: PL.inferred }, extra || {});
}

async function animateAction(a, state, out, actor, prev) {
  const M = PL.M, L = M.L, [name, x, y, z] = a;
  const apply = () => applyAction(state, out, a, P.numbers);
  const draw = extra => renderMap(M, state, liveInfo(out, Object.assign({ prev }, extra)));
  switch (name) {
    case "send": case "reply":
      await fly(x, y, name === "send" ? "req" : "res", z != null ? tx(z) : "");
      apply(); draw(); return;
    case "enqueue": {
      const idx = state.queues[x].length;
      apply(); draw({ pending: { queue: x, index: idx } });
      const p = L.pos[x], to = idx < VIS ? qPos(p, idx) : [p.x + p.w - 66, p.y + 34];
      await flyChip(actor && L.pos[actor] ? centerOf(actor) : to, to, y);
      draw(); return;
    }
    case "pickup": {
      const job = state.queues[x][0], k = state.workers[y].indexOf(null);
      const from = qPos(L.pos[x], 0);
      apply(); draw({ pending: { worker: y, slot: k } });
      if (k >= 0 && job != null) {
        const [sx, sy] = slotPos(L.pos[y], k);
        await flyChip(from, [sx + G.slot / 2 - 27, sy + G.slot / 2 - 11], job);
      }
      draw(); pulse(y); return;
    }
    case "free": apply(); draw(); pulse(x); await hold(220); return;
    case "cache.get": {
      const hit = own(state.caches[x], y);
      await fly(actor, x, "req", ui("arrow.get", { key: y, r: "?" }).replace(/ → \?$/, ""));
      apply(); draw({ hit: out.hit, hitCache: x });
      await fly(x, actor, "res", hit ? ui("hit") : ui("miss"));
      return;
    }
    case "cache.set": case "cache.set-if-fresh": {
      const v = isRef(z) ? (get(state.vars, z.slice(1)) || {}).v : z;
      await fly(actor, x, "req", name === "cache.set" ? ui("arrow.set", { key: y, v: valueText(v) }) : ui("arrow.fresh", { key: y }));
      apply(); draw(); pulse(x); return;
    }
    case "cache.del": await fly(actor, x, "req", ui("arrow.del", { key: y })); apply(); draw(); pulse(x); return;
    case "cache.expire": {
      const keys = Object.keys(state.caches[x]), i = keys.indexOf(y), p = L.pos[x];
      if (i >= 0) {
        const bar = sv("rect", { class: "ttl", x: p.x + 8, y: rowY(p, i) + G.rowH - 7, width: p.w - 16, height: 3 }, M.layers.chips);
        try { await tween(900, e => bar.setAttribute("width", (p.w - 16) * (1 - e))); } finally { bar.remove(); }
      }
      apply(); draw(); return;
    }
    case "mark-stale": apply(); draw(); pulse(x); return;
    case "db.read": {
      const v = get(state.stores[x], y);
      await fly(actor, x, "req", ui("arrow.read", { key: y, v: "?" }).replace(/ → \?$/, ""));
      apply(); draw(); await fly(x, actor, "res", valueText(v)); return;
    }
    case "db.write": {
      const v = isRef(z) ? (get(state.vars, z.slice(1)) || {}).v : z;
      await fly(actor, x, "req", ui("arrow.write", { key: y, v: valueText(v) }));
      apply(); draw(); pulse(x); return;
    }
    case "wait": {
      const from = state.clock_ms; apply(); const to = state.clock_ms;
      await tween(900, e => renderStats(state, { clock: from + (to - from) * e }));
      draw(); return;
    }
    case "counter": {
      const from = get(state.counters, x) || 0; apply(); const to = state.counters[x];
      await tween(600, e => renderStats(state, { counter: [x, from + (to - from) * e] }));
      draw(); return;
    }
    case "fail": {
      apply(); draw();
      const N = M.nodes[x];
      if (N && !reduced()) { N.g.classList.remove("shake"); void N.g.getBBox(); N.g.classList.add("shake"); }
      await hold(300); return;
    }
    default: apply(); draw();
  }
}

async function animateStep(i) {
  const sid = PL.sid, sts = P.states[sid], st = sts[i], entry = P.entries[sid][i];
  const prev = i ? sts[i - 1] : P.init;
  PL.inferred = stepTag(entry.step) === "inferred";
  const state = clone(prev), out = newOut();
  let actor = P.actors[sid][i];
  PL.M.layers.overlay.replaceChildren();
  PL.M.layers.labels.replaceChildren();
  renderMap(PL.M, prev, { prev, inferred: PL.inferred });
  if (!reduced()) {
    for (const a of entry.step.do) {
      await animateAction(a, state, out, actor, prev);
      renderStats(state);
      actor = nextActor(a, actor);
    }
  }
  showFinal(i);
}

function finalInfo(sid, i) {
  const sts = P.states[sid], st = sts[i], step = P.entries[sid][i].step;
  return { active: st.active, inferred: stepTag(step) === "inferred", hit: st.hit, hitCache: lastGetCache(step), hazards: st.hazards, skipped: st.skipped, failures: st.failures, prev: i ? sts[i - 1] : P.init };
}
function showFinal(i) {
  const sid = PL.sid, sts = P.states[sid], st = sts[i];
  renderMap(PL.M, st, finalInfo(sid, i));
  drawArrows(PL.M, stepArrows(i ? sts[i - 1] : P.init, P.entries[sid][i], P.actors[sid][i]));
  renderStats(st);
}

function checkFor(sid, i) { return (P.doc.checks || []).find(c => c.scenario === sid && c.step === i) || null; }
const checkKey = (sid, i) => sid + "." + i;

async function go(i, auto) {
  cancel();
  const sid = PL.sid, sts = P.states[sid];
  if (!Array.isArray(sts) || !sts.length) return;
  PL.i = clamp(i, 0, sts.length - 1);
  PL.wasAuto = auto;
  syncHash();
  const prev = PL.i ? sts[PL.i - 1] : P.init;
  renderMap(PL.M, prev, { prev });
  PL.M.layers.overlay.replaceChildren();
  PL.M.layers.labels.replaceChildren();
  renderStats(prev);
  showCaption(PL.i);
  if (pendingCheck()) return;
  setPlaying(auto);
  const my = PL.tk;
  try {
    for (;;) {
      await animateStep(PL.i);
      if (!PL.playing || my !== PL.tk) break;
      await hold(HOLD_MS);
      if (PL.i >= sts.length - 1) break;
      PL.i++;
      syncHash();
      showCaption(PL.i);
      if (pendingCheck()) return;
    }
  } catch (e) { if (e !== CANCEL) throw e; return; }
  setPlaying(false);
}
function pendingCheck() {
  const c = checkFor(PL.sid, PL.i);
  if (!c || PL.revealed.has(checkKey(PL.sid, PL.i))) return false;
  setPlaying(false);
  return true;
}
function reveal() {
  PL.revealed.add(checkKey(PL.sid, PL.i));
  go(PL.i, PL.wasAuto);
}

function showCaption(i) {
  const sid = PL.sid, sts = P.states[sid], st = sts[i], entry = P.entries[sid][i], step = entry.step;
  const prev = i ? sts[i - 1] : P.init, chk = checkFor(sid, i), revealed = PL.revealed.has(checkKey(sid, i));
  const cap = $("caption");
  const head = h("div", { class: "cap-head" },
    h("span", { class: "num" }, ui("stepOf", { i: pad2(i + 1), n: pad2(sts.length) })),
    h("h2", { id: "cap-title" }, tx(step.t)),
    step.time ? h("span", { class: "time" }, tx(step.time)) : null);
  const parts = [head];
  if (st.inherited) parts.push(h("p", { class: "inh" }, ui("inherited", { title: tx(P.scen[st.origin].title) })));
  if (step.d) parts.push(h("p", { class: "d" }, txNode(step.d)));
  parts.push(stepChips(step));
  if (chk && !revealed) {
    parts.push(h("div", { class: "check", role: "group", "aria-labelledby": "chk-q" },
      h("b", null, ui("predict")), h("p", { id: "chk-q" }, txNode(chk.q)),
      h("button", { type: "button", class: "btn primary", id: "reveal", onclick: reveal }, ui("reveal"))));
  } else {
    if (chk) parts.push(h("div", { class: "check done" }, h("b", null, ui("answer")), h("p", null, txNode(chk.answer))));
    parts.push(...banners(st));
    const ml = movesList(stepArrows(prev, entry, P.actors[sid][i]));
    if (ml) parts.push(ml);
    const ch = changes(prev, st);
    parts.push(h("p", { class: "after-line" }, h("span", { class: "after-k" }, ui("afterStep")), " ", ch.length ? ch.join(" · ") : ui("noChange")));
  }
  cap.replaceChildren(...parts);
  [...$("steps").querySelectorAll("button")].forEach((b, j) => {
    b.classList.toggle("cur", j === i);
    b.classList.toggle("done", j < i);
    if (j === i) b.setAttribute("aria-current", "step"); else b.removeAttribute("aria-current");
  });
}

function statColumns(sid) {
  const sts = P.states[sid], cols = [];
  if (!Array.isArray(sts)) return cols;
  if (sts.some(s => s.clock_ms > 0)) cols.push({ k: "clock" });
  const names = [];
  for (const s of sts) for (const n of Object.keys(s.counters)) if (!names.includes(n)) names.push(n);
  for (const n of names) cols.push({ k: "counter", name: n });
  if (Object.keys(P.init.queues).length && sts.some(s => Object.values(s.queues).some(q => q.length))) cols.push({ k: "waiting" });
  if (Object.keys(P.init.workers).length) cols.push({ k: "busy" });
  if (sts.some(s => Object.keys(s.vars).length)) cols.push({ k: "holds" });
  return cols;
}
function renderStats(state, live) {
  const box = $("stats");
  if (!box || !PL.cols) return;
  live = live || {};
  const cells = PL.cols.map(c => {
    let k, v;
    if (c.k === "clock") { k = ui("clock"); v = fmtClock(live.clock != null ? live.clock : state.clock_ms); }
    else if (c.k === "counter") { k = c.name.replace(/_/g, " "); v = fmtInt(live.counter && live.counter[0] === c.name ? live.counter[1] : get(state.counters, c.name) || 0); }
    else if (c.k === "waiting") { k = ui("waiting"); v = fmtInt(Object.values(state.queues).reduce((a, q) => a + q.length, 0)); }
    else if (c.k === "busy") { const all = Object.values(state.workers).flat(); k = ui("busy"); v = `${all.filter(j => j !== null).length} / ${all.length}`; }
    else { k = ui("holds"); v = Object.entries(state.vars).map(([n, x]) => `${n} = ${valueText(x.v)}`).join(", ") || "—"; }
    return h("div", { class: "stat" + (c.k === "holds" ? " wide" : "") }, h("span", null, k), h("b", null, v));
  });
  box.hidden = !cells.length;
  box.replaceChildren(...cells);
}

function syncHash() {
  try { history.replaceState(null, "", "#" + (PL.compare ? "compare" : PL.sid + "." + PL.i)); } catch (e) { /* fail-open: a file:// page may refuse history writes */ }
}

// Tabs: every scenario that is not reached through an issue's before/after toggle.
function tabScenarios() {
  const viaToggle = new Set();
  for (const s of P.doc.scenarios) for (const f of s.fixed_by || []) if (P.scen[f]) viaToggle.add(f);
  return P.order.filter(id => !viaToggle.has(id));
}
function issueOf(fixId) { return P.doc.scenarios.find(s => (s.fixed_by || []).includes(fixId)) || null; }

function renderHeavy(app) {
  const tabsIds = tabScenarios();
  const tabs = h("div", { class: "tabs", role: "tablist", "aria-label": ui("scenarios") });
  const mkTab = (id, text, kind) => h("button", { type: "button", role: "tab", id: "tab-" + id, "data-tab": id, "aria-selected": "false", "aria-controls": id === "compare" ? "compare-panel" : "stage", tabindex: "-1", onclick: () => selectTab(id) },
    kind ? h("span", { class: "kind" }, ui("kind." + kind)) : null, h("span", { class: "tt" }, text));
  for (const id of tabsIds) tabs.append(mkTab(id, tx(P.scen[id].title), P.scen[id].kind));
  if (Array.isArray(P.doc.compare) && P.doc.compare.length >= 2) tabs.append(mkTab("compare", ui("compareTab"), null));
  tabs.addEventListener("keydown", e => {
    const btns = [...tabs.querySelectorAll("[role=tab]")], at = btns.indexOf(document.activeElement);
    if (at < 0) return;
    let to = null;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") to = (at + 1) % btns.length;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") to = (at - 1 + btns.length) % btns.length;
    else if (e.key === "Home") to = 0; else if (e.key === "End") to = btns.length - 1;
    if (to === null) return;
    e.preventDefault(); btns[to].focus(); btns[to].click();
  });
  const controls = h("div", { class: "controls", id: "controls" },
    h("button", { type: "button", class: "btn", id: "prev", onclick: () => go(PL.i - 1, false) }, ui("back")),
    h("button", { type: "button", class: "btn primary", id: "play", "aria-pressed": "false", onclick: onPlay }, ui("play")),
    h("button", { type: "button", class: "btn", id: "next", onclick: onNext }, ui("next")),
    h("button", { type: "button", class: "btn", id: "replay", onclick: () => { PL.revealed.clear(); go(0, true); } }, ui("replay")),
    h("label", { class: "speed" }, h("span", null, ui("speed")),
      h("select", { id: "speed" }, ["0.5", "1", "2"].map(v => h("option", { value: v, selected: v === "1" }, v + "×")))));
  const bar = h("div", { class: "bar" }, tabs, controls);
  const fixbar = h("div", { class: "fixbar", id: "fixbar", hidden: true });
  const stage = h("section", { class: "stage", id: "stage", role: "tabpanel", "aria-labelledby": "cap-title" },
    h("div", { class: "caption", id: "caption", "aria-live": "polite" }),
    h("div", { class: "stats", id: "stats" }),
    h("figure", { class: "svgbox", id: "svgbox" }),
    mapLegend());
  const side = h("div", { class: "side" },
    h("nav", { class: "panel steps-panel", "aria-label": ui("steps") }, h("h2", null, ui("steps")), h("ol", { class: "steps", id: "steps" })));
  const main = h("div", { class: "main" + (P.wideMap ? " wide-map" : ""), id: "flow-main", tabindex: "-1" }, stage, side);
  const compare = h("section", { class: "panel compare", id: "compare-panel", role: "tabpanel", "aria-labelledby": "tab-compare", hidden: true });
  const below = h("div", { class: "below" });
  for (const x of [issuesPanel(id => selectTab(id)), decisionPanel(id => selectTab(id)), numbersPanel(), evidencePanel()]) if (x) below.append(x);
  app.replaceChildren(header(), howto(), bar, fixbar, main, compare, below, footer());
  PL.M = buildMap($("svgbox"), { narrow: innerWidth < NARROW_PX });
  document.addEventListener("keydown", onKey);
  const m = /^#([a-z][a-z0-9_-]*)(?:\.(\d+))?$/.exec(location.hash);
  if (m && m[1] === "compare" && $("tab-compare")) selectTab("compare");
  else if (m && P.scen[m[1]]) selectTab(m[1], m[2] != null ? +m[2] : 0, false);
  else selectTab(tabsIds[0] || P.order[0], 0, !reduced());
}

function onPlay() {
  if (PL.compare) return;
  if (pendingCheckShown()) { reveal(); return; }
  if (PL.playing) { cancel(); return; }
  const last = P.states[PL.sid].length - 1;
  go(PL.i >= last ? 0 : PL.i, true);
}
function onNext() {
  if (pendingCheckShown()) { reveal(); return; }
  go(PL.i + 1, false);
}
const pendingCheckShown = () => !!$("reveal");
function onKey(e) {
  if (e.altKey || e.ctrlKey || e.metaKey || PL.compare) return;
  const t = e.target, tag = t && t.tagName;
  if (tag === "SELECT" || tag === "INPUT" || tag === "TEXTAREA" || (t && t.getAttribute && t.getAttribute("role") === "tab")) return;
  if (e.key === "ArrowRight") { e.preventDefault(); onNext(); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); go(PL.i - 1, false); }
}

function selectTab(id, step, auto) {
  const isCompare = id === "compare";
  const tabId = isCompare ? "compare" : (issueOf(id) && !tabScenarios().includes(id) ? issueOf(id).id : id);
  document.querySelectorAll("[role=tab]").forEach(b => {
    const on = b.dataset.tab === tabId;
    b.setAttribute("aria-selected", String(on));
    b.tabIndex = on ? 0 : -1;
  });
  PL.compare = isCompare;
  $("flow-main").hidden = isCompare;
  $("controls").hidden = isCompare;
  $("compare-panel").hidden = !isCompare;
  if (isCompare) { cancel(); $("fixbar").hidden = true; buildCompare(); syncHash(); return; }
  stopCompare();
  setScenario(id);
  go(step || 0, auto === undefined ? !reduced() : auto);
}

function setScenario(sid) {
  PL.sid = sid;
  PL.cols = statColumns(sid);
  const sts = P.states[sid], ol = $("steps");
  ol.replaceChildren();
  renderFixbar(sid);
  const broken = !Array.isArray(sts);
  $("svgbox").hidden = broken;
  $("stats").hidden = broken;
  if (broken) {
    $("caption").replaceChildren(errorBox(ui("scenarioError"), sts && sts.error));
    return;
  }
  sts.forEach((st, i) => {
    const step = P.entries[sid][i].step, marks = [];
    if (st.hazards.length) marks.push(h("span", { class: "mk hz", title: "stale-writeback" }, "!"));
    if (st.failures.length) marks.push(h("span", { class: "mk fl" }, "×"));
    if ((st.skipped || []).length) marks.push(h("span", { class: "mk sk" }, "✓"));
    if (checkFor(sid, i)) marks.push(h("span", { class: "mk ck", title: ui("predict") }, "?"));
    ol.append(h("li", null, h("button", { type: "button", class: "step-btn" + (stepTag(step) === "inferred" ? " inferred" : "") + (st.inherited ? " inh" : ""), onclick: () => go(i, false) },
      h("span", { class: "n" }, pad2(i + 1)), h("span", { class: "t" }, tx(step.t)), marks)));
  });
}

function renderFixbar(sid) {
  const bar = $("fixbar"), s = P.scen[sid];
  const issue = s.kind === "fix" ? issueOf(sid) : s;
  const fixes = issue && issue.fixed_by ? issue.fixed_by.filter(f => P.scen[f]) : [];
  if (!issue || !fixes.length) { bar.hidden = true; bar.replaceChildren(); return; }
  const grp = h("div", { class: "seg", role: "group", "aria-label": ui("fixGroup") });
  const keep = () => PL.i;
  grp.append(h("button", { type: "button", "aria-pressed": String(sid === issue.id), onclick: () => { const i = keep(); setScenario(issue.id); go(i, false); } }, ui("before")));
  for (const f of fixes) {
    grp.append(h("button", { type: "button", "aria-pressed": String(sid === f), onclick: () => { const i = keep(); setScenario(f); go(i, false); } }, ui("after", { title: tx(P.scen[f].title) })));
  }
  bar.replaceChildren(grp);
  bar.hidden = false;
}

/* ============ compare: scenarios on one clock ============ */

const CMP = { t: 0, run: false, stop: null, last: 0, model: null };

function compareModel() {
  const ids = P.doc.compare.filter(id => Array.isArray(P.states[id]));
  const byTime = ids.some(id => P.states[id].some(s => s.clock_ms > 0));
  const lanes = ids.map(id => {
    const sts = P.states[id], segs = sts.map((st, k) => {
      const step = P.entries[id][k].step, t0 = byTime ? (k ? sts[k - 1].clock_ms : 0) : k, t1 = byTime ? st.clock_ms : k + 1;
      return { k, t0, t1, title: tx(step.t), est: stepTag(step) === "inferred" || waitTags(step).includes("estimated"), tag: waitTags(step)[0] || (byTime ? "" : "step"), st };
    });
    return { id, title: tx(P.scen[id].title), kind: P.scen[id].kind, segs, end: segs.length ? segs[segs.length - 1].t1 : 0 };
  });
  const tmax = Math.max(1, ...lanes.map(l => l.end));
  const counters = [];
  for (const l of lanes) for (const s of l.segs) for (const n of Object.keys(s.st.counters)) if (!counters.includes(n)) counters.push(n);
  return { lanes, tmax, byTime, counters };
}
function waitTags(step) {
  return step.do.filter(a => a[0] === "wait").map(a => { const m = ONE_PLACEHOLDER.exec(a[1]); const n = m && get(P.numbers, m[1]); return n ? n.tag : ""; });
}
const fmtT = t => (t <= 0 ? "0" : CMP.model.byTime ? fmtClock(t) : ui("stepUnit", { n: Math.round(t) }));

// Clock ticks land on round times (5 s, 1 min, 5 min…); a step axis on round counts.
const TIME_TICKS_MS = [100, 250, 500, 1e3, 2e3, 5e3, 1e4, 15e3, 3e4, 6e4, 12e4, 3e5, 6e5, 9e5, 18e5, 36e5, 72e5, 216e5, 432e5];
function niceStep(tmax, target, byTime) {
  const want = tmax / target;
  if (byTime) return TIME_TICKS_MS.find(t => t >= want) || TIME_TICKS_MS[TIME_TICKS_MS.length - 1];
  return Math.max(1, Math.ceil(want));
}

function buildCompare() {
  const box = $("compare-panel");
  CMP.model = compareModel();
  const md = CMP.model, narrow = innerWidth < NARROW_PX;
  const W = narrow ? 360 : 1100, X0 = narrow ? 12 : 340, X1 = narrow ? 300 : 960, ROW = narrow ? 40 : 26;
  const sc = (X1 - X0) / md.tmax;
  const svg = sv("svg", { viewBox: `0 0 ${W} 100`, class: "race", role: "img", "aria-label": ui("compareTitle") });
  let y = 16;
  const bars = [];
  const grid = sv("g", null, svg);
  for (const lane of md.lanes) {
    sv("text", { class: "rgrp", x: 12, y: y + 14 }, svg, truncate(lane.title, narrow ? 46 : 60));
    y += 24;
    const rows = md.byTime ? lane.segs.filter(s => s.t1 > s.t0) : lane.segs;
    for (const s of rows) {
      if (narrow) { sv("text", { class: "rlab", x: X0, y: y + 11 }, svg, truncate(s.title, 52)); y += 15; }
      else sv("text", { class: "rlab", x: 12, y: y + 13 }, svg, truncate(s.title, 46));
      sv("rect", { class: "rtrack", x: X0 + s.t0 * sc, y, width: Math.max(2, (s.t1 - s.t0) * sc), height: 16, rx: 3 }, svg);
      const bar = sv("rect", { class: `rbar l${md.lanes.indexOf(lane) % 4}` + (s.est ? " est" : "") + (s.st.hazards.length || s.st.failures.length ? " bad" : ""), x: X0 + s.t0 * sc, y, width: 0, height: 16, rx: 3 }, svg);
      sv("title", null, bar, `${s.title}: ${fmtT(s.t0)} → ${fmtT(s.t1)}`);
      if (s.tag && !narrow) sv("text", { class: "rtag t-" + s.tag, x: X0 + s.t1 * sc + 6, y: y + 12 }, svg, s.tag === "step" ? "" : ui("tag." + s.tag));
      bars.push({ bar, a: s.t0, b: s.t1 });
      y += ROW - (narrow ? 15 : 0) + (narrow ? 12 : 0);
    }
    const markX = X0 + lane.end * sc;
    sv("path", { class: "rmark", d: `M${markX} ${y} l5 7 l-5 7 l-5 -7 z` }, svg);
    const right = !narrow || markX < W / 2;
    sv("text", { class: "rmile", x: right && narrow ? markX + 9 : markX - 9, y: y + 11, "text-anchor": right && narrow ? "start" : "end" }, svg, ui("doneAt", { t: fmtT(lane.end) }));
    for (const s of lane.segs) {
      if (!(s.st.hazards.length || s.st.failures.length)) continue;
      const x = X0 + s.t1 * sc;
      sv("circle", { class: "rbad", cx: x, cy: y + 7, r: 5 }, svg);
    }
    y += 30;
  }
  const step = niceStep(md.tmax, narrow ? 3 : 6, md.byTime);
  for (let t = 0; t <= md.tmax + 1e-9; t += step) {
    const x = X0 + t * sc;
    sv("line", { class: "rgrid", x1: x, y1: 8, x2: x, y2: y - 10 }, grid);
    sv("text", { class: "rtick", x, y: y + 4, "text-anchor": "middle" }, svg, fmtT(t));
  }
  const head = sv("line", { class: "rhead", x1: X0, y1: 8, x2: X0, y2: y - 10 }, svg);
  svg.setAttribute("viewBox", `0 0 ${W} ${y + 14}`);
  CMP.bars = bars; CMP.head = head; CMP.X0 = X0; CMP.sc = sc;
  const cards = h("div", { class: "rcards" }, md.lanes.map((l, i) => h("div", { class: "rcard l" + (i % 4) },
    h("h3", null, l.title),
    h("div", { class: "rvals" },
      md.counters.map(n => h("div", null, h("span", null, n.replace(/_/g, " ")), h("b", { "data-c": l.id + "|" + n }, "0"))),
      h("div", null, h("span", null, ui("hazards")), h("b", { "data-h": l.id }, "0")),
      h("div", null, h("span", null, ui("failures")), h("b", { "data-f": l.id }, "0"))))));
  const table = h("div", { class: "tbl" }, h("table", null,
    h("thead", null, h("tr", null, h("th", null, ""), md.lanes.map(l => h("th", null, l.title)))),
    h("tbody", null,
      h("tr", null, h("td", null, ui("totalTime")), md.lanes.map(l => h("td", { class: "n" }, fmtT(l.end)))),
      md.counters.map(n => h("tr", null, h("td", null, n.replace(/_/g, " ")), md.lanes.map(l => {
        const last = l.segs[l.segs.length - 1];
        return h("td", { class: "n" }, fmtInt(last ? get(last.st.counters, n) || 0 : 0));
      }))),
      h("tr", null, h("td", null, ui("hazards")), md.lanes.map(l => h("td", { class: "n" }, fmtInt(l.segs.reduce((a, s) => a + s.st.hazards.length, 0))))),
      h("tr", null, h("td", null, ui("failures")), md.lanes.map(l => h("td", { class: "n" }, fmtInt(l.segs.reduce((a, s) => a + s.st.failures.length, 0))))))));
  box.replaceChildren(
    h("div", { class: "race-head" },
      h("div", null, h("h2", null, ui("compareTitle")), h("p", { class: "muted" }, ui("compareLede"), md.byTime ? "" : " " + ui("timeAxisSteps"))),
      h("div", { class: "controls" },
        h("button", { type: "button", class: "btn primary", id: "r-play", onclick: () => (CMP.run ? stopCompare() : playCompare()) }, ui("play")),
        h("button", { type: "button", class: "btn", onclick: () => { stopCompare(); CMP.t = 0; renderCompare(); playCompare(); } }, ui("replay")))),
    h("div", { class: "clock", id: "r-clock", "aria-live": "off" }),
    h("figure", { class: "svgbox" }, svg), cards, table);
  stopCompare();
  CMP.t = reduced() ? md.tmax : 0;
  renderCompare();
  if (!reduced()) playCompare();
}

function counterAt(lane, name, t) {
  let v = 0;
  for (const s of lane.segs) {
    const before = s.k ? get(lane.segs[s.k - 1].st.counters, name) || 0 : 0, after = get(s.st.counters, name) || 0;
    if (t >= s.t1) { v = after; continue; }
    if (t > s.t0 && s.t1 > s.t0) v = before + (after - before) * (t - s.t0) / (s.t1 - s.t0);
    break;
  }
  return v;
}
function renderCompare() {
  const md = CMP.model, t = CMP.t;
  for (const r of CMP.bars) r.bar.setAttribute("width", Math.max(0, Math.min(t, r.b) - r.a) * CMP.sc);
  const x = CMP.X0 + t * CMP.sc;
  CMP.head.setAttribute("x1", x); CMP.head.setAttribute("x2", x);
  $("r-clock").textContent = fmtT(t);
  for (const l of md.lanes) {
    for (const n of md.counters) { const b = document.querySelector(`[data-c="${l.id}|${n}"]`); if (b) b.textContent = fmtInt(counterAt(l, n, t)); }
    const done = l.segs.filter(s => s.t1 <= t + 1e-9);
    const hb = document.querySelector(`[data-h="${l.id}"]`), fb = document.querySelector(`[data-f="${l.id}"]`);
    if (hb) hb.textContent = fmtInt(done.reduce((a, s) => a + s.st.hazards.length, 0));
    if (fb) fb.textContent = fmtInt(done.reduce((a, s) => a + s.st.failures.length, 0));
  }
}
function tickCompare(now) {
  if (!CMP.run) return;
  const dt = now - CMP.last; CMP.last = now;
  CMP.t = Math.min(CMP.model.tmax, CMP.t + (dt / COMPARE_RUN_MS) * CMP.model.tmax * speed());
  renderCompare();
  if (CMP.t >= CMP.model.tmax) { stopCompare(); return; }
  CMP.stop = nextFrame(tickCompare);
}
function playCompare() {
  if (CMP.t >= CMP.model.tmax) CMP.t = 0;
  CMP.run = true; CMP.last = performance.now();
  const b = $("r-play"); if (b) b.textContent = ui("pause");
  CMP.stop = nextFrame(tickCompare);
}
function stopCompare() {
  CMP.run = false; if (CMP.stop) CMP.stop();
  const b = $("r-play"); if (b) b.textContent = ui("play");
}

/* ============ theme, language, boot ============ */

function readPref(k) { try { return localStorage.getItem(STORE_KEYS[k]); } catch (e) { return null; } } // fail-open: storage may be blocked
function writePref(k, v) { try { localStorage.setItem(STORE_KEYS[k], v); } catch (e) { /* fail-open: storage may be blocked */ } }
function applyTheme() {
  const root = document.documentElement;
  if (P.theme === "auto") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", P.theme);
  const b = $("theme-btn"); if (b) b.textContent = ui("theme", { mode: ui("theme" + cap(P.theme)) });
}
function cycleTheme() {
  const order = ["auto", "light", "dark"];
  P.theme = order[(order.indexOf(P.theme) + 1) % order.length];
  writePref("theme", P.theme);
  applyTheme();
}
function setLang(l) {
  if (l === P.lang) return;
  P.lang = l;
  writePref("lang", l);
  rerender();
}
function rerender() {
  const app = $("flow-app"), keep = { sid: PL.sid, i: PL.i, compare: PL.compare };
  cancel(); stopCompare();
  document.documentElement.lang = P.lang;
  P.need = measureNeeds();
  P.wideMap = layoutWide(P.need).W > WIDE_MAP_W;
  document.removeEventListener("keydown", onKey);
  if (P.tier === "heavy") {
    renderHeavy(app);
    if (keep.compare) selectTab("compare"); else if (keep.sid) selectTab(keep.sid, keep.i, false);
  } else renderLight(app);
}

function makeContext(data) {
  const doc = data.scenario;
  if (!doc || !Array.isArray(doc.scenarios) || !Array.isArray(doc.nodes) || !doc.nodes.length) throw new Error(ui("noScenario"));
  P = { doc, tier: data.tier === "heavy" ? "heavy" : "light", numbers: doc.numbers || {}, lang: "en", theme: "auto",
        nodeById: {}, scen: scenarioIndex(doc), order: doc.scenarios.map(s => s.id), states: {}, entries: {}, actors: {}, pendingCards: [] };
  for (const n of doc.nodes) put(P.nodeById, n.id, n);
  P.hasJa = P.tier === "heavy" && hasJa(doc);
  const lang = readPref("lang");
  if (P.hasJa && lang === "ja") P.lang = "ja";
  P.theme = ["light", "dark"].includes(readPref("theme")) ? readPref("theme") : "auto";
  P.init = Object.assign(initialState(doc), { step: -1, active: [], messages: [], hit: null, failures: [], notes: [], hazards: [], skipped: [] });
  for (const sid of P.order) {
    try {
      P.entries[sid] = effectiveSteps(sid, P.scen);
      P.states[sid] = reduceScenario(doc, sid);
      P.actors[sid] = actorsFor(P.entries[sid]);
    } catch (e) {
      P.states[sid] = { error: e.message };
    }
  }
  const mq = matchMedia("(prefers-reduced-motion: reduce)");
  P.reducedMotion = mq.matches;
  mq.addEventListener("change", e => { P.reducedMotion = e.matches; });
  P.need = measureNeeds();
  P.wideMap = layoutWide(P.need).W > WIDE_MAP_W;
  return P;
}

function boot() {
  const root = document.documentElement, app = $("flow-app");
  try {
    makeContext(JSON.parse($("flow-data").textContent));
    root.lang = P.lang;
    applyTheme();
    (P.tier === "heavy" ? renderHeavy : renderLight)(app);
    app.removeAttribute("aria-busy");
    const broken = P.order.filter(id => !Array.isArray(P.states[id]));
    root.setAttribute("data-flow-steps", P.order.map(id => id + ":" + (Array.isArray(P.states[id]) ? P.states[id].length : "error")).join(","));
    if (broken.length) root.setAttribute("data-flow-error", broken.map(id => id + ": " + P.states[id].error).join("; "));
    else root.setAttribute("data-flow-ok", "true");
    let narrow = innerWidth < NARROW_PX;
    addEventListener("resize", () => { const now = innerWidth < NARROW_PX; if (now !== narrow) { narrow = now; rerender(); } });
  } catch (e) {
    root.setAttribute("data-flow-error", String((e && e.message) || e));
    app.removeAttribute("aria-busy");
    app.replaceChildren(errorBox(P ? ui("fatal") : UI.en.fatal, String((e && e.message) || e)));
  }
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();

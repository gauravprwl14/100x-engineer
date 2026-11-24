#!/usr/bin/env node
// Benchmark: does the explain page's first picture get better or worse? Builds each case with the
// engine in this checkout, opens it in headless Chrome with tests/flow/picture-probe.js, and prints
// what the reader sees with no click: boxes, groups, labelled links, links tied to a numbered
// journey, links through a box they do not connect, boxes overlapping, and the smallest text.
// Offline and deterministic: no model is called. Chrome is optional; without it the script exits 0
// with SKIP.
//
//   node tests/flow/bench-picture.mjs --cases <cases.json> [--width 1280] [--out DIR] [--json] [--shots]
//
// cases.json: [{"name": "...", "scenario": "path.json", "overlay": "adds-a-system-block.json", "repo": "clone", "tier": "heavy"}]
// A path is relative to the cases file; `overlay` merges its keys over the scenario (the "after" arm). Run it on two checkouts (or two scenario files) and compare
// the tables; `--shots` writes a PNG per case beside the page so you can look at the picture too.
import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync, existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..", "..");
const CHROME = process.env.FLOW_CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const NO_NET = "--host-resolver-rules=MAP * ~NOTFOUND";
const VIRTUAL_TIME_MS = 5000;

const args = process.argv.slice(2);
const opt = (name, dflt) => { const i = args.indexOf("--" + name); return i < 0 ? dflt : (args[i + 1] ?? true); };
const casesFile = opt("cases", null);
const width = Number(opt("width", 1280));
const asJson = args.includes("--json");
const shots = args.includes("--shots");
const engine = opt("engine", join(ROOT, "scripts", "flow.py"));
if (!casesFile) { console.error("bench-picture: --cases <cases.json> is required"); process.exit(2); }
if (!existsSync(CHROME)) { console.log("SKIP bench-picture: Google Chrome not found (set FLOW_CHROME)"); process.exit(0); }

const out = opt("out", mkdtempSync(join(tmpdir(), "bench-picture-")));
mkdirSync(out, { recursive: true });
const cases = JSON.parse(readFileSync(casesFile, "utf8"));
const base = dirname(resolve(casesFile));
const probeJs = readFileSync(join(HERE, "picture-probe.js"), "utf8");

function measure(c) {
  const dir = join(out, c.name.replace(/[^A-Za-z0-9_.-]+/g, "_"));
  let scenario = resolve(base, c.scenario);
  if (c.overlay) { // the same subject, plus the `system` block from the overlay: the "after" arm of a pair
    mkdirSync(dir, { recursive: true });
    const merged = JSON.parse(readFileSync(scenario, "utf8"));
    Object.assign(merged, JSON.parse(readFileSync(resolve(base, c.overlay), "utf8")));
    scenario = join(dir, "scenario.json");
    writeFileSync(scenario, JSON.stringify(merged));
  }
  const argv = [engine, "build", scenario, "--tier", c.tier || "heavy", "--out", dir];
  if (c.repo) argv.push("--repo", resolve(base, c.repo));
  const b = spawnSync("python3", argv, { encoding: "utf8" });
  if (b.status !== 0) return { name: c.name, error: "build refused: " + (b.stderr || b.stdout).trim().split("\n").slice(-3).join(" | ") };
  const page = readFileSync(join(dir, "index.html"), "utf8");
  const probed = join(dir, "index.probe.html");
  writeFileSync(probed, page.replace("</body>", "<script>" + probeJs + "</script></body>"));
  const r = spawnSync(CHROME, [NO_NET, "--headless=new", "--disable-gpu", "--no-first-run", `--window-size=${width},900`,
    `--virtual-time-budget=${VIRTUAL_TIME_MS}`, "--dump-dom", "file://" + probed], { encoding: "utf8", maxBuffer: 64 << 20 });
  const m = /data-picture="([^"]*)"/.exec(r.stdout || "");
  if (!m) return { name: c.name, error: "the probe left no result" };
  const decoded = m[1].replace(/&quot;/g, '"').replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&#39;/g, "'");
  const res = { name: c.name, htmlKB: Math.round(Buffer.byteLength(page) / 1024), ...JSON.parse(decoded) };
  if (shots) {
    const png = join(dir, "page.png");
    spawnSync(CHROME, [NO_NET, "--headless=new", "--disable-gpu", "--no-first-run", `--window-size=${width},2200`,
      `--virtual-time-budget=${VIRTUAL_TIME_MS}`, `--screenshot=${png}`, "file://" + join(dir, "index.html")], { encoding: "utf8" });
    res.shot = png;
  }
  return res;
}

const rows = cases.map(measure);
if (asJson) { console.log(JSON.stringify(rows, null, 2)); process.exit(rows.some(r => r.error) ? 1 : 0); }

const cols = [["case", r => r.name], ["picture", r => r.picture], ["boxes", r => r.boxes], ["w/ subtitle", r => r.withSub],
  ["groups", r => r.groups], ["links", r => r.links], ["labelled", r => r.labelled], ["on journey", r => r.onJourney],
  ["through box", r => r.through], ["label clashes", r => r.tagOverlaps], ["overlaps", r => r.overlaps], ["outside parent", r => r.outsideParent],
  ["min font px", r => r.minFontPx], ["map scrolls", r => r.mapScrolls], ["words explaining", r => r.explainWords], ["words of code", r => r.codeWords],
  ["bare step #", r => r.stepRefs], ["why/steps", r => r.whyOfSteps], ["top px", r => r.topPx], ["page KB", r => r.htmlKB]];
const cell = (v) => v === null || v === undefined ? "-" : String(v);
const table = rows.filter(r => !r.error).map(r => cols.map(([, f]) => cell(f(r))));
const widths = cols.map(([h], i) => Math.max(h.length, ...table.map(t => t[i].length)));
const line = a => a.map((s, i) => s.padEnd(widths[i])).join("  ");
console.log(`window ${width}px, out ${out}`);
console.log(line(cols.map(([h]) => h)));
for (const t of table) console.log(line(t));
for (const r of rows.filter(r => r.error)) console.log(`ERROR ${r.name}: ${r.error}`);
if (shots) for (const r of rows.filter(r => r.shot)) console.log(`shot ${r.name}: ${r.shot}`);
process.exit(rows.some(r => r.error) ? 1 : 0);

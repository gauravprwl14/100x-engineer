// Injected by tests/test_flow.sh into a copy of a built page (never shipped): after boot, records
// on <html data-probe> whether the #<id> deep-link target is shown in the viewport, every map
// edge that passes through a box it does not connect, and in `problems` every page section that
// breaks its contract (before-you-watch, terms, outline highlight, code pane, labels, contents,
// folding sections, diagrams, reflow). The fold and diagram checks run after the first pass, in
// later timers, because opening a section and loading mermaid both settle asynchronously.
setTimeout(function () {
  var out = { ok: document.documentElement.getAttribute("data-flow-ok"), target: null, crossings: [], problems: [], facts: {} };
  var id = null;
  try { id = location.hash.length > 1 ? decodeURIComponent(location.hash.slice(1)) : null; } catch (e) { id = null; }
  var t = id && document.getElementById(id);
  if (t) {
    var r = t.getBoundingClientRect();
    out.target = { hidden: t.hidden || getComputedStyle(t).display === "none", top: Math.round(r.top), h: Math.round(r.height), vh: innerHeight };
  }
  document.querySelectorAll("svg.map").forEach(function (svg) {
    var boxes = Array.prototype.map.call(svg.querySelectorAll("g.node"), function (g) {
      var b = g.querySelector("rect.box");
      return { id: g.getAttribute("data-node"), x: +b.getAttribute("x"), y: +b.getAttribute("y"), w: +b.getAttribute("width"), h: +b.getAttribute("height") };
    });
    svg.querySelectorAll("path.edge").forEach(function (p) {
      var ends = (p.getAttribute("data-edge") || "|").split("|"), len = p.getTotalLength();
      for (var i = 1; i < 80; i++) {
        var q = p.getPointAtLength(len * i / 80);
        boxes.forEach(function (b) {
          if (ends.indexOf(b.id) >= 0) return;
          var hit = q.x > b.x + 1 && q.x < b.x + b.w - 1 && q.y > b.y + 1 && q.y < b.y + b.h - 1;
          var k = ends.join("|") + " through " + b.id;
          if (hit && out.crossings.indexOf(k) < 0) out.crossings.push(k);
        });
      }
    });
  });

  var problem = function (s) { out.problems.push(s); };
  var shown = function (el) { return !!el && !el.hidden && !el.closest("[hidden]") && getComputedStyle(el).display !== "none"; };
  var payload = {};
  try { payload = JSON.parse(document.getElementById("flow-data").textContent); } catch (e) { problem("flow-data is not JSON"); }
  var doc = payload.scenario || {}, heavy = payload.tier === "heavy";
  var snippets = payload.snippets && typeof payload.snippets === "object" ? payload.snippets : {};

  // Before you watch: present whenever the scenario has a context or terms.
  out.facts.before = !!document.querySelector(".before");
  if ((doc.context || (doc.terms || []).length) && !out.facts.before) problem("context or terms given but no Before you watch section");

  // Terms: each wrapped term is a button described by a definition that exists; focus shows the
  // popup, Escape hides it, a tap pins it and a second tap closes it.
  var terms = document.querySelectorAll(".term");
  out.facts.terms = terms.length;
  Array.prototype.forEach.call(terms, function (b) {
    var d = b.getAttribute("aria-describedby");
    if (b.tagName !== "BUTTON" || b.tabIndex < 0) problem("term '" + b.textContent + "' is not focusable");
    if (!d || !document.getElementById(d)) problem("term '" + b.textContent + "' has no definition to describe it");
  });
  var first = Array.prototype.find.call(terms, shown);
  if (first) {
    var tip = function () { return document.getElementById("term-tip"); };
    first.focus();
    var onFocus = shown(tip());
    first.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    var afterEsc = shown(tip());
    first.blur();
    first.click();
    var onTap = shown(tip());
    first.click();
    var afterTap = shown(tip());
    out.facts.tip = { onFocus: onFocus, afterEsc: afterEsc, onTap: onTap, afterSecondTap: afterTap };
    if (!onFocus) problem("focusing a term does not show its meaning");
    if (afterEsc) problem("Escape does not close the term popup");
    if (!onTap || afterTap) problem("tapping a term does not toggle its meaning");
  }

  // Outline: on a heavy page opened at #<scenario>.<step>, every line linked to that step is lit.
  var cur = Array.prototype.map.call(document.querySelectorAll(".ol-line.cur"), function (b) { return b.getAttribute("data-ol"); });
  out.facts.outlineCur = cur;
  var m = heavy && id ? /^([a-z][a-z0-9_-]*)\.(\d+)$/.exec(id) : null;
  if (m) {
    (doc.outline || []).forEach(function (o, oi) {
      (o.lines || []).forEach(function (ln, li) {
        if (o.scenario === m[1] && (ln.steps || []).indexOf(+m[2]) >= 0 && cur.indexOf(oi + "." + li) < 0) problem("outline line " + oi + "." + li + " not highlighted at step " + m[2]);
      });
    });
  }

  // Code: without snippets there is no Real code tab and no real-code block; on a heavy page the
  // pane sits right of the diagram at >= 1100px and below it otherwise.
  var realTab = document.getElementById("code-real");
  out.facts.realTab = realTab ? (shown(realTab) ? "shown" : "hidden") : "absent";
  out.facts.snippets = document.querySelectorAll(".snip").length;
  if (!Object.keys(snippets).length && (out.facts.realTab === "shown" || out.facts.snippets)) problem("Real code shown with no snippets in the payload");
  var pane = document.getElementById("codepane"), map = document.getElementById("svgbox");
  if (shown(pane) && shown(map)) {
    var pr = pane.getBoundingClientRect(), mr = map.getBoundingClientRect();
    out.facts.codePane = innerWidth >= 1100 ? "right" : "below";
    if (innerWidth >= 1100 ? pr.left < mr.right - 1 : pr.top < mr.bottom - 1) problem("code pane is not " + out.facts.codePane + " of the diagram at " + innerWidth + "px");
  }

  if (/Held in memory/i.test((document.getElementById("flow-app") || document.body).innerText)) problem("old label 'Held in memory' still shown");

  // Contents: a row per folding section, in page order; Evidence starts folded, the rest open.
  var folds = Array.prototype.slice.call(document.querySelectorAll("details.fold[data-sec]"));
  var rows = Array.prototype.map.call(document.querySelectorAll("nav.contents .toc a"), function (a) { return a.getAttribute("href"); });
  var want = folds.map(function (d) { return "#" + d.id; });
  out.facts.contents = rows;
  if (!document.querySelector("nav.contents")) problem("no Contents card");
  if (rows.join() !== want.join()) problem("Contents rows " + rows.join() + " do not match the sections " + want.join());
  folds.forEach(function (d) {
    if (!d.firstElementChild || d.firstElementChild.tagName !== "SUMMARY") problem("section " + d.id + " has no summary heading");
    if (d.open !== (d.dataset.sec !== "evidence")) problem("section " + d.id + " starts " + (d.open ? "open" : "folded"));
  });
  var nDg = (doc.diagrams || []).length;
  if (!nDg && (document.getElementById("mermaid-js") || document.getElementById("sec-diagrams"))) problem("mermaid or a Diagrams section on a page with no diagrams");

  var wait = function (ms, fn) { setTimeout(fn, ms); };
  var settled = function () { return Array.prototype.every.call(document.querySelectorAll(".dg-box"), function (b) { return b.dataset.state === "ready" || b.dataset.state === "fallback"; }); };
  var poll = function (left, fn) { if (settled() || left <= 0) fn(); else wait(100, function () { poll(left - 100, fn); }); };
  var checkDiagram = function (k) {
    var box = document.querySelector(".dg-box"), d = (doc.diagrams || [])[k] || {};
    var st = box ? box.dataset.state : "absent", pre = box && box.querySelector(".dg-src");
    out.facts["diagram" + k] = st;
    if (st === "ready" ? !box.querySelector("svg") : st !== "fallback") problem("diagram " + k + " is " + st + ", neither drawn nor shown as source");
    if (!window.mermaid && st !== "fallback") problem("mermaid did not load but diagram " + k + " shows no fallback");
    if (st === "fallback" && (!pre || pre.textContent !== d.source || !box.querySelector(".dg-note"))) problem("diagram " + k + " fallback is not its source with a note");
  };

  // Diagrams: mermaid comes pinned from cdnjs with SRI; offline, each shows its source.
  poll(2500, function () {
    if (nDg) {
      var s = document.getElementById("mermaid-js");
      out.facts.mermaid = { loaded: !!window.mermaid, src: s && s.getAttribute("src") };
      if (!s || !/^https:\/\/cdnjs\.cloudflare\.com\/ajax\/libs\/mermaid\/11\.[0-9]+\.[0-9]+\//.test(s.getAttribute("src")) || !/^sha(384|512)-/.test(s.getAttribute("integrity") || "") || s.getAttribute("crossorigin") !== "anonymous") problem("mermaid script is not pinned cdnjs 11.x with integrity and crossorigin=anonymous");
      checkDiagram(0);
      var sw = document.querySelectorAll(".dg-switch button");
      if (nDg > 1 && sw.length !== nDg) problem(nDg + " diagrams but " + sw.length + " switcher buttons");
      if (nDg > 1) sw[1].click();
    }
    poll(2000, function () {
      if (nDg > 1) {
        checkDiagram(1);
        if (document.querySelector('.dg-switch button[aria-pressed="true"]') !== document.querySelectorAll(".dg-switch button")[1]) problem("diagram switcher does not press the shown diagram");
      }
      foldChecks();
    });
  });

  // Folding: Collapse all and Expand all reach every section; folding the walkthrough pauses it;
  // a Contents link and a #<scenario>.<step> deep link each open the section they point into.
  function foldChecks() {
    var play = document.getElementById("play"), collapse = document.getElementById("collapse-all"), expand = document.getElementById("expand-all");
    if (play && play.getAttribute("aria-pressed") !== "true") play.click();
    out.facts.playingBeforeFold = play ? play.getAttribute("aria-pressed") : null;
    if (collapse) collapse.click();
    wait(80, function () {
      if (folds.some(function (d) { return d.open; })) problem("Collapse all leaves a section open");
      if (play && play.getAttribute("aria-pressed") !== "false") problem("folding the walkthrough does not pause playback");
      var last = folds[folds.length - 1], link = last && document.querySelector('nav.contents a[href="#' + last.id + '"]');
      if (link) { link.click(); if (!last.open) problem("Contents link to " + last.id + " does not open it"); }
      if (collapse) collapse.click();
      var first = (doc.scenarios || [])[0], card = first ? first.id + ".0" : null;
      if (card) location.hash = "#" + card;
      wait(150, function () {
        var holder = heavy ? document.getElementById("sec-walk") : document.getElementById("sec-steps");
        var target = heavy ? document.getElementById("stage") : document.getElementById(card);
        out.facts.deepLinkOpens = !!(holder && holder.open);
        if (card && holder && !holder.open) problem("deep link #" + card + " does not open its folded section");
        if (card && target && !shown(target)) problem("deep link #" + card + " target is not shown");
        if (expand) expand.click();
        if (folds.some(function (d) { return !d.open; })) problem("Expand all leaves a section folded");
        wait(80, function () {
          out.facts.scrollW = document.documentElement.scrollWidth;
          out.facts.innerW = innerWidth;
          if (document.documentElement.scrollWidth > innerWidth + 1) problem("page scrolls sideways: " + document.documentElement.scrollWidth + "px wide at " + innerWidth + "px");
          document.documentElement.setAttribute("data-probe", JSON.stringify(out));
        });
      });
    });
  }
}, 1500);

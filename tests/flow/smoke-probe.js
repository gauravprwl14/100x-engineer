// Injected by tests/test_flow.sh into a copy of a built page (never shipped): after boot, records
// on <html data-probe> whether the #<id> deep-link target is shown in the viewport, every map
// edge that passes through a box it does not connect, and in `problems` every page section that
// breaks its contract (before-you-watch, terms, outline highlight, code pane, labels, reflow).
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
  out.facts.before = !!document.querySelector("section.before");
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
  out.facts.scrollW = document.documentElement.scrollWidth;
  out.facts.innerW = innerWidth;
  if (document.documentElement.scrollWidth > innerWidth + 1) problem("page scrolls sideways: " + document.documentElement.scrollWidth + "px wide at " + innerWidth + "px");
  document.documentElement.setAttribute("data-probe", JSON.stringify(out));
}, 1500);

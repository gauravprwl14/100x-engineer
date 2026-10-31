// Injected by tests/test_flow.sh into a copy of a built page (never shipped): after boot, records
// on <html data-probe> whether the #<id> deep-link target is shown in the viewport, every map
// edge that passes through a box it does not connect, and in `problems` every page section that
// breaks its contract (hero, legend, before-you-watch, terms, outline highlight, code pane, labels,
// contents and side nav, Show all toggles, folding sections, diagrams, reflow). The fold, diagram
// and side-nav checks run after the first pass, in later timers, because opening a section, loading
// mermaid and the scroll observer all settle asynchronously.
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

  // Hero: the purpose and at least one TL;DR card (one per tldr key when the data has tldr); each
  // At-a-glance tile links to a section that exists; Risks and Decision appear exactly when the
  // data has issues and a decision.
  var heroEl = document.querySelector("header.hero"), tl = doc.tldr || {};
  var cards = document.querySelectorAll(".hero .tldr > li");
  out.facts.hero = { cards: cards.length, tiles: Array.prototype.map.call(document.querySelectorAll(".hero .tile a.tile-a"), function (a) { return a.getAttribute("href"); }) };
  if (!heroEl || !heroEl.querySelector("h1")) problem("no hero with the title");
  var purposeEl = document.querySelector(".hero .purpose-lead");
  if (!purposeEl || !purposeEl.textContent.trim()) problem("hero has no purpose sentence");
  if (!cards.length) problem("hero has no TL;DR card");
  // tldr's "what" is the headline, so it is not also a card
  var tlKeys = ["how", "watch_out"].filter(function (k) { return tl[k]; }).length;
  var tlWhat = tl.what && (typeof tl.what === "string" ? tl.what : tl.what.en);
  // {{name}} placeholders render as numbers, so compare the text before the first one
  var tlLead = tlWhat ? tlWhat.split("{{")[0].trim() : "";
  if (tlLead && purposeEl && purposeEl.textContent.trim().indexOf(tlLead) !== 0) problem("tldr.what is not the hero headline");
  if (doc.tldr && cards.length !== tlKeys) problem("tldr has " + tlKeys + " text(s) but the hero shows " + cards.length + " card(s)");
  out.facts.hero.tiles.forEach(function (href) {
    var sec = document.getElementById(href.slice(1));
    if (!sec || sec.tagName !== "DETAILS") problem("At-a-glance tile " + href + " does not point to a section");
  });
  var hasIssues = (doc.scenarios || []).some(function (s) { return s.severity; });
  if (!!document.querySelector(".tile-risks") !== hasIssues) problem("Risks tile " + (hasIssues ? "missing" : "shown without issues"));
  if (!!document.querySelector(".tile-decision") !== !!doc.decision) problem("Decision tile " + (doc.decision ? "missing" : "shown without a decision"));

  // Legend: in Evidence (Numbers when there is no evidence), never above the sections; the
  // Confidence tile's button shows it in a popover that Escape closes, returning focus.
  var legendHost = document.getElementById(Object.keys(doc.evidence || {}).length ? "sec-evidence" : "sec-numbers");
  var legends = document.querySelectorAll(".howto:not(.pop-legend)");
  out.facts.legendIn = legends.length === 1 && legends[0].closest("details") ? legends[0].closest("details").id : null;
  if (legendHost && (legends.length !== 1 || !legendHost.contains(legends[0]))) problem("the evidence legend is not (only) in " + legendHost.id);
  var popButton = document.getElementById("conf-pop-btn"), pop = document.getElementById("conf-pop");
  if (popButton) {
    popButton.click();
    var popOpen = shown(pop) && popButton.getAttribute("aria-expanded") === "true" && pop.querySelectorAll(".how").length === 5;
    popButton.focus();
    popButton.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    out.facts.popover = { opens: popOpen, closesOnEscape: !shown(pop), focusBack: document.activeElement === popButton };
    if (!popOpen) problem("How sure is each claim? does not open the five-tag legend");
    if (shown(pop) || document.activeElement !== popButton) problem("Escape does not close the legend popover back onto its button");
  }

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
  // pane sits right of the diagram when the content column is >= 1100px and below it otherwise.
  var realTab = document.getElementById("code-real");
  out.facts.realTab = realTab ? (shown(realTab) ? "shown" : "hidden") : "absent";
  out.facts.snippets = document.querySelectorAll(".snip").length;
  if (!Object.keys(snippets).length && (out.facts.realTab === "shown" || out.facts.snippets)) problem("Real code shown with no snippets in the payload");
  var pane = document.getElementById("codepane"), map = document.getElementById("svgbox");
  if (shown(pane) && shown(map)) {
    var pr = pane.getBoundingClientRect(), mr = map.getBoundingClientRect();
    var col = (document.querySelector(".doc-main") || document.body).clientWidth;
    out.facts.codePane = col >= 1100 ? "right" : "below";
    if (col >= 1100 ? pr.left < mr.right - 1 : pr.top < mr.bottom - 1) problem("code pane is not " + out.facts.codePane + " of the diagram in a " + col + "px column");
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
        showAllChecks();
        wait(80, function () {
          out.facts.scrollW = document.documentElement.scrollWidth;
          out.facts.innerW = innerWidth;
          if (document.documentElement.scrollWidth > innerWidth + 1) problem("page scrolls sideways: " + document.documentElement.scrollWidth + "px wide at " + innerWidth + "px");
          sideNavChecks(function () { document.documentElement.setAttribute("data-probe", JSON.stringify(out)); });
        });
      });
    });
  }

  // Show all: each toggle hides rows to start, shows every row when pressed, and hides them again.
  function showAllChecks() {
    var btns = document.querySelectorAll(".show-all, .terms-toggle");
    out.facts.showAll = btns.length;
    Array.prototype.forEach.call(btns, function (b) {
      var holder = document.getElementById(b.getAttribute("aria-controls"));
      var hiddenRows = function () { return holder.hidden ? 1 : holder.querySelectorAll(":scope > [hidden]").length; };
      var before = hiddenRows();
      b.click();
      var open = hiddenRows(), pressed = b.getAttribute("aria-expanded");
      b.click();
      if (!before || open || pressed !== "true" || hiddenRows() !== before) problem("toggle '" + b.textContent + "' does not show all and hide again (" + before + "/" + open + "/" + hiddenRows() + ")");
    });
  }

  // Contents: from 1200px a sticky nav beside the sections that marks the section being read;
  // below that, a card above them.
  function sideNavChecks(done) {
    var nav = document.querySelector("nav.contents"), firstSec = folds[0];
    if (!nav || !firstSec) { done(); return; }
    var wide = innerWidth >= 1200, nr = nav.getBoundingClientRect(), fr = firstSec.getBoundingClientRect();
    out.facts.sideNav = wide ? getComputedStyle(nav).position : "top";
    if (wide && (getComputedStyle(nav).position !== "sticky" || nr.right > fr.left)) problem("Contents is not a sticky nav left of the sections at " + innerWidth + "px");
    if (!wide && nr.bottom > fr.top) problem("Contents is not above the sections at " + innerWidth + "px");
    var target = folds[Math.min(folds.length - 1, Math.floor(folds.length / 2))];
    window.scrollTo(0, target.getBoundingClientRect().top + scrollY - 10);
    window.dispatchEvent(new Event("scroll"));
    wait(100, function () {
      var cur = document.querySelector("nav.contents .toc a[aria-current]");
      out.facts.currentSection = cur ? cur.getAttribute("href") : null;
      if (!cur || cur.getAttribute("href") !== "#" + target.id) problem("scrolled to " + target.id + " but Contents marks " + (cur ? cur.getAttribute("href") : "nothing"));
      window.scrollTo(0, 0);
      done();
    });
  }
}, 1500);

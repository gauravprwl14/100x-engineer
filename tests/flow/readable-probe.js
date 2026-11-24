// Injected by tests/test_flow.sh into a copy of a built readable page (never shipped). After boot it
// drives the page the way a reader does and leaves the broken contracts as JSON on <html data-readable>:
// the article is what shows first, the code waits behind a switch, every journey step carries its
// sentence, the map fits its column and keeps readable text, and each way into the player opens it.
setTimeout(function () {
  var out = { problems: [], facts: {} };
  var P = function (s) { out.problems.push(s); };
  var shown = function (el) { return !!el && el.getClientRects().length > 0; };
  try {
    var read = document.getElementById("rd-panel"), watch = document.getElementById("watch-wrap");
    if (document.documentElement.getAttribute("data-flow-ok") !== "true") P("the page did not render (no data-flow-ok)");
    if (!read || !watch) { P("no read panel or no watch wrapper"); }
    else {
      if (!shown(read)) P("the article is hidden at load");
      if (shown(watch)) P("the animated player is showing at load");
      out.facts.readSteps = document.querySelectorAll(".rd-step").length;
      if (!out.facts.readSteps) P("the article holds no steps");
    }
    var codes = document.querySelectorAll(".ol-plain .ol-code"), tool = document.querySelector(".ol-tools button");
    out.facts.plainLines = document.querySelectorAll(".ol-plain .ol-says").length;
    if (codes.length) {
      if (shown(codes[0])) P("outline code is showing before anyone asked for it");
      if (!tool) P("no Show the code switch");
      else { tool.click(); if (!shown(codes[0])) P("Show the code did not show the code"); tool.click(); if (shown(codes[0])) P("Hide the code did not hide it"); }
    }
    var steps = document.querySelectorAll(".sys-journey > ol > li").length, whys = document.querySelectorAll(".sys-journey .sys-why").length;
    out.facts.journey = steps; out.facts.why = whys;
    if (steps && steps !== whys) P("journey: " + whys + " sentences for " + steps + " steps");
    var holder = document.querySelector(".sys-holder"), svg = document.querySelector("svg.sysmap");
    if (holder && svg) {
      if (holder.scrollWidth > holder.clientWidth + 1) P("the map scrolls sideways in a " + holder.clientWidth + "px column");
      var vb = svg.viewBox.baseVal, scale = svg.getBoundingClientRect().width / vb.width;
      out.facts.mapScale = Math.round(scale * 100) / 100;
      if (scale * 10.5 < 8.9) P("map text is " + Math.round(scale * 105) / 10 + "px at its smallest");
    }
    var btn = document.querySelector('.modebar [data-mode="watch"]'), back = document.querySelector('.modebar [data-mode="read"]');
    if (!btn || !back) P("no Read / Watch switch");
    else {
      btn.click();
      if (!shown(watch)) P("Watch did not show the player");
      if (shown(read)) P("the article is still showing in Watch");
      if (!shown(document.getElementById("stage"))) P("the stage is hidden in Watch");
      back.click();
      if (shown(watch)) P("Read did not hide the player");
      if (!shown(read)) P("Read did not show the article");
    }
    var go = document.querySelector(".ol-go");
    if (go) { go.click(); if (!shown(watch)) P("an outline link did not open the player"); if (back) back.click(); }
    var payload = {};
    try { payload = JSON.parse(document.getElementById("flow-data").textContent).scenario || {}; } catch (e) { P("flow-data is not JSON"); }
    var cardEls = document.querySelectorAll(".sys-card");
    out.facts.cards = cardEls.length;
    if (cardEls.length) {
      var marked = document.querySelector("svg.sysmap .has-card");
      if (!marked) P("no part on the map is marked as having a card");
      else {
        marked.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        var card = document.getElementById("card-" + (marked.dataset.part || marked.dataset.group));
        if (!card || !card.open) P("clicking a part on the map did not open its card");
      }
      var deeper = document.querySelector(".sys-card a.btn");
      if (!deeper || !/^\.\.\/[a-z0-9-]+\/index\.html$/.test(deeper.getAttribute("href"))) P("a card has no link to its own page");
    }
    if (payload.parent) {
      var crumb = document.querySelector(".crumb a");
      if (!crumb || crumb.getAttribute("href").indexOf("../" + payload.parent.page + "/index.html#card-") !== 0) P("the deeper page has no way back to its parent");
    }
    var watchBtn = document.querySelector(".sys-journey .btn");
    if (watchBtn) { watchBtn.click(); if (!shown(watch)) P("a journey Watch button did not open the player"); if (back) back.click(); }
  } catch (e) { P("probe threw: " + (e && e.message || e)); }
  document.documentElement.setAttribute("data-readable", JSON.stringify(out));
}, 2500);

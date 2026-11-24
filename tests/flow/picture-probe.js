// Injected by tests/flow/bench-picture.mjs into a copy of a built page (never shipped). After boot it
// measures the picture a reader sees first, with no click, and leaves the numbers as JSON on
// <html data-picture>. It reads the old role-column map (svg.map) or the system map (svg.sysmap) with
// the same keys, so one page can be measured before and after the same subject gains a system map.
setTimeout(function () {
  var out = { picture: "none", boxes: 0, withSub: 0, groups: 0, links: 0, labelled: 0, onJourney: 0,
              through: 0, tagOverlaps: 0, minFontPx: null, overlaps: 0, outsideParent: 0, w: 0, h: 0, problems: [] };
  try {
    var sys = document.querySelector("svg.sysmap"), old = document.querySelector("svg.map");
    var svg = sys || old;
    if (svg) {
      out.picture = sys ? "sysmap" : "map";
      var vb = svg.viewBox.baseVal, shown = svg.getBoundingClientRect();
      var scale = vb && vb.width ? shown.width / vb.width : 1;
      out.w = Math.round(vb.width); out.h = Math.round(vb.height);
      out.topPx = Math.round(shown.top + (window.pageYOffset || 0));
      var boxSel = sys ? "g.sys-part" : "g.node", subSel = sys ? "text.sys-sub" : "text.sub";
      var boxes = Array.prototype.map.call(svg.querySelectorAll(boxSel), function (g) {
        var r = g.querySelector("rect");
        return { id: g.getAttribute(sys ? "data-part" : "data-node"), sub: !!g.querySelector(subSel),
                 x: +r.getAttribute("x"), y: +r.getAttribute("y"), w: +r.getAttribute("width"), h: +r.getAttribute("height") };
      });
      out.boxes = boxes.length;
      out.withSub = boxes.filter(function (b) { return b.sub; }).length;
      out.groups = sys ? svg.querySelectorAll("g.sys-group").length : svg.querySelectorAll("text.zone").length;
      var links = svg.querySelectorAll(sys ? "path.sys-link" : "path.edge");
      out.links = links.length;
      if (sys) {
        out.labelled = svg.querySelectorAll("text.sys-lbl-t").length;
        out.onJourney = svg.querySelectorAll("path.sys-link[data-n]").length;
      }
      // an edge through a box it does not connect
      Array.prototype.forEach.call(links, function (p) {
        var ends = (p.getAttribute(sys ? "data-link" : "data-edge") || "|").split("|"), len = p.getTotalLength(), hit = {};
        for (var i = 1; i < 80; i++) {
          var q = p.getPointAtLength(len * i / 80);
          boxes.forEach(function (b) {
            if (ends.indexOf(b.id) >= 0) return;
            if (q.x > b.x + 1 && q.x < b.x + b.w - 1 && q.y > b.y + 1 && q.y < b.y + b.h - 1) hit[b.id] = 1;
          });
        }
        out.through += Object.keys(hit).length;
      });
      if (sys) { // link labels that sit on another label or on a part
        var tags = Array.prototype.map.call(svg.querySelectorAll("g.sys-lbl"), function (g) {
          var m = /translate\(([-\d.]+),([-\d.]+)\)/.exec(g.getAttribute("transform") || ""), r = g.querySelector("rect");
          return { x: +m[1], y: +m[2], w: +r.getAttribute("width"), h: +r.getAttribute("height") };
        });
        var ov = function (A, B) { return A.x < B.x + B.w && B.x < A.x + A.w && A.y < B.y + B.h && B.y < A.y + A.h; };
        tags.forEach(function (t, i) {
          for (var j = i + 1; j < tags.length; j++) if (ov(t, tags[j])) out.tagOverlaps++;
          boxes.forEach(function (b) { if (ov(t, b)) out.tagOverlaps++; });
        });
      }
      // boxes that overlap each other
      for (var a = 0; a < boxes.length; a++) for (var c = a + 1; c < boxes.length; c++) {
        var A = boxes[a], B = boxes[c];
        if (A.x < B.x + B.w && B.x < A.x + A.w && A.y < B.y + B.h && B.y < A.y + A.h) out.overlaps++;
      }
      if (sys) { // a part outside the group that holds it, by the group's own rectangle
        Array.prototype.forEach.call(svg.querySelectorAll("g.sys-part[data-parent]"), function (g) {
          var pr = svg.querySelector('g.sys-group[data-group="' + g.getAttribute("data-parent") + '"] rect'), r = g.querySelector("rect");
          if (!pr) return;
          var x = +r.getAttribute("x"), y = +r.getAttribute("y"), w = +r.getAttribute("width"), h = +r.getAttribute("height");
          var X = +pr.getAttribute("x"), Y = +pr.getAttribute("y"), W = +pr.getAttribute("width"), H = +pr.getAttribute("height");
          if (x < X || y < Y || x + w > X + W || y + h > Y + H) out.outsideParent++;
        });
      }
      // the smallest text on the picture, in the pixels the reader sees at this window width
      var min = null;
      Array.prototype.forEach.call(svg.querySelectorAll("text"), function (t) {
        if (!t.textContent.trim() || t.closest("[hidden]")) return;
        var px = parseFloat(getComputedStyle(t).fontSize) * scale;
        if (min === null || px < min) min = px;
      });
      out.minFontPx = min === null ? null : Math.round(min * 10) / 10;
    }
  } catch (e) { out.problems.push(String(e && e.message || e)); }
  // What a reader can read with no click: words of explanation, words of code, bare step numbers, and whether
  // the map has to scroll sideways. Counted from what is rendered, so a hidden panel counts for nothing.
  try {
    var shown = function (el) { return el.getClientRects().length > 0; };
    var words = function (t) { return (t.trim().match(/\S+/g) || []).length; };
    var sum = function (sel) { var n = 0; document.querySelectorAll(sel).forEach(function (el) { if (shown(el)) n += words(el.innerText || ""); }); return n; };
    out.explainWords = sum(".sys-jt, .sys-why, .ol-says, .rd-step .d, .rd-step h4, #caption p.d, #caption .cap-head :is(h2, h3, h4)");
    out.codeWords = sum(".ol-line code");
    out.stepRefs = Array.prototype.filter.call(document.querySelectorAll(".ol-n"), shown).length;
    var holder = document.querySelector(".sys-holder");
    out.mapScrolls = holder ? (holder.scrollWidth > holder.clientWidth + 1 ? 1 : 0) : null;
    var steps = document.querySelectorAll(".sys-journey > ol > li");
    out.whyOfSteps = steps.length ? document.querySelectorAll(".sys-why").length + "/" + steps.length : null;
  } catch (e) { out.problems.push(String(e && e.message || e)); }
  document.documentElement.setAttribute("data-picture", JSON.stringify(out));
}, 1500);

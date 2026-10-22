// Injected by tests/test_flow.sh into a copy of a built page (never shipped): after boot, records
// on <html data-probe> whether the #<id> deep-link target is shown in the viewport, and every map
// edge that passes through a box it does not connect.
setTimeout(function () {
  var out = { ok: document.documentElement.getAttribute("data-flow-ok"), target: null, crossings: [] };
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
  document.documentElement.setAttribute("data-probe", JSON.stringify(out));
}, 1500);

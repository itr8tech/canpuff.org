/* canpuff.org — progressive enhancement only. Everything here is optional:
   the pages read, print and deep-link fine with JavaScript disabled. */
(function () {
  "use strict";

  var root = document.documentElement;

  /* ---------- theme toggle (system preference is the default) ---------- */
  var btn = document.getElementById("theme");
  if (btn) {
    btn.addEventListener("click", function () {
      var isDark = root.dataset.theme
        ? root.dataset.theme === "dark"
        : window.matchMedia("(prefers-color-scheme: dark)").matches;
      var next = isDark ? "light" : "dark";
      root.dataset.theme = next;
      try { localStorage.setItem("canpuff-theme", next); } catch (e) { /* private mode */ }
    });
  }

  var doc = document.querySelector(".doc");
  if (!doc) return;

  /* ---------- section anchors ---------- */
  var heads = doc.querySelectorAll("h2[id], h3[id], h4[id]");
  Array.prototype.forEach.call(heads, function (h) {
    var a = document.createElement("a");
    a.className = "anchor";
    a.href = "#" + h.id;
    a.textContent = "§";
    a.setAttribute("aria-label", "Permalink to this section");
    h.insertBefore(a, h.firstChild);
  });

  /* ---------- table-of-contents highlighting ---------- */
  var rail = document.querySelector(".toc");
  if (!rail) return;

  var links = {};
  Array.prototype.forEach.call(rail.querySelectorAll("a[href^='#']"), function (a) {
    links[decodeURIComponent(a.getAttribute("href").slice(1))] = a;
  });

  var stops = Array.prototype.filter.call(heads, function (h) { return links[h.id]; });
  if (!stops.length) return;

  var active = null, queued = false;

  function sync() {
    queued = false;
    var threshold = 140, best = stops[0];
    for (var i = 0; i < stops.length; i++) {
      if (stops[i].getBoundingClientRect().top <= threshold) best = stops[i];
      else break;
    }
    if (best === active) return;
    if (active) links[active.id].removeAttribute("data-active");
    active = best;
    var link = links[active.id];
    link.setAttribute("data-active", "");

    /* Keep the marker in view without ever touching page scroll. */
    if (rail.scrollHeight > rail.clientHeight + 8) {
      var l = link.getBoundingClientRect(), r = rail.getBoundingClientRect();
      if (l.top < r.top + 8) rail.scrollTop += l.top - r.top - 8;
      else if (l.bottom > r.bottom - 8) rail.scrollTop += l.bottom - r.bottom + 8;
    }
  }

  function onScroll() {
    if (!queued) { queued = true; requestAnimationFrame(sync); }
  }

  addEventListener("scroll", onScroll, { passive: true });
  addEventListener("resize", onScroll);
  sync();
})();

/* motion.js — a small, native motion layer for the mockup.
   Zero-dependency, progressive-enhancement, reduced-motion aware. Uses only
   native browser APIs (IntersectionObserver + requestAnimationFrame + CSS
   transitions) — not a bundled animation library — consistent with this
   codebase's zero-dependency convention (pathograph.js / reveal.js) and with
   Su's razor. Every final value already lives in the HTML, so with JS off or
   reduced-motion on, everything shows at its final state; this only ADDS the
   count-up / bar-fill motion when motion is allowed.

   Provides:
     • count-up on numeric stats  — .stat .num  and  .statstrip .item .n
     • bar fill 0→value on scroll-in — .bfill (animates from its own inline width)
   Each element animates once, the first time it scrolls into view, then is
   unobserved (no replays, no per-keystroke re-triggering). */
(function () {
  var reduce = window.matchMedia &&
               window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) return;

  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      io.unobserve(e.target);
      if (typeof e.target.__play === "function") e.target.__play();
    });
  }, { threshold: 0.35, rootMargin: "0px 0px -8% 0px" });

  // ---- count-up ---------------------------------------------------------
  // Only animates text shaped as  <optional non-digits><number><optional
  // non-digits>  (e.g. "4,846", "~2,400", "38%", "4.6"). Anything with digits
  // in the middle or none at all — "2/13", "↓", "CC0"→0 — is safely skipped.
  var NUM_RE = /^(\D*)([\d,]+(?:\.\d+)?)(\D*)$/;
  function fmt(n, decimals, grouped) {
    var s = decimals ? n.toFixed(decimals) : String(Math.round(n));
    if (grouped) {
      var parts = s.split(".");
      parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
      s = parts.join(".");
    }
    return s;
  }
  function armCount(el) {
    var m = String(el.textContent).trim().match(NUM_RE);
    if (!m) return;
    var prefix = m[1], raw = m[2], suffix = m[3];
    var grouped = raw.indexOf(",") >= 0;
    var decimals = raw.indexOf(".") >= 0 ? raw.split(".")[1].length : 0;
    var target = parseFloat(raw.replace(/,/g, ""));
    if (!isFinite(target) || target === 0) return;   // nothing to count
    el.__play = function () {
      var dur = 1100, t0 = 0;
      (function step(ts) {
        if (!t0) t0 = ts || performance.now();
        var p = Math.min(1, ((ts || performance.now()) - t0) / dur);
        var eased = 1 - Math.pow(1 - p, 3);           // ease-out cubic
        el.textContent = prefix + fmt(target * eased, decimals, grouped) + suffix;
        if (p < 1) requestAnimationFrame(step);
        else el.textContent = prefix + fmt(target, decimals, grouped) + suffix;
      })();
    };
    el.textContent = prefix + fmt(0, decimals, grouped) + suffix;    // start at 0
    io.observe(el);
  }

  // ---- bar fill ---------------------------------------------------------
  function armBar(el) {
    var target = el.style.width;
    if (!target) return;                              // no inline width → skip
    el.style.width = "0%";
    el.__play = function () { el.style.width = target; };  // CSS transition animates
    io.observe(el);
  }

  function init() {
    document.querySelectorAll(".stat .num, .statstrip .item .n").forEach(armCount);
    document.querySelectorAll(".bfill").forEach(armBar);
  }
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();

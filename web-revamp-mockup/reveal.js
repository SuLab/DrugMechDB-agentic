/* Scroll-reveal, progressive-enhancement.
   Content is fully visible by default (in HTML/CSS). This script ONLY hides-then-
   reveals when motion is allowed — so no-JS and reduced-motion users always see
   everything. Transform/opacity only; ease-out entrances; staggered groups.
   Grounded in the motion guidance: ease-out for entering, honor
   prefers-reduced-motion, no infinite/decorative animation (each element reveals
   once, then is unobserved).

   Markup:
     data-reveal          — reveal this element once when it scrolls in
     data-reveal-group    — reveal its direct children, staggered, as a set
   window.revealScan(root) re-arms any newly-added nodes (used after dynamic render). */
(function () {
  var reduce = window.matchMedia &&
               window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) return;                       // leave content visible, no motion

  var STEP = 55;                            // ms of stagger between grouped items
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
    });
  }, { rootMargin: "0px 0px -6% 0px", threshold: 0.06 });

  function arm(el, i) {
    if (el.classList.contains("reveal")) return;
    el.classList.add("reveal");
    if (i) el.style.transitionDelay = (i * STEP) + "ms";
    io.observe(el);
  }

  function scan(root) {
    root = root || document;
    root.querySelectorAll("[data-reveal]").forEach(function (el) { arm(el, 0); });
    root.querySelectorAll("[data-reveal-group]").forEach(function (g) {
      Array.prototype.slice.call(g.children).forEach(function (c, i) { arm(c, i); });
    });
  }

  scan(document);
  window.revealScan = scan;
})();

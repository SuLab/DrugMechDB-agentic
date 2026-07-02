/* Scroll-reveal, progressive-enhancement.
   Content is fully visible by default (in HTML/CSS). This script ONLY hides-then-
   reveals when motion is allowed — so no-JS and reduced-motion users always see
   everything. Transform/opacity only; ease-out entrances; staggered groups.
   Grounded in the motion guidance: ease-out for entering, honor
   prefers-reduced-motion, no infinite/decorative animation (each element reveals
   once, then is unobserved).

   Runs exactly once per page load, no matter how many times this file is
   included or when the script tag executes relative to DOMContentLoaded:
     - a page-level guard (window.__dmdbReveal) makes re-execution a no-op.
     - a WeakSet (not a class check) is the single source of truth for "already
       armed", so nothing can be armed or observed twice.
     - the first pass waits one animation frame after `load` (fonts/images
       finished, layout settled) before measuring intersections, so a late
       web-font swap or image reflow can't shift what's "in view" mid-reveal.

   Markup:
     data-reveal          — reveal this element once when it scrolls in
     data-reveal-group    — reveal its direct children, staggered, as a set
   window.revealScan(root) re-arms any newly-added nodes (used after dynamic render). */
(function () {
  if (window.__dmdbReveal) return;   // idempotency guard — this file can only init once
  window.__dmdbReveal = true;

  var reduce = window.matchMedia &&
               window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) return;                       // leave content visible, no motion

  var STEP = 55;                            // ms of stagger between grouped items
  var armed = new WeakSet();                // authoritative "already armed" set
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
    });
  }, { rootMargin: "0px 0px -6% 0px", threshold: 0.06 });

  function arm(el, i) {
    if (armed.has(el)) return;
    armed.add(el);
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

  function settle() { requestAnimationFrame(function () { scan(document); }); }

  // First pass now (script sits at end of body, so the DOM it needs already
  // exists) — then one corrective pass after everything (fonts, images) has
  // fully loaded, purely additive: already-armed elements are untouched.
  settle();
  if (document.readyState === "complete") settle();
  else window.addEventListener("load", settle, { once: true });

  window.revealScan = scan;
})();

/* Scroll-pinned step story ("See a mechanism path unfold").
   Zero-dependency, native scroll — no scroll-jacking, no virtual scroll.
   A tall track (.pathwalk-track) holds a sticky stage (.pathwalk-stage, CSS
   position:sticky). As the user scrolls through the track's height, the stage
   stays pinned in the viewport while a 0..1 progress value — computed from
   getBoundingClientRect, rAF-throttled — lights up .pw-step elements in
   sequence (vertical chain, left) and cross-fades the matching
   .pw-detail-item caption (evidence + paper credential, right). The last
   slice of scroll switches the stage into ".finale": the vertical walk
   fades out and a large, single-line horizontal recap of the whole path
   (.pw-finale) fades in — CSS handles that crossfade, this file only ever
   toggles the "finale" class.

   This deliberately isn't built on a scroll library (GSAP ScrollTrigger,
   Lenis, Framer Motion): the effect is just "sticky panel + scroll-fraction",
   which this file does in ~50 lines with zero network dependency — consistent
   with the rest of this codebase (pathograph.js, reveal.js are both
   zero-dependency too). Swap in ScrollTrigger later only if the timeline
   needs real physics/scrubbed keyframes this can't express.

   Progressive enhancement: under prefers-reduced-motion, or on short/mobile
   viewports, styles.css unpins the stage and shows the walk AND the finale
   statically, stacked, at full opacity — this script simply doesn't run (see
   the guard below), so there is nothing to keep in sync. */
(function () {
  var reduce = window.matchMedia &&
               window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var track = document.querySelector(".pathwalk-track");
  if (!track || reduce) return;

  // Also skip on the same layouts CSS already collapses to a static list —
  // no point computing a scroll fraction nothing will visually reflect.
  if (window.matchMedia("(max-width: 760px), (max-height: 620px)").matches) return;

  var stage = track.querySelector(".pathwalk-stage");
  var steps = Array.prototype.slice.call(track.querySelectorAll(".pw-step"));
  var details = Array.prototype.slice.call(track.querySelectorAll(".pw-detail-item"));
  var fill = track.querySelector(".pw-rail .fill");
  var pct = track.querySelector(".pw-rail .pct");
  var nWalk = steps.length;        // the vertical-chain steps
  var nSlices = nWalk + 1;         // +1 reserved for the finale recap
  var ticking = false;

  function update() {
    ticking = false;
    var r = track.getBoundingClientRect();
    var total = r.height - window.innerHeight;
    var raw = total > 0 ? (-r.top) / total : (r.top <= 0 ? 1 : 0);
    var p = Math.max(0, Math.min(1, raw));
    var activeIdx = Math.min(nSlices - 1, Math.floor(p * nSlices));
    var finale = activeIdx >= nWalk;

    stage.classList.toggle("finale", finale);
    steps.forEach(function (el, i) {
      el.classList.toggle("done", i < activeIdx);
      el.classList.toggle("active", i === activeIdx && !finale);
    });
    details.forEach(function (el, i) {
      el.classList.toggle("show", i === activeIdx && !finale);
    });
    if (fill) fill.style.width = (p * 100).toFixed(1) + "%";
    if (pct) pct.textContent = Math.round(p * 100) + "%";
  }

  function onScroll() {
    if (!ticking) { requestAnimationFrame(update); ticking = true; }
  }

  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll, { passive: true });
  update();
})();

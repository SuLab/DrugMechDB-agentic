/* Lightweight interactive pathograph — pure SVG, zero dependencies.
   Layered left→right layout (rank = longest path from a drug/source node),
   always-on deduplicated edge labels rendered in a top layer (never hidden),
   hover-to-highlight, click-a-node callback, wheel-zoom + drag-pan.
   This is what replaces the ~95 KB static matplotlib PNG per record. */

const TYPE_COLOR = {
  Drug:"#4f46e5", ChemicalSubstance:"#7c3aed", Protein:"#2563eb", GeneFamily:"#0ea5e9",
  MacromolecularComplex:"#0891b2", Pathway:"#0d9488", BiologicalProcess:"#16a34a",
  MolecularActivity:"#4d7c0f", CellularComponent:"#d97706", Cell:"#ea580c",
  GrossAnatomicalStructure:"#a16207", PhenotypicFeature:"#db2777", Disease:"#dc2626",
  OrganismTaxon:"#6b7280"
};
const DIR_COLOR = { pos:"#059669", neg:"#e11d48", neutral:"#64748b" };
const SVGNS = "http://www.w3.org/2000/svg";

function el(tag, attrs={}) {
  const e = document.createElementNS(SVGNS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
}
function edgeDir(key) {
  const k = key.toLowerCase();
  if (/(decrease|inhibit|negativ|down|block|disrupt|suppress|antagon)/.test(k)) return "neg";
  if (/(increase|positiv|activat|\bup\b|stimulat|induc|agonist|correlated)/.test(k)) return "pos";
  return "neutral";
}
function wrap(name, max) {
  const words = name.split(" "); const lines = []; let cur = "";
  for (const w of words) {
    if ((cur + " " + w).trim().length > max) { if (cur) lines.push(cur); cur = w; }
    else cur = (cur + " " + w).trim();
  }
  if (cur) lines.push(cur);
  if (lines.length > 3) { lines.length = 3; lines[2] = lines[2].slice(0, max - 1) + "…"; }
  return lines;
}
const avg = a => a.reduce((s, x) => s + x, 0) / a.length;

function renderPathograph(containerId, record, onNodeClick) {
  const host = document.getElementById(containerId);
  host.innerHTML = "";
  const W = host.clientWidth, H = host.clientHeight;
  const NODE_W = 150, COL_W = 262, ROW_GAP = 18, PAD = 34;

  // --- ranks (longest path from source) ---
  const incoming = {}, byId = {};
  record.nodes.forEach(n => { incoming[n.id] = []; byId[n.id] = n; });
  record.links.forEach(l => incoming[l.target].push(l.source));
  const rank = {};
  (function () {
    const seen = {};
    function r(id) {
      if (rank[id] !== undefined) return rank[id];
      if (seen[id]) return 0; seen[id] = true;
      if (!incoming[id].length) return rank[id] = 0;
      let m = 0; incoming[id].forEach(p => m = Math.max(m, r(p) + 1));
      return rank[id] = m;
    }
    record.nodes.forEach(n => r(n.id));
  })();

  // --- layout: group by rank, lay out each column ---
  const cols = {};
  record.nodes.forEach(n => { (cols[rank[n.id]] = cols[rank[n.id]] || []).push(n); });
  const layout = {};
  let maxColH = 0;
  Object.keys(cols).forEach(c => {
    let h = 0;
    cols[c].forEach(n => { n._lines = wrap(n.name, 22); n._h = n._lines.length * 13 + 26; h += n._h + ROW_GAP; });
    maxColH = Math.max(maxColH, h - ROW_GAP);
  });
  Object.keys(cols).forEach(c => {
    const colH = cols[c].reduce((a, n) => a + n._h + ROW_GAP, 0) - ROW_GAP;
    let y = PAD + (maxColH - colH) / 2;
    cols[c].forEach(n => { layout[n.id] = { x: PAD + c * COL_W, y, w: NODE_W, h: n._h }; y += n._h + ROW_GAP; });
  });
  const numCols = Object.keys(cols).length;
  const gW = PAD * 2 + (numCols - 1) * COL_W + NODE_W;
  const gH = PAD * 2 + maxColH;

  // --- svg scaffold ---
  const svg = el("svg", { width: "100%", height: "100%" });
  const defs = el("defs");
  ["neutral", "pos", "neg"].forEach(d => {
    const m = el("marker", { id: "arw-" + d, viewBox: "0 0 10 10", refX: "9", refY: "5", markerWidth: "7", markerHeight: "7", orient: "auto-start-reverse" });
    m.appendChild(el("path", { d: "M0,0 L10,5 L0,10 z", fill: DIR_COLOR[d] }));
    defs.appendChild(m);
  });
  svg.appendChild(defs);
  const vp = el("g", { id: "vp" });
  const edgeLayer = el("g"), nodeLayer = el("g"), labelLayer = el("g");
  vp.appendChild(edgeLayer); vp.appendChild(nodeLayer); vp.appendChild(labelLayer); // labels on top
  svg.appendChild(vp); host.appendChild(svg);

  // --- edges ---
  const edgeEls = [];
  const groups = {}; // dedupe labels by (rankSrc -> rankTgt :: predicate)
  record.links.forEach(l => {
    const s = layout[l.source], t = layout[l.target];
    if (!s || !t) return;
    const x1 = s.x + s.w, y1 = s.y + s.h / 2, x2 = t.x, y2 = t.y + t.h / 2, dx = (x2 - x1) * 0.5;
    const dir = edgeDir(l.key);
    const p = el("path", {
      d: `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`,
      class: "gedge " + dir, "marker-end": `url(#arw-${dir})`
    });
    p.addEventListener("mouseenter", e => showTip(e, `<div class="tt-name">${byId[l.source].name}</div><div>${l.key}</div><div class="tt-name" style="margin-top:4px">${byId[l.target].name}</div>`));
    p.addEventListener("mousemove", moveTip);
    p.addEventListener("mouseleave", hideTip);
    edgeLayer.appendChild(p);
    edgeEls.push({ p, s: l.source, t: l.target });

    const key = rank[l.source] + ">" + rank[l.target] + "::" + l.key;
    const g = groups[key] || (groups[key] = { key: l.key, dir, mx: [], my: [], ids: new Set() });
    g.mx.push((x1 + x2) / 2); g.my.push((y1 + y2) / 2); g.ids.add(l.source); g.ids.add(l.target);
  });

  // --- nodes ---
  const nodeEls = {};
  record.nodes.forEach(n => {
    const lo = layout[n.id], color = TYPE_COLOR[n.label] || "#6b7280";
    const g = el("g", { class: "gnode" });
    g.appendChild(el("rect", { x: lo.x, y: lo.y, width: lo.w, height: lo.h, rx: "9", fill: color }));
    n._lines.forEach((ln, i) => {
      const tx = el("text", { x: lo.x + lo.w / 2, y: lo.y + 16 + i * 13, "text-anchor": "middle" });
      tx.textContent = ln; g.appendChild(tx);
    });
    const ty = el("text", { x: lo.x + lo.w / 2, y: lo.y + lo.h - 7, "text-anchor": "middle", class: "gtype" });
    ty.textContent = n.label; g.appendChild(ty);
    g.addEventListener("mouseenter", e => { highlight(n.id); showTip(e, `<div class="tt-name">${n.name}</div><div class="tt-meta">${n.id} · ${n.label}</div>`); });
    g.addEventListener("mousemove", moveTip);
    g.addEventListener("mouseleave", () => { clearHl(); hideTip(); });
    g.addEventListener("click", () => onNodeClick && onNodeClick(n));
    nodeLayer.appendChild(g); nodeEls[n.id] = g;
  });

  // --- edge labels (deduped, top layer, white pill, dir-colored text) ---
  const labelEls = [];
  Object.values(groups).forEach(grp => {
    const x = avg(grp.mx), y = avg(grp.my);
    const g = el("g", { class: "elabel" });
    const bg = el("rect", { rx: "6", fill: "#ffffff", stroke: "#e2e8f0", "stroke-width": "1" });
    const txt = el("text", { x, y: y + 3, "text-anchor": "middle", fill: DIR_COLOR[grp.dir], "font-weight": "600", "font-size": "11" });
    txt.textContent = grp.key;
    g.appendChild(bg); g.appendChild(txt); labelLayer.appendChild(g);
    requestAnimationFrame(() => { try { const b = txt.getBBox(); bg.setAttribute("x", b.x - 6); bg.setAttribute("y", b.y - 3); bg.setAttribute("width", b.width + 12); bg.setAttribute("height", b.height + 6); } catch (e) {} });
    labelEls.push({ g, ids: grp.ids });
  });

  // --- hover highlight ---
  function highlight(id) {
    const keep = new Set([id]);
    edgeEls.forEach(e => { if (e.s === id || e.t === id) { keep.add(e.s); keep.add(e.t); e.p.style.strokeWidth = "2.8"; } else e.p.classList.add("dimmed"); });
    record.nodes.forEach(n => { if (!keep.has(n.id)) nodeEls[n.id].classList.add("dimmed"); });
    labelEls.forEach(l => { if (!l.ids.has(id)) l.g.classList.add("dimmed"); });
  }
  function clearHl() {
    edgeEls.forEach(e => { e.p.style.strokeWidth = ""; e.p.classList.remove("dimmed"); });
    record.nodes.forEach(n => nodeEls[n.id].classList.remove("dimmed"));
    labelEls.forEach(l => l.g.classList.remove("dimmed"));
  }

  // --- tooltip ---
  let tip = document.querySelector(".tooltip");
  if (!tip) { tip = document.createElement("div"); tip.className = "tooltip"; document.body.appendChild(tip); }
  function showTip(e, html) { tip.innerHTML = html; tip.style.opacity = "1"; moveTip(e); }
  function moveTip(e) { tip.style.left = (e.clientX + 14) + "px"; tip.style.top = (e.clientY + 14) + "px"; }
  function hideTip() { tip.style.opacity = "0"; }

  // --- pan + zoom ---
  let tf = { x: 0, y: 0, k: 1 };
  const fitK = Math.min((W - 20) / gW, (H - 20) / gH, 1.1);
  function fit() { tf.k = fitK; tf.x = (W - gW * fitK) / 2; tf.y = (H - gH * fitK) / 2; apply(); }
  function apply() { vp.setAttribute("transform", `translate(${tf.x},${tf.y}) scale(${tf.k})`); }
  fit();
  svg.addEventListener("wheel", e => {
    e.preventDefault();
    const r = svg.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
    const f = e.deltaY < 0 ? 1.12 : 0.89, nk = Math.max(0.3, Math.min(3, tf.k * f));
    tf.x = mx - (mx - tf.x) * (nk / tf.k); tf.y = my - (my - tf.y) * (nk / tf.k); tf.k = nk; apply();
  }, { passive: false });
  let drag = null;
  svg.addEventListener("pointerdown", e => { drag = { x: e.clientX - tf.x, y: e.clientY - tf.y }; host.classList.add("grabbing"); });
  window.addEventListener("pointermove", e => { if (drag) { tf.x = e.clientX - drag.x; tf.y = e.clientY - drag.y; apply(); } });
  window.addEventListener("pointerup", () => { drag = null; host.classList.remove("grabbing"); });
  host._reset = fit;

  return { types: [...new Set(record.nodes.map(n => n.label))] };
}

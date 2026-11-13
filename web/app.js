"use strict";
// F.I.R.E.S. burning activity calendar. Plain JS, no build step, vendored libs only (works offline).

const API = "/api";
const DAY_MS = 86400000;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTH_START_DOY = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];   // non-leap year
const UNITS = [["week", "Weeks"], ["day", "Days"]];
const METRICS = [["cell_days", "Fire cell-days"], ["detections", "Detections"]];
const RAMP_STEPS = 6;
const MIN_BOX_DEG = 0.25;

const VIEWS = [["harmonized", "Aqua-equivalent"], ["raw", "By sensor"]];
const state = { aois: [], aoi: "levant", bbox: null, view: "harmonized", sensor: "NOAA-20-VIIRS", unit: "week",
                metric: "cell_days", data: null, request: null };
const $ = (id) => document.getElementById(id);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const fmt = new Intl.NumberFormat("en", { maximumFractionDigits: 1 });
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

// ---------- URL state (shareable links) ----------
function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  if (p.get("bbox")) { state.bbox = p.get("bbox").split(",").map(Number); state.aoi = null; }
  else if (p.get("aoi")) state.aoi = p.get("aoi");
  for (const k of ["view", "sensor", "unit", "metric"]) if (p.get(k)) state[k] = p.get(k);
}
function writeHash() {
  const p = new URLSearchParams();
  if (state.bbox) p.set("bbox", state.bbox.join(",")); else p.set("aoi", state.aoi);
  p.set("view", state.view); p.set("sensor", state.sensor); p.set("unit", state.unit); p.set("metric", state.metric);
  history.replaceState(null, "", "#" + p.toString());
}

// ---------- segmented controls ----------
function segmented(el, options, current, onPick) {
  el.innerHTML = "";
  for (const [value, label] of options) {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = label; b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(value === current));
    b.addEventListener("click", () => onPick(value));
    el.appendChild(b);
  }
}
function renderFilters() {
  const sensors = state.data ? state.data.sensors.map((s) => [s.sensor, s.sensor]) : [[state.sensor, state.sensor]];
  segmented($("view-seg"), VIEWS, state.view, (v) => { state.view = v; load(); });
  $("sensor-seg").hidden = harmonizedView();
  segmented($("sensor-seg"), sensors, state.sensor, (v) => { state.sensor = v; load(); });
  segmented($("unit-seg"), UNITS, state.unit, (v) => { state.unit = v; load(); });
  segmented($("metric-seg"), METRICS, state.metric, (v) => { state.metric = v; load(); });
}

// ---------- map ----------
let map, aoiLayer, countriesLayer;
function initMap() {
  map = L.map("map", { worldCopyJump: false, maxBounds: [[-90, -200], [90, 200]], minZoom: 1, zoomSnap: 0.25,
                       attributionControl: true }).setView([25, 20], 1.5);
  map.attributionControl.setPrefix(false);
  aoiLayer = L.layerGroup().addTo(map);
  fetch("data/countries.geojson").then((r) => r.json()).then((geo) => {
    countriesLayer = L.geoJSON(geo, { style: countryStyle, interactive: false }).addTo(map);
    countriesLayer.bringToBack();
    map.attributionControl.addAttribution("Natural Earth");
  }).catch(() => setStatus("Basemap not available; the calendar still works."));
  initDraw();
}
const countryStyle = () => ({ color: css("--land-edge"), weight: 0.6, fillColor: css("--land"), fillOpacity: 1 });

function showAoi(bbox) {
  aoiLayer.clearLayers();
  const [w, s, e, n] = bbox;
  const style = { color: css("--aoi"), weight: 2, fillOpacity: 0.08 };
  const parts = w <= e ? [[[s, w], [n, e]]] : [[[s, w], [n, 180]], [[s, -180], [n, e]]];   // antimeridian
  for (const b of parts) L.rectangle(b, style).addTo(aoiLayer);
  map.fitBounds(parts[0], { padding: [20, 20], maxZoom: 6 });
}

// Box drawing without plugins: drag with the map's panning switched off.
function initDraw() {
  let drawing = false, start = null, rect = null;
  const stop = () => {
    drawing = false; start = null; map.dragging.enable(); $("map").classList.remove("drawing");
    $("draw-btn").classList.remove("active"); $("draw-hint").hidden = true;
    if (rect) { map.removeLayer(rect); rect = null; }
  };
  $("draw-btn").addEventListener("click", () => {
    if (drawing) return stop();
    drawing = true; map.dragging.disable(); $("map").classList.add("drawing");
    $("draw-btn").classList.add("active"); $("draw-hint").hidden = false;
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && drawing) stop(); });
  map.on("mousedown", (e) => { if (drawing) start = e.latlng; });
  map.on("mousemove", (e) => {
    if (!drawing || !start) return;
    const b = L.latLngBounds(start, e.latlng);
    if (rect) rect.setBounds(b); else rect = L.rectangle(b, { color: css("--aoi"), weight: 1.5, dashArray: "4 3", fillOpacity: 0.05 }).addTo(map);
  });
  map.on("mouseup", (e) => {
    if (!drawing || !start) return;
    const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
    const r2 = (v) => Math.round(v * 100) / 100;
    const w = r2(clamp(Math.min(start.lng, e.latlng.lng), -180, 180)), east = r2(clamp(Math.max(start.lng, e.latlng.lng), -180, 180));
    const s = r2(clamp(Math.min(start.lat, e.latlng.lat), -90, 90)), n = r2(clamp(Math.max(start.lat, e.latlng.lat), -90, 90));
    stop();
    if (east - w < MIN_BOX_DEG || n - s < MIN_BOX_DEG) { setStatus("Draw a larger box: at least one 0.25° grid cell."); return; }
    state.bbox = [w, s, east, n]; state.aoi = null; syncAoiSelect(); load();
  });
}

// ---------- AOI select ----------
function syncAoiSelect() {
  const sel = $("aoi-select");
  sel.innerHTML = "";
  for (const a of state.aois) sel.add(new Option(a.label, a.name, false, a.name === state.aoi));
  if (state.bbox) sel.add(new Option(`Custom box (${state.bbox.join(", ")})`, "__custom", false, true));
}

// ---------- data ----------
function setStatus(msg) { $("status").textContent = msg || ""; }

async function load() {
  writeHash(); renderFilters();
  const params = new URLSearchParams({ unit: state.unit, metric: state.metric });
  if (state.bbox) params.set("bbox", state.bbox.join(",")); else params.set("aoi", state.aoi);
  if (state.request) state.request.abort();
  const ctrl = new AbortController(); state.request = ctrl;
  setStatus("Loading…");
  try {
    const r = await fetch(`${API}/calendar?${params}`, { signal: ctrl.signal });
    const body = await r.json();
    if (!r.ok) throw new Error(body.detail || r.statusText);
    state.data = body;
    if (!body.sensors.some((s) => s.sensor === state.sensor)) state.sensor = body.sensors[0].sensor;
    setStatus("");
    showAoi(body.aoi.grid_bbox || body.aoi.bbox);
    writeHash(); renderFilters(); renderAll();
    loadSeason(params, ctrl);
  } catch (err) {
    if (err.name !== "AbortError") setStatus(`Could not load the calendar: ${err.message}`);
  }
}

// ---------- periods ----------
function isoWeekStart(year, week) {               // Monday of ISO week `week` of ISO year `year`
  const jan4 = Date.UTC(year, 0, 4);
  const dow = new Date(jan4).getUTCDay() || 7;
  return jan4 - (dow - 1) * DAY_MS + (week - 1) * 7 * DAY_MS;
}
const dateFmt = (ms, opts) => new Date(ms).toLocaleDateString("en-GB", { timeZone: "UTC", ...opts });
function periodLabel(unit, year, p) {
  if (unit === "week") {
    const a = isoWeekStart(year, p + 1), b = a + 6 * DAY_MS;
    return `Week ${p + 1}, ${dateFmt(a, { day: "numeric", month: "short" })} – ${dateFmt(b, { day: "numeric", month: "short", year: "numeric" })}`;
  }
  return dateFmt(Date.UTC(year, 0, 1) + p * DAY_MS, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

// ---------- colour bins (quantiles of the positive values on screen) ----------
function binsFor(values) {
  const pos = values.flat().filter((v) => v !== null && v > 0).sort((a, b) => a - b);
  if (!pos.length) return [];
  const t = [];
  for (let i = 1; i < RAMP_STEPS; i++) t.push(pos[Math.min(pos.length - 1, Math.floor((i / RAMP_STEPS) * pos.length))]);
  return [...new Set(t)];
}
const binOf = (v, thresholds) => thresholds.filter((t) => v > t).length;
// With fewer bins than ramp steps, spread the bins across the whole ramp (cells and legend use this one rule).
const binColor = (bin, nBins) => `var(--fire-${1 + Math.round((bin * (RAMP_STEPS - 1)) / Math.max(1, nBins - 1))})`;

// ---------- which series is on screen ----------
const harmonizedView = () => state.view === "harmonized" && !!(state.data && state.data.harmonized);
function series() {
  const d = state.data;
  if (harmonizedView()) {
    const h = d.harmonized;
    return { name: h.label, values: h.values, coverage: h.coverage, data_days: h.data_days, lo: h.lo, hi: h.hi,
             estimated: h.estimated_days, substituted: h.substituted_days, sources: h.sources, harmonized: true };
  }
  const s = d.sensors.find((x) => x.sensor === state.sensor) || d.sensors[0];
  state.sensor = s.sensor;
  return { ...s, name: s.sensor, harmonized: false };
}

function renderBadge() {
  const d = state.data, b = $("badge");
  if (state.view === "harmonized" && !d.harmonized) {
    b.innerHTML = `<strong>Aqua-equivalent not available here:</strong> ${esc(d.harmonized_unavailable)}. Showing ${esc(state.sensor)}.`;
    b.hidden = false; return;
  }
  if (harmonizedView()) {
    const h = d.harmonized;
    b.innerHTML = `<strong>${h.provisional ? "Provisional estimate" : "Harmonized estimate"}:</strong> ${esc(h.label)}, ` +
      `method: ${esc(h.method)}. ${esc(h.band_note)}.<ul>${h.caveats.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>`;
    b.hidden = false; return;
  }
  const s = series();
  b.hidden = !s.note;
  if (s.note) b.innerHTML = `<strong>${esc(s.sensor)}:</strong> ${esc(s.note)}`;
}

// ---------- chart ----------
function renderAll() {
  const d = state.data;
  const label = d.aoi.name ? d.aoi.label : "Custom box";
  const what = harmonizedView() ? "Aqua-equivalent fire cell-days" : `${METRICS.find((m) => m[0] === d.metric)[1].toLowerCase()}, ${state.sensor}`;
  $("chart-title").textContent = `${label}: ${what} per ${d.unit}`;
  $("chart-sub").textContent = `${d.metric_label}. Data ${d.data_range[0]} to ${d.data_range[1]}.`;
  renderFilters();
  renderBadge();
  $("aoi-summary").textContent = `${fmt.format(d.aoi.cells)} grid cells of 0.25°` +
    (d.aoi.grid_bbox ? ` · [${d.aoi.grid_bbox.join(", ")}]` : " · box contains no grid cell centre");
  $("notes").innerHTML = d.notes.map((n) => `<li>${esc(n)}</li>`).join("");
  renderChart();
}

function renderChart() {
  const d = state.data;
  if (!d) return;
  const s = series();
  const thresholds = binsFor(s.values);
  const week = d.unit === "week";
  const left = 44, top = 22;
  const avail = $("chart").clientWidth || 800;
  // Weeks: whole-pixel cells with a 2px gap. Days: fractional widths that fill the panel, no gap below 4px.
  const cw = week ? Math.max(10, Math.floor((avail - left - 8) / d.periods)) : Math.max(2, (avail - left - 8) / d.periods);
  const gap = week ? 2 : cw >= 4 ? 1 : 0;
  const ch = week ? 20 : 16;
  const W = left + d.periods * cw + 8, H = top + d.years.length * ch + 4;
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("width", W); svg.setAttribute("height", H);
  svg.setAttribute("role", "img");
  if (!week) svg.setAttribute("shape-rendering", "crispEdges");
  svg.setAttribute("aria-label", `${s.name} ${d.metric_label} by ${d.unit} and year. Use "Show as table" for the values.`);
  svg.innerHTML = `<defs><pattern id="hatch" patternUnits="userSpaceOnUse" width="5" height="5" patternTransform="rotate(45)">
      <rect width="5" height="5" style="fill:var(--surface-1)"/><line x1="0" y1="0" x2="0" y2="5" style="stroke:var(--hatch);stroke-width:1.4"/></pattern></defs>`;

  // month ticks
  MONTH_START_DOY.forEach((doy, i) => {
    const p = week ? Math.floor((doy - 1) / 7) : doy - 1;
    const t = document.createElementNS(ns, "text");
    t.setAttribute("x", left + p * cw); t.setAttribute("y", 14); t.setAttribute("class", "axis");
    t.textContent = MONTHS[i]; svg.appendChild(t);
  });

  d.years.forEach((year, yi) => {
    const y = top + yi * ch;
    const t = document.createElementNS(ns, "text");
    t.setAttribute("x", 0); t.setAttribute("y", y + ch / 2 + 4); t.setAttribute("class", "axis");
    t.textContent = year; svg.appendChild(t);
    for (let p = 0; p < d.periods; p++) {
      const v = s.values[yi][p], cov = s.coverage[yi][p];
      if (cov === "absent") continue;   // ISO week 53 / day 366 that this year does not have
      const r = document.createElementNS(ns, "rect");
      r.setAttribute("x", left + p * cw); r.setAttribute("y", y);
      r.setAttribute("width", gap ? Math.max(1, cw - gap) : cw + 0.5); r.setAttribute("height", ch - gap);   // +0.5: no seams
      r.setAttribute("rx", week ? 2 : 1);
      r.setAttribute("class", "cell");
      r.style.fill = v === null ? "url(#hatch)" : v === 0 ? "var(--zero)" : binColor(binOf(v, thresholds), thresholds.length + 1);
      r.dataset.y = yi; r.dataset.p = p;
      svg.appendChild(r);
      if (v !== null && cov === "partial") {   // partial coverage: a bar along the top, visible at any cell width
        const bar = document.createElementNS(ns, "rect");
        bar.setAttribute("x", left + p * cw); bar.setAttribute("y", y);
        bar.setAttribute("width", gap ? Math.max(1, cw - gap) : cw + 0.5); bar.setAttribute("height", 3);
        bar.style.fill = "var(--text-primary)"; bar.style.pointerEvents = "none";
        svg.appendChild(bar);
      }
    }
  });

  svg.addEventListener("mousemove", (e) => hover(e, s, d));
  svg.addEventListener("mouseleave", () => { $("tooltip").hidden = true; });
  $("chart").replaceChildren(svg);
  renderLegend(thresholds, d);
  if (!$("table-wrap").hidden) renderTable();
}

function hover(e, s, d) {
  const tip = $("tooltip");
  const cell = e.target.closest(".cell");
  if (!cell) { tip.hidden = true; return; }
  const yi = +cell.dataset.y, p = +cell.dataset.p;
  const v = s.values[yi][p], cov = s.coverage[yi][p];
  const unitLabel = s.harmonized ? "Aqua-equivalent fire cell-days" : METRICS.find((m) => m[0] === d.metric)[1].toLowerCase();
  const estimated = s.harmonized && s.estimated[yi][p] > 0;
  const zeroText = s.harmonized ? (estimated ? "(estimated: VIIRS detected no fire)" : "(observed, no fire)")
                                : "(observed, no fire)";
  const valueLine = v === null
    ? "<strong>No data</strong> <span class=muted>(sensor gap or outside the data range; not zero)</span>"
    : `<strong>${fmt.format(v)}</strong> ${unitLabel}${v === 0 ? ` <span class=muted>${zeroText}</span>` : ""}` +
      (s.harmonized ? `<br><span class=muted>${estimated ? `estimate (${s.estimated[yi][p]} of ${s.data_days[yi][p]} day(s) from VIIRS)` : "Aqua-MODIS observed"}</span>` : "");
  const covLine = cov === "partial"
    ? `<br><span class=muted>Partial coverage: ${s.data_days[yi][p]} of ${d.period_days} day(s) with data; not a complete total</span>` : "";
  const bandLine = s.harmonized && v !== null
    ? (s.lo[yi][p] === null ? "" : `<br><span class=muted>90% range ${fmt.format(s.lo[yi][p])} – ${fmt.format(s.hi[yi][p])}</span>`) +
      (s.substituted[yi][p] ? `<br><span class=muted>${s.substituted[yi][p]} day(s) from ${esc(s.sources.slice(1).join(" / "))} (${esc(s.sources[0])} missing)</span>` : "")
    : "";
  tip.innerHTML = `${esc(periodLabel(d.unit, d.years[yi], p))}<br>${valueLine}${bandLine}${covLine}<br><span class=muted>${esc(s.name)}</span>`;
  tip.hidden = false;
  const x = Math.min(window.innerWidth - tip.offsetWidth - 8, e.clientX + 14);
  tip.style.left = `${x}px`; tip.style.top = `${e.clientY + 14}px`;
}

function renderLegend(thresholds, d) {
  const s = series();
  const unitLabel = s.harmonized ? "Aqua-equivalent fire cell-days" : METRICS.find((m) => m[0] === d.metric)[1].toLowerCase();
  const n = thresholds.length + 1;
  const lows = [0, ...thresholds];
  const steps = lows.map((lo, i) => `<span class="step"><span class="sw" style="background:${binColor(i, n)}"></span>` +
    `<span class="tick">${i === 0 ? "&gt;0" : "&gt;" + fmt.format(lo)}</span></span>`).join("");
  const anyFire = s.values.flat().some((v) => v > 0);
  $("legend").innerHTML = (anyFire ? `
    <span class="item"><span class="ramp">${steps}</span></span><span class="item muted">${esc(unitLabel)}${s.harmonized ? "" : ", " + esc(state.sensor)}</span>` : "") + `
    <span class="item"><span class="sw" style="background:var(--zero)"></span>0: no fire ${s.harmonized ? "(observed or estimated)" : "observed"}</span>
    <span class="item"><svg width="22" height="12" aria-hidden="true"><rect width="22" height="12" rx="2" fill="url(#hatch)"/></svg>No data (not zero)</span>
    <span class="item"><svg width="22" height="12" aria-hidden="true"><rect width="22" height="12" rx="2" style="fill:var(--fire-3)"/><rect width="22" height="3" style="fill:var(--text-primary)"/></svg>Partial coverage</span>`;
}

// ---------- season panels (climatology, critical periods, unusual weeks) ----------
async function loadSeason(params, ctrl) {
  const q = new URLSearchParams({ series: harmonizedView() ? "harmonized" : state.sensor });
  if (params.get("bbox")) q.set("bbox", params.get("bbox")); else q.set("aoi", params.get("aoi"));
  try {
    const get = (ep) => fetch(`${API}/calendar/${ep}?${q}`, { signal: ctrl.signal })
      .then(async (r) => (r.ok ? r.json() : { error: (await r.json().catch(() => ({}))).detail || r.statusText }));
    const [clim, crit, anom] = await Promise.all(["climatology", "critical-periods", "anomalies"].map(get));
    state.season = { clim, crit, anom };
  } catch (err) {
    if (err.name === "AbortError") return;
    state.season = { error: err.message };
  }
  renderSeason();
}

function renderSeason() {
  const s = state.season;
  if (!s) return;
  const empty = (msg) => `<p class="empty">${esc(msg)}</p>`;
  const failed = s.error || [s.clim, s.crit, s.anom].find((x) => x.error);
  if (failed) {
    const msg = s.error || failed.error;
    for (const id of ["season-chart", "periods", "anomalies"]) $(id).innerHTML = empty(msg);
    $("season-sub").textContent = "";
    return;
  }
  const c = s.clim;
  $("season-sub").textContent = `${c.series_label}. History: ${c.history_years.length} year(s)` +
    (c.history_years.length ? ` (${[...new Set([c.history_years[0], c.history_years[c.history_years.length - 1]])].join("–")})` : "") +
    (c.gate_rule ? `. Season rule: ${c.gate_rule}` : "") + ".";
  if (c.status !== "ok") {
    for (const id of ["season-chart", "periods", "anomalies"]) $(id).innerHTML = empty(c.message);
    return;
  }
  renderProfile(c);
  $("periods").innerHTML = s.crit.periods.length
    ? `<ol>${s.crit.periods.slice(0, 5).map((p) => `<li><strong>${esc(p.label)}</strong> · ${p.weeks} weeks · ` +
        `${Math.round(p.share_of_year * 100)}% of a typical year's activity · peak week ${p.peak_week}</li>`).join("")}</ol>`
    : empty(s.crit.message || "No critical period.");
  $("anomalies").innerHTML = s.anom.anomalies.length
    ? `<ul>${s.anom.anomalies.slice(0, 8).map((a) => `<li><strong>${a.year}, week ${a.week}</strong> ` +
        `(from ${esc(a.week_start)}): ${fmt.format(a.value)} vs usual ${fmt.format(a.median)}` +
        `${a.z !== null ? ` (z ${fmt.format(a.z)})` : ""}</li>`).join("")}</ul>`
    : empty("No unusual weeks in the record.");
}

function renderProfile(c) {
  const ns = "http://www.w3.org/2000/svg";
  const W = Math.max(320, $("season-chart").clientWidth || 700), H = 180, left = 40, right = 8, top = 10, bottom = 22;
  const x = (w) => left + ((w - 1) / 51) * (W - left - right);
  const ser = series();
  // The climatology is weekly fire cell-days: only overlay the latest year when the calendar shows the same thing.
  const comparable = state.data.unit === "week" && state.data.metric === "cell_days";
  // Same scaling as the climatology: partial weeks with >= 5 data days scaled to 7, thinner weeks left out.
  const li = ser.values.length - 1;
  const latestRow = !comparable || li < 0 ? [] : ser.values[li].map((v, w) => {
    const cov = ser.coverage[li][w], days = ser.data_days[li][w];
    if (v === null || cov === "none" || cov === "absent") return null;
    if (cov === "partial") return days >= 5 ? (v * 7) / days : null;
    return v;
  });
  const latestYear = state.data.years[state.data.years.length - 1];
  const ymax = Math.max(1, ...c.weeks.map((w) => w.p90 || 0), ...latestRow.slice(0, 52).map((v) => v || 0));
  const y = (v) => top + (1 - v / ymax) * (H - top - bottom);
  // Break the line at missing weeks: a gap is not zero and is not interpolated.
  const path = (pts) => pts.map((p, i) => p[1] === null ? "" :
    `${i && pts[i - 1][1] !== null ? "L" : "M"}${p[0].toFixed(1)},${y(p[1]).toFixed(1)}`).join("");
  const band = c.weeks.filter((w) => w.p10 !== null);
  const bandPath = band.length ? `M${band.map((w) => `${x(w.week).toFixed(1)},${y(w.p90).toFixed(1)}`).join("L")}` +
    `L${band.slice().reverse().map((w) => `${x(w.week).toFixed(1)},${y(w.p10).toFixed(1)}`).join("L")}Z` : "";
  const gated = c.gated_weeks.map((w) => `<rect class="gated" x="${x(w) - (W - left - right) / 104}" y="${top}" width="${(W - left - right) / 52}" height="${H - top - bottom}"/>`).join("");
  const ticks = MONTH_START_DOY.map((doy, i) => `<text class="axis" x="${x(Math.floor((doy - 1) / 7) + 1)}" y="${H - 6}">${MONTHS[i]}</text>`).join("");
  const yt = [0, ymax / 2, ymax].map((v) => `<text class="axis" x="0" y="${y(v) + 4}">${fmt.format(v)}</text>`).join("");
  $("season-chart").innerHTML = `<svg xmlns="${ns}" width="${W}" height="${H}" role="img" aria-label="Weekly median with p10 to p90 range; dashed line is ${latestYear}">
    ${gated}<path class="band" d="${bandPath}"/>
    <path class="median" d="${path(c.weeks.map((w) => [x(w.week), w.median]))}"/>
    <path class="latest" d="${path(latestRow.slice(0, 52).map((v, i) => [x(i + 1), v]))}"/>${ticks}${yt}</svg>
    <p class="hint">Solid: weekly median · band: p10–p90${comparable ? ` · dashed: ${latestYear}` : ""} · shaded: in-season weeks.</p>`;
}

// ---------- table view ----------
function renderTable() {
  const d = state.data, s = series();
  const rows = [];
  for (let p = 0; p < d.periods; p++) {
    const cells = d.years.map((_, yi) => s.values[yi][p]);
    if (cells.every((v) => v === null)) continue;
    const name = d.unit === "week" ? `Week ${p + 1}` : `Day ${p + 1}`;
    rows.push(`<tr><td>${name}</td>${cells.map((v, yi) => `<td>${v === null ? (s.coverage[yi][p] === "absent" ? "" : "no data") : fmt.format(v)}${
      v !== null && s.harmonized && s.lo[yi][p] !== null ? ` (${fmt.format(s.lo[yi][p])}–${fmt.format(s.hi[yi][p])})` : ""}${
      v !== null && s.coverage[yi][p] === "partial" ? " *" : ""}</td>`).join("")}</tr>`);
  }
  $("table-wrap").innerHTML = `<table><caption class="hint" style="caption-side:bottom;text-align:left;padding:4px 8px">
    ${esc(s.name)}, ${esc(d.metric_label)}.${s.harmonized ? " Brackets: 90% range." : ""} * partial coverage.</caption>
    <thead><tr><th>${d.unit === "week" ? "ISO week" : "Day"}</th>${d.years.map((y) => `<th>${y}</th>`).join("")}</tr></thead>
    <tbody>${rows.join("") || `<tr><td colspan="${d.years.length + 1}">No data for this sensor.</td></tr>`}</tbody></table>`;
}
$("table-btn").addEventListener("click", () => {
  const wrap = $("table-wrap"), show = wrap.hidden;
  wrap.hidden = !show; $("table-btn").setAttribute("aria-expanded", String(show));
  $("table-btn").textContent = show ? "Hide table" : "Show as table";
  if (show) renderTable();
});

// ---------- boot ----------
$("aoi-select").addEventListener("change", (e) => {
  if (e.target.value === "__custom") return;
  state.aoi = e.target.value; state.bbox = null; syncAoiSelect(); load();
});
window.addEventListener("resize", () => {
  clearTimeout(window._rz);
  window._rz = setTimeout(() => { renderChart(); if (state.season && state.season.clim && state.season.clim.status === "ok") renderProfile(state.season.clim); }, 150);
});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (countriesLayer) countriesLayer.setStyle(countryStyle);
  if (state.data) showAoi(state.data.aoi.grid_bbox || state.data.aoi.bbox);
});

(async function boot() {
  readHash();
  initMap();
  renderFilters();
  try {
    state.aois = await (await fetch(`${API}/aois`)).json();
  } catch { state.aois = []; }
  if (!state.bbox && !state.aois.some((a) => a.name === state.aoi) && state.aois.length) state.aoi = state.aois[0].name;
  syncAoiSelect();
  load();
})();

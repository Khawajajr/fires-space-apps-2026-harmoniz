"use strict";
// F.I.R.E.S. burning activity calendar. Plain JS, no build step, vendored libs only (works offline).

const API = "/api";
const DAY_MS = 86400000;
const MONTH_START_DOY = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];   // non-leap year
const UNITS = ["week", "day"];
const METRICS = ["cell_days", "detections"];
const RAMP_STEPS = 6;
const MIN_BOX_DEG = 0.25;

const VIEWS = ["harmonized", "raw"];
const state = { aois: [], aoi: "levant", bbox: null, view: "harmonized", sensor: "NOAA-20-VIIRS", unit: "week",
                metric: "cell_days", lang: "en", data: null, request: null };
const $ = (id) => document.getElementById(id);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const fmt = new Intl.NumberFormat("en", { maximumFractionDigits: 1 });
const fmt3 = new Intl.NumberFormat("en", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

// ---------- language: every string, English and Arabic, is in i18n/strings.json (shared with the API) ----------
let STRINGS = { en: {}, ar: {} };
// In Arabic every inserted value is wrapped in a first-strong isolate (U+2068 .. U+2069): dates, number ranges and
// sensor names keep their own order inside right-to-left text ("2026-11-14" would otherwise show as "14-11-2026").
const isolate = (v) => (state.lang === "ar" ? `\u2068${v}\u2069` : String(v));
function t(key, params = {}) {
  const text = (STRINGS[state.lang] || {})[key] ?? STRINGS.en[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (m, k) => (k in params ? isolate(params[k]) : m));
}
const month = (i) => t(`ui.month.${i + 1}`);
function applyLang() {
  const root = document.documentElement;
  root.lang = state.lang;
  root.dir = state.lang === "ar" ? "rtl" : "ltr";
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-aria]").forEach((el) => el.setAttribute("aria-label", t(el.dataset.i18nAria)));
  $("table-btn").textContent = t($("table-wrap").hidden ? "ui.show_table" : "ui.hide_table");
}
const savedLang = () => { try { return localStorage.getItem("fires.lang"); } catch { return null; } };
const saveLang = (l) => { try { localStorage.setItem("fires.lang", l); } catch { /* private window: not remembered */ } };

// ---------- URL state (shareable links) ----------
function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  if (p.get("bbox")) { state.bbox = p.get("bbox").split(",").map(Number); state.aoi = null; }
  else if (p.get("aoi")) state.aoi = p.get("aoi");
  for (const k of ["view", "sensor", "unit", "metric"]) if (p.get(k)) state[k] = p.get(k);
  const lang = p.get("lang") || savedLang();
  if (lang === "en" || lang === "ar") state.lang = lang;
}
function writeHash() {
  const p = new URLSearchParams();
  if (state.bbox) p.set("bbox", state.bbox.join(",")); else p.set("aoi", state.aoi);
  p.set("view", state.view); p.set("sensor", state.sensor); p.set("unit", state.unit); p.set("metric", state.metric);
  if (state.lang !== "en") p.set("lang", state.lang);
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
  segmented($("view-seg"), VIEWS.map((v) => [v, t(`ui.view.${v}`)]), state.view, (v) => { state.view = v; load(); });
  $("sensor-seg").hidden = harmonizedView();
  segmented($("sensor-seg"), sensors, state.sensor, (v) => { state.sensor = v; load(); });
  segmented($("unit-seg"), UNITS.map((u) => [u, t(`ui.unit.${u}`)]), state.unit, (v) => { state.unit = v; load(); });
  segmented($("metric-seg"), METRICS.map((m) => [m, t(`ui.metric.${m}`)]), state.metric, (v) => { state.metric = v; load(); });
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
  }).catch(() => setStatus(t("ui.basemap_missing")));
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
    if (east - w < MIN_BOX_DEG || n - s < MIN_BOX_DEG) { setStatus(t("ui.box_too_small")); return; }
    state.bbox = [w, s, east, n]; state.aoi = null; syncAoiSelect(); load();
  });
}

// ---------- AOI select ----------
function syncAoiSelect() {
  const sel = $("aoi-select");
  sel.innerHTML = "";
  for (const a of state.aois) sel.add(new Option(a.label, a.name, false, a.name === state.aoi));
  if (state.bbox) sel.add(new Option(t("ui.custom_box", { bbox: state.bbox.join(", ") }), "__custom", false, true));
}

// ---------- data ----------
function setStatus(msg) { $("status").textContent = msg || ""; }

async function load() {
  writeHash(); renderFilters();
  const params = new URLSearchParams({ unit: state.unit, metric: state.metric, lang: state.lang });
  if (state.bbox) params.set("bbox", state.bbox.join(",")); else params.set("aoi", state.aoi);
  if (state.request) state.request.abort();
  const ctrl = new AbortController(); state.request = ctrl;
  setStatus(t("ui.loading"));
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
    loadRisk(body.aoi.grid_bbox || body.aoi.bbox, ctrl);
  } catch (err) {
    if (err.name !== "AbortError") setStatus(t("ui.load_failed", { err: err.message }));
  }
}

// ---------- periods ----------
function isoWeekStart(year, week) {               // Monday of ISO week `week` of ISO year `year`
  const jan4 = Date.UTC(year, 0, 4);
  const dow = new Date(jan4).getUTCDay() || 7;
  return jan4 - (dow - 1) * DAY_MS + (week - 1) * 7 * DAY_MS;
}
// Arabic month names, Western digits ("-u-nu-latn"), in Arabic; British English otherwise.
const dateFmt = (ms, opts) => new Date(ms).toLocaleDateString(state.lang === "ar" ? "ar-u-nu-latn" : "en-GB",
                                                              { timeZone: "UTC", ...opts });
function periodLabel(unit, year, p) {
  if (unit === "week") {
    const a = isoWeekStart(year, p + 1), b = a + 6 * DAY_MS;
    return t("ui.week_label", { n: p + 1, from: dateFmt(a, { day: "numeric", month: "short" }),
                                to: dateFmt(b, { day: "numeric", month: "short", year: "numeric" }) });
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
    b.innerHTML = `<strong>${esc(t("ui.badge.unavailable_title"))}:</strong> ${esc(d.harmonized_unavailable)}. ` +
      esc(t("ui.badge.showing", { sensor: state.sensor }));
    b.hidden = false; return;
  }
  if (harmonizedView()) {
    const h = d.harmonized;
    b.innerHTML = `<strong>${esc(t(h.provisional ? "ui.badge.provisional" : "ui.badge.harmonized"))}:</strong> ${esc(h.label)}, ` +
      `${esc(t("ui.badge.method", { method: h.method }))}. ${esc(h.band_note)}.<ul>${h.caveats.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>`;
    b.hidden = false; return;
  }
  const s = series();
  b.hidden = !s.note;
  if (s.note) b.innerHTML = `<strong>${esc(s.sensor)}:</strong> ${esc(s.note)}`;
}

// ---------- chart ----------
function renderAll() {
  const d = state.data;
  const label = d.aoi.name ? d.aoi.label : t("ui.custom_box_short");
  const what = harmonizedView() ? t("ui.what_harmonized") : t("ui.what_sensor", { metric: t(`ui.metric_lc.${d.metric}`), sensor: state.sensor });
  $("chart-title").textContent = t("ui.chart_title", { label, what, unit: t(`ui.per.${d.unit}`) });
  $("chart-sub").textContent = t("ui.chart_sub", { metric: d.metric_label, from: d.data_range[0], to: d.data_range[1] });
  renderFilters();
  renderBadge();
  $("aoi-summary").textContent = t("ui.aoi_summary", { n: fmt.format(d.aoi.cells) }) +
    (d.aoi.grid_bbox ? ` · ${isolate(`[${d.aoi.grid_bbox.join(", ")}]`)}` : ` · ${t("ui.no_cell_centre")}`);
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
  svg.setAttribute("aria-label", t("ui.chart_aria", { name: s.name, metric: d.metric_label, unit: t(`ui.per.${d.unit}`) }));
  svg.innerHTML = `<defs><pattern id="hatch" patternUnits="userSpaceOnUse" width="5" height="5" patternTransform="rotate(45)">
      <rect width="5" height="5" style="fill:var(--surface-1)"/><line x1="0" y1="0" x2="0" y2="5" style="stroke:var(--hatch);stroke-width:1.4"/></pattern></defs>`;

  // month ticks
  MONTH_START_DOY.forEach((doy, i) => {
    const p = week ? Math.floor((doy - 1) / 7) : doy - 1;
    const t = document.createElementNS(ns, "text");
    t.setAttribute("x", left + p * cw); t.setAttribute("y", 14); t.setAttribute("class", "axis");
    t.textContent = month(i); svg.appendChild(t);
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
  const unitLabel = s.harmonized ? t("ui.what_harmonized") : t(`ui.metric_lc.${d.metric}`);
  const estimated = s.harmonized && s.estimated[yi][p] > 0;
  const zeroText = t(s.harmonized && estimated ? "ui.tip.zero_est" : "ui.tip.zero_obs");
  const valueLine = v === null
    ? `<strong>${esc(t("ui.tip.no_data"))}</strong> <span class=muted>${esc(t("ui.tip.no_data_note"))}</span>`
    : `<strong>${fmt.format(v)}</strong> ${esc(unitLabel)}${v === 0 ? ` <span class=muted>${esc(zeroText)}</span>` : ""}` +
      (s.harmonized ? `<br><span class=muted>${esc(estimated ? t("ui.tip.estimate", { n: s.estimated[yi][p], m: s.data_days[yi][p] }) : t("ui.tip.observed"))}</span>` : "");
  const covLine = cov === "partial"
    ? `<br><span class=muted>${esc(t("ui.tip.partial", { n: s.data_days[yi][p], m: d.period_days }))}</span>` : "";
  const bandLine = s.harmonized && v !== null
    ? (s.lo[yi][p] === null ? "" : `<br><span class=muted>${esc(t("ui.tip.range", { lo: fmt.format(s.lo[yi][p]), hi: fmt.format(s.hi[yi][p]) }))}</span>`) +
      (s.substituted[yi][p] ? `<br><span class=muted>${esc(t("ui.tip.substituted", { n: s.substituted[yi][p], sources: s.sources.slice(1).join(" / "), missing: s.sources[0] }))}</span>` : "")
    : "";
  tip.innerHTML = `${esc(periodLabel(d.unit, d.years[yi], p))}<br>${valueLine}${bandLine}${covLine}<br><span class=muted>${esc(s.name)}</span>`;
  tip.hidden = false;
  const x = state.lang === "ar" ? Math.max(8, e.clientX - tip.offsetWidth - 14)
                                : Math.min(window.innerWidth - tip.offsetWidth - 8, e.clientX + 14);
  tip.style.left = `${x}px`; tip.style.top = `${e.clientY + 14}px`;
}

function renderLegend(thresholds, d) {
  const s = series();
  const unitLabel = s.harmonized ? t("ui.what_harmonized") : t(`ui.metric_lc.${d.metric}`);
  const n = thresholds.length + 1;
  const lows = [0, ...thresholds];
  const steps = lows.map((lo, i) => `<span class="step"><span class="sw" style="background:${binColor(i, n)}"></span>` +
    `<span class="tick">${i === 0 ? "&gt;0" : "&gt;" + fmt.format(lo)}</span></span>`).join("");
  const anyFire = s.values.flat().some((v) => v > 0);
  $("legend").innerHTML = (anyFire ? `
    <span class="item"><span class="ramp">${steps}</span></span><span class="item muted">${esc(unitLabel)}${s.harmonized ? "" : ", " + esc(state.sensor)}</span>` : "") + `
    <span class="item"><span class="sw" style="background:var(--zero)"></span>${esc(t(s.harmonized ? "ui.legend.zero_harmonized" : "ui.legend.zero_raw"))}</span>
    <span class="item"><svg width="22" height="12" aria-hidden="true"><rect width="22" height="12" rx="2" fill="url(#hatch)"/></svg>${esc(t("ui.legend.no_data"))}</span>
    <span class="item"><svg width="22" height="12" aria-hidden="true"><rect width="22" height="12" rx="2" style="fill:var(--fire-3)"/><rect width="22" height="3" style="fill:var(--text-primary)"/></svg>${esc(t("ui.legend.partial"))}</span>`;
}

// ---------- season panels (climatology, critical periods, unusual weeks) ----------
async function loadSeason(params, ctrl) {
  const q = new URLSearchParams({ series: harmonizedView() ? "harmonized" : state.sensor, lang: state.lang });
  if (params.get("bbox")) q.set("bbox", params.get("bbox")); else q.set("aoi", params.get("aoi"));
  try {
    const get = (ep) => fetch(`${API}/calendar/${ep}?${q}`, { signal: ctrl.signal })
      .then(async (r) => (r.ok ? r.json() : { error: (await r.json().catch(() => ({}))).detail || r.statusText }));
    const [clim, crit, anom, now] = await Promise.all(["climatology", "critical-periods", "anomalies", "now"].map(get));
    state.season = { clim, crit, anom, now };
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
  renderNow(s.now, empty);
  const failed = s.error || [s.clim, s.crit, s.anom].find((x) => x.error);
  if (failed) {
    const msg = s.error || failed.error;
    for (const id of ["season-chart", "periods", "anomalies"]) $(id).innerHTML = empty(msg);
    $("season-sub").textContent = "";
    return;
  }
  const c = s.clim;
  $("season-sub").textContent = t("ui.season_sub", { label: c.series_label, n: c.history_years.length }) +
    (c.history_years.length ? ` (${[...new Set([c.history_years[0], c.history_years[c.history_years.length - 1]])].join("–")})` : "") +
    (c.gate_rule ? `. ${t("ui.season_rule", { rule: t(`ui.rule.${c.gate_rule}`) })}` : "") + ".";
  if (c.status !== "ok") {
    for (const id of ["season-chart", "periods", "anomalies"]) $(id).innerHTML = empty(c.message);
    return;
  }
  renderProfile(c);
  $("periods").innerHTML = s.crit.all_year
    ? empty(s.crit.summary)
    : s.crit.periods.length
    ? `<ol>${s.crit.periods.slice(0, 5).map((p) => `<li><strong>${esc(p.label)}</strong> · ` +
        `${esc(t("ui.period_item", { weeks: p.weeks, share: Math.round(p.share_of_year * 100), peak: p.peak_week }))}</li>`).join("")}</ol>`
    : empty(s.crit.message || t("ui.no_period"));
  $("anomalies").innerHTML = s.anom.anomalies.length
    ? `<ul>${s.anom.anomalies.slice(0, 8).map((a) => `<li><strong>${esc(t("ui.anomaly_head", { year: a.year, week: a.week }))}</strong> ` +
        esc(t("ui.anomaly_body", { start: a.week_start, value: fmt.format(a.value), median: fmt.format(a.median) })) +
        `${a.z !== null ? ` (z ${fmt.format(a.z)})` : ""}</li>`).join("")}</ul>`
    : empty(t("ui.no_anomalies"));
}

function renderNow(n, empty) {
  if (!n || n.error) { $("now").innerHTML = empty((n && n.error) || t("ui.not_available")); return; }
  const when = n.week ? t("ui.now.when", { week: n.week, year: n.year, from: n.week_start, to: n.week_end }) : "";
  if (n.status !== "ok") {
    const scaled = n.data_days < 7 ? t("ui.now.scaled", { n: n.data_days }) : "";
    $("now").innerHTML = `${when ? `<p class="now-summary">${esc(t(n.series === "harmonized" ? "ui.now.value_harmonized" : "ui.now.value_raw",
      { when, value: fmt.format(n.value), scaled }))}</p>` : ""}` + empty(n.message);
    return;
  }
  const top = Math.max(n.p90, n.value) * 1.15 || 1;
  const pos = (v) => `${Math.min(100, (100 * v) / top).toFixed(1)}%`;
  $("now").innerHTML = `<p class="now-level">${esc(t(`ui.level.${n.level}`))}</p>
    <p class="now-summary">${esc(n.summary)}</p>
    <div class="now-scale" role="img" aria-label="${esc(t("ui.now.scale_aria", { p10: fmt.format(n.p10), p90: fmt.format(n.p90), value: fmt.format(n.value) }))}">
      <div class="range" style="left:${pos(n.p10)};width:calc(${pos(n.p90)} - ${pos(n.p10)})"></div>
      <div class="mark" style="left:${pos(n.value)}"></div></div>
    <p class="hint">${esc(t("ui.now.hint"))}</p>`;
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
  const ticks = MONTH_START_DOY.map((doy, i) => `<text class="axis" x="${x(Math.floor((doy - 1) / 7) + 1)}" y="${H - 6}">${esc(month(i))}</text>`).join("");
  const yt = [0, ymax / 2, ymax].map((v) => `<text class="axis" x="0" y="${y(v) + 4}">${fmt.format(v)}</text>`).join("");
  $("season-chart").innerHTML = `<svg xmlns="${ns}" width="${W}" height="${H}" role="img" aria-label="${esc(t("ui.profile.aria", { year: latestYear }))}">
    ${gated}<path class="band" d="${bandPath}"/>
    <path class="median" d="${path(c.weeks.map((w) => [x(w.week), w.median]))}"/>
    <path class="latest" d="${path(latestRow.slice(0, 52).map((v, i) => [x(i + 1), v]))}"/>${ticks}${yt}</svg>
    <p class="hint">${esc(t("ui.profile.hint", { latest: comparable ? t("ui.profile.latest", { year: latestYear }) : "" }))}</p>`;
}

// ---------- next 7 days: risk ----------
const RISK_LEVELS = ["low", "moderate", "high", "very_high", "extreme"];
const riskColor = (level) => `var(--fire-${RISK_LEVELS.indexOf(level) + 2})`;
let riskLayer = null;

async function loadRisk(bbox, ctrl) {
  try {
    const [map, health, meta] = await Promise.all([
      fetch(`${API}/predictions/risk-map?min_risk=0&bbox=${bbox.join(",")}`, { signal: ctrl.signal }).then((r) => r.json()),
      fetch(`${API}/health`, { signal: ctrl.signal }).then((r) => r.json()),
      fetch(`${API}/meta`, { signal: ctrl.signal }).then((r) => r.json()),
    ]);
    state.risk = { map, health, meta };
  } catch (err) {
    if (err.name === "AbortError") return;
    state.risk = { error: err.message };
  }
  renderRisk();
}

function renderRisk() {
  const r = state.risk, el = $("risk");
  if (!r) return;
  if (r.error || !r.map || !r.map.points || !r.health || !r.health.model || !r.health.model.validation) {
    el.innerHTML = `<p class="empty">${esc(t("ui.risk.unavailable", { err: r.error ? `: ${r.error}` : "" }))}</p>`;
    return;
  }
  const m = r.map, counts = Object.fromEntries(RISK_LEVELS.map((l) => [l, 0]));
  m.levels.forEach((l) => { counts[l] += 1; });
  const top = m.points.slice(0, 5).map((p, i) => `<li>${fmt.format(p[0])}°, ${fmt.format(p[1])}°: ` +
    `<strong>${Math.round(p[2] * 100)}%</strong> (${esc(t(`ui.risk_level.${m.levels[i]}`))})</li>`).join("");
  const rows = r.health.model.validation;
  const model = rows[0], base = rows.find((x) => /persistence|burned in last/i.test(x.model));
  const info = (r.meta && r.meta.model) || {};
  const where = info.test_scored ? t("ui.risk.where_test", { blocks: (info.blocks && info.blocks.test || []).join(" – ") })
                                 : t("ui.risk.where_validation");
  const skill = base ? t("ui.risk.skill", { where, a: fmt3.format(model.roc_auc), b: fmt3.format(base.roc_auc),
                                            c: fmt3.format(model.brier), d: fmt3.format(base.brier) }) : "";
  const first = new Date(Date.parse(m.issued) + DAY_MS).toISOString().slice(0, 10);
  el.innerHTML = `<p class="hint">${esc(t("ui.risk.issued", { issued: m.issued, from: first, to: m.valid_through, deg: m.cell_deg }))}</p>
    <div class="risk-levels">${RISK_LEVELS.map((l) => `<span><i style="background:${riskColor(l)}"></i>` +
      `${esc(t(`ui.risk_level.${l}`))}: ${counts[l]}</span>`).join("")}</div>
    ${m.count ? `<ol>${top}</ol>` : `<p class="empty">${esc(t("ui.risk.none"))}</p>`}
    <p class="hint">${esc(model.model)}: ${esc(skill)} ${esc(t("ui.risk.note"))}</p>`;
  drawRiskLayer();
}

function drawRiskLayer() {
  if (riskLayer) { map.removeLayer(riskLayer); riskLayer = null; }
  const r = state.risk;
  if (!$("risk-layer").checked || !r || !r.map || !r.map.points) return;
  const h = r.map.cell_deg / 2;
  riskLayer = L.layerGroup(r.map.points.slice(0, 1500).map((p, i) => L.rectangle([[p[0] - h, p[1] - h], [p[0] + h, p[1] + h]], {
    stroke: false, fillColor: getComputedStyle(document.documentElement).getPropertyValue(`--fire-${RISK_LEVELS.indexOf(r.map.levels[i]) + 2}`).trim(),
    fillOpacity: 0.75, interactive: false }))).addTo(map);
}
$("risk-layer").addEventListener("change", drawRiskLayer);

// ---------- table view ----------
function renderTable() {
  const d = state.data, s = series();
  const rows = [];
  for (let p = 0; p < d.periods; p++) {
    const cells = d.years.map((_, yi) => s.values[yi][p]);
    if (cells.every((v) => v === null)) continue;
    const name = t(d.unit === "week" ? "ui.table.week" : "ui.table.day", { n: p + 1 });
    rows.push(`<tr><td>${esc(name)}</td>${cells.map((v, yi) => `<td>${v === null ? (s.coverage[yi][p] === "absent" ? "" : esc(t("ui.table.no_data"))) : fmt.format(v)}${
      v !== null && s.harmonized && s.lo[yi][p] !== null ? ` (${fmt.format(s.lo[yi][p])}–${fmt.format(s.hi[yi][p])})` : ""}${
      v !== null && s.coverage[yi][p] === "partial" ? " *" : ""}</td>`).join("")}</tr>`);
  }
  $("table-wrap").innerHTML = `<table><caption class="hint" style="caption-side:bottom;text-align:left;padding:4px 8px">
    ${esc(t("ui.table.caption", { name: s.name, metric: d.metric_label, brackets: s.harmonized ? t("ui.table.brackets") : "" }))}</caption>
    <thead><tr><th>${esc(t(d.unit === "week" ? "ui.table.iso_week" : "ui.table.day_col"))}</th>${d.years.map((y) => `<th>${y}</th>`).join("")}</tr></thead>
    <tbody>${rows.join("") || `<tr><td colspan="${d.years.length + 1}">${esc(t("ui.table.empty"))}</td></tr>`}</tbody></table>`;
}
$("table-btn").addEventListener("click", () => {
  const wrap = $("table-wrap"), show = wrap.hidden;
  wrap.hidden = !show; $("table-btn").setAttribute("aria-expanded", String(show));
  $("table-btn").textContent = t(show ? "ui.hide_table" : "ui.show_table");
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

async function fetchAois() {
  try { return await (await fetch(`${API}/aois?lang=${state.lang}`)).json(); } catch { return []; }
}
$("lang-btn").addEventListener("click", async () => {
  state.lang = state.lang === "ar" ? "en" : "ar";
  saveLang(state.lang);
  applyLang();
  state.aois = await fetchAois();
  syncAoiSelect();
  load();
});

(async function boot() {
  readHash();
  try { STRINGS = await (await fetch("i18n/strings.json")).json(); } catch { /* English labels in the HTML remain */ }
  applyLang();
  initMap();
  renderFilters();
  state.aois = await fetchAois();
  if (!state.bbox && !state.aois.some((a) => a.name === state.aoi) && state.aois.length) state.aoi = state.aois[0].name;
  syncAoiSelect();
  load();
})();

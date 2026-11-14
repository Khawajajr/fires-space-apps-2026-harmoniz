"use strict";
// Static snapshot only (site/, built by `godseye build-site`; the live app never loads this file).
// Answers fetch("/api/...") from the JSON files saved next to the page; anything not saved (a drawn box) gets a
// message that drawing needs the full app. Runs before app.js, so it may use app.js globals (t, state) at call time.

(function () {
  const realFetch = window.fetch.bind(window);
  const say = (key, en, params) => {
    try { const s = t(key, params); if (s !== key) return s; } catch { /* strings not loaded yet */ }
    return en;
  };
  const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

  function fileFor(url) {
    const u = new URL(url, location.href);
    const endpoint = u.pathname.replace(/^.*?\/api\//, "");
    const keys = [...u.searchParams.keys()].sort();
    const query = keys.map((k) => `${k}=${u.searchParams.get(k)}`).join("&") || "index";
    return { endpoint, drawn: u.searchParams.has("bbox") && endpoint !== "predictions/risk-map",
             path: `data/api/${endpoint}/${encodeURIComponent(query)}.json` };
  }

  window.fetch = async function (input, init) {
    const url = typeof input === "string" ? input : input.url;
    if (!/^\/api\/|\/api\//.test(new URL(url, location.href).pathname)) return realFetch(input, init);
    const f = fileFor(url);
    const drawMsg = say("ui.snapshot.draw", "Drawing a box needs the full app (see the repository README). " +
                        "This snapshot has the named areas only.");
    const notSaved = () => {
      setTimeout(() => { document.getElementById("chart-title").textContent = ""; }, 0);   // not "Loading…"
      return json(404, { detail: drawMsg });
    };
    if (f.drawn) return notSaved();
    const r = await realFetch(f.path, init);
    if (!r.ok) return notSaved();
    const saved = await r.json();
    return json(saved.status, saved.body);
  };

  // A banner saying what this page is, in the current language (app.js re-renders labels on language change).
  function banner() {
    let el = document.getElementById("snapshot-banner");
    if (!el) {
      el = document.createElement("p");
      el.id = "snapshot-banner";
      el.className = "snapshot-banner";
      el.setAttribute("role", "note");
      document.body.prepend(el);
    }
    realFetch("data/snapshot.json").then((r) => r.json()).then((s) => {
      el.textContent = say("ui.snapshot.banner",
        `Static snapshot built ${s.built}: the named areas only, as the live app answered them that day. ` +
        "Drawing a box needs the full app (see the repository README).", { built: s.built });
    }).catch(() => {});
  }
  document.addEventListener("DOMContentLoaded", () => {
    banner();
    document.getElementById("lang-btn").addEventListener("click", () => setTimeout(banner, 0));
  });
})();

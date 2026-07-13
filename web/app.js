/* svcoverage cockpit — control surface for street-level coverage extraction.
   The Google extraction can't run in a browser (undocumented, CORS-blocked, Python-only),
   so this page views/plans/compares; live Mapillary and (via a self-hosted proxy) Google
   are the in-browser data paths. */
(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const root = document.documentElement;
  const COLORS = { google: "#4285f4", mapillary: "#22c55e", kartaview: "#f59e0b", diff: "#ec4899" };

  // ---------- theme ----------
  const savedTheme = localStorage.getItem("svc-theme");
  if (savedTheme) root.dataset.theme = savedTheme;
  const isDark = () =>
    root.dataset.theme ? root.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;

  $("#theme-toggle").addEventListener("click", () => {
    const next = isDark() ? "light" : "dark";
    root.dataset.theme = next;
    localStorage.setItem("svc-theme", next);
    applyBasemapTheme();   // just toggle basemap visibility — never wipe data layers
  });

  // ---------- state ----------
  const state = {
    coverage: null,   // loaded/proxy GeoJSON FeatureCollection (may mix sources)
    diff: null,       // computed diff FeatureCollection
    mapillaryOn: false,
    mapillaryToken: localStorage.getItem("svc-mly-token") || "",
    proxyUrl: localStorage.getItem("svc-proxy-url") || "",
    bbox: null,       // [w, s, e, n]
    visible: { google: true, mapillary: true, kartaview: true, "mapillary-live": true, diff: true },
  };

  // ---------- map ----------
  const CARTO = {
    light: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
    dark: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
  };
  const CARTO_ATTR = '© <a href="https://openstreetmap.org/copyright">OpenStreetMap</a> © <a href="https://carto.com/attributions">CARTO</a>';
  const cartoTiles = (k) => ["a", "b", "c"].map((s) => CARTO[k].replace("{s}", s));
  // Both basemaps are always present; the theme toggle just flips their visibility, so the
  // coverage/mapillary/diff layers on top are never destroyed (setStyle would wipe them).
  function basemapStyle() {
    return {
      version: 8,
      sources: {
        "base-light": { type: "raster", tiles: cartoTiles("light"), tileSize: 256, attribution: CARTO_ATTR },
        "base-dark": { type: "raster", tiles: cartoTiles("dark"), tileSize: 256, attribution: CARTO_ATTR },
      },
      layers: [
        { id: "base-light", type: "raster", source: "base-light", layout: { visibility: isDark() ? "none" : "visible" } },
        { id: "base-dark", type: "raster", source: "base-dark", layout: { visibility: isDark() ? "visible" : "none" } },
      ],
    };
  }
  function applyBasemapTheme() {
    if (map.getLayer("base-light")) map.setLayoutProperty("base-light", "visibility", isDark() ? "none" : "visible");
    if (map.getLayer("base-dark")) map.setLayoutProperty("base-dark", "visibility", isDark() ? "visible" : "none");
  }

  const map = new maplibregl.Map({
    container: "map",
    style: basemapStyle(),
    center: [26.085, 44.436],
    zoom: 12,
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: "metric" }), "bottom-right");

  const LINE_WIDTH = ["interpolate", ["linear"], ["zoom"], 10, 1.4, 14, 2.6, 18, 5];

  function addDataLayers() {
    // bbox rectangle
    if (!map.getSource("bbox")) {
      map.addSource("bbox", { type: "geojson", data: emptyFC() });
      map.addLayer({ id: "bbox-fill", type: "fill", source: "bbox",
        paint: { "fill-color": COLORS.google, "fill-opacity": 0.06 } });
      map.addLayer({ id: "bbox-line", type: "line", source: "bbox",
        paint: { "line-color": COLORS.google, "line-width": 1.5, "line-dasharray": [2, 2] } });
    }
    if (state.bbox) drawBboxRect(state.bbox);

    // coverage (mixed-source, colored by properties.source)
    if (state.coverage) {
      map.addSource("coverage", { type: "geojson", data: state.coverage });
      map.addLayer({
        id: "coverage-line", type: "line", source: "coverage",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": ["match", ["get", "source"],
            "google", COLORS.google, "mapillary", COLORS.mapillary, "kartaview", COLORS.kartaview, "#8b97a8"],
          "line-width": LINE_WIDTH, "line-opacity": 0.9,
        },
      });
    }

    // live Mapillary vector tiles
    if (state.mapillaryOn && state.mapillaryToken) {
      map.addSource("mly", {
        type: "vector", minzoom: 6, maxzoom: 14,
        tiles: [`https://tiles.mapillary.com/maps/vtp/mly1_public/2/{z}/{x}/{y}?access_token=${encodeURIComponent(state.mapillaryToken)}`],
      });
      map.addLayer({
        id: "mly-live", type: "line", source: "mly", "source-layer": "sequence",
        paint: { "line-color": COLORS.mapillary, "line-width": LINE_WIDTH, "line-opacity": 0.65 },
      });
    }

    // diff highlight
    if (state.diff) {
      map.addSource("diff", { type: "geojson", data: state.diff });
      map.addLayer({ id: "diff-line", type: "line", source: "diff",
        paint: { "line-color": COLORS.diff, "line-width": ["interpolate", ["linear"], ["zoom"], 10, 3, 16, 7], "line-opacity": 0.9 } });
    }

    applyVisibility();
  }
  map.on("load", addDataLayers);

  function refreshCoverage() {
    if (map.getLayer("coverage-line")) map.removeLayer("coverage-line");
    if (map.getSource("coverage")) map.removeSource("coverage");
    if (map.getLayer("diff-line")) map.removeLayer("diff-line");
    if (map.getSource("diff")) map.removeSource("diff");
    state.diff = null;
    addDataLayers();
    renderLegend();
  }

  // ---------- bbox draw (shift-drag) + "use view" ----------
  map.boxZoom.disable();
  let drawing = false, startLngLat = null;
  map.on("mousedown", (e) => {
    if (!e.originalEvent.shiftKey) return;
    drawing = true; startLngLat = e.lngLat; map.dragPan.disable();
    map.getCanvas().style.cursor = "crosshair";
  });
  map.on("mousemove", (e) => {
    if (!drawing) return;
    drawBboxRect(bboxFrom(startLngLat, e.lngLat));
  });
  map.on("mouseup", (e) => {
    if (!drawing) return;
    drawing = false; map.dragPan.enable(); map.getCanvas().style.cursor = "";
    setBbox(bboxFrom(startLngLat, e.lngLat));
  });

  function bboxFrom(a, b) {
    return [Math.min(a.lng, b.lng), Math.min(a.lat, b.lat), Math.max(a.lng, b.lng), Math.max(a.lat, b.lat)];
  }
  function drawBboxRect(bb) {
    const [w, s, e, n] = bb;
    const poly = { type: "FeatureCollection", features: [{ type: "Feature", geometry: {
      type: "Polygon", coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] }, properties: {} }] };
    const src = map.getSource("bbox");
    if (src) src.setData(poly);
  }
  function setBbox(bb) {
    state.bbox = bb.map((v) => +v.toFixed(6));
    $("#bbox-input").value = state.bbox.join(",");
    drawBboxRect(state.bbox);
    updateCommand();
  }
  $("#use-view").addEventListener("click", () => {
    const b = map.getBounds();
    setBbox([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]);
  });
  $("#bbox-input").addEventListener("change", (e) => {
    const parts = e.target.value.split(",").map(Number);
    if (parts.length === 4 && parts.every((n) => !Number.isNaN(n))) setBbox(parts);
  });

  // ---------- mode tabs ----------
  $("#mode-tabs").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-mode]");
    if (!btn) return;
    document.querySelectorAll("#mode-tabs button").forEach((b) => b.classList.toggle("is-active", b === btn));
    document.querySelectorAll(".mode-body").forEach((b) => { b.hidden = b.dataset.body !== btn.dataset.mode; });
  });

  // ---------- file load ----------
  const drop = $("#filedrop");
  const fileInput = $("#file-input");
  drop.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", (e) => e.target.files[0] && readFile(e.target.files[0]));
  ["dragover", "dragenter"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, () => drop.classList.remove("drag")));
  drop.addEventListener("drop", (e) => { e.preventDefault(); e.dataTransfer.files[0] && readFile(e.dataTransfer.files[0]); });
  // allow dropping anywhere on the map too
  const mapEl = $("#map");
  ["dragover"].forEach((ev) => mapEl.addEventListener(ev, (e) => e.preventDefault()));
  mapEl.addEventListener("drop", (e) => { e.preventDefault(); e.dataTransfer.files[0] && readFile(e.dataTransfer.files[0]); });

  function readFile(file) {
    const reader = new FileReader();
    reader.onload = () => {
      try { loadCoverage(JSON.parse(reader.result), file.name); }
      catch (err) { toast("Couldn't parse that file as GeoJSON.", "err"); }
    };
    reader.readAsText(file);
  }
  $("#load-sample").addEventListener("click", async () => {
    try {
      const r = await fetch("samples/bucharest-sample.geojson");
      if (!r.ok) throw new Error(r.status);
      loadCoverage(await r.json(), "bucharest-sample.geojson");
    } catch (err) { toast("Sample not available on this deployment.", "err"); }
  });

  function loadCoverage(fc, name) {
    if (!fc || fc.type !== "FeatureCollection" || !Array.isArray(fc.features)) {
      toast("That isn't a GeoJSON FeatureCollection.", "err"); return;
    }
    // tag any feature missing a source (so the legend/colors work)
    fc.features.forEach((f) => { if (!f.properties) f.properties = {}; if (!f.properties.source) f.properties.source = "google"; });
    state.coverage = fc;
    refreshCoverage();
    fitTo(fc);
    toast(`Loaded ${fc.features.length} lines from ${name}.`, "ok");
  }

  // ---------- command builder ----------
  function selectedSources() {
    return [...document.querySelectorAll(".src-check:checked")].map((c) => c.value);
  }
  function updateCommand() {
    const bb = state.bbox ? state.bbox.join(",") : "W,S,E,N";
    const srcs = selectedSources().join(",") || "google";
    const prec = $("#precision-check").checked ? " --precision" : "";
    $("#command-out").textContent = `svcoverage extract --bbox ${bb} --sources ${srcs}${prec} --out coverage.geojson`;
  }
  document.querySelectorAll(".src-check, #precision-check").forEach((c) => c.addEventListener("change", updateCommand));
  $("#copy-command").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("#command-out").textContent); toast("Command copied.", "ok"); }
    catch { toast("Copy failed — select and copy manually.", "err"); }
  });
  updateCommand();

  // ---------- live Mapillary ----------
  const tokenInput = $("#mly-token");
  tokenInput.value = state.mapillaryToken;
  $("#mly-enable").addEventListener("click", () => {
    const t = tokenInput.value.trim();
    if (!t.startsWith("MLY")) { toast("Enter a Mapillary token (starts with MLY).", "err"); return; }
    state.mapillaryToken = t; localStorage.setItem("svc-mly-token", t);
    state.mapillaryOn = true; state.visible["mapillary-live"] = true;
    if (map.getLayer("mly-live")) { map.removeLayer("mly-live"); map.removeSource("mly"); }
    addDataLayers(); renderLegend();
    toast("Mapillary layer on — pan/zoom to load coverage.", "ok");
  });

  // ---------- proxy extract ----------
  const proxyInput = $("#proxy-url");
  proxyInput.value = state.proxyUrl;
  $("#proxy-extract").addEventListener("click", async () => {
    const url = proxyInput.value.trim().replace(/\/$/, "");
    if (!url) { toast("Enter your proxy URL first.", "err"); return; }
    state.proxyUrl = url; localStorage.setItem("svc-proxy-url", url);
    const b = map.getBounds();
    const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((v) => +v.toFixed(5)).join(",");
    const sources = [...document.querySelectorAll(".psrc-check:checked")].map((c) => c.value);
    const status = $("#proxy-status");
    status.textContent = "Extracting current view via proxy…";
    try {
      const r = await fetch(`${url}/extract`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ bbox, sources }),
      });
      if (!r.ok) { status.textContent = `Proxy error ${r.status}: ${(await r.text()).slice(0, 140)}`; return; }
      const fc = await r.json();
      status.textContent = `Got ${fc.features.length} lines.`;
      loadCoverage(fc, "proxy");
    } catch (err) {
      status.textContent = "Couldn't reach the proxy (is it running + CORS set to this origin?).";
    }
  });

  // ---------- legend + totals ----------
  function presentSources() {
    const set = new Set();
    if (state.coverage) state.coverage.features.forEach((f) => set.add(f.properties.source || "google"));
    if (state.mapillaryOn) set.add("mapillary-live");
    if (state.diff) set.add("diff");
    return [...set];
  }
  function kmBySource() {
    const km = {};
    if (state.coverage) for (const f of state.coverage.features) {
      const s = f.properties.source || "google";
      km[s] = (km[s] || 0) + (f.properties.length_m || 0) / 1000;
    }
    return km;
  }
  const LABELS = { google: "Google", mapillary: "Mapillary", kartaview: "KartaView", "mapillary-live": "Mapillary (live)", diff: "Diff — gaps" };
  function renderLegend() {
    const ul = $("#legend"); ul.innerHTML = "";
    const km = kmBySource();
    const srcs = presentSources();
    for (const s of srcs) {
      const color = COLORS[s] || COLORS[s.replace("-live", "")] || "#8b97a8";
      const li = document.createElement("li");
      const kmTxt = km[s] != null ? `${km[s].toFixed(2)} km` : "";
      li.innerHTML = `<span class="swatch" style="background:${color}"></span>
        <span>${LABELS[s] || s}</span><span class="km">${kmTxt}</span>
        <input class="toggle" type="checkbox" ${state.visible[s] === false ? "" : "checked"} data-layer="${s}" title="Toggle layer" />`;
      ul.appendChild(li);
    }
    ul.querySelectorAll(".toggle").forEach((t) => t.addEventListener("change", (e) => {
      state.visible[e.target.dataset.layer] = e.target.checked; applyVisibility();
    }));
    const totals = $("#totals");
    if (!srcs.length) { totals.innerHTML = '<span class="muted">No coverage loaded yet.</span>'; return; }
    const totalKm = Object.values(km).reduce((a, b) => a + b, 0);
    const nseg = state.coverage ? state.coverage.features.length : 0;
    totals.textContent = `${nseg} lines · ${totalKm.toFixed(2)} km total`;
  }
  function applyVisibility() {
    const vis = (id, on) => map.getLayer(id) && map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
    // coverage layer is mixed; approximate per-source toggle via filter
    if (map.getLayer("coverage-line")) {
      const hidden = ["google", "mapillary", "kartaview"].filter((s) => state.visible[s] === false);
      map.setFilter("coverage-line", hidden.length ? ["!", ["in", ["get", "source"], ["literal", hidden]]] : null);
    }
    vis("mly-live", state.visible["mapillary-live"] !== false);
    vis("diff-line", state.visible.diff !== false);
  }

  // ---------- coverage diff (turf) ----------
  $("#diff-btn").addEventListener("click", () => {
    if (!state.coverage) { toast("Load coverage first.", "err"); return; }
    const feats = state.coverage.features;
    const g = feats.filter((f) => f.properties.source === "google");
    const m = feats.filter((f) => f.properties.source === "mapillary");
    if (!g.length || !m.length) { toast("Diff needs both Google and Mapillary lines loaded.", "err"); return; }
    try {
      const mBuf = m.map((f) => turf.buffer(f, 20, { units: "meters" })).filter(Boolean);
      const onlyG = g.filter((f) => !mBuf.some((b) => turf.booleanIntersects(f, b)));
      state.diff = { type: "FeatureCollection", features: onlyG };
      state.visible.diff = true;
      if (map.getLayer("diff-line")) { map.removeLayer("diff-line"); map.removeSource("diff"); }
      addDataLayers(); renderLegend();
      toast(`${onlyG.length} Google lines have no Mapillary within 20 m (approx).`, "ok");
    } catch (err) { toast("Diff failed on this data.", "err"); }
  });

  // ---------- export ----------
  $("#export-btn").addEventListener("click", () => {
    if (!state.coverage) { toast("Nothing to export yet.", "err"); return; }
    const blob = new Blob([JSON.stringify(state.coverage)], { type: "application/geo+json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "coverage.geojson"; a.click();
    URL.revokeObjectURL(a.href);
    toast("Exported coverage.geojson.", "ok");
  });

  // ---------- clear ----------
  $("#clear-btn").addEventListener("click", () => {
    state.coverage = null; state.diff = null; state.mapillaryOn = false;
    ["coverage-line", "diff-line", "mly-live"].forEach((id) => map.getLayer(id) && map.removeLayer(id));
    ["coverage", "diff", "mly"].forEach((id) => map.getSource(id) && map.removeSource(id));
    const src = map.getSource("bbox"); if (src) src.setData(emptyFC());
    state.bbox = null; $("#bbox-input").value = ""; updateCommand(); renderLegend();
    toast("Cleared.", "ok");
  });

  // ---------- helpers ----------
  function emptyFC() { return { type: "FeatureCollection", features: [] }; }
  function fitTo(fc) {
    try {
      const b = turf.bbox(fc);
      if (b.every(Number.isFinite)) map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 48, maxZoom: 16, duration: 600 });
    } catch { /* ignore */ }
  }
  function toast(msg, kind) {
    const el = document.createElement("div");
    el.className = `toast ${kind || ""}`; el.textContent = msg;
    $("#toasts").appendChild(el);
    setTimeout(() => el.remove(), 3400);
  }

  // ---------- mobile panel ----------
  $("#panel-toggle").addEventListener("click", () => $("#panel").classList.toggle("open"));

  renderLegend();
})();

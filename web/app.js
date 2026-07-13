/* tracelines cockpit — control surface for street-level coverage extraction.
   Google extraction can't run in a browser (undocumented, CORS-blocked, Python-only), so this
   page views/plans/compares; live Mapillary and (via a self-hosted proxy) Google are the live paths. */
(() => {
  "use strict";

  const $ = (s) => document.querySelector(s);
  const root = document.documentElement;
  const COLORS = { google: "#4285f4", mapillary: "#22c55e", kartaview: "#f59e0b", diff: "#ec4899" };
  const NO_DATE = "#8b97a8";

  // ---------- theme ----------
  const savedTheme = localStorage.getItem("tl-theme");
  if (savedTheme) root.dataset.theme = savedTheme;
  const isDark = () =>
    root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  $("#theme-toggle").addEventListener("click", () => {
    const next = isDark() ? "light" : "dark";
    root.dataset.theme = next;
    localStorage.setItem("tl-theme", next);
    if (state.basemap === "auto") applyBasemap();
  });

  // ---------- state ----------
  const state = {
    coverage: null, diff: null, fullcity: false,
    mapillaryOn: false,
    mapillaryToken: localStorage.getItem("tl-mly-token") || "",
    // Default to the shared hosted demo proxy (Cloud Run, hardened + rate-limited). Override in the
    // Proxy tab to point at your own (see the "Deploy your own proxy" docs). May sleep / rate-limit.
    proxyUrl: localStorage.getItem("tl-proxy-url") || "https://tracelines-proxy-ttfjfqlcwq-ew.a.run.app",
    bbox: null, nearestMode: false, marker: null,
    colorMode: "source", minYear: 2007, opacity: 0.9, basemap: "auto",
    visible: { google: true, mapillary: true, kartaview: true, "mapillary-live": true, diff: true, fullcity: true },
  };

  // ---------- map + basemaps ----------
  const ATTR_OSM = '© <a href="https://openstreetmap.org/copyright">OpenStreetMap</a> © <a href="https://carto.com/attributions">CARTO</a>';
  const ATTR_ESRI = "Imagery © Esri, Maxar, Earthstar Geographics";
  const carto = (k) => ["a", "b", "c"].map((s) => `https://${s}.basemaps.cartocdn.com/${k}/{z}/{x}/{y}.png`);
  function baseStyle() {
    return {
      version: 8,
      sources: {
        "base-light": { type: "raster", tiles: carto("light_all"), tileSize: 256, attribution: ATTR_OSM },
        "base-dark": { type: "raster", tiles: carto("dark_all"), tileSize: 256, attribution: ATTR_OSM },
        "base-sat": { type: "raster", tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"], tileSize: 256, attribution: ATTR_ESRI },
      },
      layers: [
        { id: "base-light", type: "raster", source: "base-light", layout: { visibility: "none" } },
        { id: "base-dark", type: "raster", source: "base-dark", layout: { visibility: "none" } },
        { id: "base-sat", type: "raster", source: "base-sat", layout: { visibility: "none" } },
      ],
    };
  }
  function activeBase() {
    if (state.basemap === "satellite") return "base-sat";
    if (state.basemap === "light") return "base-light";
    if (state.basemap === "dark") return "base-dark";
    return isDark() ? "base-dark" : "base-light";
  }
  function applyBasemap() {
    const on = activeBase();
    for (const id of ["base-light", "base-dark", "base-sat"]) {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", id === on ? "visible" : "none");
    }
  }

  const map = new maplibregl.Map({ container: "map", style: baseStyle(), center: [26.1, 44.44], zoom: 11.5, hash: "map" });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: "metric" }), "bottom-right");

  const LW = ["interpolate", ["linear"], ["zoom"], 10, 1.4, 14, 2.6, 18, 5];
  const YEAR_EXPR = ["case", ["has", "capture_date"], ["to-number", ["slice", ["get", "capture_date"], 0, 4]], 0];

  function colorExpr() {
    if (state.colorMode === "year") {
      return ["case", ["==", YEAR_EXPR, 0], NO_DATE,
        ["interpolate", ["linear"], YEAR_EXPR, 2012, "#5b21b6", 2018, "#2563eb", 2022, "#06b6d4", 2025, "#22c55e"]];
    }
    return ["match", ["get", "source"], "google", COLORS.google, "mapillary", COLORS.mapillary, "kartaview", COLORS.kartaview, NO_DATE];
  }

  function addCoverageLayer(id, sourceId) {
    if (map.getLayer(id)) map.removeLayer(id);
    map.addLayer({
      id, type: "line", source: sourceId,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": colorExpr(), "line-width": LW, "line-opacity": state.opacity },
    });
    map.on("click", id, (e) => inspectLine(e));
    map.on("mouseenter", id, () => { if (!state.nearestMode) map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", id, () => { if (!state.nearestMode) map.getCanvas().style.cursor = ""; });
  }

  function addDataLayers() {
    if (!map.getSource("bbox")) {
      map.addSource("bbox", { type: "geojson", data: emptyFC() });
      map.addLayer({ id: "bbox-fill", type: "fill", source: "bbox", paint: { "fill-color": COLORS.google, "fill-opacity": 0.06 } });
      map.addLayer({ id: "bbox-line", type: "line", source: "bbox", paint: { "line-color": COLORS.google, "line-width": 1.5, "line-dasharray": [2, 2] } });
    }
    if (state.bbox) drawBboxRect(state.bbox);
    if (state.fullcity && map.getSource("fullcity")) addCoverageLayer("fullcity-line", "fullcity");
    if (state.coverage) { map.addSource("coverage", { type: "geojson", data: state.coverage }); addCoverageLayer("coverage-line", "coverage"); }
    if (state.mapillaryOn && state.mapillaryToken) {
      map.addSource("mly", { type: "vector", minzoom: 6, maxzoom: 14, tiles: [`https://tiles.mapillary.com/maps/vtp/mly1_public/2/{z}/{x}/{y}?access_token=${encodeURIComponent(state.mapillaryToken)}`] });
      map.addLayer({ id: "mly-live", type: "line", source: "mly", "source-layer": "sequence", paint: { "line-color": COLORS.mapillary, "line-width": LW, "line-opacity": 0.65 } });
    }
    if (state.diff) { map.addSource("diff", { type: "geojson", data: state.diff }); map.addLayer({ id: "diff-line", type: "line", source: "diff", paint: { "line-color": COLORS.diff, "line-width": ["interpolate", ["linear"], ["zoom"], 10, 3, 16, 7], "line-opacity": 0.9 } }); }
    applyBasemap();
    applyVisibility();
    updatePaint();
  }
  map.on("load", addDataLayers);

  function updatePaint() {
    for (const id of ["coverage-line", "fullcity-line"]) {
      if (map.getLayer(id)) {
        map.setPaintProperty(id, "line-color", colorExpr());
        map.setPaintProperty(id, "line-opacity", state.opacity);
      }
    }
  }

  // ---------- View controls ----------
  $("#basemap-sel").addEventListener("change", (e) => { state.basemap = e.target.value; applyBasemap(); });
  $("#opacity-slider").addEventListener("input", (e) => { state.opacity = +e.target.value; updatePaint(); });
  $("#color-mode").addEventListener("change", (e) => {
    state.colorMode = e.target.value;
    $("#year-row").hidden = state.colorMode !== "year";
    updatePaint(); applyVisibility(); renderLegend();
  });
  $("#year-slider").addEventListener("input", (e) => { state.minYear = +e.target.value; $("#year-val").textContent = state.minYear; applyVisibility(); });

  function applyVisibility() {
    const yearMode = state.colorMode === "year";
    const yfilter = yearMode ? [">=", YEAR_EXPR, state.minYear] : null;
    for (const [layer, srcKeys] of [["coverage-line", ["google", "mapillary", "kartaview"]], ["fullcity-line", ["google"]]]) {
      if (!map.getLayer(layer)) continue;
      const hidden = srcKeys.filter((s) => state.visible[s] === false);
      const parts = [];
      if (hidden.length) parts.push(["!", ["in", ["get", "source"], ["literal", hidden]]]);
      if (yfilter) parts.push(yfilter);
      map.setFilter(layer, parts.length ? ["all", ...parts] : null);
    }
    if (map.getLayer("fullcity-line")) map.setLayoutProperty("fullcity-line", "visibility", state.visible.fullcity === false ? "none" : "visible");
    if (map.getLayer("mly-live")) map.setLayoutProperty("mly-live", "visibility", state.visible["mapillary-live"] === false ? "none" : "visible");
    if (map.getLayer("diff-line")) map.setLayoutProperty("diff-line", "visibility", state.visible.diff === false ? "none" : "visible");
  }

  // ---------- bbox draw ----------
  map.boxZoom.disable();
  let drawing = false, startLL = null;
  map.on("mousedown", (e) => { if (!e.originalEvent.shiftKey) return; drawing = true; startLL = e.lngLat; map.dragPan.disable(); map.getCanvas().style.cursor = "crosshair"; });
  map.on("mousemove", (e) => { if (drawing) drawBboxRect(bboxFrom(startLL, e.lngLat)); });
  map.on("mouseup", (e) => { if (!drawing) return; drawing = false; map.dragPan.enable(); map.getCanvas().style.cursor = ""; setBbox(bboxFrom(startLL, e.lngLat)); });
  const bboxFrom = (a, b) => [Math.min(a.lng, b.lng), Math.min(a.lat, b.lat), Math.max(a.lng, b.lng), Math.max(a.lat, b.lat)];
  function drawBboxRect(bb) {
    const [w, s, e, n] = bb;
    const src = map.getSource("bbox");
    if (src) src.setData({ type: "FeatureCollection", features: [{ type: "Feature", geometry: { type: "Polygon", coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] }, properties: {} }] });
  }
  function setBbox(bb) { state.bbox = bb.map((v) => +v.toFixed(6)); $("#bbox-input").value = state.bbox.join(","); drawBboxRect(state.bbox); updateCommand(); }
  $("#use-view").addEventListener("click", () => { const b = map.getBounds(); setBbox([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]); });
  $("#bbox-input").addEventListener("change", (e) => { const p = e.target.value.split(",").map(Number); if (p.length === 4 && p.every((n) => !Number.isNaN(n))) setBbox(p); });

  // ---------- mode tabs ----------
  $("#mode-tabs").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-mode]"); if (!btn) return;
    document.querySelectorAll("#mode-tabs button").forEach((b) => b.classList.toggle("is-active", b === btn));
    document.querySelectorAll(".mode-body").forEach((b) => { b.hidden = b.dataset.body !== btn.dataset.mode; });
    state.nearestMode = btn.dataset.mode === "nearest";
    map.getCanvas().style.cursor = state.nearestMode ? "crosshair" : "";
  });

  // ---------- file load ----------
  const drop = $("#filedrop"), fileInput = $("#file-input");
  drop.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", (e) => e.target.files[0] && readFile(e.target.files[0]));
  ["dragover", "dragenter"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, () => drop.classList.remove("drag")));
  drop.addEventListener("drop", (e) => { e.preventDefault(); e.dataTransfer.files[0] && readFile(e.dataTransfer.files[0]); });
  $("#map").addEventListener("dragover", (e) => e.preventDefault());
  $("#map").addEventListener("drop", (e) => { e.preventDefault(); e.dataTransfer.files[0] && readFile(e.dataTransfer.files[0]); });
  function readFile(file) {
    const r = new FileReader();
    r.onload = () => { try { loadCoverage(JSON.parse(r.result), file.name); } catch { toast("Couldn't parse that file as GeoJSON.", "err"); } };
    r.readAsText(file);
  }
  $("#load-sample").addEventListener("click", () => fetchGeojson("samples/bucharest-sample.geojson", "bucharest-sample"));
  $("#load-fullcity").addEventListener("click", loadFullCity);
  async function fetchGeojson(url, name) {
    try { const r = await fetch(url); if (!r.ok) throw new Error(r.status); loadCoverage(await r.json(), name); }
    catch { toast("Sample not available on this deployment.", "err"); }
  }
  function loadCoverage(fc, name) {
    if (!fc || fc.type !== "FeatureCollection" || !Array.isArray(fc.features)) { toast("Not a GeoJSON FeatureCollection.", "err"); return; }
    fc.features.forEach((f) => { if (!f.properties) f.properties = {}; if (!f.properties.source) f.properties.source = "google"; });
    state.coverage = fc; refreshCoverage(); fitTo(fc);
    toast(`Loaded ${fc.features.length} lines from ${name}.`, "ok");
  }
  async function loadFullCity() {
    toast("Loading full Bucharest (~0.8 MB)…", "ok");
    try {
      const r = await fetch("samples/bucharest-city-google.geojson"); if (!r.ok) throw new Error(r.status);
      const fc = await r.json();
      if (map.getLayer("fullcity-line")) map.removeLayer("fullcity-line");
      if (map.getSource("fullcity")) map.removeSource("fullcity");
      map.addSource("fullcity", { type: "geojson", data: fc });
      state.fullcity = true; state.fullcityCount = fc.features.length;
      addCoverageLayer("fullcity-line", "fullcity");
      $("#snapshot-banner").hidden = false;
      applyVisibility(); updatePaint(); renderLegend();
      toast(`Full Bucharest: ${fc.features.length.toLocaleString()} lines.`, "ok");
    } catch { toast("Full-city dataset not available on this deployment.", "err"); }
  }
  function refreshCoverage() {
    ["coverage-line", "diff-line"].forEach((id) => map.getLayer(id) && map.removeLayer(id));
    ["coverage", "diff"].forEach((id) => map.getSource(id) && map.removeSource(id));
    state.diff = null; addDataLayers(); renderLegend();
  }

  // ---------- command builder ----------
  const selSources = () => [...document.querySelectorAll(".src-check:checked")].map((c) => c.value);
  function updateCommand() {
    const bb = state.bbox ? state.bbox.join(",") : "W,S,E,N";
    const prec = $("#precision-check").checked ? " --precision" : "";
    $("#command-out").textContent = `tracelines extract --bbox ${bb} --sources ${selSources().join(",") || "google"}${prec} --out coverage.geojson`;
  }
  document.querySelectorAll(".src-check, #precision-check").forEach((c) => c.addEventListener("change", updateCommand));
  $("#copy-command").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("#command-out").textContent); toast("Command copied.", "ok"); }
    catch { toast("Copy failed — select manually.", "err"); }
  });
  updateCommand();

  // ---------- Mapillary live ----------
  const tokenInput = $("#mly-token"); tokenInput.value = state.mapillaryToken;
  $("#mly-enable").addEventListener("click", () => {
    const t = tokenInput.value.trim();
    if (!t.startsWith("MLY")) { toast("Enter a Mapillary token (starts with MLY).", "err"); return; }
    state.mapillaryToken = t; localStorage.setItem("tl-mly-token", t);
    state.mapillaryOn = true; state.visible["mapillary-live"] = true;
    if (map.getLayer("mly-live")) { map.removeLayer("mly-live"); map.removeSource("mly"); }
    addDataLayers(); renderLegend();
    toast("Mapillary layer on — pan/zoom to load.", "ok");
  });

  // ---------- proxy ----------
  const proxyInput = $("#proxy-url"); proxyInput.value = state.proxyUrl;
  const proxyBase = () => (proxyInput.value.trim() || state.proxyUrl).replace(/\/$/, "");
  $("#proxy-check").addEventListener("click", async () => {
    const url = proxyBase(); if (!url) { toast("Enter your proxy URL.", "err"); return; }
    state.proxyUrl = url; localStorage.setItem("tl-proxy-url", url);
    try { const h = await (await fetch(`${url}/health`)).json();
      $("#proxy-status").textContent = `✓ connected · max ${h.max_bbox_deg2} deg² · ${h.rate_per_min}/min · mapillary ${h.mapillary ? "on" : "off"}`;
    } catch { $("#proxy-status").textContent = "✗ couldn't reach the proxy (running? CORS set to this origin?)"; }
  });
  $("#proxy-extract").addEventListener("click", async () => {
    const url = proxyBase(); if (!url) { toast("Enter your proxy URL.", "err"); return; }
    state.proxyUrl = url; localStorage.setItem("tl-proxy-url", url);
    const b = map.getBounds();
    const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((v) => +v.toFixed(5)).join(",");
    const sources = [...document.querySelectorAll(".psrc-check:checked")].map((c) => c.value);
    const st = $("#proxy-status"); st.textContent = "Extracting current view…";
    try {
      const r = await fetch(`${url}/extract`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ bbox, sources }) });
      if (!r.ok) { st.textContent = `Proxy ${r.status}: ${(await r.text()).slice(0, 120)}`; return; }
      const fc = await r.json(); st.textContent = `Got ${fc.features.length} lines.`;
      if (fc.properties && fc.properties.stats) st.textContent += ` ${fc.properties.stats.total_km} km.`;
      loadCoverage(fc, "proxy");
    } catch { st.textContent = "Couldn't reach the proxy (running + CORS to this origin?)."; }
  });

  // ---------- nearest (click) ----------
  map.on("click", async (e) => {
    if (!state.nearestMode) return;
    const { lat, lng } = e.lngLat;
    const url = proxyBase();
    if (url) {
      const trekker = $("#nearest-trekker").checked;
      try {
        const res = await (await fetch(`${url}/nearest?lat=${lat}&lon=${lng}&include_trekker=${trekker}`)).json();
        if (!res || res.result === null) { toast("No official coverage near there.", "err"); return; }
        showNearest(res, lat, lng);
      } catch { toast("Nearest needs a reachable proxy (Proxy tab → Check).", "err"); }
    } else if (state.mapillaryToken) {
      mapillaryNearest(lat, lng);
    } else {
      toast("Nearest needs a proxy (Google) or a Mapillary token.", "err");
    }
  });
  function setMarker(lat, lon) {
    if (state.marker) state.marker.remove();
    state.marker = new maplibregl.Marker({ color: COLORS.google }).setLngLat([lon, lat]).addTo(map);
  }
  function showNearest(res, clat, clon) {
    setMarker(res.lat, res.lon);
    detail(`
      <h3>Nearest official pano</h3>
      <div class="row"><span class="k">source</span><span class="v">${res.sv_source || "?"}</span></div>
      <div class="row"><span class="k">captured</span><span class="v">${res.date || "?"}</span></div>
      <div class="row"><span class="k">distance</span><span class="v">${res.distance_m} m</span></div>
      <div class="row"><span class="k">pano id</span><span class="v">${res.id.slice(0, 12)}…</span></div>
      <a class="sv-link" href="${res.streetview_url}" target="_blank" rel="noopener">Open in Street View →</a>
      <button class="btn ghost small" id="hist-btn" style="margin-top:9px">Show history ⏱</button>
      <div class="hist" id="hist-box" hidden></div>`);
    $("#hist-btn").addEventListener("click", () => loadHistory(clat, clon));
  }
  async function loadHistory(lat, lon) {
    const url = proxyBase(); if (!url) { toast("History needs the proxy.", "err"); return; }
    const box = $("#hist-box"); box.hidden = false; box.textContent = "Loading history…";
    try {
      const h = await (await fetch(`${url}/historical?lat=${lat}&lon=${lon}`)).json();
      if (!h.count) { box.textContent = "No historical captures."; return; }
      const p = h.panos;
      box.innerHTML = `<div class="row"><span class="k">${p.length} captures</span><span class="hist-date" id="hd">${p[0].date || "?"}</span></div>
        <input type="range" id="hist-slider" min="0" max="${p.length - 1}" step="1" value="0" style="width:100%" />
        <a class="sv-link" id="hist-link" href="${p[0].sv_url}" target="_blank" rel="noopener">Open this capture →</a>`;
      $("#hist-slider").addEventListener("input", (ev) => {
        const it = p[+ev.target.value]; $("#hd").textContent = it.date || "?"; $("#hist-link").href = it.sv_url;
      });
    } catch { box.textContent = "Couldn't load history."; }
  }
  async function mapillaryNearest(lat, lon) {
    const d = 0.0015;
    const u = `https://graph.mapillary.com/images?access_token=${encodeURIComponent(state.mapillaryToken)}&fields=id,captured_at,geometry,is_pano&bbox=${lon - d},${lat - d},${lon + d},${lat + d}&limit=50`;
    try {
      const data = (await (await fetch(u)).json()).data || [];
      if (!data.length) { toast("No Mapillary imagery near there.", "err"); return; }
      let best = null, bd = Infinity;
      for (const im of data) { const [ilon, ilat] = im.geometry.coordinates; const dd = (ilon - lon) ** 2 + (ilat - lat) ** 2; if (dd < bd) { bd = dd; best = im; } }
      const [blon, blat] = best.geometry.coordinates;
      setMarker(blat, blon);
      const dt = best.captured_at ? new Date(best.captured_at).toISOString().slice(0, 7) : "?";
      detail(`<h3>Nearest Mapillary image</h3>
        <div class="row"><span class="k">captured</span><span class="v">${dt}</span></div>
        <div class="row"><span class="k">360°</span><span class="v">${best.is_pano ? "yes" : "no"}</span></div>
        <a class="sv-link" href="https://www.mapillary.com/app/?pKey=${best.id}&focus=photo" target="_blank" rel="noopener">Open in Mapillary →</a>`);
    } catch { toast("Mapillary lookup failed (token valid?).", "err"); }
  }

  // ---------- line inspector ----------
  function inspectLine(e) {
    if (state.nearestMode) return;
    const p = e.features && e.features[0] && e.features[0].properties; if (!p) return;
    let ids = p.pano_ids;
    if (typeof ids === "string") { try { ids = JSON.parse(ids); } catch { ids = null; } }
    const svlink = Array.isArray(ids) && ids.length
      ? `<a class="sv-link" href="https://www.google.com/maps/@?api=1&map_action=pano&pano=${ids[Math.floor(ids.length / 2)]}" target="_blank" rel="noopener">Open in Street View →</a>` : "";
    detail(`<h3>Coverage segment</h3>
      <div class="row"><span class="k">source</span><span class="v">${p.source}</span></div>
      ${p.capture_date ? `<div class="row"><span class="k">captured</span><span class="v">${p.capture_date}</span></div>` : ""}
      <div class="row"><span class="k">length</span><span class="v">${p.length_m != null ? p.length_m + " m" : "?"}</span></div>
      ${svlink}`);
  }
  function detail(html) { $("#detail-body").innerHTML = html; $("#detail-card").hidden = false; }
  $("#detail-close").addEventListener("click", () => { $("#detail-card").hidden = true; if (state.marker) { state.marker.remove(); state.marker = null; } });
  $("#banner-x").addEventListener("click", () => { $("#snapshot-banner").hidden = true; });

  // ---------- geocoder (Nominatim) ----------
  const gInput = $("#geocoder-input"), gResults = $("#geocoder-results");
  let gTimer = null;
  $("#geocoder").addEventListener("submit", (e) => e.preventDefault());
  gInput.addEventListener("input", () => {
    clearTimeout(gTimer);
    const q = gInput.value.trim();
    if (q.length < 3) { gResults.hidden = true; return; }
    gTimer = setTimeout(async () => {
      try {
        const r = await fetch(`https://nominatim.openstreetmap.org/search?format=jsonv2&limit=5&q=${encodeURIComponent(q)}`, { headers: { "Accept-Language": "en" } });
        const list = await r.json();
        gResults.innerHTML = list.map((x) => `<li data-lat="${x.lat}" data-lon="${x.lon}">${x.display_name}</li>`).join("");
        gResults.hidden = list.length === 0;
      } catch { gResults.hidden = true; }
    }, 350);
  });
  gResults.addEventListener("click", (e) => {
    const li = e.target.closest("li"); if (!li) return;
    map.flyTo({ center: [+li.dataset.lon, +li.dataset.lat], zoom: 15, duration: 800 });
    gResults.hidden = true; gInput.value = li.textContent.split(",")[0];
  });
  document.addEventListener("click", (e) => { if (!$("#geocoder").contains(e.target)) gResults.hidden = true; });

  // ---------- legend + totals ----------
  function kmBySource() {
    const km = {};
    if (state.coverage) for (const f of state.coverage.features) { const s = f.properties.source || "google"; km[s] = (km[s] || 0) + (f.properties.length_m || 0) / 1000; }
    return km;
  }
  const LABELS = { google: "Google", mapillary: "Mapillary", kartaview: "KartaView", "mapillary-live": "Mapillary (live)", diff: "Diff — gaps", fullcity: "Bucharest (full)" };
  function renderLegend() {
    const ul = $("#legend"); ul.innerHTML = "";
    const km = kmBySource();
    const srcs = new Set();
    if (state.coverage) state.coverage.features.forEach((f) => srcs.add(f.properties.source || "google"));
    if (state.fullcity) srcs.add("fullcity");
    if (state.mapillaryOn) srcs.add("mapillary-live");
    if (state.diff) srcs.add("diff");
    for (const s of srcs) {
      const color = COLORS[s] || COLORS[s.replace("-live", "")] || (s === "fullcity" ? COLORS.google : NO_DATE);
      const li = document.createElement("li");
      const kmTxt = s === "fullcity" ? (state.fullcityCount ? `${state.fullcityCount.toLocaleString()} lines` : "") : (km[s] != null ? `${km[s].toFixed(2)} km` : "");
      li.innerHTML = `<span class="swatch" style="background:${color}"></span><span>${LABELS[s] || s}</span><span class="km">${kmTxt}</span><input class="toggle" type="checkbox" ${state.visible[s] === false ? "" : "checked"} data-layer="${s}" title="Toggle layer" />`;
      ul.appendChild(li);
    }
    ul.querySelectorAll(".toggle").forEach((t) => t.addEventListener("change", (e) => { state.visible[e.target.dataset.layer] = e.target.checked; applyVisibility(); }));
    const totals = $("#totals");
    if (!srcs.size) { totals.innerHTML = '<span class="muted">No coverage loaded yet.</span>'; return; }
    const totalKm = Object.values(km).reduce((a, b) => a + b, 0);
    const n = state.coverage ? state.coverage.features.length : 0;
    totals.textContent = `${n} lines · ${totalKm.toFixed(2)} km` + (state.fullcity ? ` · +full city` : "");
  }

  // ---------- diff / probe / export / clear ----------
  $("#diff-btn").addEventListener("click", () => {
    if (!state.coverage) { toast("Load coverage first (diff runs on the loaded layer, not the full city).", "err"); return; }
    const g = state.coverage.features.filter((f) => f.properties.source === "google");
    const m = state.coverage.features.filter((f) => f.properties.source === "mapillary");
    if (!g.length || !m.length) { toast("Diff needs both Google and Mapillary lines loaded.", "err"); return; }
    if (g.length + m.length > 4000) { toast("Too many features for an in-browser diff — use a smaller extract.", "err"); return; }
    try {
      const mBuf = m.map((f) => turf.buffer(f, 20, { units: "meters" })).filter(Boolean);
      const onlyG = g.filter((f) => !mBuf.some((b) => turf.booleanIntersects(f, b)));
      state.diff = { type: "FeatureCollection", features: onlyG }; state.visible.diff = true;
      if (map.getLayer("diff-line")) { map.removeLayer("diff-line"); map.removeSource("diff"); }
      addDataLayers(); renderLegend();
      toast(`${onlyG.length} Google lines have no Mapillary within 20 m (approx).`, "ok");
    } catch { toast("Diff failed on this data.", "err"); }
  });
  $("#probe-btn").addEventListener("click", async () => {
    const url = proxyBase();
    const b = map.getBounds();
    const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((v) => +v.toFixed(5)).join(",");
    if (url) {
      try {
        const pr = await (await fetch(`${url}/probe?bbox=${bbox}&sources=google`)).json();
        const g = pr.google || {};
        detail(`<h3>Probe (proxy)</h3><div class="row"><span class="k">segments</span><span class="v">${g.segments ?? "?"}</span></div><div class="row"><span class="k">km</span><span class="v">${g.total_km ?? "?"}</span></div><div class="row"><span class="k">median year</span><span class="v">${g.median_capture_year ?? "?"}</span></div>`);
      } catch { toast("Probe needs a reachable proxy.", "err"); }
    } else if (state.coverage) {
      const km = kmBySource(); detail(`<h3>Probe (loaded data)</h3>${Object.entries(km).map(([s, v]) => `<div class="row"><span class="k">${s}</span><span class="v">${v.toFixed(2)} km</span></div>`).join("")}<p class="fineprint">Set a proxy to probe the live current view.</p>`);
    } else { toast("Probe needs a proxy or loaded data.", "err"); }
  });
  $("#export-btn").addEventListener("click", () => {
    if (!state.coverage) { toast("Nothing to export (the full-city layer is display-only — export a smaller extract).", "err"); return; }
    const blob = new Blob([JSON.stringify(state.coverage)], { type: "application/geo+json" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "coverage.geojson"; a.click(); URL.revokeObjectURL(a.href);
    toast("Exported coverage.geojson.", "ok");
  });
  $("#clear-btn").addEventListener("click", () => {
    state.coverage = null; state.diff = null; state.mapillaryOn = false; state.fullcity = false; state.fullcityCount = 0;
    ["coverage-line", "diff-line", "mly-live", "fullcity-line"].forEach((id) => map.getLayer(id) && map.removeLayer(id));
    ["coverage", "diff", "mly", "fullcity"].forEach((id) => map.getSource(id) && map.removeSource(id));
    const src = map.getSource("bbox"); if (src) src.setData(emptyFC());
    state.bbox = null; $("#bbox-input").value = ""; $("#snapshot-banner").hidden = true; $("#detail-card").hidden = true;
    if (state.marker) { state.marker.remove(); state.marker = null; }
    updateCommand(); renderLegend(); toast("Cleared.", "ok");
  });

  // ---------- helpers ----------
  function emptyFC() { return { type: "FeatureCollection", features: [] }; }
  function fitTo(fc) { try { const b = turf.bbox(fc); if (b.every(Number.isFinite)) map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 48, maxZoom: 16, duration: 600 }); } catch { /* noop */ } }
  function toast(msg, kind) { const el = document.createElement("div"); el.className = `toast ${kind || ""}`; el.textContent = msg; $("#toasts").appendChild(el); setTimeout(() => el.remove(), 3600); }
  $("#panel-toggle").addEventListener("click", () => $("#panel").classList.toggle("open"));

  renderLegend();
})();

#!/usr/bin/env node
// tracelines — a tiny CLI over the hosted tracelines proxy.
// Nearest OFFICIAL Street View car coverage (never a photosphere), historical stacks,
// area extraction to GeoJSON, and density probes. Zero dependencies (Node >=18 global fetch).
import { writeFileSync } from "node:fs";

const VERSION = "0.2.0";
const DEFAULT_PROXY =
  process.env.TRACELINES_PROXY || "https://tracelines-proxy-ttfjfqlcwq-ew.a.run.app";

const HELP = `tracelines ${VERSION} — nearest OFFICIAL Street View coverage (never photospheres)

Usage:
  tracelines nearest <lat> <lon> [--trekker]
  tracelines historical <lat> <lon>
  tracelines extract (--bbox W,S,E,N | --area NAME) [--sources google,mapillary] [--precision] [--out file.geojson]
  tracelines probe --bbox W,S,E,N [--sources google]
  tracelines health

Options:
  --proxy <url>   Proxy base URL (env TRACELINES_PROXY; default: the hosted demo)
  --json          Print raw JSON
  -h, --help      Show this help
  -v, --version   Show version

The default hosted proxy is hardened & rate-limited and may sleep or cap bbox size.
Run your own for real work: https://github.com/Prekzursil/tracelines#deploy-your-own-proxy-free`;

const BOOL_FLAGS = new Set(["trekker", "precision", "json", "help", "version"]);

function parseArgs(argv) {
  const flags = {};
  const pos = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "-h") flags.help = true;
    else if (a === "-v") flags.version = true;
    else if (a.startsWith("--")) {
      const key = a.slice(2);
      if (BOOL_FLAGS.has(key)) flags[key] = true;
      else flags[key] = argv[++i];
    } else pos.push(a);
  }
  return { flags, pos };
}

function die(msg, code = 1) {
  console.error(`tracelines: ${msg}`);
  process.exit(code);
}

function num(x, name) {
  const n = Number(x);
  if (x === undefined || !Number.isFinite(n)) die(`${name} must be a number (got ${JSON.stringify(x)})`);
  return n;
}

async function req(base, path, { method = "GET", body } = {}) {
  const url = base.replace(/\/$/, "") + path;
  let res;
  try {
    res = await fetch(url, {
      method,
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    return die(`could not reach the proxy at ${base} (${e.message}). Is it running / awake?`);
  }
  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : String(text).slice(0, 200);
    return die(`proxy ${res.status}: ${detail}`);
  }
  return data;
}

async function main() {
  const { flags, pos } = parseArgs(process.argv.slice(2));
  if (flags.version) return console.log(VERSION);
  const cmd = pos[0];
  if (!cmd || flags.help) return console.log(HELP);
  const base = flags.proxy || DEFAULT_PROXY;
  const raw = Boolean(flags.json);

  if (cmd === "nearest") {
    const lat = num(pos[1], "lat");
    const lon = num(pos[2], "lon");
    const q = new URLSearchParams({ lat, lon, include_trekker: Boolean(flags.trekker) });
    const d = await req(base, `/nearest?${q}`);
    if (raw) return console.log(JSON.stringify(d, null, 2));
    if (!d.id) return console.log("No official coverage nearby.");
    console.log(`${d.id}  ${d.sv_source}  ${d.date || "?"}  ${d.distance_m}m  (third-party: ${d.is_third_party})`);
    console.log(d.streetview_url);
  } else if (cmd === "historical") {
    const lat = num(pos[1], "lat");
    const lon = num(pos[2], "lon");
    const d = await req(base, `/historical?lat=${lat}&lon=${lon}`);
    if (raw) return console.log(JSON.stringify(d, null, 2));
    console.log(`${d.count} capture(s):`);
    for (const p of d.panos) console.log(`  ${p.date || "?"}  ${p.sv_source || ""}  ${p.id}`);
  } else if (cmd === "extract") {
    if (!flags.bbox && !flags.area) die("extract needs --bbox W,S,E,N or --area NAME");
    const body = {
      bbox: flags.bbox || null,
      area: flags.area || null,
      sources: (flags.sources || "google").split(",").map((s) => s.trim()).filter(Boolean),
      precision: Boolean(flags.precision),
      include_trekker: Boolean(flags.trekker),
    };
    if (flags["min-run"]) body.min_run = num(flags["min-run"], "--min-run");
    const fc = await req(base, "/extract", { method: "POST", body });
    if (flags.out) {
      writeFileSync(flags.out, JSON.stringify(fc));
      const km = fc.properties?.stats?.total_km;
      console.log(`Wrote ${fc.features?.length ?? 0} features to ${flags.out}${km ? ` (${km} km)` : ""}`);
    } else {
      console.log(JSON.stringify(fc, null, raw ? 2 : 0));
    }
  } else if (cmd === "probe") {
    if (!flags.bbox) die("probe needs --bbox W,S,E,N");
    const q = new URLSearchParams({ bbox: flags.bbox, sources: flags.sources || "google" });
    const d = await req(base, `/probe?${q}`);
    console.log(JSON.stringify(d, null, 2));
  } else if (cmd === "health") {
    const d = await req(base, "/health");
    console.log(JSON.stringify(d, null, 2));
  } else {
    die(`unknown command ${JSON.stringify(cmd)}. Run: tracelines --help`);
  }
}

main();

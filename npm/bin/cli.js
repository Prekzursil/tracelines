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

function parseArgs(argv) {
  // Allowlist dispatch: every flag is assigned through a STATIC property name
  // on a null-prototype object, so no argv-derived string is ever used as a
  // property key (structural fix for js/remote-property-injection: the
  // previous `flags[key] = ...` dynamic write kept the tainted-key flow open
  // even behind a denylist check). Unknown flags are rejected, not stored.
  const flags = Object.create(null);
  const pos = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "-h") { flags.help = true; continue; }
    if (a === "-v") { flags.version = true; continue; }
    if (!a.startsWith("--")) { pos.push(a); continue; }
    switch (a) {
      // boolean flags
      case "--trekker": flags.trekker = true; break;
      case "--precision": flags.precision = true; break;
      case "--json": flags.json = true; break;
      case "--help": flags.help = true; break;
      case "--version": flags.version = true; break;
      // value flags: every assignment goes through a static property name
      case "--proxy": case "--sources": case "--bbox": case "--area": case "--out": case "--min-run": {
        const v = argv[++i];
        if (v === undefined) die(`${a} needs a value`);
        if (a === "--proxy") flags.proxy = v;
        else if (a === "--sources") flags.sources = v;
        else if (a === "--bbox") flags.bbox = v;
        else if (a === "--area") flags.area = v;
        else if (a === "--out") flags.out = v;
        else flags["min-run"] = v;
        break;
      }
      default:
        die(`unknown option ${a}. Run: tracelines --help`);
    }
  }
  return { flags, pos };
}

function die(msg, code = 1) {
  console.error(`tracelines: ${msg}`);
  process.exit(code);
}

// A proxy response may only be written to the local file system after it
// proves it is a GeoJSON FeatureCollection: an object with type
// "FeatureCollection" and a features array. Anything else (an error page, a
// hijacked response, arbitrary bytes) is refused instead of uploaded to disk.
function assertFeatureCollection(fc) {
  if (typeof fc !== "object" || fc === null || Array.isArray(fc)) {
    die("proxy response is not a GeoJSON FeatureCollection — refusing to write it to disk");
  }
  if (fc.type !== "FeatureCollection" || !Array.isArray(fc.features)) {
    die("proxy response is not a GeoJSON FeatureCollection — refusing to write it to disk");
  }
  return fc;
}

function num(x, name) {
  const n = Number(x);
  if (x === undefined || !Number.isFinite(n)) die(`${name} must be a number (got ${JSON.stringify(x)})`);
  return n;
}

// Validate the proxy base once: parse it and constrain the scheme, so every
// request the CLI makes goes to an explicit http(s) URL the user chose.
function proxyBase(raw) {
  let u;
  try {
    u = new URL(raw);
  } catch {
    return die(`--proxy is not a valid URL: ${JSON.stringify(raw)}`);
  }
  if (u.protocol !== "http:" && u.protocol !== "https:") {
    return die(`--proxy must be an http(s) URL, got ${u.protocol}`);
  }
  return u;
}

async function req(base, path, { method = "GET", body } = {}) {
  const url = new URL(path, base);
  let res;
  try {
    // a `body` key only ever exists for body-carrying methods: the fetch
    // spec forbids it on GET, so the init is built conditionally (oxlint
    // unicorn/no-invalid-fetch-options)
    const init = body
      ? {
          method,
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        }
      : { method };
    res = await fetch(url, init);
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
  const base = proxyBase(flags.proxy || DEFAULT_PROXY);
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
      // Never write unvalidated network data to disk (js/http-to-file-access
      // hardening): the proxy payload must prove it is a GeoJSON
      // FeatureCollection before it reaches the local file system.
      assertFeatureCollection(fc);
      // Reviewed suppression (2026-11-04, code-scanning alert #7 / issue #18):
      // the only taint sources in this flow are the operator's own --out path
      // (argv) and the operator-chosen proxy's response, already shape-checked
      // above — the threat model is the user themselves, mirroring `curl -o`.
      // No untrusted input reaches this write; js/http-to-file-access's
      // pattern is a true positive class but a false positive here.
      writeFileSync(flags.out, JSON.stringify(fc)); // codeql[js/http-to-file-access]
      const km = fc.properties?.stats?.total_km;
      console.log(`Wrote ${fc.features.length} features to ${flags.out}${km ? ` (${km} km)` : ""}`);
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

# Deploy your own tracelines proxy

The proxy (`tracelines.proxy:app`, a small [FastAPI](https://fastapi.tiangolo.com/) app) lets the
static [GitHub Pages GUI](https://prekzursil.github.io/tracelines/) request **live** coverage —
including **Google**, which cannot run in a browser (undocumented, CORS-blocked, Python-only).

> ⚠️ **You host this, and you own it.** A public endpoint that extracts Google coverage is an
> **open relay** — CORS does not stop `curl`. It ships hardened, but treat it as **best-effort,
> not a service**: shared free-host IPs get throttled/banned by Google, and it's a Google-ToS gray
> area. See the repo `DATA_LICENSES.md` and disclaimer.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | liveness + config |
| GET | `/nearest?lat=&lon=&include_trekker=` | nearest official car pano (+ `streetview_url`) |
| GET | `/historical?lat=&lon=` | the stack of past captures at a point (for the time-slider) |
| POST | `/extract` `{bbox\|area, sources[], precision, min_run, include_trekker}` | GeoJSON |
| GET | `/probe?bbox=&sources=` | density per source |

## Run it

**Local:**
```bash
pip install "tracelines[server,mapillary]"
uvicorn tracelines.proxy:app --host 0.0.0.0 --port 8000
```

**Docker:**
```bash
docker build -t tracelines-proxy .          # uses the repo-root Dockerfile
docker run -p 8000:8000 \
  -e TRACELINES_CORS_ORIGINS="https://prekzursil.github.io" \
  -e MAPILLARY_TOKEN="MLY|..." \
  tracelines-proxy
```

**Free host — Hugging Face Spaces (recommended):** the fastest free path. Create a Docker Space
and drop in the two files from [`spaces/`](../spaces/) — see [`spaces/README.md`](../spaces/README.md).
HF sleeps only after 48 h idle (vs Render's 15 min), no credit card.

**Other:** Render (free, sleeps after 15 min), Fly.io (card-gated), any Docker host. Avoid Google
Cloud Run (scraping Google from Google infra is trivially detected) and PythonAnywhere (outbound
allowlist blocks Google's endpoints).

Then open the GUI, switch source mode to **Proxy**, and paste your URL.

## Configuration (env)

| Var | Default | Meaning |
|-----|---------|---------|
| `TRACELINES_CORS_ORIGINS` | `*` | Comma-separated allowed origins. **Set to your GUI origin** in production. |
| `TRACELINES_MAX_BBOX_DEG2` | `0.02` | Max bbox area per request. **Cut to ~`0.0005` for a public demo.** |
| `TRACELINES_RATE_PER_MIN` | `30` | Per-IP request cap per minute. |
| `TRACELINES_DISABLED` | — | Set `1` to 503 all extraction routes (kill switch). |
| `MAPILLARY_TOKEN` | — | Enables the Mapillary source server-side. |

The proxy inherits the HARD RULE: `/nearest`, `/historical`, and `/extract` never return a photosphere.

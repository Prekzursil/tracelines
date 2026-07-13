# svcoverage proxy backend

A tiny [FastAPI](https://fastapi.tiangolo.com/) service that wraps `svcoverage` so the static
[GitHub Pages GUI](https://prekzursil.github.io/svcoverage/) can request **live** coverage —
including **Google**, which cannot run in a browser (undocumented, CORS-blocked, Python-only).

> ⚠️ **You host this, and you own it.** A public endpoint that extracts Google coverage carries
> the same ToS responsibility as running the CLI, at higher visibility. Keep the bbox cap on,
> lock CORS to your GUI origin, and don't run it as an open, unthrottled public service. See the
> repo `DATA_LICENSES.md` and disclaimer.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | liveness + config |
| GET | `/nearest?lat=&lon=&include_trekker=` | nearest official car pano |
| POST | `/extract` `{bbox\|area, sources[], precision, min_run, include_trekker}` | GeoJSON FeatureCollection |
| GET | `/probe?bbox=&sources=` | density per source |

## Run it

**Local:**
```bash
pip install "svcoverage[server,mapillary]"
uvicorn server.app:app --host 0.0.0.0 --port 8000
```

**Docker:**
```bash
docker build -t svcoverage-proxy .
docker run -p 8000:8000 \
  -e SVCOVERAGE_CORS_ORIGINS="https://prekzursil.github.io" \
  -e MAPILLARY_TOKEN="MLY|..." \
  svcoverage-proxy
```

**Fly.io / Render / Hugging Face Space:** any platform that runs a Docker image or a Python
web service works. Point it at this repo's `Dockerfile`, expose port 8000, and set the env vars below.

Then open the GUI, switch the source mode to **"Live Google (proxy)"**, and paste your proxy URL
(e.g. `https://your-host`).

## Configuration (env)

| Var | Default | Meaning |
|-----|---------|---------|
| `SVCOVERAGE_CORS_ORIGINS` | `*` | Comma-separated allowed origins. **Set this to your GUI origin** in production. |
| `SVCOVERAGE_MAX_BBOX_DEG2` | `0.02` | Max bbox area (deg²) per request (~a city district). Guards against giant scrapes. |
| `MAPILLARY_TOKEN` | — | Enables the Mapillary source server-side. |

## Notes

- Extraction is resumable + cached (diskcache) on the server, so repeat requests are fast.
- The bbox cap returns HTTP `413` for oversized areas — extract large regions locally with the CLI.
- This service inherits the HARD RULE: `/nearest` and `/extract` never return a photosphere.

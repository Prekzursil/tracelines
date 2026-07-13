---
title: tracelines proxy
emoji: 🛰️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: agpl-3.0
---

# tracelines proxy

A demo-hardened live-extraction backend for
[tracelines](https://github.com/Prekzursil/tracelines) — it lets the static
[cockpit GUI](https://prekzursil.github.io/tracelines/) request **live Google** coverage,
which cannot run in a browser.

> **⚠️ Hugging Face now requires a PRO subscription to host Docker Spaces** on free `cpu-basic`
> (static Spaces stay free, but this proxy needs a running container). If you don't have HF PRO,
> use the **free** paths instead — a one-click **[Deploy to Render](../render.yaml)** (no card),
> or any Docker host / Google Cloud Run. See the repo's *"Deploy your own proxy"* section.
> This Space still works if you *do* have HF PRO.

## Deploy your own (a few clicks, free)

1. Create a **new Space** → SDK: **Docker** → make it public or private.
2. Add the two files from the repo's [`spaces/`](https://github.com/Prekzursil/tracelines/tree/main/spaces) folder (this `README.md` + `Dockerfile`).
3. Wait for the build; your proxy is at `https://<user>-<space>.hf.space`.
4. In the GUI, switch to the **Proxy** mode and paste that URL.

## ⚠️ It's a demo, and you own it

A public proxy that extracts Google coverage is an **open relay** — CORS does not stop
`curl`, so anyone can route their scraping through it, on your IP and your account. It ships
**hardened** (tiny bbox cap, per-IP rate limit) and you should treat it as **best-effort, not a
service**: shared free-host IPs get throttled/banned by Google, and it's a Google-ToS gray area.
For real work, run the CLI or a private self-host.

## Configuration (Space → Settings → Variables)

| Var | Default here | Meaning |
|-----|--------------|---------|
| `TRACELINES_MAX_BBOX_DEG2` | `0.0005` | max bbox per request (~a few blocks). Keep it small for a public demo. |
| `TRACELINES_RATE_PER_MIN` | `20` | per-IP request cap per minute. |
| `TRACELINES_CORS_ORIGINS` | your Pages origin | lock to your GUI origin. |
| `TRACELINES_DISABLED` | — | set `1` to 503 all extraction routes (kill switch). |
| `MAPILLARY_TOKEN` | — | (secret) enables the Mapillary source server-side. |

Endpoints: `/health` `/nearest` `/historical` `/extract` `/probe`.

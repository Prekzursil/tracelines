# Hugging Face Space (Docker SDK) — tracelines live-extraction proxy.
# Deploy: create a new Space (SDK: Docker) and add this Dockerfile + the README.md next to it.
# Demo-hardened by default; override any value in Space → Settings → Variables and secrets.
FROM python:3.12-slim

# Install tracelines + the server extra straight from the repo.
# (After a PyPI release you can switch to:  pip install "tracelines[server,mapillary]" )
RUN pip install --no-cache-dir \
    "tracelines[server,mapillary] @ git+https://github.com/Prekzursil/tracelines.git@main"

# Demo hardening — a public proxy is an open relay unless you keep these tight.
ENV TRACELINES_MAX_BBOX_DEG2=0.0005 \
    TRACELINES_RATE_PER_MIN=20 \
    TRACELINES_CORS_ORIGINS=https://prekzursil.github.io

# HF Spaces route to the port declared as app_port in README.md (7860 by default).
EXPOSE 7860
CMD ["uvicorn", "tracelines.proxy:app", "--host", "0.0.0.0", "--port", "7860"]

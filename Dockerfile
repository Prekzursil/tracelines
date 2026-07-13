# tracelines proxy backend — self-host to give the GUI live extraction (including Google).
# Build:  docker build -t tracelines-proxy .
# Run:    docker run -p 8000:8000 -e TRACELINES_CORS_ORIGINS="https://prekzursil.github.io" tracelines-proxy
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE THIRD_PARTY_LICENSES.md ./
COPY tracelines ./tracelines

# shapely 2.x ships manylinux wheels with bundled GEOS, so no system libs are needed.
RUN pip install --no-cache-dir ".[server,mapillary]"

ENV TRACELINES_CORS_ORIGINS="*" \
    TRACELINES_MAX_BBOX_DEG2="0.02"
EXPOSE 8000
CMD ["uvicorn", "tracelines.proxy:app", "--host", "0.0.0.0", "--port", "8000"]

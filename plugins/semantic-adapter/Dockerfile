# semantic-adapter: plugin MCP de capa semántica (FastMCP sobre FastAPI, puerto 8004).
# Se construye desde la raíz del repo para copiar la ontología de energy_lab.
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AGNO_TELEMETRY=false \
    PORT=8004 \
    SEMANTIC_ONTOLOGY_PATH=/app/ontologia/auto_ontology.yaml \
    SEMANTIC_CACHE_DIR=/app/cache

WORKDIR /app
COPY plugins/semantic-adapter/pyproject.toml plugins/semantic-adapter/README.md ./
COPY plugins/semantic-adapter/src ./src
RUN pip install --no-cache-dir . \
    && useradd --uid 1000 --create-home plugin \
    && mkdir -p /app/cache && chown plugin /app/cache
COPY semantic/ontologia/energy_lab /app/ontologia

USER plugin
EXPOSE 8004
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8004/health', timeout=4)"
CMD ["semantic-adapter"]

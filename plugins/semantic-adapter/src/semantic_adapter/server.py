"""Servidor MCP del plugin semantic-adapter (FastMCP en FastAPI, como los plugins de Octavius).

Variables:
  ENERGY_SEMANTIC_LAYER       off (por omisión) | local
  SEMANTIC_ONTOLOGY_PATH      YAML nativo exportado por Auto Ontology
  SEMANTIC_ONTOLOGY_CERTIFIED true solo cuando una persona lo revisó
  SEMANTIC_BASE_URL           endpoint compatible con OpenAI (InferNode)
  SEMANTIC_API_KEY            llave del endpoint
  SEMANTIC_LLM_MODEL          extractor de entidades (nemotron-3.5-lightning)
  SEMANTIC_EMBED_MODEL        embeddings (qwen3-embedding-8b)
  SEMANTIC_EMBED_DIMENSIONS   2048
  SEMANTIC_THRESHOLD          coseno mínimo para dar un concepto por cubierto (0.55)
  SEMANTIC_CACHE_DIR          caché del índice
  LLM_EXTRA_HEADERS_JSON      encabezados del gateway (Cloudflare Access)
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from fastmcp import FastMCP

from .embedder import OpenAICompatibleEmbedder
from .extractor import AgnoEntityExtractor
from .index import SemanticIndex
from .ontology import load_ontology
from .service import SemanticService

_DEFAULT_ONTOLOGY = (
    Path(__file__).resolve().parents[4] / "semantic" / "ontologia" / "energy_lab" / "auto_ontology.yaml"
)

mcp = FastMCP("SemanticAdapter")


def layer_mode() -> str:
    mode = os.environ.get("ENERGY_SEMANTIC_LAYER", "off").strip().lower()
    return mode if mode in ("off", "local") else "off"


def _disabled() -> dict | None:
    if layer_mode() == "off":
        return {"enabled": False, "reason": "ENERGY_SEMANTIC_LAYER=off"}
    return None


@lru_cache(maxsize=1)
def _service() -> SemanticService:
    base_url = os.environ["SEMANTIC_BASE_URL"]
    api_key = os.environ["SEMANTIC_API_KEY"]
    dims = os.environ.get("SEMANTIC_EMBED_DIMENSIONS", "2048").strip()
    ontology = load_ontology(
        Path(os.environ.get("SEMANTIC_ONTOLOGY_PATH", str(_DEFAULT_ONTOLOGY))),
        certified=os.environ.get("SEMANTIC_ONTOLOGY_CERTIFIED", "false").lower() == "true",
    )
    embedder = OpenAICompatibleEmbedder(
        base_url=base_url,
        api_key=api_key,
        model=os.environ.get("SEMANTIC_EMBED_MODEL", "qwen3-embedding-8b"),
        dimensions=int(dims) if dims else None,
    )
    cache = os.environ.get("SEMANTIC_CACHE_DIR")
    return SemanticService(
        ontology,
        SemanticIndex(ontology, embedder, cache_dir=Path(cache) if cache else None),
        AgnoEntityExtractor(
            base_url=base_url,
            api_key=api_key,
            model=os.environ.get("SEMANTIC_LLM_MODEL", "nemotron-3.5-lightning"),
        ),
        threshold=float(os.environ.get("SEMANTIC_THRESHOLD", "0.55")),
    )


@mcp.tool()
def search_terms(query: str, limit: int = 5) -> dict:
    """Busca en la ontología los términos y columnas más cercanos a un concepto de negocio.

    Devuelve la vista y la columna físicas de cada coincidencia, con su puntaje (coseno 0-1).
    """
    return _disabled() or _service().search_terms(query, limit=max(1, min(limit, 20)))


@mcp.tool()
def get_term(name: str) -> dict:
    """Devuelve un término de la ontología con su descripción, vistas y columnas."""
    return _disabled() or _service().get_term(name)


@mcp.tool()
def check_answerable(question: str) -> dict:
    """Dice si la ontología cubre los conceptos que la pregunta necesita.

    No responde la pregunta ni escribe SQL. Si algún concepto no tiene cobertura, la
    pregunta no se puede responder con estos datos y se lista en "uncovered".
    """
    return _disabled() or _service().check_answerable(question)


def create_app():
    from fastapi import FastAPI

    mcp_app = mcp.http_app(path="/mcp")
    app = FastAPI(title="semantic-adapter", lifespan=mcp_app.lifespan)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "layer": layer_mode()}

    app.mount("/mcp", mcp_app)
    return app


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8004")))


if __name__ == "__main__":
    main()

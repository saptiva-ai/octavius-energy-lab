"""
El stream del chat no debe comprimirse en el camino.

Equipo (2026-10-21) veía siempre el anillo con las frases de arranque. Causa,
medida con la imagen de la web 1.0.17: el servidor de Next comprime con gzip
las respuestas del proxy cuando el navegador lo pide, y el gzip retiene el SSE
completo; `meta`, `status` y el texto llegaban juntos al final. Con
`Cache-Control: no-transform` la compresión se salta y cada evento llega a su
tiempo.
"""

import pytest

from src.routers.chat.endpoints.message_endpoints import respuesta_sse


async def _eventos():
    yield {"event": "meta", "data": "{}"}


@pytest.mark.unit
def test_el_stream_del_chat_pide_que_nadie_lo_transforme_ni_lo_acumule():
    respuesta = respuesta_sse(_eventos())

    cache = respuesta.headers["cache-control"]
    assert "no-transform" in cache
    assert "no-store" in cache
    assert respuesta.headers["x-accel-buffering"] == "no"
    assert respuesta.headers["content-type"].startswith("text/event-stream")


def _app_con_middleware_de_cache():
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    from src.middleware.cache_control import CacheControlMiddleware

    app = FastAPI()
    app.add_middleware(CacheControlMiddleware)

    @app.post("/api/chat")
    async def chat():
        return respuesta_sse(_eventos())

    @app.get("/api/sessions")
    async def sesiones():
        return JSONResponse({"ok": True})

    return app


# Equipo (2026-10-22) seguía viendo solo el anillo con la web 1.0.18: en
# producción el navegador recibía los 735 eventos en una sola lectura a los
# 18.8 s, con gzip y `Cache-Control: no-store, no-cache, must-revalidate,
# max-age=0`. CacheControlMiddleware reescribía el encabezado de todo /api/ y
# borraba el `no-transform` del stream; la prueba de arriba no lo veía porque
# no pasa por los middlewares.
@pytest.mark.unit
def test_el_middleware_de_cache_no_le_quita_el_no_transform_al_stream():
    from fastapi.testclient import TestClient

    respuesta = TestClient(_app_con_middleware_de_cache()).post("/api/chat")

    cache = respuesta.headers["cache-control"]
    assert "no-transform" in cache
    assert "no-store" in cache


@pytest.mark.unit
def test_las_demas_respuestas_de_la_api_siguen_sin_cache():
    from fastapi.testclient import TestClient

    respuesta = TestClient(_app_con_middleware_de_cache()).get("/api/sessions")

    assert (
        respuesta.headers["cache-control"]
        == "no-store, no-cache, must-revalidate, max-age=0"
    )
    assert respuesta.headers["pragma"] == "no-cache"

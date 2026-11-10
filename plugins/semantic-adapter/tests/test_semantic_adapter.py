"""Ontología, índice, verificación de respondibilidad y servidor MCP, sin red."""

from __future__ import annotations

import asyncio
import json

import pytest

from conftest import FixedExtractor, HashEmbedder
from semantic_adapter.extractor import Entity
from semantic_adapter.index import SemanticIndex
from semantic_adapter.service import SemanticService

# -- ontología ------------------------------------------------------------------


def test_carga_terminos_con_su_vista_y_columnas_fisicas(ontology) -> None:
    assert len(ontology.terms) == 7
    hogar = ontology.term("Hogar")
    assert hogar.tables == ["agg.hogares"]
    assert {c.column for c in hogar.columns} == {"agg.hogares.hogar", "agg.hogares.grupo_tarifa"}
    assert ontology.certified is False
    assert len(ontology.version) == 12


def test_term_es_insensible_a_mayusculas_y_acentos(ontology) -> None:
    assert ontology.term("load zone").name == "Load Zone"
    assert ontology.term("TARIFA DINÁMICA").name == "Tarifa Dinamica"
    assert ontology.term("no existe") is None


# -- correcciones humanas ----------------------------------------------------------


def test_las_correcciones_renombran_y_agregan_sinonimos(corrected) -> None:
    zona = corrected.term("Zona de carga")
    assert zona is not None and zona.corrected
    assert corrected.term("load zone") is zona  # el nombre del modelo queda como sinónimo
    banda = next(c for c in corrected.term("tarifa dinámica").columns if c.column.endswith(".banda"))
    assert "67.20" in banda.description
    assert corrected.term("Hogar").corrected is False


def test_relaciones_y_medidas_quedan_ligadas_al_termino(corrected) -> None:
    related = corrected.related(corrected.term("Hogar"))
    assert {r["from"] for r in related["relations"]} == {
        "agg.consumo_hogar_diario.hogar",
        "agg.consumo_hogar_media_hora.hogar",
    }
    assert related["measures"] == []
    precio = corrected.related(corrected.term("Precio Zona Hora"))
    assert {m["name"] for m in precio["measures"]} == {"Precio promedio", "Horas con precio negativo"}


def test_propuesta_sin_revisar_no_esta_certificada(corrected, ontology) -> None:
    assert corrected.corrections.orphans == []
    assert corrected.corrections.applied > 0
    assert corrected.certified is False
    assert corrected.version != ontology.version  # la versión cubre exportación y correcciones


def _write(tmp_path, text: str):
    path = tmp_path / "correcciones.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_certifica_quien_revisa(tmp_path) -> None:
    from conftest import ONTOLOGY
    from semantic_adapter.ontology import load_ontology

    fixes = _write(tmp_path, "revisado_por: analista\ncertificada: true\n")
    loaded = load_ontology(ONTOLOGY, corrections=fixes)
    assert loaded.certified is True
    assert loaded.summary()["corrections"]["reviewed_by"] == "analista"


def test_correccion_huerfana_quita_la_certificacion(tmp_path) -> None:
    from conftest import ONTOLOGY
    from semantic_adapter.ontology import load_ontology

    fixes = _write(
        tmp_path,
        """
revisado_por: analista
certificada: true
terminos:
  agg.vista_borrada:
    nombre: Ya no existe
  agg.hogares:
    columnas:
      agg.hogares.columna_borrada:
        nombre: Tampoco
relaciones:
  - desde: agg.consumo_hogar_diario.hogar
    hacia: agg.clientes.id
medidas:
  - nombre: Medida vieja
    vista: agg.vista_borrada
    sql: count(*)
""",
    )
    loaded = load_ontology(ONTOLOGY, corrections=fixes)
    assert loaded.certified is False
    assert loaded.corrections.orphans == [
        "terminos.agg.vista_borrada",
        "terminos.agg.hogares.columnas.agg.hogares.columna_borrada",
        "relaciones.agg.consumo_hogar_diario.hogar->agg.clientes.id",
        "medidas.Medida vieja",
    ]
    assert loaded.relations == [] and loaded.measures == []


def test_sin_archivo_de_correcciones_se_usa_la_exportacion(tmp_path) -> None:
    from conftest import ONTOLOGY
    from semantic_adapter.ontology import load_ontology

    assert load_ontology(ONTOLOGY, corrections=tmp_path / "no-existe.yaml").corrections.applied == 0


# -- índice ---------------------------------------------------------------------


def test_busqueda_encuentra_la_columna_por_su_nombre_fisico(ontology, embedder) -> None:
    index = SemanticIndex(ontology, embedder)
    hits = index.search("grupo tarifa del hogar", limit=3)
    # grupo_tarifa existe en hogares y en consumo_hogar_*: basta con que Hogar aparezca arriba.
    assert "Hogar" in {h.term for h in hits}
    assert any(h.column and h.column.endswith(".grupo_tarifa") for h in hits)
    assert all(0 <= h.score <= 1 for h in hits)


def test_el_indice_se_cachea_por_version_y_modelo(ontology, tmp_path) -> None:
    first = HashEmbedder()
    SemanticIndex(ontology, first, cache_dir=tmp_path).search("zona", limit=1)
    calls_building = first.calls
    second = HashEmbedder()
    SemanticIndex(ontology, second, cache_dir=tmp_path).search("zona", limit=1)
    assert calls_building == 2  # documentos + consulta
    assert second.calls == 1  # solo la consulta
    cached = list(tmp_path.glob("*.json"))
    assert len(cached) == 1 and ontology.version in cached[0].name


def test_las_medidas_se_indexan(corrected, embedder) -> None:
    hits = SemanticIndex(corrected, embedder).search("horas con precio negativo", limit=1)
    assert hits[0].kind == "measure" and hits[0].table == "agg.precio_zona_hora"


# -- respondibilidad -------------------------------------------------------------


def _service(ontology, entities, threshold=0.3) -> SemanticService:
    return SemanticService(
        ontology,
        SemanticIndex(ontology, HashEmbedder()),
        FixedExtractor(entities),
        threshold=threshold,
    )


def test_pregunta_cubierta_es_respondible(ontology) -> None:
    result = _service(
        ontology,
        [Entity("consumo kwh del hogar", "metric"), Entity("grupo tarifa", "dimension")],
    ).check_answerable("¿Cuánto consumen los hogares por grupo de tarifa?")
    assert result["answerable"] is True
    assert result["coverage"] == 1.0
    assert result["uncovered"] == []
    assert {c["table"] for c in result["covered"]} & {"agg.hogares", "agg.consumo_hogar_diario"}


def test_entidad_sin_cobertura_la_hace_no_respondible(ontology) -> None:
    result = _service(
        ontology,
        [Entity("consumo kwh del hogar", "metric"), Entity("apagones de la red", "metric")],
    ).check_answerable("¿Qué hogares tendrán un apagón mañana?")
    assert result["answerable"] is False
    assert result["coverage"] == 0.5
    assert [u["entity"] for u in result["uncovered"]] == ["apagones de la red"]


def test_las_referencias_de_tiempo_no_cuentan_contra_la_cobertura(ontology) -> None:
    result = _service(
        ontology,
        [Entity("precio zona", "metric"), Entity("mañana", "time")],
    ).check_answerable("¿Cuál será el precio por zona mañana?")
    assert result["coverage"] == 1.0
    assert result["time_references"] == ["mañana"]


def test_sin_entidades_no_se_declara_respondible(ontology) -> None:
    result = _service(ontology, []).check_answerable("hola")
    assert result["answerable"] is False
    assert result["reason"] == "no_entities"


def test_cada_respuesta_declara_la_ontologia_y_su_estado(ontology) -> None:
    result = _service(ontology, [Entity("zona", "dimension")]).check_answerable("zonas")
    assert result["ontology"] == {
        "version": ontology.version,
        "certified": False,
        "terms": 7,
        "source": "auto-ontology-agno",
        "corrections": {"applied": 0, "orphans": [], "reviewed_by": ""},
    }


# -- servidor MCP -----------------------------------------------------------------


def test_herramientas_mcp_en_memoria(ontology, monkeypatch) -> None:
    from fastmcp import Client

    from semantic_adapter import server

    service = _service(ontology, [Entity("grupo tarifa", "dimension")])
    monkeypatch.setattr(server, "_service", lambda: service)
    monkeypatch.setenv("ENERGY_SEMANTIC_LAYER", "local")

    async def run():
        async with Client(server.mcp) as client:
            names = {t.name for t in await client.list_tools()}
            search = await client.call_tool("search_terms", {"query": "zona de carga", "limit": 2})
            answer = await client.call_tool("check_answerable", {"question": "¿tarifas?"})
            term = await client.call_tool("get_term", {"name": "Hogar"})
            return names, search, answer, term

    names, search, answer, term = asyncio.run(run())
    assert names == {"search_terms", "check_answerable", "get_term"}
    assert len(json.loads(search.content[0].text)["hits"]) == 2
    assert json.loads(answer.content[0].text)["answerable"] is True
    payload = json.loads(term.content[0].text)["term"]
    assert payload["name"] == "Hogar"
    assert {"relations", "measures"} <= payload.keys()


def test_capa_apagada_lo_dice_en_vez_de_responder(monkeypatch) -> None:
    from fastmcp import Client

    from semantic_adapter import server

    monkeypatch.setenv("ENERGY_SEMANTIC_LAYER", "off")

    async def run():
        async with Client(server.mcp) as client:
            return await client.call_tool("check_answerable", {"question": "x"})

    payload = json.loads(asyncio.run(run()).content[0].text)
    assert payload == {"enabled": False, "reason": "ENERGY_SEMANTIC_LAYER=off"}


@pytest.mark.parametrize("value", ["", "otra"])
def test_valor_invalido_del_interruptor_equivale_a_apagado(value, monkeypatch) -> None:
    from semantic_adapter import server

    monkeypatch.setenv("ENERGY_SEMANTIC_LAYER", value)
    assert server.layer_mode() == "off"

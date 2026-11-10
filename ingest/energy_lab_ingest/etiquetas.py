"""Etiquetas en español para interpretar los datos.

Los identificadores internos (kind, entity_kind, llaves de calidad) se quedan
como contratos estables en inglés; todo lo que lee una persona usa estas
etiquetas.
"""

from __future__ import annotations

TIPOS_DE_SERIE = {
    "consumption": "Consumo eléctrico",
    "demand": "Demanda eléctrica",
    "price": "Precio total de la energía",
    "price_energy": "Componente de energía del precio",
    "price_losses": "Componente de pérdidas del precio",
    "price_congestion": "Componente de congestión del precio",
    "tariff_price": "Precio de la tarifa dinámica",
    "temperature": "Temperatura",
}

TIPOS_DE_ENTIDAD = {
    "household": "Hogar",
    "client": "Cliente",
    "load_zone": "Zona de carga",
    "node": "Nodo",
    "region": "Región",
    "system": "Sistema",
    "weather_point": "Punto meteorológico",
}

COHORTES = {
    "tariff": "Tarifa",
    "system": "Sistema eléctrico",
    "ccr": "Centro de control regional",
}

UNIDADES = {
    "kWh": "kWh por intervalo",
    "kW": "kW promedio del intervalo",
    "MXN/MWh": "pesos por MWh",
    "p/kWh": "peniques por kWh",
}

CALIDAD = {
    "rows_read": "Filas leídas",
    "hours_read": "Horas leídas",
    "api_calls": "Llamadas al servicio",
    "null_values": "Valores nulos",
    "zero_values": "Valores en cero",
    "negative_values": "Valores negativos",
    "negative_total": "Horas con precio total negativo",
    "negative_energy": "Horas con componente de energía negativa",
    "negative_losses": "Horas con componente de pérdidas negativa",
    "negative_congestion": "Horas con componente de congestión negativa",
    "nonexistent_local_time": "Horas locales inexistentes por cambio de horario (descartadas)",
    "ambiguous_local_time": "Horas locales ambiguas por cambio de horario (primera ocurrencia)",
    "leading_zeros_skipped": "Ceros previos al alta del cliente (no cargados)",
    "off_grid_timestamps": "Marcas fuera de la malla de tiempo (descartadas)",
    "duplicates_dropped": "Duplicados eliminados",
    "duplicates_conflicting": "Duplicados con valores distintos",
    "keys_without_data": "Claves sin datos",
    "unexpected_keys": "Claves inesperadas en la respuesta",
    "malformed_rows": "Filas mal formadas",
    "skipped_rows": "Filas omitidas",
    "band_high": "Medias horas en banda alta",
    "band_normal": "Medias horas en banda normal",
    "band_low": "Medias horas en banda baja",
}


def etiqueta(diccionario: dict[str, str], clave: str) -> str:
    """Etiqueta en español; si no hay, la clave tal cual para no ocultar nada."""
    return diccionario.get(clave, clave)


def describir_calidad(calidad: dict[str, int]) -> list[str]:
    """Líneas legibles del reporte de calidad, sin las llaves en cero."""
    return [f"{etiqueta(CALIDAD, k)}: {v:,}" for k, v in sorted(calidad.items()) if v]

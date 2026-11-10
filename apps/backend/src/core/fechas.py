"""Fecha de "hoy" para el chat: la de Ciudad de México.

El servidor corre en UTC; a las 18:00 de CDMX ya es el día siguiente en UTC
y el chat decía "hoy es 7 de noviembre" (usuario simulado, 2026-11-06).
CDMX no tiene horario de verano desde 2022; la zona lo resuelve igual.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

ZONA_CDMX = ZoneInfo("America/Mexico_City")


def hoy_cdmx(instante: datetime | None = None) -> date:
    """Fecha en CDMX del instante dado (ahora, si no se da)."""
    instante = instante or datetime.now(tz=timezone.utc)
    return instante.astimezone(ZONA_CDMX).date()

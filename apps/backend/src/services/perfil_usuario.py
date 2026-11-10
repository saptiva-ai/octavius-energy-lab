"""Ámbito de datos del usuario autenticado para las tools del plugin de dominio.

FEAT-2026-09-02__perfiles-y-permisos-por-rol. El backend no conoce el dominio
(regla anti-deuda #1): solo lee el perfil del usuario (`User.ambito`) y lo
entrega como un dict que el plugin interpreta. Se inyecta en CADA llamada a las
tools de datos desde el orquestador, nunca desde los argumentos que emite el
LLM, así el modelo no puede ampliar el ámbito.

Sin perfil (usuarios previos, demo@example.com) devuelve None: la consulta
corre sin restricción, como hasta ahora.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)

ROLES_VALIDOS = ("gerente_tienda", "jefe_departamento", "compras")


def ambito_desde_usuario(usuario: Any) -> Optional[dict[str, Any]]:
    """Dict de ámbito a partir de un `User` (documento o dict). Función pura."""
    if usuario is None:
        return None
    ambito = (
        usuario.get("ambito")
        if isinstance(usuario, dict)
        else getattr(usuario, "ambito", None)
    )
    if ambito is None:
        return None
    if not isinstance(ambito, dict):
        ambito = ambito.model_dump() if hasattr(ambito, "model_dump") else dict(ambito)
    rol = ambito.get("rol")
    if rol not in ROLES_VALIDOS:
        logger.warning("perfil_usuario.rol_desconocido", rol=rol)
        return None
    usuario_nombre = (
        usuario.get("username")
        if isinstance(usuario, dict)
        else getattr(usuario, "username", None)
    )
    salida: dict[str, Any] = {"rol": rol}
    if ambito.get("tienda_id"):
        salida["tienda_id"] = str(ambito["tienda_id"])
    if ambito.get("tienda_nombre"):
        salida["tienda_nombre"] = str(ambito["tienda_nombre"])
    if ambito.get("categorias"):
        salida["categorias"] = [str(c) for c in ambito["categorias"]]
    if usuario_nombre:
        salida["usuario"] = str(usuario_nombre)
    return salida


async def ambito_de_usuario(user_id: Optional[str]) -> Optional[dict[str, Any]]:
    """Carga el usuario y devuelve su ámbito; None si no hay usuario o perfil.

    Fail-safe: cualquier error de base regresa None con warning; el chat sigue
    (sin restricción, igual que antes de esta feature).
    """
    if not user_id or user_id == "mock-user-id":
        return None
    try:
        from ..models.user import User

        usuario = await User.get(user_id)
    except Exception as exc:  # noqa: BLE001 — fail-safe, no romper el chat
        logger.warning("perfil_usuario.no_disponible", error=str(exc))
        return None
    return ambito_desde_usuario(usuario)


def tools_con_ambito(schemas: list[dict[str, Any]]) -> set[str]:
    """Nombres de tools cuyo schema declara el parámetro `ambito`."""
    nombres: set[str] = set()
    for schema in schemas or []:
        funcion = schema.get("function", schema) if isinstance(schema, dict) else {}
        params = (funcion.get("parameters") or {}).get("properties") or {}
        if "ambito" in params and funcion.get("name"):
            nombres.add(str(funcion["name"]))
    return nombres

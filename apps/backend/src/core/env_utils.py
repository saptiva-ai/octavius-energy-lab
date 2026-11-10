"""
Lectura tolerante de configuración numérica del entorno.

Los presupuestos de tokens son configurables por variable de entorno; un
valor vacío o no numérico cae al default sin lanzar, para que un typo en
`envs/.env` nunca tire el arranque del backend.
"""

import os

import structlog

logger = structlog.get_logger(__name__)


def entero_de_env(nombre: str, default: int) -> int:
    """Leer un entero de `nombre`; vacío o inválido regresa `default`."""
    try:
        return int(os.getenv(nombre, "") or default)
    except ValueError:
        logger.warning("env.valor_invalido", variable=nombre, default=default)
        return default

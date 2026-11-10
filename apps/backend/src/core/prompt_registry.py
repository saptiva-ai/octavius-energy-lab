"""
Sistema de registro y gestión de system prompts por modelo.
Permite configurar prompts base, addendums y parámetros específicos por modelo.
"""

import hashlib
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

import structlog
import yaml
from pydantic import BaseModel, Field

from .env_utils import entero_de_env
from .fechas import hoy_cdmx

logger = structlog.get_logger(__name__)

# Bloque RAG del system prompt. Solo entra cuando la conversación tiene
# documentos adjuntos: con el bloque siempre presente, el modelo escribía
# `get_relevant_segments(...)` como texto en follow-ups sin documentos
# ("explícame" tras una consulta retail, visto en vivo 2026-09-03).
RAG_BLOCK = (
    "**Documentos Adjuntos (RAG - Retrieval Augmented Generation)**\n"
    "      * CRÍTICO: Si el usuario ha adjuntado documentos (PDFs, imágenes, etc.) "
    "y hace una pregunta sobre ellos:\n"
    "        1. **SIEMPRE** usa la herramienta `get_relevant_segments` PRIMERO "
    "antes de responder\n"
    "        2. Proporciona el `conversation_id` actual y la pregunta del usuario "
    "como parámetro `question`\n"
    "        3. Los segmentos retornados contienen el contexto del documento "
    "necesario para responder\n"
    "        4. Usa SOLO la información de los segmentos retornados - NO inventes "
    "información\n"
    "      * Ejemplos de preguntas que requieren llamar a `get_relevant_segments`:\n"
    '        - "¿Qué es esto?" → Usa get_relevant_segments para obtener resumen '
    "del documento\n"
    '        - "¿De qué trata?" → Usa get_relevant_segments\n'
    '        - "¿Cuál es el precio?" → Usa get_relevant_segments para buscar '
    "información de precios\n"
    '        - "Resume el documento" → Usa get_relevant_segments para obtener '
    "segmentos clave\n"
    "        - Cualquier pregunta sobre contenido del documento adjunto\n"
    "      * Si no hay segmentos relevantes o la herramienta falla, dilo "
    "honestamente y sugiere reformular la pregunta.\n\n      "
)


class ModelParams(BaseModel):
    """
    Parámetros de generación para un modelo específico.

    Todos los parámetros son opcionales y pueden ser customizados por modelo.
    Si no se especifican en el registry.yaml, se usan los valores por defecto.
    """

    # Parámetros core de sampling
    temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Temperatura de sampling (0.0 = determinista, 2.0 = muy aleatorio)",
    )
    top_p: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="Top-p nucleus sampling (límite de diversidad)",
    )

    # Penalties para evitar repetición
    presence_penalty: float = Field(
        default=0.0, ge=-2.0, le=2.0, description="Penalización por presencia de tokens"
    )
    frequency_penalty: float = Field(
        default=0.2,
        ge=-2.0,
        le=2.0,
        description="Penalización por frecuencia de tokens",
    )

    # Control de longitud
    max_tokens: Optional[int] = Field(
        default=None,
        ge=1,
        le=8192,
        description="Máximo de tokens a generar (si no se define, usa límite por canal)",
    )

    # Parámetros adicionales (OpenAI standard)
    stop: Optional[list[str]] = Field(
        default=None, description="Secuencias que detienen la generación"
    )
    n: Optional[int] = Field(
        default=None, ge=1, le=10, description="Número de completions a generar"
    )
    seed: Optional[int] = Field(
        default=None, description="Seed para reproducibilidad determinística"
    )


class PromptEntry(BaseModel):
    """Entrada de prompt para un modelo específico."""

    system_base: str = Field(..., description="System prompt base con placeholders")
    addendum: Optional[str] = Field(
        default=None, description="Addendum específico del modelo"
    )
    params: ModelParams = Field(
        default_factory=ModelParams, description="Parámetros de generación"
    )


class PromptRegistry:
    """
    Registro centralizado de system prompts y parámetros por modelo.

    Responsabilidades:
    - Cargar configuración desde YAML
    - Resolver prompts con sustitución de placeholders
    - Inyectar descripciones de herramientas
    - Aplicar addendums por modelo
    - Proveer parámetros de generación por modelo y canal
    """

    # Límites de tokens por canal (conservadores para latencia óptima).
    # El de `chat` es configurable con `CHAT_CHANNEL_MAX_TOKENS` (ver
    # `_max_tokens_for_channel`): los modelos de razonamiento gastan tokens en
    # pensar ANTES de escribir y ese consumo no se ve en la respuesta, así que
    # con 1200 devolvían contenido vacío (medido: qwen3.6 necesitó 919 tokens
    # para una narración corta y ~1500 con el contexto real del chat).
    CHANNEL_MAX_TOKENS = {
        "chat": 1200,
        "report": 3500,
        "title": 64,
        "summary": 256,
        "code": 2048,
    }

    def _max_tokens_for_channel(self, channel: str) -> int:
        """Límite de tokens del canal; el de `chat` es configurable por entorno."""
        default = self.CHANNEL_MAX_TOKENS.get(channel, 1200)
        if channel == "chat":
            return entero_de_env("CHAT_CHANNEL_MAX_TOKENS", default)
        return default

    def __init__(self, registry_path: Optional[str] = None):
        """
        Inicializar registro de prompts.

        Args:
            registry_path: Ruta al archivo YAML de registro. Si es None, usa el default.
        """
        self.registry_path = registry_path
        self.version: str = "v1"
        self.copilot_name: str = "CopilotOS"
        self.org_name: str = "Saptiva"
        self.models: Dict[str, PromptEntry] = {}

        if registry_path:
            self.load(registry_path)

    def load(self, path: str) -> None:
        """
        Cargar registro desde archivo YAML.

        Args:
            path: Ruta al archivo YAML de configuración

        Raises:
            FileNotFoundError: Si el archivo no existe
            ValueError: Si el YAML es inválido
        """
        try:
            registry_file = Path(path)
            if not registry_file.exists():
                raise FileNotFoundError(f"Prompt registry not found: {path}")

            with open(registry_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            # Validar estructura básica
            if not data:
                raise ValueError("Empty prompt registry file")

            self.version = data.get("version", "v1")
            self.copilot_name = data.get("copilot_name", "CopilotOS")
            self.org_name = data.get("org_name", "Saptiva")

            # Cargar modelos
            models_data = data.get("models", {})
            if not models_data:
                raise ValueError("No models defined in registry")

            for model_name, model_config in models_data.items():
                try:
                    # Validar que tenga system_base
                    if "system_base" not in model_config:
                        logger.warning(
                            "Model missing system_base, skipping", model=model_name
                        )
                        continue

                    # Parsear params si existen
                    params_data = model_config.get("params", {})
                    params = ModelParams(**params_data)

                    # Crear entry
                    entry = PromptEntry(
                        system_base=model_config["system_base"],
                        addendum=model_config.get("addendum"),
                        params=params,
                    )

                    self.models[model_name] = entry
                    logger.debug(
                        "Loaded prompt entry",
                        model=model_name,
                        has_addendum=entry.addendum is not None,
                        params=params.model_dump(),
                    )

                except Exception as e:
                    logger.error(
                        "Failed to load model config", model=model_name, error=str(e)
                    )
                    continue

            if not self.models:
                raise ValueError("No valid models loaded from registry")

            logger.info(
                "Prompt registry loaded successfully",
                path=path,
                version=self.version,
                models_count=len(self.models),
                models=list(self.models.keys()),
            )

        except FileNotFoundError:
            raise
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in prompt registry: {e}")
        except Exception as e:
            logger.error("Failed to load prompt registry", error=str(e), path=path)
            raise

    def resolve(
        self,
        model: str,
        tools_markdown: Optional[str] = None,
        channel: str = "chat",
        has_documents: bool = False,
    ) -> Tuple[str, Dict]:
        """
        Resolver system prompt y parámetros para un modelo y canal.

        Args:
            model: Nombre del modelo (e.g., "Saptiva Turbo", "Saptiva Cortex")
            tools_markdown: Descripción de herramientas en markdown (opcional)
            channel: Canal de comunicación (chat, report, title, etc.)

        Returns:
            Tupla de (system_text, params_dict) donde:
            - system_text: System prompt completamente resuelto
            - params_dict: Diccionario con parámetros de generación
        """
        # Resolver modelo (fallback a default si no existe)
        entry = self.models.get(model)
        if not entry:
            logger.warning(
                "Model not found in registry, using default",
                model=model,
                available_models=list(self.models.keys()),
            )
            entry = self.models.get("default")
            if not entry:
                raise ValueError(
                    f"Model '{model}' not found and no default model available"
                )

        # Paso 1: Sustituir placeholders base
        system_text = entry.system_base
        system_text = system_text.replace("{CopilotOS}", self.copilot_name)
        system_text = system_text.replace("{Saptiva}", self.org_name)

        # Fecha de hoy en CDMX: el servidor va en UTC y de noche decía "mañana".
        system_text = system_text.replace("{CURRENT_DATE}", hoy_cdmx().isoformat())

        # Instrucciones RAG solo con documentos adjuntos en la conversación.
        system_text = system_text.replace("{RAG}", RAG_BLOCK if has_documents else "")

        # Paso 2: Inyectar herramientas si están disponibles
        if tools_markdown:
            system_text = system_text.replace("{TOOLS}", tools_markdown)
        else:
            # Si no hay herramientas, remover completamente la sección
            # IMPORTANTE: No mencionar herramientas para evitar que el modelo las sugiera
            system_text = system_text.replace(
                "Herramientas disponibles\n{TOOLS}\n      * Llama herramientas cuando:\n        - Falte dato verificable\n        - Se requiera cálculo, búsqueda o acción conectada\n      * Si una herramienta falla, explica brevemente el error y ofrece alternativa.\n\n      ",
                "",
            )
            # Fallback para remover solo el placeholder
            system_text = system_text.replace("{TOOLS}", "")

        # Paso 3: Aplicar addendum si existe
        if entry.addendum:
            # Agregar addendum al final con separador claro
            system_text = f"{system_text}\n\n---\n**Instrucciones específicas del modelo:**\n{entry.addendum}"

        # Paso 4: Preparar parámetros con max_tokens por canal
        params = entry.params.model_dump()

        # Sobrescribir max_tokens según canal SOLO si el modelo no lo define
        # Esto permite que modelos específicos (e.g., Saptiva Legacy) tengan su propio límite
        if "max_tokens" not in params or params["max_tokens"] is None:
            params["max_tokens"] = self._max_tokens_for_channel(channel)
        # else: el modelo ya definió max_tokens en sus params, lo respetamos

        # Agregar metadata
        params["_metadata"] = {
            "model": model,
            "channel": channel,
            "version": self.version,  # For test compatibility
            "prompt_version": self.version,
            "system_hash": self._hash_system_prompt(system_text),
            "has_addendum": entry.addendum is not None,
            "has_tools": tools_markdown is not None,
        }

        logger.debug(
            "Resolved prompt for model",
            model=model,
            channel=channel,
            system_hash=params["_metadata"]["system_hash"],
            prompt_length=len(system_text),
            max_tokens=params["max_tokens"],
        )

        return system_text, params

    @staticmethod
    def _hash_system_prompt(system_text: str) -> str:
        """
        Generar hash SHA256 del system prompt para telemetría.

        Args:
            system_text: Texto del system prompt

        Returns:
            Hash SHA256 (primeros 16 caracteres)
        """
        return hashlib.sha256(system_text.encode("utf-8")).hexdigest()[:16]

    def get_available_models(self) -> list:
        """Retornar lista de modelos disponibles en el registro."""
        return list(self.models.keys())

    def validate(self) -> bool:
        """
        Validar que el registro esté correctamente configurado.

        Returns:
            True si el registro es válido

        Raises:
            ValueError: Si hay problemas de configuración
        """
        if not self.models:
            raise ValueError("No models loaded in registry")

        if "default" not in self.models:
            raise ValueError("Registry must have a 'default' model entry")

        # Validar que todos los prompts tengan los placeholders necesarios
        for model_name, entry in self.models.items():
            system_base = entry.system_base

            if "{CopilotOS}" not in system_base and "{Saptiva}" not in system_base:
                logger.warning(
                    "Model prompt missing organization placeholders", model=model_name
                )

        logger.info("Prompt registry validation passed", models=len(self.models))
        return True


# Singleton global del registro (lazy loading)
_prompt_registry: Optional[PromptRegistry] = None


def get_prompt_registry(force_reload: bool = False) -> PromptRegistry:
    """
    Obtener instancia singleton del registro de prompts.

    Args:
        force_reload: Si True, fuerza recarga del registro

    Returns:
        Instancia de PromptRegistry
    """
    global _prompt_registry

    if _prompt_registry is None or force_reload:
        # Cargar desde variable de entorno o usar default
        from ..core.config import get_settings

        settings = get_settings()

        registry_path = getattr(
            settings,
            "prompt_registry_path",
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "prompts",
                "registry.yaml",
            ),
        )

        logger.info("Loading prompt registry", path=registry_path)
        _prompt_registry = PromptRegistry(registry_path)
        _prompt_registry.validate()

    return _prompt_registry

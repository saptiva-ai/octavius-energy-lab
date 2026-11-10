"""
Configuration management for the FastAPI application.
"""

import logging
import os
from datetime import datetime
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Import secrets manager - handle import error gracefully during development
try:
    from .secrets import get_database_url, get_secret, mask_secret

    SECRETS_AVAILABLE = True
except ImportError:
    logging.warning(
        "Secrets manager not available, falling back to environment variables"
    )
    SECRETS_AVAILABLE = False

    def get_secret(
        name: str, required: bool = True, min_length: int = 8
    ) -> Optional[str]:
        return os.getenv(name)

    def get_database_url(service: str = "mongodb") -> str:
        if service == "mongodb":
            return os.getenv("MONGODB_URL", "")
        elif service == "redis":
            return os.getenv("REDIS_URL", "")
        return ""

    def mask_secret(secret: str, visible_chars: int = 4) -> str:
        if len(secret) <= visible_chars * 2:
            return "*" * len(secret)
        return (
            secret[:visible_chars]
            + "*" * (len(secret) - visible_chars * 2)
            + secret[-visible_chars:]
        )


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server
    host: str = Field(default="0.0.0.0", description="Host to bind the server")
    port: int = Field(default=8000, description="Port to bind the server")
    debug: bool = Field(default=False, description="Enable debug mode")
    reload: bool = Field(default=False, description="Enable auto-reload")

    # Application
    app_name: str = Field(default="Copilot OS API")
    app_version: str = Field(default="0.1.0")
    app_description: str = Field(default="API for chat and deep research")

    # Database (MongoDB) - Secure configuration
    db_min_pool_size: int = Field(
        default=10, description="MongoDB min connection pool size"
    )
    db_max_pool_size: int = Field(
        default=100, description="MongoDB max connection pool size"
    )
    db_connection_timeout_ms: int = Field(
        default=5000, description="MongoDB connection timeout"
    )
    db_server_selection_timeout_ms: int = Field(
        default=5000, description="MongoDB server selection timeout"
    )
    db_max_idle_time_ms: int = Field(
        default=300000, description="MongoDB max idle time in ms"
    )
    db_connect_timeout_ms: int = Field(
        default=10000, description="MongoDB connect timeout"
    )

    # Redis - Secure configuration
    redis_pool_size: int = Field(default=10, description="Redis connection pool size")

    # Domain analytics plugin (retail-advisor) — MCP over HTTP (streamable).
    # Full MCP endpoint, incl. path (mcp.http_app(path="/mcp") mounted at /mcp → /mcp/mcp).
    retail_advisor_url: str = Field(
        default="http://retail-advisor:8002/mcp/mcp",
        description="Retail-advisor MCP endpoint (domain plugin)",
    )
    tool_retail_advisor_enabled: bool = Field(
        default=True,
        description="Expose the retail-advisor analytics tool in the UI/chat",
    )
    retail_advisor_function_calling: bool = Field(
        default=False,
        description=(
            "Usar function-calling nativo (el LLM decide llamar las tools del "
            "retail-advisor). Si False, se usa el pre-fetch tool-augmented."
        ),
    )
    retail_advisor_decide_model: Optional[str] = Field(
        default=None,
        description=(
            "Modelo SOLO para el paso decide del function-calling (la "
            "narración conserva el modelo de la sesión). El decide de "
            "Saptiva Turbo emite args vacíos/truncados según el fraseo "
            "(card decide-robusto 2026-07-13); Saptiva Ops resolvió los "
            "fraseos rotos en pruebas en vivo. None = modelo de la sesión. "
            "Si el decide con este modelo falla, se reintenta una vez con "
            "el de la sesión (fail-safe)."
        ),
    )
    retail_advisor_narration_model: Optional[str] = Field(
        default=None,
        description=(
            "Modelo SOLO para NARRAR un turno que ya trae resultados de las "
            "tools de datos. Mismo problema que el decide, con otra cara: los "
            "razonadores gastan el presupuesto pensando y devuelven contenido "
            "vacío con finish_reason=length. Medido 2026-09-03 sobre los "
            "contextos de la demo (tests/evals/bench_narracion.py): "
            "gemma-4-26b narra en 2.3-3.1 s sin razonamiento y sin vacías; "
            "qwen3.6-27b tarda 15.7-23.8 s y devolvió una vacía de 9. "
            "None = modelo de la sesión (comportamiento previo). Solo aplica "
            "cuando el turno ejecutó tools; la conversación normal conserva "
            "el modelo elegido por el usuario."
        ),
    )

    # Weaviate - Vector Database
    weaviate_url: str = Field(
        default="http://weaviate:8080", description="Weaviate URL"
    )
    weaviate_grpc_port: int = Field(default=50051, description="Weaviate gRPC port")
    rag_collection_name: str = Field(
        default="RAG_Documents", description="RAG collection name"
    )

    @computed_field
    @property
    def mongodb_url(self) -> str:
        """MongoDB connection URL with secure credentials."""
        try:
            return get_database_url("mongodb")
        except Exception:
            # Fallback to environment variable for compatibility
            return os.getenv("MONGODB_URL", "")

    @computed_field
    @property
    def redis_url(self) -> str:
        """Redis connection URL with secure credentials."""
        try:
            return get_database_url("redis")
        except Exception:
            # Fallback to environment variable for compatibility
            return os.getenv("REDIS_URL", "")

    @computed_field
    @property
    def jwt_secret_key(self) -> str:
        """JWT secret key from secure source."""
        try:
            return get_secret("JWT_SECRET_KEY", required=True, min_length=32)
        except Exception:
            # Fallback to environment variable for compatibility
            return os.getenv("JWT_SECRET_KEY", "")

    @computed_field
    @property
    def secret_key(self) -> str:
        """Application secret key from secure source."""
        try:
            return get_secret("SECRET_KEY", required=True, min_length=32)
        except Exception:
            # Fallback to environment variable for compatibility
            return os.getenv("SECRET_KEY", "")

    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_access_token_expire_minutes: int = Field(
        default=1440, description="Access token expiry"
    )
    jwt_refresh_token_expire_days: int = Field(
        default=7, description="Refresh token expiry"
    )

    # Email (SMTP for password reset)
    smtp_host: str = Field(
        default="smtp.gmail.com", description="SMTP server host", alias="MAIL_SERVER"
    )
    smtp_port: int = Field(
        default=587, description="SMTP server port", alias="MAIL_PORT"
    )
    smtp_user: str = Field(
        default="", description="SMTP username (email)", alias="MAIL_USERNAME"
    )
    smtp_password: str = Field(
        default="",
        description="SMTP password (app password for Gmail)",
        alias="MAIL_PASSWORD",
    )
    smtp_from_email: str = Field(
        default="support@saptiva.com",
        description="From email address",
        alias="MAIL_FROM",
    )
    mail_from_name: str = Field(
        default="Octavios Support", description="From name", alias="MAIL_FROM_NAME"
    )
    password_reset_url_base: str = Field(
        default="http://localhost:3000", description="Base URL for password reset links"
    )

    # Aletheia
    aletheia_base_url: str = Field(
        default="http://aletheia:8000", description="Aletheia API base URL"
    )
    aletheia_api_key: str = Field(default="", description="Aletheia API key")
    aletheia_timeout: int = Field(default=120, description="Aletheia request timeout")
    aletheia_max_retries: int = Field(default=3, description="Aletheia max retries")

    # Deep Research Kill Switch (P0-DR-KILL-001)
    # This is a GLOBAL kill switch that completely disables Deep Research
    # When enabled, all research endpoints return 410 GONE
    deep_research_kill_switch: bool = Field(
        default=True,
        description="KILL SWITCH: When True, Deep Research is completely disabled (returns 410 GONE)",
    )

    # Legacy flags (kept for backward compatibility but dominated by kill switch)
    deep_research_enabled: bool = Field(
        default=False,
        description="Master switch for Deep Research feature (overridden by kill_switch)",
    )
    deep_research_auto: bool = Field(
        default=False,
        description="Auto-trigger Deep Research (overridden by kill_switch)",
    )
    deep_research_complexity_threshold: float = Field(
        default=0.7, description="Complexity threshold for auto-triggering (0.0-1.0)"
    )

    # Tool visibility flags (server-driven UI toggles)
    tool_add_files_enabled: bool = Field(
        default=True,
        description="Expose Add Files tool in the UI",
        alias="TOOL_ADD_FILES_ENABLED",
    )
    tool_document_review_enabled: bool = Field(
        default=True,
        description="Expose Document Review tool in the UI",
        alias="TOOL_DOCUMENT_REVIEW_ENABLED",
    )
    tool_files_enabled: bool = Field(
        default=True,
        description="Expose unified Files tool in the UI",
        alias="TOOL_FILES_ENABLED",
    )
    tool_flags_updated_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of the last manual update to tool flags",
        alias="TOOL_FLAGS_UPDATED_AT",
    )

    # Session cookie configuration (used for SSE auth)
    session_cookie_name: str = Field(
        default="sess", description="Name of the session cookie"
    )
    session_cookie_secure: bool = Field(
        default=False,
        description="Mark session cookie as Secure",
        alias="SESSION_COOKIE_SECURE",
    )
    session_cookie_domain: Optional[str] = Field(
        default=None,
        description="Domain attribute for the session cookie",
        alias="SESSION_COOKIE_DOMAIN",
    )
    session_cookie_path: str = Field(
        default="/",
        description="Path attribute for the session cookie",
        alias="SESSION_COOKIE_PATH",
    )
    session_cookie_samesite: str = Field(
        default="lax",
        description="SameSite attribute for the session cookie",
        alias="SESSION_COOKIE_SAMESITE",
    )

    # Chat creation rollout flag (P0-CHAT-OPTIMISTIC-ROLLBACK)
    create_chat_optimistic: bool = Field(
        default=True, description="Enable single-flight optimistic chat creation flow"
    )

    # Chat Configuration (P0-CHAT-BASE-004)
    # Nombre del modelo tal como lo espera el gateway configurado
    # (`SAPTIVA_BASE_URL`): "Saptiva Turbo" en api.saptiva.com, ids tipo
    # `nemotron-…`/`qwen-…` en InferNode. Usar `default_chat_model()` como
    # default de schemas/modelos en vez de hardcodear.
    chat_default_model: str = Field(
        default="Saptiva Turbo",
        description="Default model for simple chat when kill switch is active",
    )
    chat_allowed_models: str = Field(
        default="Saptiva Turbo,Saptiva Cortex,Saptiva Ops,Saptiva Coder,Saptiva Legacy",
        description="Comma-separated list of allowed chat models",
    )
    data_model_routing_enabled: bool = Field(
        default=True,
        description="Auto-escalate to Legacy for complex data queries (multi-bank, dense tables)",
    )
    data_model_escalation_target: str = Field(
        default="Saptiva Legacy",
        description="Model to use when data complexity triggers escalation",
    )

    # Plugin URLs (Plugin-First Architecture)
    file_manager_url: str = Field(
        default="http://file-manager:8001",
        description="File Manager plugin URL for file operations",
    )

    # SAPTIVA
    saptiva_base_url: str = Field(
        default="https://api.saptiva.com", description="SAPTIVA API base URL"
    )
    saptiva_timeout: int = Field(default=30, description="SAPTIVA request timeout")
    saptiva_max_retries: int = Field(default=3, description="SAPTIVA max retries")

    @computed_field
    @property
    def saptiva_api_key(self) -> str:
        """SAPTIVA API key from secure source."""
        try:
            return get_secret("SAPTIVA_API_KEY", required=False) or ""
        except Exception:
            # Fallback to environment variable
            return os.getenv("SAPTIVA_API_KEY", "")

    # Text Extraction Configuration
    # Controls which backend is used for PDF/image text extraction
    extractor_provider: str = Field(
        default="third_party",
        description="Text extraction provider: 'third_party' (pypdf+pytesseract), 'saptiva' (Saptiva Native Tools) or 'huggingface' (DeepSeek OCR)",
        alias="EXTRACTOR_PROVIDER",
    )
    huggingface_ocr_endpoint: str = Field(
        default="https://saptivaDev1-DeepSeek-OCR-Space.hf.space/ocr",
        description="Hugging Face OCR endpoint (DeepSeek or compatible)",
        alias="HF_OCR_ENDPOINT",
    )
    huggingface_ocr_prompt_mode: str = Field(
        default="auto",
        description="Prompt mode for Hugging Face OCR: 'auto', 'plain', or 'markdown'",
        alias="HF_OCR_PROMPT_MODE",
    )
    huggingface_ocr_prompt_plain: str = Field(
        default="<image>\\nFree OCR.",
        description="Prompt used when requesting plain text output from Hugging Face OCR",
        alias="HF_OCR_PROMPT_PLAIN",
    )
    huggingface_ocr_prompt_markdown: str = Field(
        default="<image>\\nConvert to markdown.",
        description="Prompt used when requesting markdown output from Hugging Face OCR",
        alias="HF_OCR_PROMPT_MARKDOWN",
    )
    huggingface_ocr_timeout: float = Field(
        default=45.0,
        description="Timeout (seconds) for Hugging Face OCR requests",
        alias="HF_OCR_TIMEOUT",
    )
    huggingface_ocr_max_retries: int = Field(
        default=3,
        description="Maximum retries for Hugging Face OCR calls",
        alias="HF_OCR_MAX_RETRIES",
    )

    @computed_field
    @property
    def huggingface_ocr_token(self) -> str:
        """Hugging Face token for DeepSeek OCR integration."""
        try:
            return get_secret("HF_TOKEN", required=False) or os.getenv("HF_TOKEN", "")
        except Exception:
            return os.getenv("HF_TOKEN", "")

    # PDF OCR Fallback Configuration (for image-only/scanned PDFs)
    max_ocr_pages: int = Field(
        default=30,
        description="Maximum number of pages to OCR for image-only PDFs (controls cost/latency)",
        alias="MAX_OCR_PAGES",
    )
    ocr_raster_dpi: int = Field(
        default=180,
        description="DPI for PDF rasterization before OCR (150-200 recommended, higher = better quality but slower)",
        alias="OCR_RASTER_DPI",
    )

    # Cache
    cache_version: str = Field(
        default="v1",
        description="Cache version prefix. Bump on deploy to invalidate all versioned caches.",
        alias="CACHE_VERSION",
    )

    # Rate Limiting
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_calls: int = Field(
        default=100, description="Rate limit calls per period"
    )
    rate_limit_period: int = Field(
        default=60, description="Rate limit period in seconds"
    )

    # CORS - Parse from environment variable or use defaults
    cors_origins: List[str] = Field(
        default=["http://localhost:3000"],
        description="Allowed CORS origins (comma-separated or JSON array)",
    )
    cors_allow_credentials: bool = Field(
        default=True, description="Allow CORS credentials"
    )
    allowed_hosts: List[str] = Field(
        default=["localhost", "127.0.0.1", "testserver"],
        description="Allowed hosts (comma-separated or JSON array)",
    )

    @computed_field
    @property
    def parsed_cors_origins(self) -> List[str]:
        """Parse CORS origins from environment variable supporting both JSON and CSV format."""
        import json

        cors_str = os.getenv("CORS_ORIGINS", "")

        if not cors_str:
            return self.cors_origins

        # Try parsing as JSON array first
        try:
            parsed = json.loads(cors_str)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: split by comma
        return [origin.strip() for origin in cors_str.split(",") if origin.strip()]

    @computed_field
    @property
    def parsed_allowed_hosts(self) -> List[str]:
        """Parse allowed hosts from environment variable supporting both JSON and CSV format."""
        import json

        hosts_str = os.getenv("ALLOWED_HOSTS", "")

        if not hosts_str:
            return self.allowed_hosts

        # Try parsing as JSON array first
        try:
            parsed = json.loads(hosts_str)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: split by comma
        return [host.strip() for host in hosts_str.split(",") if host.strip()]

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format")

    # OpenTelemetry
    otel_service_name: str = Field(
        default="octavios-api", description="OTel service name"
    )
    otel_exporter_otlp_endpoint: str = Field(
        default="", description="OTel OTLP endpoint"
    )

    # Security
    secure_cookies: bool = Field(default=False, description="Use secure cookies")
    https_only: bool = Field(default=False, description="HTTPS only mode")

    # Prompt Registry (System Prompts por Modelo)
    prompt_registry_path: str = Field(
        default="/app/prompts/registry.yaml",
        description="Ruta al archivo YAML de registro de prompts",
    )
    enable_model_system_prompt: bool = Field(
        default=True, description="Feature flag: habilitar system prompts por modelo"
    )

    # Simple Memory System (JSON-based fact recall)
    memory_enabled: bool = Field(
        default=True, description="Enable simple memory system for fact recall"
    )
    memory_max_facts: int = Field(
        default=50, description="Max facts to store per session"
    )
    memory_recent_messages: int = Field(
        default=10, description="Recent messages to include in LLM context"
    )

    def log_config_safely(self) -> dict:
        """Return configuration for logging with secrets masked."""
        config = {}
        for field_name, field_info in self.model_fields.items():
            value = getattr(self, field_name)
            if (
                "secret" in field_name.lower()
                or "password" in field_name.lower()
                or "key" in field_name.lower()
            ):
                config[field_name] = mask_secret(str(value)) if value else "<not_set>"
            elif "url" in field_name.lower() and (
                "mongodb" in field_name.lower() or "redis" in field_name.lower()
            ):
                # Mask credentials in connection URLs
                if value:
                    # Extract and mask password from URLs like mongodb://user:pass@host
                    import re

                    masked_url = re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", value)
                    config[field_name] = masked_url
                else:
                    config[field_name] = "<not_set>"
            else:
                config[field_name] = value
        return config

    # File Upload & Storage
    max_file_size: int = Field(
        default=10485760,
        description="Max file size in bytes (default: 10MB, prod: 50MB)",
        alias="MAX_FILE_SIZE",
    )
    allowed_file_types: List[str] = Field(
        default=["txt", "md", "pdf", "docx"], description="Allowed file types"
    )
    files_root: str = Field(
        default="/tmp/octavios_documents",
        description="Root directory for file storage (configurable per environment)",
        alias="FILES_ROOT",
    )
    files_ttl_days: int = Field(
        default=7, description="TTL for uploaded files in days", alias="FILES_TTL_DAYS"
    )
    files_quota_mb_per_user: int = Field(
        default=500,
        description="Storage quota per user in MB",
        alias="FILES_QUOTA_MB_PER_USER",
    )

    # Background Tasks
    celery_broker_url: str = Field(
        default="redis://localhost:6379/1", description="Celery broker URL"
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/2", description="Celery result backend URL"
    )


@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()


def default_chat_model() -> str:
    """Modelo por defecto del chat (`CHAT_DEFAULT_MODEL`).

    Pensado como `default_factory` de schemas/modelos: hardcodear el nombre
    hace que, al cambiar de gateway, toda petición sin modelo explícito falle
    con `model_not_found`. Tolerante a fallos: si la config no carga, cae al
    default histórico en vez de romper el import del módulo.
    """
    try:
        return get_settings().chat_default_model
    except Exception:  # noqa: BLE001 - un default nunca debe tumbar el boot
        return "Saptiva Turbo"

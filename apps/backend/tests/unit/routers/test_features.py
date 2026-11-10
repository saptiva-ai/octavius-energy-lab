"""
Unit tests for features router.

Tests:
- get_tool_visibility endpoint
- Tool flag combinations
- Backward compatibility with legacy flags
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.routers.features import get_tool_visibility

pytestmark = [pytest.mark.unit]


class TestGetToolVisibility:
    """Test get_tool_visibility endpoint."""

    @pytest.mark.asyncio
    async def test_returns_tools_list(self):
        """Test returns a list of tools."""
        mock_settings = _create_mock_settings()

        result = await get_tool_visibility(settings=mock_settings)

        assert "tools" in result
        assert isinstance(result["tools"], list)
        assert len(result["tools"]) > 0

    @pytest.mark.asyncio
    async def test_returns_rev_timestamp(self):
        """Test returns rev timestamp."""
        mock_settings = _create_mock_settings()

        result = await get_tool_visibility(settings=mock_settings)

        assert "rev" in result
        assert isinstance(result["rev"], int)

    @pytest.mark.asyncio
    async def test_files_tool_enabled(self):
        """Test files tool is enabled when tool_files_enabled is True."""
        mock_settings = _create_mock_settings(tool_files_enabled=True)

        result = await get_tool_visibility(settings=mock_settings)
        files_tool = _find_tool(result["tools"], "files")

        assert files_tool is not None
        assert files_tool["enabled"] is True

    @pytest.mark.asyncio
    async def test_files_tool_disabled(self):
        """Test files tool is disabled when all file flags are False."""
        mock_settings = _create_mock_settings(
            tool_files_enabled=False,
            tool_add_files_enabled=False,
            tool_document_review_enabled=False,
        )

        result = await get_tool_visibility(settings=mock_settings)
        files_tool = _find_tool(result["tools"], "files")

        assert files_tool is not None
        assert files_tool["enabled"] is False

    @pytest.mark.asyncio
    async def test_files_fallback_to_add_files(self):
        """Test files tool uses add_files fallback."""
        mock_settings = _create_mock_settings(
            tool_files_enabled=False,
            tool_add_files_enabled=True,
            tool_document_review_enabled=False,
        )

        result = await get_tool_visibility(settings=mock_settings)
        files_tool = _find_tool(result["tools"], "files")

        assert files_tool["enabled"] is True

    @pytest.mark.asyncio
    async def test_files_fallback_to_document_review(self):
        """Test files tool uses document_review fallback."""
        mock_settings = _create_mock_settings(
            tool_files_enabled=False,
            tool_add_files_enabled=False,
            tool_document_review_enabled=True,
        )

        result = await get_tool_visibility(settings=mock_settings)
        files_tool = _find_tool(result["tools"], "files")

        assert files_tool["enabled"] is True

    @pytest.mark.asyncio
    async def test_retail_advisor_tool(self):
        """Test retail-advisor tool reflects setting."""
        mock_settings = _create_mock_settings(tool_retail_advisor_enabled=True)

        result = await get_tool_visibility(settings=mock_settings)
        retail_tool = _find_tool(result["tools"], "retail-advisor")

        assert retail_tool is not None
        assert retail_tool["enabled"] is True

    @pytest.mark.asyncio
    async def test_legacy_add_files_disabled_when_files_enabled(self):
        """Test legacy add-files is disabled when files tool is enabled."""
        mock_settings = _create_mock_settings(
            tool_files_enabled=True,
            tool_add_files_enabled=True,
        )

        result = await get_tool_visibility(settings=mock_settings)
        add_files_tool = _find_tool(result["tools"], "add-files")

        assert add_files_tool is not None
        assert add_files_tool["enabled"] is False

    @pytest.mark.asyncio
    async def test_legacy_add_files_enabled_when_files_disabled(self):
        """Test legacy add-files is enabled when files tool is disabled."""
        mock_settings = _create_mock_settings(
            tool_files_enabled=False,
            tool_add_files_enabled=True,
        )

        result = await get_tool_visibility(settings=mock_settings)
        add_files_tool = _find_tool(result["tools"], "add-files")

        assert add_files_tool["enabled"] is True

    @pytest.mark.asyncio
    async def test_legacy_document_review_disabled_when_files_enabled(self):
        """Test legacy document-review is disabled when files tool is enabled."""
        mock_settings = _create_mock_settings(
            tool_files_enabled=True,
            tool_document_review_enabled=True,
        )

        result = await get_tool_visibility(settings=mock_settings)
        doc_review_tool = _find_tool(result["tools"], "document-review")

        assert doc_review_tool is not None
        assert doc_review_tool["enabled"] is False

    @pytest.mark.asyncio
    async def test_updated_at_included(self):
        """Test updated_at is included in tool entries."""
        now = datetime.utcnow()
        mock_settings = _create_mock_settings(tool_flags_updated_at=now)

        result = await get_tool_visibility(settings=mock_settings)
        files_tool = _find_tool(result["tools"], "files")

        assert "updated_at" in files_tool
        assert files_tool["updated_at"] == now.isoformat()

    @pytest.mark.asyncio
    async def test_updated_at_none(self):
        """Test updated_at is None when not set."""
        mock_settings = _create_mock_settings(tool_flags_updated_at=None)

        result = await get_tool_visibility(settings=mock_settings)
        files_tool = _find_tool(result["tools"], "files")

        assert files_tool["updated_at"] is None

    @pytest.mark.asyncio
    async def test_all_expected_tools_present(self):
        """Test all expected tools are present."""
        mock_settings = _create_mock_settings()

        result = await get_tool_visibility(settings=mock_settings)
        tool_keys = [t["key"] for t in result["tools"]]

        expected_keys = [
            "files",
            "retail-advisor",
            "add-files",
            "document-review",
        ]
        for key in expected_keys:
            assert key in tool_keys


# Helper functions


def _create_mock_settings(
    tool_files_enabled: bool = False,
    tool_add_files_enabled: bool = False,
    tool_document_review_enabled: bool = False,
    tool_retail_advisor_enabled: bool = False,
    tool_flags_updated_at: datetime = None,
) -> MagicMock:
    """Create mock settings object."""
    mock = MagicMock()
    mock.tool_files_enabled = tool_files_enabled
    mock.tool_add_files_enabled = tool_add_files_enabled
    mock.tool_document_review_enabled = tool_document_review_enabled
    mock.tool_retail_advisor_enabled = tool_retail_advisor_enabled
    mock.retail_advisor_function_calling = False
    mock.tool_flags_updated_at = tool_flags_updated_at
    return mock


def _find_tool(tools: list, key: str) -> dict:
    """Find a tool by key in the tools list."""
    for tool in tools:
        if tool["key"] == key:
            return tool
    return None


class TestGetToolViews:
    """Vistas predefinidas (feedback round 1, 2026-10-16, punto 14):
    el backend relaya lo que el plugin declara, por perfil, y tolera caídas."""

    @pytest.mark.asyncio
    async def test_relays_plugin_views_for_profile(self, monkeypatch):
        from src.routers import features

        mock_settings = _create_mock_settings()
        mock_settings.tool_retail_advisor_enabled = True
        mock_settings.retail_advisor_url = "http://retail-advisor:8002/mcp/mcp"
        vistas = [
            {
                "id": "venta_mes",
                "titulo": "Venta del mes",
                "prompt": "¿Cuánto vendimos este mes?",
                "perfiles": ["compras"],
            }
        ]
        llamadas = []

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"vistas": vistas}

        class _Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return None

            async def get(self, url, params=None):
                llamadas.append((url, params))
                return _Resp()

        monkeypatch.setattr(features.httpx, "AsyncClient", _Client)
        result = await features.get_tool_views(perfil="compras", settings=mock_settings)
        assert result == {"views": vistas}
        assert llamadas == [
            ("http://retail-advisor:8002/vistas", {"perfil": "compras"})
        ]

    @pytest.mark.asyncio
    async def test_plugin_down_returns_empty_list(self, monkeypatch):
        from src.routers import features

        mock_settings = _create_mock_settings()
        mock_settings.tool_retail_advisor_enabled = True
        mock_settings.retail_advisor_url = "http://retail-advisor:8002/mcp/mcp"

        class _Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return None

            async def get(self, url, params=None):
                raise RuntimeError("caído")

        monkeypatch.setattr(features.httpx, "AsyncClient", _Client)
        assert await features.get_tool_views(settings=mock_settings) == {"views": []}


class TestGetToolGuide:
    """Guía rápida del modal de ayuda (QA, P2.2, 2026-10-21): estaba
    fija en la web; ahora la declara el plugin con los datos de la base."""

    @pytest.mark.asyncio
    async def test_relays_plugin_guide(self, monkeypatch):
        from src.routers import features

        mock_settings = _create_mock_settings()
        mock_settings.tool_retail_advisor_enabled = True
        mock_settings.retail_advisor_url = "http://retail-advisor:8002/mcp/mcp"
        guia = {"puedes": ["Pronóstico de venta."], "no_tiene": ["Pedidos."]}
        llamadas = []

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"guia": guia}

        class _Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return None

            async def get(self, url, params=None):
                llamadas.append(url)
                return _Resp()

        monkeypatch.setattr(features.httpx, "AsyncClient", _Client)
        result = await features.get_tool_guide(settings=mock_settings)
        assert result == {"guide": guia}
        assert llamadas == ["http://retail-advisor:8002/ayuda"]

    @pytest.mark.asyncio
    async def test_plugin_down_returns_empty_guide(self, monkeypatch):
        from src.routers import features

        mock_settings = _create_mock_settings()
        mock_settings.tool_retail_advisor_enabled = True
        mock_settings.retail_advisor_url = "http://retail-advisor:8002/mcp/mcp"

        class _Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return None

            async def get(self, url, params=None):
                raise RuntimeError("caído")

        monkeypatch.setattr(features.httpx, "AsyncClient", _Client)
        assert await features.get_tool_guide(settings=mock_settings) == {
            "guide": {"puedes": [], "no_tiene": []}
        }


class TestGetToolViewsTodas:
    @pytest.mark.asyncio
    async def test_sin_perfil_pide_todas_las_vistas(self, monkeypatch):
        """Decisión del equipo (2026-10-19): en la POC todos los usuarios ven
        todos los datos y todas las vistas; la web no manda perfil."""
        from src.routers import features

        mock_settings = _create_mock_settings()
        mock_settings.tool_retail_advisor_enabled = True
        mock_settings.retail_advisor_url = "http://retail-advisor:8002/mcp/mcp"
        llamadas = []

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"vistas": []}

        class _Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return None

            async def get(self, url, params=None):
                llamadas.append(params)
                return _Resp()

        monkeypatch.setattr(features.httpx, "AsyncClient", _Client)
        await features.get_tool_views(settings=mock_settings)
        assert llamadas == [None]

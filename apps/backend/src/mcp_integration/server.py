"""
MCP Server - FastMCP Integration

Uses FastMCP SDK (official MCP Python implementation) with best practices:
- Automatic schema generation from type hints
- Built-in context management (logging, sampling, progress)
- Standardized error handling
- In-memory testing support

Integration approach:
1. FastMCP tools for new capabilities (audit_file, excel_analyzer, viz_tool)
2. FastAPI routes for HTTP/REST API compatibility
3. Hybrid mode: Both MCP protocol and REST endpoints
"""

import os
import sys
from typing import Optional

if os.getenv("RUN_MCP_STACK", "true").lower() != "true":
    # Allow backend to start without MCP stack (e.g., client without MCP support or test runs)
    raise ModuleNotFoundError("MCP stack disabled via RUN_MCP_STACK=false")

# Avoid clashing with the official `mcp` package used by fastmcp when this module is imported
_local_mcp_module = sys.modules.get("mcp")
_local_mcp_server = sys.modules.get("mcp.server")
sys.modules.pop("mcp.server", None)
sys.modules.pop("mcp", None)

from fastmcp import Context, FastMCP

# Restore local module references after fastmcp finishes importing protocol types
if _local_mcp_module:
    sys.modules["mcp"] = _local_mcp_module
if _local_mcp_server:
    sys.modules["mcp.server"] = _local_mcp_server
import structlog
from pydantic import BaseModel, Field

try:
    from .tools.audit_file import AuditFileTool
except ModuleNotFoundError:
    # audit_file tool is optional for this client; keep server importable
    AuditFileTool = None
from ..models.document import Document
from ..services.minio_storage import get_minio_storage

logger = structlog.get_logger(__name__)

# Initialize FastMCP server
mcp = FastMCP(
    name="OctaviOS MCP",
    version="1.0.0",
    instructions="Model Context Protocol server for Saptiva OctaviOS Chat",
)


# ============================================================================
# TOOL 1: audit_file - COPILOTO-AUDIT Compliance Validation
# ============================================================================


class AuditInput(BaseModel):
    doc_id: str = Field(..., description="ID del documento")
    user_id: str = Field(..., description="ID del usuario propietario")
    policy_id: str = Field("auto", description="ID de la política")


@mcp.tool()
async def audit_file(args: AuditInput, ctx: Context = None) -> dict:
    """
    Validate PDF documents against COPILOTO-AUDIT compliance policies.
    """
    if AuditFileTool is None:
        raise RuntimeError("audit_file tool no disponible en este entorno.")

    doc_id = args.doc_id
    user_id = args.user_id
    policy_id = args.policy_id

    logger.info("🕵️ [SERVER TOOL START]", doc_id=doc_id, user_id=user_id)

    tool_instance = AuditFileTool()
    return await tool_instance.execute(
        {
            "doc_id": doc_id,
            "user_id": user_id,
            "policy_id": policy_id,
            "enable_disclaimer": True,
            "enable_format": True,
            "enable_logo": True,
            "enable_grammar": True,
        }
    )


# ============================================================================
# TOOL 2: excel_analyzer - Excel Data Analysis
# ============================================================================


@mcp.tool()
async def excel_analyzer(
    doc_id: str,
    sheet_name: Optional[str] = None,
    operations: list[str] = None,
    aggregate_columns: list[str] = None,
    ctx: Context = None,
) -> dict:
    """
    Analyze Excel files and return statistics, aggregations, and validation.

    Operations:
    - stats: Row/column counts, data types, null counts
    - aggregate: Sum, mean, median, std, min, max for numeric columns
    - validate: Missing values, type mismatches
    - preview: First 10 rows as JSON records

    Args:
        doc_id: Document ID (Excel file)
        sheet_name: Sheet name (default: first sheet)
        operations: Operations to perform (default: ["stats", "preview"])
        aggregate_columns: Columns to aggregate (for "aggregate" operation)
        ctx: FastMCP context (auto-injected)

    Returns:
        Analysis results with requested operations

    Example:
        >>> result = await excel_analyzer(
        ...     doc_id="doc_123",
        ...     operations=["stats", "aggregate"],
        ...     aggregate_columns=["revenue", "cost"]
        ... )
        >>> print(result["stats"]["row_count"])
    """
    import pandas as pd

    operations = operations or ["stats", "preview"]
    aggregate_columns = aggregate_columns or []
    user_id = getattr(ctx, "user_id", None) if ctx else None

    if ctx:
        await ctx.info(f"Excel analyzer tool invoked for doc_id={doc_id}")

    logger.info("Excel analyzer tool execution started", doc_id=doc_id, user_id=user_id)

    # 1. Get document
    doc = await Document.get(doc_id)
    if not doc:
        raise ValueError(f"Document not found: {doc_id}")

    # 2. Check ownership
    if user_id and doc.user_id != user_id:
        raise PermissionError(
            f"User {user_id} not authorized to analyze document {doc_id}"
        )

    # 3. Check file type
    if doc.content_type not in [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    ]:
        raise ValueError(f"Document is not an Excel file: {doc.content_type}")

    # 4. Load Excel file
    minio_storage = get_minio_storage()
    excel_path, is_temp = minio_storage.materialize_document(
        doc.minio_key, filename=doc.filename
    )

    try:
        if ctx:
            await ctx.report_progress(0.2, "Loading Excel file...")

        df = pd.read_excel(excel_path, sheet_name=sheet_name or 0)
        actual_sheet_name = sheet_name or "Sheet1"

        if ctx:
            await ctx.report_progress(0.5, f"Analyzing {len(df)} rows...")

        result = {"doc_id": doc_id, "sheet_name": actual_sheet_name}

        # 5. Perform operations
        if "stats" in operations:
            columns_info = []
            for col in df.columns:
                columns_info.append(
                    {
                        "name": col,
                        "dtype": str(df[col].dtype),
                        "non_null_count": int(df[col].count()),
                        "null_count": int(df[col].isnull().sum()),
                    }
                )
            result["stats"] = {
                "row_count": len(df),
                "column_count": len(df.columns),
                "columns": columns_info,
            }

        if "aggregate" in operations:
            aggregates = {}
            for col in aggregate_columns:
                if col not in df.columns or not pd.api.types.is_numeric_dtype(df[col]):
                    continue
                aggregates[col] = {
                    "sum": float(df[col].sum()),
                    "mean": float(df[col].mean()),
                    "median": float(df[col].median()),
                    "std": float(df[col].std()),
                    "min": float(df[col].min()),
                    "max": float(df[col].max()),
                }
            result["aggregates"] = aggregates

        if "validate" in operations:
            total_missing = int(df.isnull().sum().sum())
            columns_with_missing = df.columns[df.isnull().any()].tolist()
            result["validation"] = {
                "total_missing_values": total_missing,
                "columns_with_missing": columns_with_missing,
                "type_mismatches": [],
            }

        if "preview" in operations:
            result["preview"] = df.head(10).to_dict(orient="records")

        if ctx:
            await ctx.report_progress(1.0, "Analysis complete")

        return result

    finally:
        if is_temp and excel_path.exists():
            excel_path.unlink()


# ============================================================================
# TOOL 3: viz_tool - Data Visualization
# ============================================================================


@mcp.tool()
async def viz_tool(
    chart_type: str,
    data_source: dict,
    x_column: Optional[str] = None,
    y_column: Optional[str] = None,
    title: str = "Chart",
    library: str = "plotly",
    ctx: Context = None,
) -> dict:
    """
    Generate interactive chart specifications (Plotly/ECharts).

    Chart types: bar, line, pie, scatter, heatmap, histogram
    Data sources:
    - inline: {"type": "inline", "data": [...]}
    - excel: {"type": "excel", "doc_id": "...", "sheet_name": "..."}
    - sql: {"type": "sql", "sql_query": "..."}

    Args:
        chart_type: Type of chart
        data_source: Data source configuration
        x_column: X-axis column name
        y_column: Y-axis column name
        title: Chart title
        library: Charting library ("plotly" or "echarts")
        ctx: FastMCP context (auto-injected)

    Returns:
        Chart specification ready for frontend rendering

    Example:
        >>> result = await viz_tool(
        ...     chart_type="bar",
        ...     data_source={
        ...         "type": "inline",
        ...         "data": [
        ...             {"month": "Jan", "revenue": 10000},
        ...             {"month": "Feb", "revenue": 15000},
        ...         ]
        ...     },
        ...     x_column="month",
        ...     y_column="revenue",
        ...     title="Monthly Revenue"
        ... )
        >>> print(result["spec"])
    """
    import pandas as pd

    user_id = getattr(ctx, "user_id", None) if ctx else None

    if ctx:
        await ctx.info(f"Viz tool invoked: chart_type={chart_type}, library={library}")

    logger.info(
        "Viz tool execution started",
        chart_type=chart_type,
        library=library,
        user_id=user_id,
    )

    # 1. Load data
    if ctx:
        await ctx.report_progress(0.3, "Loading data source...")

    source_type = data_source.get("type")

    if source_type == "inline":
        data = data_source["data"]

    elif source_type == "excel":
        doc_id = data_source["doc_id"]
        sheet_name = data_source.get("sheet_name")

        doc = await Document.get(doc_id)
        if not doc:
            raise ValueError(f"Document not found: {doc_id}")
        if user_id and doc.user_id != user_id:
            raise PermissionError(
                f"User {user_id} not authorized to access document {doc_id}"
            )

        minio_storage = get_minio_storage()
        excel_path, is_temp = minio_storage.materialize_document(
            doc.minio_key, filename=doc.filename
        )

        try:
            df = pd.read_excel(excel_path, sheet_name=sheet_name or 0)
            data = df.to_dict(orient="records")
        finally:
            if is_temp and excel_path.exists():
                excel_path.unlink()

    elif source_type == "sql":
        raise NotImplementedError("SQL data source not yet implemented")

    else:
        raise ValueError(f"Unknown data source type: {source_type}")

    if not data:
        raise ValueError("No data loaded from source")

    # 2. Generate chart spec
    if ctx:
        await ctx.report_progress(0.7, "Generating chart specification...")

    x_data = [row[x_column] for row in data] if x_column else list(range(len(data)))
    y_data = [row[y_column] for row in data] if y_column else [0] * len(data)

    if library == "plotly":
        if chart_type == "bar":
            spec = {
                "data": [{"type": "bar", "x": x_data, "y": y_data}],
                "layout": {
                    "title": title,
                    "xaxis": {"title": x_column or "X"},
                    "yaxis": {"title": y_column or "Y"},
                },
            }
        elif chart_type == "line":
            spec = {
                "data": [
                    {
                        "type": "scatter",
                        "mode": "lines+markers",
                        "x": x_data,
                        "y": y_data,
                    }
                ],
                "layout": {
                    "title": title,
                    "xaxis": {"title": x_column or "X"},
                    "yaxis": {"title": y_column or "Y"},
                },
            }
        elif chart_type == "pie":
            spec = {
                "data": [{"type": "pie", "labels": x_data, "values": y_data}],
                "layout": {"title": title},
            }
        else:
            spec = {
                "data": [
                    {"type": "scatter", "mode": "markers", "x": x_data, "y": y_data}
                ],
                "layout": {
                    "title": title,
                    "xaxis": {"title": x_column or "X"},
                    "yaxis": {"title": y_column or "Y"},
                },
            }

    elif library == "echarts":
        spec = {
            "title": {"text": title},
            "tooltip": {},
            "xAxis": {"data": x_data},
            "yAxis": {},
            "series": [{"name": y_column or "Y", "type": chart_type, "data": y_data}],
        }

    else:
        raise ValueError(f"Unsupported library: {library}")

    if ctx:
        await ctx.report_progress(1.0, "Chart specification generated")

    return {
        "library": library,
        "spec": spec,
        "preview_data": data[:10],
        "metadata": {
            "data_points": len(data),
            "columns": list(data[0].keys()) if data else [],
        },
    }


# ============================================================================
# TOOL 4: deep_research - Aletheia Multi-step Research
# ============================================================================


@mcp.tool()
async def deep_research(
    query: str,
    depth: str = "medium",
    focus_areas: list[str] = None,
    max_iterations: Optional[int] = None,
    include_sources: bool = True,
    ctx: Context = None,
) -> dict:
    """
    Perform multi-step research using Aletheia service.

    Breaks down complex queries, gathers information from multiple sources,
    and synthesizes findings into comprehensive reports.

    Args:
        query: Research question or topic to investigate
        depth: Research depth ("shallow", "medium", "deep")
        focus_areas: Specific areas to focus research on (optional)
        max_iterations: Maximum research iterations (overrides depth setting)
        include_sources: Include source citations in report
        ctx: FastMCP context (auto-injected)

    Returns:
        Research task with status and findings

    Example:
        >>> result = await deep_research(
        ...     query="What are the latest trends in renewable energy?",
        ...     depth="medium",
        ...     focus_areas=["solar", "wind", "battery storage"]
        ... )
        >>> print(result["summary"])
    """
    from ..services.deep_research_service import create_research_task

    focus_areas = focus_areas or []
    user_id = getattr(ctx, "user_id", None) if ctx else None

    # Map depth to iterations if not explicitly provided
    if max_iterations is None:
        depth_to_iterations = {"shallow": 2, "medium": 3, "deep": 5}
        max_iterations = depth_to_iterations.get(depth, 3)

    if ctx:
        await ctx.info(
            f"Deep research tool invoked: query='{query}', depth={depth}, max_iterations={max_iterations}"
        )

    logger.info(
        "Deep research tool execution started",
        query=query,
        depth=depth,
        max_iterations=max_iterations,
        user_id=user_id,
    )

    # Create research task
    if ctx:
        await ctx.report_progress(0.1, "Creating research task...")

    task = await create_research_task(
        query=query,
        user_id=user_id,
        chat_id=None,
        max_iterations=max_iterations,
        focus_areas=focus_areas,
    )

    if ctx:
        await ctx.info(
            f"Research task created: task_id={str(task.id)}, status={task.status}"
        )

    # Build response
    result = {
        "task_id": str(task.id),
        "status": task.status.value if hasattr(task.status, "value") else task.status,
        "query": query,
        "iterations_completed": 0,
        "metadata": {
            "started_at": task.created_at.isoformat() if task.created_at else None,
            "max_iterations": max_iterations,
            "depth": depth,
        },
    }

    # If task is already completed
    if hasattr(task, "status") and task.status.value == "completed" and task.result:
        result.update(
            {
                "summary": task.result.get("summary", ""),
                "findings": task.result.get("findings", []),
                "sources": task.result.get("sources", []) if include_sources else [],
                "iterations_completed": task.result.get("iterations_completed", 0),
                "metadata": {
                    **result["metadata"],
                    "completed_at": (
                        task.completed_at.isoformat() if task.completed_at else None
                    ),
                    "total_duration_ms": task.result.get("total_duration_ms", 0),
                    "tokens_used": task.result.get("tokens_used", 0),
                },
            }
        )

    if ctx:
        await ctx.report_progress(1.0, f"Research task {task.status}")

    return result


# ============================================================================
# TOOL 5: extract_document_text - Multi-tier Text Extraction
# ============================================================================


@mcp.tool()
async def extract_document_text(
    doc_id: str,
    method: str = "auto",
    page_numbers: Optional[list[int]] = None,
    include_metadata: bool = True,
    cache_ttl_seconds: int = 3600,
    ctx: Context = None,
) -> dict:
    """
    Extract text from PDF and image documents using multi-tier strategy.

    Uses 3-tier fallback:
    1. pypdf (fast, for text-based PDFs)
    2. Saptiva PDF SDK (complex layouts)
    3. Saptiva OCR (image-based PDFs)

    Args:
        doc_id: Document ID to extract text from
        method: Extraction method ("auto", "pypdf", "saptiva_sdk", "ocr")
        page_numbers: Specific page numbers to extract (1-indexed, optional)
        include_metadata: Include document metadata in response
        cache_ttl_seconds: Cache TTL in seconds (default: 1 hour)
        ctx: FastMCP context (auto-injected)

    Returns:
        Extracted text with metadata and method information

    Example:
        >>> result = await extract_document_text(
        ...     doc_id="doc_123",
        ...     method="auto",
        ...     include_metadata=True
        ... )
        >>> print(result["text"])
        >>> print(result["method_used"])
    """
    import time

    from ..services.document_extraction import extract_text_from_pdf
    from ..services.document_service import get_document_text

    start_time = time.time()
    page_numbers = page_numbers or []
    user_id = getattr(ctx, "user_id", None) if ctx else None

    if ctx:
        await ctx.info(
            f"Extract document text tool invoked: doc_id={doc_id}, method={method}"
        )

    logger.info(
        "Document extraction tool execution started",
        doc_id=doc_id,
        method=method,
        user_id=user_id,
    )

    # 1. Get document
    doc = await Document.get(doc_id)
    if not doc:
        raise ValueError(f"Document not found: {doc_id}")

    # 2. Check ownership
    if user_id and doc.user_id != user_id:
        raise PermissionError(
            f"User {user_id} not authorized to access document {doc_id}"
        )

    # 3. Check document type
    if doc.content_type not in [
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/tiff",
    ]:
        raise ValueError(
            f"Unsupported document type: {doc.content_type}. "
            "Supported types: PDF, PNG, JPEG, TIFF"
        )

    # 4. Extract text
    extracted_text = None
    method_used = None
    from_cache = False

    if method == "auto":
        # Try cache first
        if ctx:
            await ctx.report_progress(0.2, "Checking cache...")

        try:
            cached_text = await get_document_text(doc_id)
            if cached_text:
                extracted_text = cached_text
                method_used = "cache"
                from_cache = True
                if ctx:
                    await ctx.info("Text retrieved from cache")
        except Exception as e:
            logger.warning("Cache retrieval failed", doc_id=doc_id, error=str(e))

        # If not cached, extract
        if not extracted_text:
            if ctx:
                await ctx.report_progress(
                    0.4, "Extracting text using multi-tier strategy..."
                )

            minio_storage = get_minio_storage()
            file_path, is_temp = minio_storage.materialize_document(
                doc.minio_key, filename=doc.filename
            )

            try:
                extraction_result = await extract_text_from_pdf(
                    pdf_path=file_path,
                    doc_id=doc_id,
                    cache_ttl_seconds=cache_ttl_seconds,
                )
                extracted_text = extraction_result.get("text", "")
                method_used = extraction_result.get("method", "pypdf")

                if ctx:
                    await ctx.info(f"Text extracted using method: {method_used}")
            finally:
                if is_temp and file_path.exists():
                    file_path.unlink()

    duration_ms = (time.time() - start_time) * 1000

    # 5. Build response
    result = {
        "doc_id": doc_id,
        "text": extracted_text or "",
        "method_used": method_used or "unknown",
    }

    if include_metadata:
        word_count = len(extracted_text.split()) if extracted_text else 0
        char_count = len(extracted_text) if extracted_text else 0

        result["metadata"] = {
            "filename": doc.filename,
            "content_type": doc.content_type,
            "size_bytes": doc.size_bytes,
            "char_count": char_count,
            "word_count": word_count,
            "extraction_duration_ms": duration_ms,
            "cached": from_cache,
        }

    if ctx:
        await ctx.report_progress(
            1.0, f"Extraction complete ({len(extracted_text or '')} chars)"
        )

    logger.info(
        "Document extraction completed",
        doc_id=doc_id,
        method_used=method_used,
        char_count=len(extracted_text) if extracted_text else 0,
        duration_ms=duration_ms,
        cached=from_cache,
    )

    return result


# ============================================================================
# Export MCP server
# ============================================================================

__all__ = ["mcp"]

"""Data Visualization Tool - Generates chart specifications."""

from typing import Any, Dict, List, Optional

import pandas as pd
import structlog

from ...models.document import Document
from ...services.minio_storage import get_minio_storage
from ..protocol import ToolCapability, ToolCategory, ToolSpec
from ..tool import Tool

logger = structlog.get_logger(__name__)


class VizTool(Tool):
    """Data Visualization Tool - Generates Plotly/ECharts specs."""

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="viz_tool",
            version="1.0.0",
            display_name="Data Visualization Generator",
            description="Generates interactive chart specifications (Plotly/ECharts) from data sources. Returns JSON spec for frontend rendering.",
            category=ToolCategory.VISUALIZATION,
            capabilities=[
                ToolCapability.SYNC,
                ToolCapability.IDEMPOTENT,
                ToolCapability.CACHEABLE,
            ],
            input_schema={
                "type": "object",
                "properties": {
                    "chart_type": {
                        "type": "string",
                        "enum": [
                            "bar",
                            "line",
                            "pie",
                            "scatter",
                            "heatmap",
                            "histogram",
                        ],
                    },
                    "data_source": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["inline", "excel", "sql"],
                            },
                            "doc_id": {"type": "string"},
                            "sheet_name": {"type": "string"},
                            "sql_query": {"type": "string"},
                            "data": {"type": "array", "items": {"type": "object"}},
                        },
                        "required": ["type"],
                    },
                    "x_column": {"type": "string"},
                    "y_column": {"type": "string"},
                    "title": {"type": "string"},
                    "library": {
                        "type": "string",
                        "enum": ["plotly", "echarts"],
                        "default": "plotly",
                    },
                },
                "required": ["chart_type", "data_source"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "library": {"type": "string"},
                    "spec": {"type": "object"},
                    "preview_data": {"type": "array"},
                    "metadata": {"type": "object"},
                },
            },
            tags=["visualization", "charts", "plotly", "echarts", "bi", "analytics"],
            requires_auth=True,
            rate_limit={"calls_per_minute": 30},
            timeout_ms=15000,
            max_payload_size_kb=500,
        )

    async def validate_input(self, payload: Dict[str, Any]) -> None:
        if "chart_type" not in payload:
            raise ValueError("Missing required field: chart_type")
        if "data_source" not in payload:
            raise ValueError("Missing required field: data_source")
        data_source = payload["data_source"]
        if "type" not in data_source:
            raise ValueError("Missing required field: data_source.type")

    async def execute(
        self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        chart_type = payload["chart_type"]
        data_source = payload["data_source"]
        x_column = payload.get("x_column")
        y_column = payload.get("y_column")
        title = payload.get("title", "Chart")
        library = payload.get("library", "plotly")
        user_id = context.get("user_id") if context else None

        logger.info(
            "Viz tool execution started",
            chart_type=chart_type,
            library=library,
            user_id=user_id,
        )

        data = await self._load_data(data_source, user_id)
        if not data:
            raise ValueError("No data loaded from source")

        if library == "plotly":
            spec = self._generate_plotly_spec(
                chart_type, data, x_column, y_column, title
            )
        elif library == "echarts":
            spec = self._generate_echarts_spec(
                chart_type, data, x_column, y_column, title
            )
        else:
            raise ValueError(f"Unsupported library: {library}")

        return {
            "library": library,
            "spec": spec,
            "preview_data": data[:10],
            "metadata": {
                "data_points": len(data),
                "columns": list(data[0].keys()) if data else [],
            },
        }

    async def _load_data(
        self, data_source: Dict[str, Any], user_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        source_type = data_source["type"]

        if source_type == "inline":
            return data_source["data"]

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
                return df.to_dict(orient="records")
            finally:
                if is_temp and excel_path.exists():
                    excel_path.unlink()

        elif source_type == "sql":
            raise NotImplementedError("SQL data source not yet implemented")
        else:
            raise ValueError(f"Unknown data source type: {source_type}")

    def _generate_plotly_spec(
        self,
        chart_type: str,
        data: List[Dict],
        x_column: Optional[str],
        y_column: Optional[str],
        title: str,
    ) -> Dict:
        x_data = [row[x_column] for row in data] if x_column else list(range(len(data)))
        y_data = [row[y_column] for row in data] if y_column else [0] * len(data)

        if chart_type == "bar":
            return {
                "data": [{"type": "bar", "x": x_data, "y": y_data}],
                "layout": {
                    "title": title,
                    "xaxis": {"title": x_column or "X"},
                    "yaxis": {"title": y_column or "Y"},
                },
            }
        elif chart_type == "line":
            return {
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
            return {
                "data": [{"type": "pie", "labels": x_data, "values": y_data}],
                "layout": {"title": title},
            }
        else:
            return {
                "data": [
                    {"type": "scatter", "mode": "markers", "x": x_data, "y": y_data}
                ],
                "layout": {
                    "title": title,
                    "xaxis": {"title": x_column or "X"},
                    "yaxis": {"title": y_column or "Y"},
                },
            }

    def _generate_echarts_spec(
        self,
        chart_type: str,
        data: List[Dict],
        x_column: Optional[str],
        y_column: Optional[str],
        title: str,
    ) -> Dict:
        x_data = [row[x_column] for row in data] if x_column else list(range(len(data)))
        y_data = [row[y_column] for row in data] if y_column else [0] * len(data)

        return {
            "title": {"text": title},
            "tooltip": {},
            "xAxis": {"data": x_data},
            "yAxis": {},
            "series": [{"name": y_column or "Y", "type": chart_type, "data": y_data}],
        }

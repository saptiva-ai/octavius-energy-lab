"""
Research reports API endpoints.
"""

import tempfile
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, StreamingResponse

from ..core.auth import get_current_user
from ..core.config import Settings, get_settings
from ..models.task import Task as TaskModel
from ..models.task import TaskStatus
from ..models.validation_report import ValidationReport
from ..schemas.common import ApiResponse

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/report/{task_id}", tags=["reports"])
async def download_research_report(
    task_id: str,
    format: str = Query(
        default="md", pattern="^(md|html|pdf)$", description="Report format"
    ),
    include_sources: bool = Query(
        default=True, description="Include source references"
    ),
    http_request: Request = None,
    settings: Settings = Depends(get_settings),
):
    """
    Download research report in specified format.

    Retrieves the final report from Aletheia artifacts and serves it to the user.
    """

    user_id = getattr(http_request.state, "user_id", "anonymous")

    if settings.deep_research_kill_switch:
        logger.warning(
            "research_blocked",
            message="Report download blocked by kill switch",
            user_id=user_id,
            kill_switch=True,
        )
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={
                "error": "Deep Research feature is not available",
                "error_code": "DEEP_RESEARCH_DISABLED",
                "message": "This feature has been disabled.",
                "kill_switch": True,
            },
        )

    try:
        # Verify task exists and user has access
        task = await TaskModel.get(task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
            )

        if task.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to task"
            )

        # Check if task is completed
        if task.status != TaskStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Report not available. Task status: {task.status.value}",
            )

        # Future: Integrate with Aletheia artifact storage
        # Implementation needed:
        # 1. Query Aletheia API for task artifacts
        # 2. Download report file from MinIO/S3 bucket
        # 3. Cache report locally for subsequent requests
        # For now, generate a mock report
        report_content = _generate_mock_report(task, format, include_sources)

        # Determine content type and filename
        content_type_map = {
            "md": "text/markdown",
            "html": "text/html",
            "pdf": "application/pdf",
        }

        filename = f"research_report_{task_id}.{format}"
        content_type = content_type_map[format]

        logger.info(
            "Serving research report",
            task_id=task_id,
            format=format,
            user_id=user_id,
            include_sources=include_sources,
        )

        # Create temporary file for the report
        with tempfile.NamedTemporaryFile(
            mode="w+b", suffix=f".{format}", delete=False
        ) as tmp_file:
            if format == "pdf":
                # For PDF, we'd need to convert content to bytes
                tmp_file.write(report_content.encode("utf-8"))
            else:
                tmp_file.write(report_content.encode("utf-8"))
            tmp_file_path = tmp_file.name

        # Return file response
        return FileResponse(
            path=tmp_file_path,
            filename=filename,
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Task-ID": task_id,
                "X-Generated-At": datetime.utcnow().isoformat(),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error serving research report", error=str(e), task_id=task_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate report",
        )


@router.get("/report/{task_id}/preview", tags=["reports"])
async def preview_research_report(
    task_id: str,
    format: str = Query(
        default="html", pattern="^(html|md)$", description="Preview format"
    ),
    http_request: Request = None,
    settings: Settings = Depends(get_settings),
):
    """
    Preview research report in browser without downloading.
    """

    user_id = getattr(http_request.state, "user_id", "anonymous")

    if settings.deep_research_kill_switch:
        logger.warning(
            "research_blocked",
            message="Report preview blocked by kill switch",
            user_id=user_id,
            kill_switch=True,
        )
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={
                "error": "Deep Research feature is not available",
                "error_code": "DEEP_RESEARCH_DISABLED",
                "message": "This feature has been disabled.",
                "kill_switch": True,
            },
        )

    try:
        # Verify task and access (same as download)
        task = await TaskModel.get(task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
            )

        if task.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to task"
            )

        if task.status != TaskStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Report not available. Task status: {task.status.value}",
            )

        # Generate preview content
        content = _generate_mock_report(task, format, include_sources=True)

        content_type = "text/html" if format == "html" else "text/plain"

        logger.info(
            "Serving report preview", task_id=task_id, format=format, user_id=user_id
        )

        return StreamingResponse(
            iter([content.encode("utf-8")]),
            media_type=content_type,
            headers={"X-Task-ID": task_id, "X-Preview-Mode": "true"},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error serving report preview", error=str(e), task_id=task_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate preview",
        )


@router.get("/report/{task_id}/metadata", tags=["reports"])
async def get_report_metadata(
    task_id: str,
    http_request: Request = None,
    settings: Settings = Depends(get_settings),
):
    """
    Get metadata about the research report.
    """

    user_id = getattr(http_request.state, "user_id", "anonymous")

    if settings.deep_research_kill_switch:
        logger.warning(
            "research_blocked",
            message="Report metadata blocked by kill switch",
            user_id=user_id,
            kill_switch=True,
        )
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={
                "error": "Deep Research feature is not available",
                "error_code": "DEEP_RESEARCH_DISABLED",
                "message": "This feature has been disabled.",
                "kill_switch": True,
            },
        )

    try:
        # Verify task and access
        task = await TaskModel.get(task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
            )

        if task.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to task"
            )

        # Generate metadata
        metadata = {
            "task_id": task_id,
            "status": task.status.value,
            "query": task.input_data.get("query", ""),
            "created_at": task.created_at.isoformat(),
            "completed_at": (
                task.completed_at.isoformat() if task.completed_at else None
            ),
            "available_formats": ["md", "html", "pdf"],
            "estimated_size_mb": 0.5,  # Mock size
            "source_count": 15,  # Mock count
            "evidence_count": 8,  # Mock count
            "processing_time_seconds": 120.0,  # Mock time
            "can_download": task.status == TaskStatus.COMPLETED,
            "artifacts": {
                "report": True,
                "sources": True,
                "citations": True,
                "metadata": True,
            },
        }

        logger.info("Retrieved report metadata", task_id=task_id, user_id=user_id)

        return metadata

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving report metadata", error=str(e), task_id=task_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve metadata",
        )


@router.post("/report/{task_id}/share", tags=["reports"])
async def create_shareable_link(
    task_id: str,
    http_request: Request,
    format: str = "html",
    expires_in_hours: int = 24,
    settings: Settings = Depends(get_settings),
):
    """
    Create a shareable link for a research report.
    """

    user_id = getattr(http_request.state, "user_id", "anonymous")

    if settings.deep_research_kill_switch:
        logger.warning(
            "research_blocked",
            message="Report sharing blocked by kill switch",
            user_id=user_id,
            kill_switch=True,
        )
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={
                "error": "Deep Research feature is not available",
                "error_code": "DEEP_RESEARCH_DISABLED",
                "message": "This feature has been disabled.",
                "kill_switch": True,
            },
        )

    try:
        # Verify task exists and user has access
        task = await TaskModel.get(task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
            )

        if task.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to task"
            )

        if task.status != TaskStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Report not available. Task status: {task.status.value}",
            )

        # Generate shareable token
        import base64
        import json

        share_data = {
            "task_id": task_id,
            "user_id": user_id,
            "format": format,
            "expires_at": (datetime.utcnow().timestamp() + (expires_in_hours * 3600)),
        }

        encoded_data = base64.urlsafe_b64encode(
            json.dumps(share_data).encode()
        ).decode()

        # Create shareable URL
        base_url = str(http_request.base_url).rstrip("/")
        shareable_url = f"{base_url}/api/report/shared/{encoded_data}"

        logger.info(
            "Created shareable link",
            task_id=task_id,
            user_id=user_id,
            expires_in_hours=expires_in_hours,
        )

        return {
            "success": True,
            "shareable_url": shareable_url,
            "expires_in_hours": expires_in_hours,
            "expires_at": datetime.fromtimestamp(share_data["expires_at"]).isoformat(),
            "format": format,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating shareable link", error=str(e), task_id=task_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create shareable link",
        )


@router.get("/report/shared/{share_token}", tags=["reports"])
async def get_shared_report(
    share_token: str, settings: Settings = Depends(get_settings)
):
    """
    Access a shared research report via shareable link.
    """

    if settings.deep_research_kill_switch:
        logger.warning(
            "research_blocked",
            message="Shared report access blocked by kill switch",
            kill_switch=True,
        )
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={
                "error": "Deep Research feature is not available",
                "error_code": "DEEP_RESEARCH_DISABLED",
                "message": "This feature has been disabled.",
                "kill_switch": True,
            },
        )

    try:
        import base64
        import json

        # Decode share token
        try:
            decoded_data = base64.urlsafe_b64decode(share_token.encode()).decode()
            share_data = json.loads(decoded_data)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid share token"
            )

        # Check expiry
        if datetime.utcnow().timestamp() > share_data["expires_at"]:
            raise HTTPException(
                status_code=status.HTTP_410_GONE, detail="Shared link has expired"
            )

        task_id = share_data["task_id"]
        format = share_data.get("format", "html")

        # Verify task still exists
        task = await TaskModel.get(task_id)
        if not task or task.status != TaskStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report no longer available",
            )

        # Generate and serve the report
        content = _generate_mock_report(task, format, include_sources=True)

        content_type = "text/html" if format == "html" else "text/plain"

        logger.info("Served shared report", task_id=task_id, format=format)

        return StreamingResponse(
            iter([content.encode("utf-8")]),
            media_type=content_type,
            headers={"X-Task-ID": task_id, "X-Shared-Report": "true"},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error serving shared report", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load shared report",
        )


@router.delete("/report/{task_id}", response_model=ApiResponse, tags=["reports"])
async def delete_research_report(
    task_id: str,
    http_request: Request = None,
    settings: Settings = Depends(get_settings),
):
    """
    Delete research report and associated artifacts.
    """

    user_id = getattr(http_request.state, "user_id", "anonymous")

    if settings.deep_research_kill_switch:
        logger.warning(
            "research_blocked",
            message="Report deletion blocked by kill switch",
            user_id=user_id,
            kill_switch=True,
        )
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={
                "error": "Deep Research feature is not available",
                "error_code": "DEEP_RESEARCH_DISABLED",
                "message": "This feature has been disabled.",
                "kill_switch": True,
            },
        )

    try:
        # Verify task and access
        task = await TaskModel.get(task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
            )

        if task.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to task"
            )

        # Future: Implement artifact cleanup
        # Implementation needed:
        # 1. Query task for artifact URLs/keys
        # 2. Call Aletheia API to delete task artifacts
        # 3. Remove files from MinIO/S3 bucket
        # 4. Clean up any cached report files
        # For now, just remove task record from database

        await task.delete()

        logger.info("Deleted research report", task_id=task_id, user_id=user_id)

        return ApiResponse(success=True, message="Research report deleted successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting research report", error=str(e), task_id=task_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete report",
        )


@router.get("/audit/{report_id}/download", tags=["audit-reports"])
async def download_audit_report_pdf(
    report_id: str, current_user: dict = Depends(get_current_user)
):
    """
    Download audit report PDF on-demand.

    This endpoint generates and serves the PDF report without needing MinIO.
    Used as fallback when MINIO_STORAGE_ENABLED=false.

    Args:
        report_id: ValidationReport UUID
        current_user: Authenticated user from JWT token

    Returns:
        PDF file response

    Example:
        GET /api/reports/audit/123e4567-e89b-12d3-a456-426614174000/download
    """
    try:
        # Fetch validation report from MongoDB
        report = await ValidationReport.get(report_id)

        if not report:
            logger.warning("Audit report not found", report_id=report_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Audit report not found"
            )

        # Verify ownership
        user_id = current_user.get("sub") or current_user.get("user_id")
        if report.user_id != user_id:
            logger.warning(
                "Access denied to audit report",
                report_id=report_id,
                report_owner=report.user_id,
                requesting_user=user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this audit report",
            )

        # Check if PDF was pre-generated during audit
        attachments = report.attachments or {}
        pdf_report_path = attachments.get("pdf_report_path")

        if not pdf_report_path:
            logger.warning(
                "No pre-generated PDF available for audit report",
                report_id=report_id,
                user_id=user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="PDF report not available. Re-run the audit to generate a new report.",
            )

        # Check if the file exists
        from pathlib import Path

        pdf_path = Path(pdf_report_path)
        if not pdf_path.exists():
            logger.warning(
                "Pre-generated PDF file not found on disk",
                report_id=report_id,
                pdf_path=pdf_report_path,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="PDF report file not found. Re-run the audit to generate a new report.",
            )

        # Create filename with timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"auditoria_{report.client_name or 'demo'}_{timestamp}.pdf"

        logger.info(
            "Serving pre-generated audit PDF",
            report_id=report_id,
            user_id=user_id,
            filename=filename,
            source_path=pdf_report_path,
        )

        # Return PDF as download
        return FileResponse(
            path=pdf_report_path,
            filename=filename,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Report-ID": report_id,
                "X-Generated-At": datetime.utcnow().isoformat(),
                "X-Source": "pre-generated",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to generate audit report PDF",
            error=str(e),
            exc_type=type(e).__name__,
            report_id=report_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate audit report PDF: {str(e)}",
        )


def _generate_mock_report(task: TaskModel, format: str, include_sources: bool) -> str:
    """
    Generate a mock research report for testing.

    In production, this would fetch the actual report from Aletheia artifacts.
    """

    query = task.input_data.get("query", "Unknown query")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    if format == "md":
        content = f"""# Research Report: {query}

**Generated:** {timestamp}  
**Task ID:** {task.id}  
**Status:** {task.status.value}

## Executive Summary

This is a mock research report generated for testing purposes. In a real implementation, this would contain the actual research findings from the Aletheia orchestrator.

## Key Findings

1. **Finding 1:** This is a placeholder finding that demonstrates the report structure.
2. **Finding 2:** Another important discovery from the research process.
3. **Finding 3:** Additional insights gathered during the investigation.

## Detailed Analysis

### Section 1: Background
The research query "{query}" was processed using advanced AI agents and web search capabilities.

### Section 2: Methodology
- Web search and source collection
- Evidence extraction and analysis
- Synthesis and fact-checking
- Quality assessment and validation

### Section 3: Results
The analysis revealed several important patterns and insights relevant to the original query.

## Conclusions

Based on the comprehensive analysis, we can conclude that the research objectives have been met successfully.
"""

        if include_sources:
            content += """
## Sources

1. [Example Source 1](https://example1.com) - Primary research article
2. [Example Source 2](https://example2.com) - Supporting documentation
3. [Example Source 3](https://example3.com) - Expert analysis

## Citations

- Source 1: Cited in findings 1 and 2
- Source 2: Referenced in methodology section
- Source 3: Used for validation and fact-checking
"""

    elif format == "html":
        content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Research Report: {query}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
        h1 {{ color: #333; border-bottom: 2px solid #eee; }}
        h2 {{ color: #666; }}
        .metadata {{ background: #f5f5f5; padding: 15px; border-radius: 5px; }}
        .finding {{ margin: 10px 0; padding: 10px; background: #f9f9f9; border-left: 4px solid #007cba; }}
    </style>
</head>
<body>
    <h1>Research Report: {query}</h1>
    
    <div class="metadata">
        <strong>Generated:</strong> {timestamp}<br>
        <strong>Task ID:</strong> {task.id}<br>
        <strong>Status:</strong> {task.status.value}
    </div>

    <h2>Executive Summary</h2>
    <p>This is a mock research report generated for testing purposes. In a real implementation, this would contain the actual research findings from the Aletheia orchestrator.</p>

    <h2>Key Findings</h2>
    <div class="finding"><strong>Finding 1:</strong> This is a placeholder finding that demonstrates the report structure.</div>
    <div class="finding"><strong>Finding 2:</strong> Another important discovery from the research process.</div>
    <div class="finding"><strong>Finding 3:</strong> Additional insights gathered during the investigation.</div>

    <h2>Detailed Analysis</h2>
    <h3>Background</h3>
    <p>The research query "{query}" was processed using advanced AI agents and web search capabilities.</p>
    
    <h3>Results</h3>
    <p>The analysis revealed several important patterns and insights relevant to the original query.</p>

    <h2>Conclusions</h2>
    <p>Based on the comprehensive analysis, we can conclude that the research objectives have been met successfully.</p>
</body>
</html>"""

    else:  # PDF format - return markdown that could be converted to PDF
        content = _generate_mock_report(task, "md", include_sources)

    return content

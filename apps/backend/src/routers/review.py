"""
Document review router - handles review workflow and SSE events.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Optional
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sse_starlette.sse import EventSourceResponse

from ..core.auth import get_current_user
from ..core.config import get_settings
from ..models.document import Document, DocumentStatus
from ..models.review_job import ReviewJob, ReviewStatus
from ..models.user import User
from ..models.validation_report import ValidationReport
from ..schemas.audit_message import ValidationReportResponse
from ..schemas.review import (
    ColorAuditResponse,
    ColorPairResponse,
    GrammarFindingResponse,
    ReviewEventData,
    ReviewReportResponse,
    ReviewStartRequest,
    ReviewStartResponse,
    ReviewStatusResponse,
    ReviewWarningResponse,
    SpellingFindingResponse,
    StyleNoteResponse,
    SuggestedRewriteResponse,
    SummaryBulletResponse,
)
from ..services.audit_mcp_client import (
    MCPAuditorUnavailableError,
    audit_document_via_mcp,
)
from ..services.minio_storage import get_minio_storage
from ..services.review_service import review_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/review", tags=["review"])


@router.post(
    "/start", response_model=ReviewStartResponse, status_code=status.HTTP_201_CREATED
)
async def start_review(
    request: ReviewStartRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Start document review.

    Creates a review job and begins processing:
    1. LanguageTool grammar/spelling check
    2. Saptiva LLM suggestions
    3. Summary generation (if requested)
    4. Color accessibility audit (if requested)

    Args:
        request: Review configuration
        current_user: Authenticated user

    Returns:
        ReviewStartResponse with job_id
    """
    logger.info(
        "Review start requested",
        doc_id=request.doc_id,
        model=request.model,
        user_id=str(current_user.id),
    )

    # Get document
    doc = await Document.get(request.doc_id)

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Check ownership
    if doc.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to review this document",
        )

    # Check document status
    if doc.status != DocumentStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document not ready for review. Status: {doc.status}",
        )

    # Create review job
    job = await review_service.create_review_job(
        doc=doc,
        user_id=str(current_user.id),
        request=request,
    )

    # Start processing in background
    asyncio.create_task(_process_review_job(job.job_id, str(doc.id)))

    logger.info(
        "Review job created",
        job_id=job.job_id,
        doc_id=request.doc_id,
    )

    return ReviewStartResponse(
        job_id=job.job_id,
        status=job.status.value,
    )


@router.get("/events/{job_id}")
async def review_events(
    job_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    Server-Sent Events (SSE) for review progress.

    Streams real-time updates as review progresses through stages:
    RECEIVED → EXTRACT → LT_GRAMMAR → LLM_SUGGEST → SUMMARY → COLOR_AUDIT → READY

    Args:
        job_id: Review job ID
        current_user: Authenticated user

    Returns:
        SSE stream
    """
    logger.info("SSE connection requested", job_id=job_id, user_id=str(current_user.id))

    # Verify job exists and user owns it
    job = await ReviewJob.find_one(ReviewJob.job_id == job_id)

    if not job:
        # Compatibility alias for files/events
        document = await Document.get(job_id)
        if document and document.user_id == str(current_user.id):
            from .files import file_events as files_event_handler

            return await files_event_handler(job_id, request, current_user)

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review job not found",
        )

    if job.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this job",
        )

    trace_id = request.query_params.get("t") or uuid4().hex
    request.state.trace_id = trace_id

    settings = get_settings()
    origin = request.headers.get("origin") or request.headers.get("referer")
    allowed_origins = set(settings.parsed_cors_origins or [])
    if (
        origin
        and allowed_origins
        and not any(origin.startswith(o) for o in allowed_origins)
    ):
        logger.warning(
            "Blocked SSE origin", origin=origin, allowed=list(allowed_origins)
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden origin",
        )

    async def event_generator() -> AsyncGenerator[dict, None]:
        """Generate SSE events"""
        nonlocal job  # Reference outer job variable
        try:
            # Emit initial metadata event for trace correlation
            yield {
                "event": "meta",
                "data": ReviewEventData(
                    job_id=job.job_id,
                    status="meta",
                    progress=job.progress or 0.0,
                    current_stage=job.current_stage,
                    timestamp=datetime.utcnow().isoformat(),
                    trace_id=trace_id,
                    message=None,
                ).model_dump_json(),
            }

            last_status = None

            # Poll for updates
            while True:
                # Refresh job
                job = await ReviewJob.find_one(ReviewJob.job_id == job_id)

                if not job:
                    break

                # Send update if status changed
                if job.status != last_status:
                    event_data = ReviewEventData(
                        job_id=job.job_id,
                        status=job.status.value,
                        progress=job.progress,
                        current_stage=job.current_stage,
                        message=(
                            job.error_message
                            if job.status == ReviewStatus.FAILED
                            else None
                        ),
                        trace_id=trace_id,
                        timestamp=datetime.utcnow().isoformat(),
                    )

                    yield {
                        "event": "status",
                        "data": event_data.model_dump_json(),
                    }

                    last_status = job.status

                    logger.info(
                        "SSE event sent",
                        job_id=job_id,
                        status=job.status.value,
                        progress=job.progress,
                    )

                # Check if job is complete
                if job.status in [
                    ReviewStatus.READY,
                    ReviewStatus.FAILED,
                    ReviewStatus.CANCELLED,
                ]:
                    break

                # Wait before next poll
                await asyncio.sleep(1.0)

        except asyncio.CancelledError:
            logger.info("SSE connection closed by client", job_id=job_id)
        except Exception as e:
            logger.error("SSE stream error", job_id=job_id, error=str(e))

    return EventSourceResponse(event_generator())


@router.get("/status/{job_id}", response_model=ReviewStatusResponse)
async def get_review_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get review job status"""
    job = await ReviewJob.find_one(ReviewJob.job_id == job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review job not found",
        )

    if job.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this job",
        )

    return ReviewStatusResponse(
        job_id=job.job_id,
        status=job.status.value,
        progress=job.progress,
        current_stage=job.current_stage,
        error_message=job.error_message,
    )


@router.get("/report/{doc_id}", response_model=ReviewReportResponse)
async def get_review_report(
    doc_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get completed review report.

    Returns comprehensive findings including:
    - Summary (if generated)
    - Spelling errors
    - Grammar issues
    - Style notes
    - Suggested rewrites
    - Color accessibility audit

    Args:
        doc_id: Document ID
        current_user: Authenticated user

    Returns:
        ReviewReportResponse
    """
    # Get document
    doc = await Document.get(doc_id)

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if doc.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this document",
        )

    # Get most recent completed job for this document
    job = await ReviewJob.find_one(
        ReviewJob.doc_id == doc_id,
        ReviewJob.status == ReviewStatus.READY,
    ).sort(-ReviewJob.created_at)

    if not job or not job.report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed review found for this document",
        )

    # Build response
    report = job.report

    # Convert color audit
    color_audit_data = report.color_audit or {}
    color_audit = ColorAuditResponse(
        pairs=[
            ColorPairResponse(
                fg=pair.get("fg", "#000000"),
                bg=pair.get("bg", "#FFFFFF"),
                ratio=pair.get("ratio", 0.0),
                wcag=pair.get("wcag", "fail"),
                location=pair.get("location"),
            )
            for pair in color_audit_data.get("pairs", [])
        ],
        pass_count=color_audit_data.get("pass_count", 0),
        fail_count=color_audit_data.get("fail_count", 0),
    )

    # Build response
    response = ReviewReportResponse(
        doc_id=doc_id,
        job_id=job.job_id,
        summary=[
            SummaryBulletResponse(page=s.page, bullets=s.bullets)
            for s in report.summary
        ],
        spelling=[
            SpellingFindingResponse(
                page=s.page,
                span=s.span,
                suggestions=s.suggestions,
            )
            for s in report.spelling
        ],
        grammar=[
            GrammarFindingResponse(
                page=g.page,
                span=g.span,
                rule=g.rule,
                explain=g.explain,
                suggestions=g.suggestions,
            )
            for g in report.grammar
        ],
        style_notes=[
            StyleNoteResponse(
                page=s.page,
                issue=s.issue,
                advice=s.advice,
                span=s.span,
            )
            for s in report.style_notes
        ],
        suggested_rewrites=[
            SuggestedRewriteResponse(
                page=r.page,
                block_id=r.block_id,
                original=r.original,
                proposal=r.proposal,
                rationale=r.rationale,
            )
            for r in report.suggested_rewrites
        ],
        color_audit=color_audit,
        artifacts=report.artifacts,
        metrics={
            "lt_findings_count": job.lt_findings_count,
            "llm_calls_count": job.llm_calls_count,
            "tokens_in": job.tokens_in,
            "tokens_out": job.tokens_out,
            "processing_time_ms": job.processing_time_ms,
        },
        created_at=job.created_at.isoformat(),
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        warnings=[
            ReviewWarningResponse(
                stage=w.stage,
                code=w.code,
                message=w.message,
            )
            for w in report.warnings
        ],
        llm_status=report.llm_status,
    )

    logger.info(
        "Review report retrieved",
        doc_id=doc_id,
        job_id=job.job_id,
        findings_count=len(report.spelling) + len(report.grammar),
    )

    return response


@router.post(
    "/validate", response_model=ValidationReportResponse, status_code=status.HTTP_200_OK
)
async def validate_document_414(
    doc_id: str,
    policy_id: str = "auto",
    client_name: str = None,  # DEPRECATED: Use policy_id instead
    enable_disclaimer: bool = True,
    enable_format: bool = True,
    enable_logo: bool = True,
    current_user: User = Depends(get_current_user),
):
    """
    Validate document against Copiloto Audit compliance rules.

    **V2 UPDATE**: Now supports policy-based validation with auto-detection

    Validates:
    - **Disclaimers**: Presence and coverage on all pages (footer detection)
    - **Format**: Number formatting, fonts, colors (brand compliance)
    - **Logo**: Presence, size, position on required pages

    Args:
        doc_id: Document ID to validate
        policy_id: Policy to apply (default: "auto")
            - "auto": Auto-detect policy based on document content
            - "demo-std": Standard Demo Capital validation
            - "demo-strict": Strict validation for premium clients
            - "bancomuestra": BancoMuestra-specific validation
            - "afore-xxi": Afore XXI-specific validation
        client_name: DEPRECATED - Use policy_id instead. Only used if policy doesn't specify client_name
        enable_disclaimer: Run disclaimer auditor (default: True)
        enable_format: Run format auditor (default: True)
        enable_logo: Run logo auditor (default: True)
        current_user: Authenticated user

    Returns:
        ValidationReportResponse with findings and summary

    Example (with auto-detection):
        POST /api/review/validate?doc_id=abc123&policy_id=auto

    Example (with explicit policy):
        POST /api/review/validate?doc_id=abc123&policy_id=bancomuestra

    Example (legacy - backward compatible):
        POST /api/review/validate?doc_id=abc123&client_name=BancoMuestra

        Response:
        {
          "job_id": "val-xyz789",
          "status": "done",
          "findings": [
            {
              "id": "disclaimer-missing-5-abc",
              "category": "compliance",
              "rule": "disclaimer_coverage",
              "issue": "Disclaimer ausente o inválido en página 5",
              "severity": "high",
              "location": {"page": 5, "bbox": null},
              "suggestion": "Agregar disclaimer válido en el footer de la página 5"
            }
          ],
          "summary": {
            "total_findings": 1,
            "policy_id": "bancomuestra",
            "policy_name": "BancoMuestra Custom",
            "disclaimer_coverage": 0.95,
            "findings_by_severity": {"high": 1}
          }
        }
    """
    logger.info(
        "Compliance validation requested",
        doc_id=doc_id,
        policy_id=policy_id,
        client_name=client_name,
        user_id=str(current_user.id),
        enable_disclaimer=enable_disclaimer,
        enable_format=enable_format,
        enable_logo=enable_logo,
    )

    # ========================================================================
    # 1. Get and validate document
    # ========================================================================

    doc = await Document.get(doc_id)

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Check ownership
    if doc.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to validate this document",
        )

    # Check document status
    if doc.status != DocumentStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document not ready for validation. Status: {doc.status}",
        )

    # ========================================================================
    # 2. Get PDF path from local filesystem (V1)
    # ========================================================================

    temp_pdf_path: Optional[Path] = None
    try:
        pdf_path = Path(doc.minio_key)

        if not pdf_path.exists():
            minio_storage = get_minio_storage()
            pdf_path, is_temp = minio_storage.materialize_document(
                doc.minio_key,
                filename=doc.filename,
            )
            if is_temp:
                temp_pdf_path = pdf_path

        logger.info(
            "PDF path resolved for validation",
            doc_id=doc_id,
            pdf_path=str(pdf_path),
            source="temp" if temp_pdf_path else "local",
            size_bytes=pdf_path.stat().st_size,
        )

    except Exception as exc:
        logger.error(
            "Failed to access PDF file",
            doc_id=doc_id,
            error=str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve document: {exc}",
        )

    # ========================================================================
    # 2.5. Call MCP Auditor Microservice
    # ========================================================================

    try:
        # Call the MCP auditor microservice
        mcp_result = await audit_document_via_mcp(
            file_path=str(pdf_path),
            policy_id=policy_id,
            client_name=client_name,
            enable_disclaimer=enable_disclaimer,
            enable_format=enable_format,
            enable_typography=True,  # Always enable all 8 auditors
            enable_grammar=True,
            enable_logo=enable_logo,
            enable_color_palette=True,
            enable_entity_consistency=True,
            enable_semantic_consistency=True,
        )

        logger.info(
            "MCP audit completed",
            doc_id=doc_id,
            job_id=mcp_result.get("job_id"),
            total_findings=mcp_result.get("total_findings", 0),
            policy_id=mcp_result.get("policy_id"),
            policy_name=mcp_result.get("policy_name"),
        )

        # ====================================================================
        # INT1: Save validation report to MongoDB
        # ====================================================================

        try:
            # Create ValidationReport document from MCP result
            validation_report = ValidationReport(
                document_id=doc_id,
                user_id=str(current_user.id),
                job_id=mcp_result.get("job_id"),
                status="done" if mcp_result.get("status") == "completed" else "error",
                client_name=mcp_result.get("policy_name"),
                auditors_enabled={
                    "disclaimer": enable_disclaimer,
                    "format": enable_format,
                    "typography": True,
                    "grammar": True,
                    "logo": enable_logo,
                    "color_palette": True,
                    "entity_consistency": True,
                    "semantic_consistency": True,
                },
                findings=mcp_result.get("top_findings", []),
                summary={
                    "total_findings": mcp_result.get("total_findings", 0),
                    "findings_by_severity": mcp_result.get("findings_by_severity", {}),
                    "findings_by_category": mcp_result.get("findings_by_category", {}),
                    "disclaimer_coverage": mcp_result.get("disclaimer_coverage"),
                    "policy_id": mcp_result.get("policy_id"),
                    "policy_name": mcp_result.get("policy_name"),
                    "validation_duration_ms": mcp_result.get("validation_duration_ms"),
                },
                attachments=(
                    {
                        "pdf_report_path": mcp_result.get("pdf_report_path"),
                        "executive_summary_markdown": mcp_result.get(
                            "executive_summary_markdown"
                        ),
                    }
                    if mcp_result.get("pdf_report_path")
                    else {}
                ),
            )

            # Insert into MongoDB
            await validation_report.insert()

            logger.info(
                "Validation report saved to MongoDB",
                report_id=str(validation_report.id),
                doc_id=doc_id,
                findings_count=mcp_result.get("total_findings", 0),
            )

            # Update document with link to validation report
            doc.validation_report_id = str(validation_report.id)
            await doc.save()

            logger.info(
                "Document linked to validation report",
                doc_id=doc_id,
                validation_report_id=str(validation_report.id),
            )

        except Exception as save_exc:
            # Log error but don't fail the request (report was generated successfully)
            logger.error(
                "Failed to save validation report to MongoDB",
                doc_id=doc_id,
                error=str(save_exc),
                exc_info=True,
            )

        # Build response in ValidationReportResponse format
        from ..schemas.audit_message import Finding, FindingLocation

        findings_list = []
        for f in mcp_result.get("top_findings", []):
            findings_list.append(
                Finding(
                    id=f.get("id", ""),
                    category=f.get("category", "other"),
                    rule=f.get("rule", ""),
                    issue=f.get("issue", ""),
                    severity=f.get("severity", "low"),
                    location=(
                        FindingLocation(
                            page=f.get("location", {}).get("page"),
                            bbox=f.get("location", {}).get("bbox"),
                        )
                        if f.get("location")
                        else None
                    ),
                    suggestion=f.get("suggestion"),
                )
            )

        return ValidationReportResponse(
            job_id=mcp_result.get("job_id", ""),
            status="done" if mcp_result.get("status") == "completed" else "error",
            findings=findings_list,
            summary={
                "total_findings": mcp_result.get("total_findings", 0),
                "findings_by_severity": mcp_result.get("findings_by_severity", {}),
                "findings_by_category": mcp_result.get("findings_by_category", {}),
                "disclaimer_coverage": mcp_result.get("disclaimer_coverage"),
                "policy_id": mcp_result.get("policy_id"),
                "policy_name": mcp_result.get("policy_name"),
                "validation_duration_ms": mcp_result.get("validation_duration_ms"),
            },
            attachments=(
                {
                    "pdf_report_path": mcp_result.get("pdf_report_path"),
                    "executive_summary_markdown": mcp_result.get(
                        "executive_summary_markdown"
                    ),
                }
                if mcp_result.get("pdf_report_path")
                else {}
            ),
        )

    except MCPAuditorUnavailableError as mcp_exc:
        logger.error(
            "MCP auditor unavailable",
            doc_id=doc_id,
            error=str(mcp_exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Audit service unavailable: {mcp_exc}",
        )

    except Exception as exc:
        logger.error(
            "Compliance validation failed",
            doc_id=doc_id,
            error=str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Validation failed: {exc}",
        )
    finally:
        if temp_pdf_path and temp_pdf_path.exists():
            try:
                temp_pdf_path.unlink()
                logger.debug(
                    "Temporary PDF cleaned up after validation",
                    doc_id=doc_id,
                    pdf_path=str(temp_pdf_path),
                )
            except Exception as cleanup_exc:
                logger.warning(
                    "Failed to cleanup temporary PDF",
                    doc_id=doc_id,
                    pdf_path=str(temp_pdf_path),
                    error=str(cleanup_exc),
                )


async def _process_review_job(job_id: str, doc_id: str):
    """Background task to process review job"""
    try:
        # Get job and document
        job = await ReviewJob.find_one(ReviewJob.job_id == job_id)
        doc = await Document.get(doc_id)

        if not job or not doc:
            logger.error("Job or document not found", job_id=job_id, doc_id=doc_id)
            return

        # Start processing
        job.started_at = datetime.utcnow()
        await job.save()

        # Run review pipeline
        await review_service.process_review(job, doc)

        logger.info("Review job completed", job_id=job_id)

    except Exception as e:
        logger.error("Review job failed", job_id=job_id, error=str(e))
        # Update job status
        job = await ReviewJob.find_one(ReviewJob.job_id == job_id)
        if job:
            await review_service.update_job_status(
                job,
                ReviewStatus.FAILED,
                error=str(e),
            )

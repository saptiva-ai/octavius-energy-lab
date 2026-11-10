"""
Review service - orchestrates document review workflow.

Coordinates LanguageTool, Saptiva LLM, and ColorAuditor to provide
comprehensive document review including grammar, style, and accessibility.
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from ..models.document import Document
from ..models.review_job import (
    GrammarFinding,
    ReviewJob,
    ReviewReport,
    ReviewStatus,
    ReviewWarning,
    SpellingFinding,
    StyleNote,
    SuggestedRewrite,
    SummaryBullet,
)
from ..schemas.review import ReviewStartRequest
from .languagetool_client import languagetool_client

# NOTE: color_auditor moved to un plugin privado de auditoría (Plugin-First Architecture)
# from .color_auditor import color_auditor
from .saptiva_client import saptiva_client

logger = structlog.get_logger(__name__)


class ReviewService:
    """Service for document review orchestration"""

    # System prompt for Saptiva
    SYSTEM_PROMPT = """Eres un revisor editorial profesional. Objetivo:
(1) ortografía/gramática, (2) estilo y claridad, (3) reescrituras conservadoras,
(4) consistencia terminológica, (5) resumen si se solicita.

Reglas:
- Responde en español.
- No inventes contenido; si falta, indícalo.
- Cita páginas como [p.X].
- Devuelve SOLO JSON por bloque; preserva significado.

Esquema JSON por bloque:
{
  "block_id":"...", "page":X,
  "findings": {
    "spelling":[{"span":"...","suggestions":["..."]}],
    "grammar":[{"span":"...","rule":"...","explain":"..."}],
    "style":[{"issue":"...","advice":"..."}]
  },
  "rewrite":{"proposal":"...","rationale":"..."},
  "summary_bullets":["..."]
}"""

    def __init__(self):
        self.lt_client = languagetool_client
        # NOTE: color_auditor moved to un plugin privado de auditoría (Plugin-First Architecture)
        # self.auditor = color_auditor
        self.max_block_tokens = 1200
        # NOTE: Cortex escalation removed - using Turbo for all reviews

    async def create_review_job(
        self,
        doc: Document,
        user_id: str,
        request: ReviewStartRequest,
    ) -> ReviewJob:
        """
        Create a new review job.

        Args:
            doc: Document to review
            user_id: User ID
            request: Review configuration

        Returns:
            Created ReviewJob
        """
        job_id = f"rev-{uuid.uuid4().hex[:12]}"

        job = ReviewJob(
            job_id=job_id,
            doc_id=str(doc.id),
            user_id=user_id,
            model=request.model,
            rewrite_policy=request.rewrite_policy,
            summary=request.summary,
            color_audit=request.color_audit,
            status=ReviewStatus.QUEUED,
        )

        await job.insert()

        logger.info(
            "Created review job",
            job_id=job_id,
            doc_id=str(doc.id),
            model=request.model,
        )

        return job

    async def update_job_status(
        self,
        job: ReviewJob,
        status: ReviewStatus,
        current_stage: Optional[str] = None,
        progress: Optional[float] = None,
        error: Optional[str] = None,
    ):
        """Update job status and emit event"""
        job.status = status
        job.updated_at = datetime.utcnow()

        if current_stage:
            job.current_stage = current_stage
        if progress is not None:
            job.progress = progress
        if error:
            job.error_message = error

        if status == ReviewStatus.READY:
            job.completed_at = datetime.utcnow()
        elif status in [ReviewStatus.FAILED, ReviewStatus.CANCELLED]:
            job.completed_at = datetime.utcnow()

        await job.save()

        logger.info(
            "Updated job status",
            job_id=job.job_id,
            status=status,
            progress=progress,
            stage=current_stage,
        )

    async def process_review(self, job: ReviewJob, doc: Document) -> ReviewReport:
        """
        Main review processing pipeline.

        Stages:
        1. RECEIVED - Job accepted
        2. EXTRACT - Extract text blocks
        3. LT_GRAMMAR - Run LanguageTool
        4. LLM_SUGGEST - Run Saptiva for suggestions
        5. SUMMARY - Generate summary (if requested)
        6. COLOR_AUDIT - Check accessibility (if requested)
        7. READY - Complete

        Args:
            job: ReviewJob
            doc: Document

        Returns:
            ReviewReport
        """
        start_time = datetime.utcnow()

        try:
            # Stage 1: RECEIVED
            await self.update_job_status(
                job,
                ReviewStatus.RECEIVED,
                "Trabajo recibido",
                progress=5.0,
            )

            # Stage 2: EXTRACT
            await self.update_job_status(
                job,
                ReviewStatus.EXTRACT,
                "Extrayendo texto del documento",
                progress=15.0,
            )

            # Extract text blocks from pages
            blocks = self._extract_blocks(doc)
            logger.info("Extracted text blocks", count=len(blocks), doc_id=str(doc.id))

            # Stage 3: LT_GRAMMAR
            await self.update_job_status(
                job,
                ReviewStatus.LT_GRAMMAR,
                "Analizando gramática con LanguageTool",
                progress=30.0,
            )

            lt_results, lt_warnings = await self._run_languagetool(blocks)
            job.lt_findings_count = sum(
                len(r["spelling"]) + len(r["grammar"]) for r in lt_results
            )

            # Stage 4: LLM_SUGGEST
            await self.update_job_status(
                job,
                ReviewStatus.LLM_SUGGEST,
                "Generando sugerencias con IA",
                progress=50.0,
            )

            llm_results, llm_warnings, llm_status = await self._run_llm_suggestions(
                blocks, lt_results, job.model, job.summary
            )
            job.llm_calls_count = len(llm_results)

            # Combine all warnings
            all_warnings = lt_warnings + llm_warnings

            # Stage 5: SUMMARY (if requested)
            if job.summary:
                await self.update_job_status(
                    job,
                    ReviewStatus.SUMMARY,
                    "Generando resumen",
                    progress=75.0,
                )

            # Stage 6: COLOR_AUDIT (if requested)
            color_audit_result = None
            if job.color_audit:
                await self.update_job_status(
                    job,
                    ReviewStatus.COLOR_AUDIT,
                    "Analizando accesibilidad de colores",
                    progress=85.0,
                )
                color_audit_result = await self._run_color_audit(doc)

            # Compile report
            report = self._compile_report(
                doc,
                lt_results,
                llm_results,
                color_audit_result,
                all_warnings,
                llm_status,
            )

            # Stage 7: READY
            await self.update_job_status(
                job,
                ReviewStatus.READY,
                "Revisión completada",
                progress=100.0,
            )

            # Calculate processing time
            end_time = datetime.utcnow()
            processing_time_ms = int((end_time - start_time).total_seconds() * 1000)
            job.processing_time_ms = processing_time_ms

            # Save report
            job.report = report
            await job.save()

            logger.info(
                "Review completed",
                job_id=job.job_id,
                processing_time_ms=processing_time_ms,
                lt_findings=job.lt_findings_count,
                llm_calls=job.llm_calls_count,
            )

            return report

        except Exception as e:
            logger.error("Review processing failed", job_id=job.job_id, error=str(e))
            await self.update_job_status(
                job,
                ReviewStatus.FAILED,
                error=str(e),
            )
            raise

    def _extract_blocks(self, doc: Document) -> List[Dict[str, Any]]:
        """Extract text blocks from document pages"""
        blocks = []

        for page in doc.pages:
            # Split page into blocks (~800-1200 tokens)
            # For simplicity, treat each page as one block
            # In production, implement smart chunking
            block = {
                "block_id": f"block-{uuid.uuid4().hex[:8]}",
                "page": page.page,
                "text": page.text_md,
            }
            blocks.append(block)

        return blocks

    async def _run_languagetool(
        self, blocks: List[Dict[str, Any]]
    ) -> tuple[List[Dict[str, Any]], List[ReviewWarning]]:
        """Run LanguageTool on all blocks

        Returns:
            Tuple of (results, warnings)
        """
        results = []
        warnings = []

        for block in blocks:
            try:
                lt_response = await self.lt_client.check_text(
                    block["text"], language="es"
                )

                spelling, grammar = self.lt_client.parse_matches(lt_response)

                results.append(
                    {
                        "block_id": block["block_id"],
                        "page": block["page"],
                        "spelling": spelling,
                        "grammar": grammar,
                    }
                )

            except Exception as e:
                logger.error(
                    "LanguageTool check failed",
                    block_id=block["block_id"],
                    error=str(e),
                )

                # Add warning for partial failure
                warnings.append(
                    ReviewWarning(
                        stage="LT_GRAMMAR",
                        code=(
                            "LT_TIMEOUT" if "timeout" in str(e).lower() else "LT_ERROR"
                        ),
                        message=f"LanguageTool falló en página {block['page']}: {str(e)[:100]}",
                    )
                )

                # Continue with empty results for this block
                results.append(
                    {
                        "block_id": block["block_id"],
                        "page": block["page"],
                        "spelling": [],
                        "grammar": [],
                    }
                )

        return results, warnings

    async def _run_llm_suggestions(
        self,
        blocks: List[Dict[str, Any]],
        lt_results: List[Dict[str, Any]],
        model: str,
        include_summary: bool,
    ) -> tuple[List[Dict[str, Any]], List[ReviewWarning], str]:
        """Run LLM to generate suggestions and rewrites

        Returns:
            Tuple of (results, warnings, llm_status)
        """
        results = []
        warnings = []
        failed_blocks = 0

        for idx, block in enumerate(blocks):
            lt_result = lt_results[idx]
            total_lt_findings = len(lt_result["spelling"]) + len(lt_result["grammar"])

            # Use the model passed in (no Cortex escalation)
            selected_model = model

            # Build user prompt
            user_prompt = self._build_user_prompt(block, lt_result, include_summary)

            try:
                # Call Saptiva
                llm_response = await saptiva_client.chat_completion(
                    model=selected_model,
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=800,
                )

                content = llm_response.choices[0]["message"]["content"]

                # Parse JSON response
                llm_data = json.loads(content)

                results.append(
                    {
                        "block_id": block["block_id"],
                        "page": block["page"],
                        "model": selected_model,
                        "llm_data": llm_data,
                    }
                )

            except json.JSONDecodeError as e:
                logger.error(
                    "Failed to parse LLM JSON response",
                    block_id=block["block_id"],
                    error=str(e),
                )
                failed_blocks += 1
                warnings.append(
                    ReviewWarning(
                        stage="LLM_SUGGEST",
                        code="LLM_PARSE_ERROR",
                        message=f"No se pudo parsear respuesta del LLM en página {block['page']}",
                    )
                )
                results.append(
                    {
                        "block_id": block["block_id"],
                        "page": block["page"],
                        "model": selected_model,
                        "llm_data": {},
                    }
                )

            except Exception as e:
                logger.error(
                    "LLM call failed",
                    block_id=block["block_id"],
                    error=str(e),
                )
                failed_blocks += 1
                warnings.append(
                    ReviewWarning(
                        stage="LLM_SUGGEST",
                        code="LLM_API_ERROR",
                        message=f"Saptiva no disponible para página {block['page']}: {str(e)[:100]}",
                    )
                )
                results.append(
                    {
                        "block_id": block["block_id"],
                        "page": block["page"],
                        "model": selected_model,
                        "llm_data": {},
                    }
                )

        # Determine overall LLM status
        llm_status = "ok"
        if failed_blocks == len(blocks):
            llm_status = "failed"
        elif failed_blocks > 0:
            llm_status = "degraded"

        return results, warnings, llm_status

    def _build_user_prompt(
        self,
        block: Dict[str, Any],
        lt_result: Dict[str, Any],
        include_summary: bool,
    ) -> str:
        """Build user prompt for LLM"""
        page = block["page"]
        text = block["text"]
        block_id = block["block_id"]

        prompt = f"""[p.{page}] {text}
block_id={block_id}
Resumen requerido={include_summary}
Devuelve SOLO el JSON con el esquema indicado."""

        return prompt

    async def _run_color_audit(self, doc: Document) -> Dict[str, Any]:
        """Run color accessibility audit"""
        # Extract all text
        full_text = "\n\n".join([page.text_md for page in doc.pages])

        # Audit colors
        # NOTE: color_auditor moved to un plugin privado de auditoría (Plugin-First Architecture)
        # audit_result = self.auditor.audit_document_colors(full_text)
        # Temporary: Return empty result until color audit is integrated via plugin
        audit_result = {
            "status": "skipped",
            "message": "Color auditor moved to auditor privado plugin",
        }

        return audit_result

    def _compile_report(
        self,
        doc: Document,
        lt_results: List[Dict[str, Any]],
        llm_results: List[Dict[str, Any]],
        color_audit_result: Optional[Dict[str, Any]],
        warnings: List[ReviewWarning],
        llm_status: str = "ok",
    ) -> ReviewReport:
        """Compile final review report"""

        spelling = []
        grammar = []
        style_notes = []
        suggested_rewrites = []
        summary = []

        # Aggregate LT results
        for lt_result in lt_results:
            page = lt_result["page"]

            for s in lt_result["spelling"]:
                spelling.append(
                    SpellingFinding(
                        page=page,
                        span=s["span"],
                        suggestions=s["suggestions"],
                        offset=s["offset"],
                        length=s["length"],
                    )
                )

            for g in lt_result["grammar"]:
                grammar.append(
                    GrammarFinding(
                        page=page,
                        span=g["span"],
                        rule=g["rule"],
                        explain=g["explain"],
                        suggestions=g["suggestions"],
                        offset=g["offset"],
                        length=g["length"],
                    )
                )

        # Aggregate LLM results
        for llm_result in llm_results:
            page = llm_result["page"]
            block_id = llm_result["block_id"]
            llm_data = llm_result.get("llm_data", {})

            # Style notes
            for style in llm_data.get("findings", {}).get("style", []):
                style_notes.append(
                    StyleNote(
                        page=page,
                        issue=style.get("issue", ""),
                        advice=style.get("advice", ""),
                    )
                )

            # Rewrite
            rewrite = llm_data.get("rewrite")
            if rewrite:
                suggested_rewrites.append(
                    SuggestedRewrite(
                        page=page,
                        block_id=block_id,
                        original=rewrite.get("proposal", ""),  # Note: keys may vary
                        proposal=rewrite.get("proposal", ""),
                        rationale=rewrite.get("rationale", ""),
                    )
                )

            # Summary
            summary_bullets = llm_data.get("summary_bullets", [])
            if summary_bullets:
                summary.append(SummaryBullet(page=page, bullets=summary_bullets))

        # Color audit
        color_audit_data = color_audit_result or {
            "pairs": [],
            "pass_count": 0,
            "fail_count": 0,
        }

        # Artifacts (presigned URLs, etc.)
        artifacts = {}

        report = ReviewReport(
            summary=summary,
            spelling=spelling,
            grammar=grammar,
            style_notes=style_notes,
            suggested_rewrites=suggested_rewrites,
            color_audit=color_audit_data,
            artifacts=artifacts,
            warnings=warnings,
            llm_status=llm_status,
        )

        return report


# Singleton instance
review_service = ReviewService()

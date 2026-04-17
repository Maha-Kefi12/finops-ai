"""
Export API handlers for PDF reports and recommendations
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
import logging

from src.storage.database import get_db
from src.graph.models import RecSnapshot, LLMReport
from src.export.pdf_generator import generate_recommendations_pdf, generate_llm_report_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/export", tags=["export"])


# ─── Export Recommendations as PDF ──────────────────────────────
@router.get("/recommendations/pdf/{snapshot_id}")
async def export_recommendations_pdf(
    snapshot_id: str,
    db: Session = Depends(get_db),
):
    """
    Export a recommendation snapshot as PDF.
    
    Returns PDF bytes with all recommendations and their details.
    """
    try:
        snapshot = db.query(RecSnapshot).filter(RecSnapshot.id == snapshot_id).first()
        
        if not snapshot:
            raise HTTPException(404, f"Snapshot not found: {snapshot_id}")
        
        # Generate PDF
        pdf_bytes = generate_recommendations_pdf(
            architecture_id=snapshot.architecture_id,
            architecture_name=snapshot.architecture_name or "Unknown Architecture",
            recommendations=snapshot.cards or [],
            total_savings_monthly=snapshot.total_savings_monthly or 0,
            source=snapshot.source or "engine",
            llm_model=snapshot.llm_model,
        )
        
        # Return as downloadable PDF
        filename = f"recommendations_{snapshot.architecture_name or 'snapshot'}_{snapshot_id[:8]}.pdf"
        
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate recommendations PDF: %s", e)
        raise HTTPException(500, f"Failed to generate PDF: {str(e)}")


# ─── Export Recommendations by Architecture ─────────────────────
@router.get("/recommendations/pdf")
async def export_recommendations_pdf_by_arch(
    architecture_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Export the latest recommendation snapshot for an architecture as PDF.
    """
    try:
        if not architecture_id:
            raise HTTPException(400, "Provide architecture_id")
        
        # Get latest completed snapshot
        snapshot = db.query(RecSnapshot).filter(
            RecSnapshot.architecture_id == architecture_id,
            RecSnapshot.status == "completed"
        ).order_by(RecSnapshot.created_at.desc()).first()
        
        if not snapshot:
            raise HTTPException(404, f"No recommendations found for architecture: {architecture_id}")
        
        # Generate PDF
        pdf_bytes = generate_recommendations_pdf(
            architecture_id=snapshot.architecture_id,
            architecture_name=snapshot.architecture_name or "Unknown Architecture",
            recommendations=snapshot.cards or [],
            total_savings_monthly=snapshot.total_savings_monthly or 0,
            source=snapshot.source or "engine",
            llm_model=snapshot.llm_model,
        )
        
        # Return as downloadable PDF
        filename = f"recommendations_{snapshot.architecture_name or architecture_id}.pdf"
        
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate recommendations PDF: %s", e)
        raise HTTPException(500, f"Failed to generate PDF: {str(e)}")


# ─── Export LLM Report as PDF ──────────────────────────────────
@router.get("/llm-report/pdf/{report_id}")
async def export_llm_report_pdf(
    report_id: str,
    db: Session = Depends(get_db),
):
    """
    Export a 5-agent LLM pipeline report as PDF.
    
    Returns PDF bytes with the full analysis report.
    """
    try:
        report = db.query(LLMReport).filter(LLMReport.id == report_id).first()
        
        if not report:
            raise HTTPException(404, f"Report not found: {report_id}")
        
        # Generate PDF
        pdf_bytes = generate_llm_report_pdf(
            architecture_id=report.architecture_id or "N/A",
            architecture_name=getattr(report, 'architecture_name', 'Unknown Architecture') or "Unknown Architecture",
            report_data=report.payload or {},
            generation_time_ms=report.generation_time_ms,
        )
        
        # Return as downloadable PDF
        arch_name = getattr(report, 'architecture_name', 'report') or 'report'
        filename = f"llm_report_{arch_name}_{report_id[:8]}.pdf"
        
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate LLM report PDF: %s", e)
        raise HTTPException(500, f"Failed to generate PDF: {str(e)}")


# ─── Export Latest LLM Report for Architecture ─────────────────
@router.get("/llm-report/pdf")
async def export_latest_llm_report_pdf(
    architecture_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Export the latest 5-agent LLM pipeline report for an architecture as PDF.
    """
    try:
        if not architecture_id:
            raise HTTPException(400, "Provide architecture_id")
        
        # Get latest report
        report = db.query(LLMReport).filter(
            LLMReport.architecture_id == architecture_id,
            LLMReport.status == "completed"
        ).order_by(LLMReport.created_at.desc()).first()
        
        if not report:
            raise HTTPException(404, f"No reports found for architecture: {architecture_id}")
        
        # Generate PDF
        pdf_bytes = generate_llm_report_pdf(
            architecture_id=report.architecture_id or "N/A",
            architecture_name=getattr(report, 'architecture_name', 'Unknown Architecture') or "Unknown Architecture",
            report_data=report.payload or {},
            generation_time_ms=report.generation_time_ms,
        )
        
        # Return as downloadable PDF
        arch_name = getattr(report, 'architecture_name', 'report') or 'report'
        filename = f"llm_report_{arch_name}.pdf"
        
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate LLM report PDF: %s", e)
        raise HTTPException(500, f"Failed to generate PDF: {str(e)}")


__all__ = ["router"]

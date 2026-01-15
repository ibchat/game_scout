"""
Morning Scan API Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import uuid
from datetime import datetime

from apps.db.session import get_db
from apps.db.models_investor import PipelineRun

router = APIRouter(prefix="/morning-scan", tags=["Morning Scan"])


class MorningScanRequest(BaseModel):
    mode: str = "fast"
    steam_limit: int = 200
    itch_limit: int = 800
    force: bool = False


@router.post("/run")
def run_morning_scan(request: MorningScanRequest, db: Session = Depends(get_db)):
    """Start morning scan pipeline"""
    
    # Check if already running
    if not request.force:
        existing = db.query(PipelineRun).filter(
            PipelineRun.state.in_(['queued', 'running'])
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Pipeline already running: {existing.id}"
            )
    
    # Create run
    run = PipelineRun(
        mode=request.mode,
        state='queued',
        stage='collect_steam',
        params=request.dict(),
        progress_total=8
    )
    
    db.add(run)
    db.commit()
    db.refresh(run)
    
    # Launch task (import locally to avoid circular dependencies)
    try:
        from apps.worker.celery_app import celery_app
        celery_app.send_task(
            'apps.worker.tasks.morning_scan.morning_scan_task',
            args=[str(run.id), request.dict()]
        )
    except Exception as e:
        db.delete(run)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to launch task: {str(e)}")
    
    return {"run_id": str(run.id), "status": "started"}


@router.get("/status")
def get_run_status(run_id: str, db: Session = Depends(get_db)):
    """Get pipeline run status"""
    
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    return {
        "run_id": str(run.id),
        "state": run.state,
        "stage": run.stage,
        "progress": {
            "done": run.progress_done,
            "total": run.progress_total
        },
        "started_at": run.started_at,
        "updated_at": run.updated_at,
        "finished_at": run.finished_at,
        "errors": run.errors or []
    }


@router.get("/history")
def get_run_history(limit: int = Query(10, le=50), db: Session = Depends(get_db)):
    """Get recent pipeline runs"""
    
    runs = db.query(PipelineRun).order_by(
        PipelineRun.started_at.desc()
    ).limit(limit).all()
    
    return [
        {
            "run_id": str(run.id),
            "mode": run.mode,
            "state": run.state,
            "started_at": run.started_at,
            "finished_at": run.finished_at
        }
        for run in runs
    ]

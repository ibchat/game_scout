from fastapi import APIRouter, HTTPException
from typing import Dict

router = APIRouter()

@router.post("/collect/steam")
async def trigger_steam_collection() -> Dict[str, str]:
    """Trigger Steam data collection"""
    try:
        from apps.worker.tasks.collect_steam import collect_steam_task
        task = collect_steam_task.delay()
        return {
            "status": "queued",
            "task_id": str(task.id),
            "message": "Сбор данных из Steam запущен"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/collect/itch")
async def trigger_itch_collection() -> Dict[str, str]:
    """Trigger Itch.io data collection"""
    try:
        from apps.worker.tasks.collect_itch import collect_itch_task
        task = collect_itch_task.delay()
        return {
            "status": "queued",
            "task_id": str(task.id),
            "message": "Сбор данных из Itch.io запущен"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

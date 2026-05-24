"""Task status endpoints (Celery AsyncResult-backed)."""

from fastapi import APIRouter, Depends
from celery.result import AsyncResult

from app.dependencies import get_current_user
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=dict)
async def get_task_status(task_id: str, current_user=Depends(get_current_user)):
    """Return Celery task status and (if ready) its result."""
    result = AsyncResult(task_id, app=celery_app)
    payload: dict = {"task_id": task_id, "status": result.status}
    if result.ready():
        payload["result"] = result.result
    return payload


"""
routes/tasks.py

GET /api/tasks      — task queue
PUT /api/tasks/{id} — approve | defer | dismiss
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from state.farm_state import farm_state
from services.websocket_manager import manager

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskAction(BaseModel):
    action: str   # approve | defer | dismiss


@router.get("/")
def get_tasks():
    return farm_state["tasks"]


@router.put("/{task_id}")
async def update_task(task_id: str, body: TaskAction):
    task = next((t for t in farm_state["tasks"] if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if body.action not in ("approve", "defer", "dismiss"):
        raise HTTPException(status_code=400, detail="action must be approve, defer, or dismiss")

    status_map = {"approve": "in-progress", "defer": "queued", "dismiss": "dismissed"}
    task["status"] = status_map[body.action]

    await manager.broadcast({"type": "TASK_UPDATE", "payload": task})
    return task

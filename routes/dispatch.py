"""
routes/dispatch.py

Every button in the frontend that sends UAV-1 or MPAR-1 somewhere
hits one of these endpoints.

POST /api/dispatch/drone  — queue a UAV-1 mission
POST /api/dispatch/robot  — assign MPAR-1 a task
GET  /api/dispatch/queue  — view both mission queues
"""

import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from state.farm_state import farm_state
from services.websocket_manager import manager

router = APIRouter(prefix="/api/dispatch", tags=["dispatch"])


# ── Request models ──────────────────────────────────────────────

class DroneMission(BaseModel):
    mode: str           # survey | spray | pollination
    zones: List[str]    # e.g. ["B3", "B4"]
    payload: str        # fungicide | foliar-nitrogen | pesticide | lime | multispectral | thermal | vibration
    priority: str = "normal"   # high | normal


class RobotTask(BaseModel):
    head: str                       # harvester | weeder | seeder
    zone: str                       # e.g. "D6" or "C"
    task: str                       # human-readable description
    scheduled_time: Optional[str] = None   # "HH:MM" — omit to queue immediately


# ── POST /api/dispatch/drone ────────────────────────────────────

@router.post("/drone", status_code=201)
async def dispatch_drone(mission: DroneMission):
    # Safety gate: block spray if wind is too high
    if mission.mode == "spray" and farm_state["environment"]["wind_speed_kmh"] > 15:
        raise HTTPException(
            status_code=422,
            detail=f"Wind {farm_state['environment']['wind_speed_kmh']} km/h exceeds 15 km/h spray limit. Mission blocked."
        )

    # Battery gate
    if farm_state["drone"]["battery_pct"] < 20:
        raise HTTPException(
            status_code=422,
            detail=f"UAV-1 battery {farm_state['drone']['battery_pct']}% below 20% minimum. Charge first."
        )

    job = {
        "id":         str(uuid.uuid4()),
        "mode":       mission.mode,
        "zones":      mission.zones,
        "payload":    mission.payload,
        "priority":   mission.priority,
        "status":     "queued",
        "created_at": datetime.utcnow().isoformat(),
    }

    # High priority goes straight after the active mission
    queue = farm_state["drone"]["mission_queue"]
    if mission.priority == "high" and len(queue) > 1:
        queue.insert(1, job)
    else:
        queue.append(job)

    # In production: call MAVLink GCS bridge here
    print(f"[GCS STUB] UAV-1 mission queued: {job}")

    await manager.broadcast({"type": "DRONE_QUEUE_UPDATE", "payload": queue})

    return {"message": "UAV-1 mission queued", "mission": job, "queue_length": len(queue)}


# ── POST /api/dispatch/robot ────────────────────────────────────

@router.post("/robot", status_code=201)
async def dispatch_robot(task: RobotTask):
    job = {
        "id":             str(uuid.uuid4()),
        "head":           task.head,
        "zone":           task.zone,
        "task":           task.task,
        "scheduled_time": task.scheduled_time,
        "status":         "queued",
        "created_at":     datetime.utcnow().isoformat(),
    }

    queue = farm_state["robot"]["head_queue"]

    # If the required head differs from current, insert a swap step first
    if task.head != farm_state["robot"]["current_head"]:
        swap = {
            "id":           str(uuid.uuid4()),
            "head":         None,
            "zone":         None,
            "task":         f"Swap to {task.head} head at dock",
            "status":       "queued",
            "is_head_swap": True,
        }
        queue.append(swap)

    queue.append(job)

    # In production: publish to ROS 2 action server here
    print(f"[ROBOT STUB] MPAR-1 task queued: {job}")

    await manager.broadcast({"type": "ROBOT_QUEUE_UPDATE", "payload": queue})

    return {"message": "MPAR-1 task queued", "job": job, "queue_length": len(queue)}


# ── GET /api/dispatch/queue ─────────────────────────────────────

@router.get("/queue")
def get_queue():
    return {
        "drone": farm_state["drone"]["mission_queue"],
        "robot": farm_state["robot"]["head_queue"],
    }

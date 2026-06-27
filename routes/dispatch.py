"""
routes/dispatch.py — v5

Supports dispatching to any of the 3 drones or 3 robots by ID.

POST /api/dispatch/drone         — queue a mission on any drone (body includes drone_id)
POST /api/dispatch/robot         — assign a task to any robot (body includes robot_id)
GET  /api/dispatch/queue         — view all fleet queues
POST /api/dispatch/fleet/recall  — emergency recall all flying drones
"""

import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from state.farm_state import farm_state
from services.websocket_manager import manager

router = APIRouter(prefix="/api/dispatch", tags=["dispatch"])


# ── Models ──────────────────────────────────────────────────────

class DroneMission(BaseModel):
    drone_id: str = "UAV-1"         # UAV-1 | UAV-2 | UAV-3
    mode: str                        # survey | spray | pollination | seed-drop
    zones: List[str]
    payload: str
    priority: str = "normal"        # high | normal


class RobotTask(BaseModel):
    robot_id: str = "MPAR-1"        # MPAR-1 | MPAR-2 | MPAR-3
    head: str                        # harvester | weeder | seeder | drip-irrigator | fertigation | soil-probe
    zone: str
    task: str
    scheduled_time: Optional[str] = None


# ── POST /api/dispatch/drone ────────────────────────────────────

@router.post("/drone", status_code=201)
async def dispatch_drone(mission: DroneMission):
    drone = farm_state["drones"].get(mission.drone_id)
    if not drone:
        raise HTTPException(status_code=404, detail=f"Drone {mission.drone_id} not found")

    # Safety: block spray if wind too high
    if mission.mode == "spray" and farm_state["environment"]["wind_speed_kmh"] > 15:
        raise HTTPException(
            status_code=422,
            detail=f"Wind {farm_state['environment']['wind_speed_kmh']} km/h exceeds 15 km/h spray limit."
        )

    # Battery gate
    if drone["battery_pct"] < 20:
        raise HTTPException(
            status_code=422,
            detail=f"{mission.drone_id} battery {drone['battery_pct']}% below 20% minimum."
        )

    # Capability check
    if mission.mode not in drone["capabilities"]:
        raise HTTPException(
            status_code=422,
            detail=f"{mission.drone_id} does not support mode '{mission.mode}'. Capabilities: {drone['capabilities']}"
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

    queue = drone["mission_queue"]
    if mission.priority == "high" and len(queue) > 1:
        queue.insert(1, job)
    else:
        queue.append(job)

    print(f"[GCS] {mission.drone_id} mission queued: {job}")
    await manager.broadcast({
        "type": "DRONE_QUEUE_UPDATE",
        "payload": {"drone_id": mission.drone_id, "queue": queue}
    })

    return {"message": f"{mission.drone_id} mission queued", "mission": job, "queue_length": len(queue)}


# ── POST /api/dispatch/robot ────────────────────────────────────

@router.post("/robot", status_code=201)
async def dispatch_robot(task: RobotTask):
    robot = farm_state["robots"].get(task.robot_id)
    if not robot:
        raise HTTPException(status_code=404, detail=f"Robot {task.robot_id} not found")

    if task.head not in robot["capabilities"]:
        raise HTTPException(
            status_code=422,
            detail=f"{task.robot_id} does not support head '{task.head}'. Capabilities: {robot['capabilities']}"
        )

    # Auto-insert head-swap if needed
    queue = robot["head_queue"]
    if task.head != robot["current_head"]:
        swap = {
            "id":           str(uuid.uuid4()),
            "head":         None,
            "zone":         None,
            "task":         f"Swap to {task.head} head at dock",
            "status":       "queued",
            "is_head_swap": True,
        }
        queue.append(swap)

    job = {
        "id":             str(uuid.uuid4()),
        "head":           task.head,
        "zone":           task.zone,
        "task":           task.task,
        "scheduled_time": task.scheduled_time,
        "status":         "queued",
        "created_at":     datetime.utcnow().isoformat(),
    }
    queue.append(job)

    print(f"[ROBOT] {task.robot_id} task queued: {job}")
    await manager.broadcast({
        "type": "ROBOT_QUEUE_UPDATE",
        "payload": {"robot_id": task.robot_id, "queue": queue}
    })

    return {"message": f"{task.robot_id} task queued", "job": job, "queue_length": len(queue)}


# ── GET /api/dispatch/queue ─────────────────────────────────────

@router.get("/queue")
def get_queue():
    return {
        "drones": {
            did: {"status": d["status"], "battery_pct": d["battery_pct"], "queue": d["mission_queue"]}
            for did, d in farm_state["drones"].items()
        },
        "robots": {
            rid: {"status": r["status"], "battery_pct": r["battery_pct"], "queue": r["head_queue"]}
            for rid, r in farm_state["robots"].items()
        },
    }


# ── POST /api/dispatch/fleet/recall ────────────────────────────

@router.post("/fleet/recall")
async def fleet_recall():
    recalled = []
    for drone_id, drone in farm_state["drones"].items():
        if drone["status"] in ("flying", "spraying"):
            drone["status"] = "returning"
            drone["current_task"] = "Emergency recall — returning to dock"
            recalled.append(drone_id)

    await manager.broadcast({"type": "FLEET_RECALLED", "payload": {"drones": recalled}})
    return {"message": f"Recalled {len(recalled)} drone(s)", "drones": recalled}

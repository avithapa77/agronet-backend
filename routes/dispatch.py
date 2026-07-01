"""
routes/dispatch.py — v6

Fixed: all farm_state lookups now use farm_state["outdoor"]["drones"]
and farm_state["outdoor"]["robots"] to match the v6 nested state structure.

POST /api/dispatch/drone         — queue a mission on any of the 3 drones
POST /api/dispatch/robot         — assign a task to any of the 3 robots
GET  /api/dispatch/queue         — full fleet queue snapshot
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
    drone_id: str = "UAV-1"   # UAV-1 | UAV-2 | UAV-3
    mode: str                  # survey | spray | pollination | seed-drop
    zones: List[str]
    payload: str
    priority: str = "normal"  # high | normal


class RobotTask(BaseModel):
    robot_id: str = "MPAR-1"  # MPAR-1 | MPAR-2 | MPAR-3
    head: str                  # harvester | weeder | seeder | drip-irrigator | fertigation | soil-probe
    zone: str
    task: str
    scheduled_time: Optional[str] = None


# ── POST /api/dispatch/drone ────────────────────────────────────

@router.post("/drone", status_code=201)
async def dispatch_drone(mission: DroneMission):
    drones = farm_state["outdoor"]["drones"]
    drone = drones.get(mission.drone_id)
    if not drone:
        raise HTTPException(404, f"Drone {mission.drone_id} not found. Valid: {list(drones)}")

    # Wind safety gate for spraying
    if mission.mode == "spray":
        wind = farm_state["outdoor"]["environment"]["wind_speed_kmh"]
        if wind > 15:
            raise HTTPException(422, f"Wind {wind} km/h exceeds 15 km/h spray limit. Unsafe to spray.")

    # Battery gate
    if drone["battery_pct"] < 20:
        # Try to auto-suggest a fallback
        fallback = next(
            (did for did, d in drones.items()
             if did != mission.drone_id and d["battery_pct"] >= 30
             and mission.mode in d.get("capabilities", [])),
            None
        )
        hint = f" Consider {fallback} ({drones[fallback]['battery_pct']:.0f}% battery)." if fallback else ""
        raise HTTPException(422, f"{mission.drone_id} battery {drone['battery_pct']:.0f}% < 20% minimum.{hint}")

    # Capability gate
    if mission.mode not in drone.get("capabilities", []):
        raise HTTPException(422,
            f"{mission.drone_id} does not support '{mission.mode}'. "
            f"Capabilities: {drone['capabilities']}")

    job = {
        "id":         str(uuid.uuid4())[:8],
        "mode":       mission.mode,
        "zones":      mission.zones,
        "payload":    mission.payload,
        "priority":   mission.priority,
        "status":     "queued",
        "auto":       False,
        "created_at": datetime.utcnow().isoformat(),
    }

    queue = drone["mission_queue"]
    if mission.priority == "high" and len(queue) > 1:
        queue.insert(1, job)   # jump to front, behind any active mission
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
    robots = farm_state["outdoor"]["robots"]
    robot = robots.get(task.robot_id)
    if not robot:
        raise HTTPException(404, f"Robot {task.robot_id} not found. Valid: {list(robots)}")

    if task.head not in robot.get("capabilities", []):
        raise HTTPException(422,
            f"{task.robot_id} does not support head '{task.head}'. "
            f"Capabilities: {robot['capabilities']}")

    queue = robot["head_queue"]

    # Auto-insert a head-swap step if the robot currently has a different head
    if task.head != robot.get("current_head"):
        queue.append({
            "id":           str(uuid.uuid4())[:8],
            "head":         None,
            "zone":         None,
            "task":         f"Swap to {task.head} head at dock",
            "status":       "queued",
            "is_head_swap": True,
        })

    job = {
        "id":             str(uuid.uuid4())[:8],
        "head":           task.head,
        "zone":           task.zone,
        "task":           task.task,
        "scheduled_time": task.scheduled_time,
        "status":         "queued",
        "auto":           False,
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
    drones = farm_state["outdoor"]["drones"]
    robots = farm_state["outdoor"]["robots"]
    return {
        "drones": {
            did: {
                "status":      d["status"],
                "battery_pct": d["battery_pct"],
                "current_task": d["current_task"],
                "queue":       d["mission_queue"],
            }
            for did, d in drones.items()
        },
        "robots": {
            rid: {
                "status":       r["status"],
                "battery_pct":  r["battery_pct"],
                "current_head": r["current_head"],
                "current_task": r["current_task"],
                "queue":        r["head_queue"],
            }
            for rid, r in robots.items()
        },
    }


# ── POST /api/dispatch/fleet/recall ────────────────────────────

@router.post("/fleet/recall")
async def fleet_recall():
    recalled = []
    for drone_id, drone in farm_state["outdoor"]["drones"].items():
        if drone["status"] in ("flying", "spraying"):
            drone["status"] = "returning"
            drone["current_task"] = "Emergency recall — returning to dock"
            recalled.append(drone_id)

    await manager.broadcast({"type": "FLEET_RECALLED", "payload": {"drones": recalled}})
    return {"message": f"Recalled {len(recalled)} drone(s)", "drones": recalled}

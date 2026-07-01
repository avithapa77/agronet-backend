"""
routes/indoor.py

Full REST control of the indoor environment.

GET  /api/indoor                         — all rooms + actuators + robots
GET  /api/indoor/rooms                   — all room summaries
GET  /api/indoor/rooms/{room_id}         — single room detail
PUT  /api/indoor/rooms/{room_id}/targets — update climate targets
PUT  /api/indoor/actuators/{room_id}/{actuator} — directly control an actuator
POST /api/indoor/robots/{robot_id}/command — send command to indoor robot
GET  /api/indoor/alerts                  — all indoor alerts
POST /api/indoor/rooms/{room_id}/override — manual climate override
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any

from state.farm_state import farm_state
from services.websocket_manager import manager

router = APIRouter(prefix="/api/indoor", tags=["indoor"])


class TargetUpdate(BaseModel):
    temp_day_c:         Optional[float] = None
    temp_night_c:       Optional[float] = None
    humidity_pct:       Optional[float] = None
    co2_ppm:            Optional[int]   = None
    vpd_kpa:            Optional[float] = None
    light_hours:        Optional[int]   = None
    light_intensity_umol: Optional[int] = None
    ph_target:          Optional[float] = None
    ec_target_ms:       Optional[float] = None


class ActuatorCommand(BaseModel):
    command: dict   # free-form dict, e.g. {"status": "on", "setpoint_c": 24}


class RobotCommand(BaseModel):
    command: str    # "harvest" | "ph_adjust" | "ec_adjust" | "seedling_cycle"
    room: Optional[str] = None


class Override(BaseModel):
    duration_min: int = 30
    settings: dict    # e.g. {"hvac": {"mode": "cool", "setpoint_c": 22}}


@router.get("/")
def get_all_indoor():
    return {
        "rooms":         farm_state["indoor"]["rooms"],
        "actuators":     farm_state["indoor"]["actuators"],
        "indoor_robots": farm_state["indoor"]["indoor_robots"],
    }


@router.get("/rooms")
def get_rooms():
    rooms = farm_state["indoor"]["rooms"]
    return [
        {
            "id":       rid,
            "name":     r["name"],
            "type":     r["type"],
            "crop":     r["crop"],
            "stage":    r["stage"],
            "status":   r["status"],
            "readings": r["readings"],
            "targets":  r["targets"],
            "alerts":   r["alerts"],
        }
        for rid, r in rooms.items()
    ]


@router.get("/rooms/{room_id}")
def get_room(room_id: str):
    room = farm_state["indoor"]["rooms"].get(room_id.upper())
    if not room:
        raise HTTPException(status_code=404, detail=f"Room {room_id} not found")
    return {
        "room":      room,
        "actuators": farm_state["indoor"]["actuators"].get(room_id.upper(), {}),
    }


@router.put("/rooms/{room_id}/targets")
async def update_targets(room_id: str, body: TargetUpdate):
    room = farm_state["indoor"]["rooms"].get(room_id.upper())
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    updates = body.dict(exclude_none=True)
    room["targets"].update(updates)

    await manager.broadcast({
        "type": "INDOOR_TARGETS_UPDATED",
        "payload": {"room": room_id.upper(), "targets": room["targets"]}
    })
    return {"message": f"Targets updated for {room_id}", "targets": room["targets"]}


@router.put("/actuators/{room_id}/{actuator}")
async def control_actuator(room_id: str, actuator: str, body: ActuatorCommand):
    room_acts = farm_state["indoor"]["actuators"].get(room_id.upper())
    if not room_acts:
        raise HTTPException(status_code=404, detail=f"Room {room_id} not found")
    if actuator not in room_acts:
        raise HTTPException(status_code=404, detail=f"Actuator {actuator} not found in {room_id}")

    room_acts[actuator].update(body.command)

    await manager.broadcast({
        "type": "INDOOR_ACTUATOR",
        "payload": {"room": room_id.upper(), "actuator": actuator, "state": room_acts[actuator]}
    })
    return {"message": f"{room_id} {actuator} updated", "state": room_acts[actuator]}


@router.post("/robots/{robot_id}/command")
async def robot_command(robot_id: str, body: RobotCommand):
    robot = farm_state["indoor"]["indoor_robots"].get(robot_id.upper())
    if not robot:
        raise HTTPException(status_code=404, detail=f"Robot {robot_id} not found")

    robot["status"] = "active"
    robot["current_task"] = f"Manual: {body.command}" + (f" in {body.room}" if body.room else "")

    await manager.broadcast({
        "type": "INDOOR_ROBOT",
        "payload": {"robot_id": robot_id.upper(), "command": body.command, "room": body.room}
    })
    return {"message": f"{robot_id} executing {body.command}", "robot": robot}


@router.get("/alerts")
def get_indoor_alerts():
    alerts = []
    for rid, room in farm_state["indoor"]["rooms"].items():
        for a in room.get("alerts", []):
            alerts.append({"room": rid, **a})
    return {"alerts": alerts, "count": len(alerts)}


@router.post("/rooms/{room_id}/override")
async def manual_override(room_id: str, body: Override):
    """
    Apply a temporary manual override to a room's actuators.
    Useful for pest treatments, emergency cooling, etc.
    """
    room_id_upper = room_id.upper()
    acts = farm_state["indoor"]["actuators"].get(room_id_upper)
    if not acts:
        raise HTTPException(status_code=404, detail="Room not found")

    for actuator, cmd in body.settings.items():
        if actuator in acts:
            acts[actuator].update(cmd)

    await manager.broadcast({
        "type": "INDOOR_OVERRIDE",
        "payload": {"room": room_id_upper, "duration_min": body.duration_min, "settings": body.settings}
    })
    return {
        "message": f"Override applied to {room_id_upper} for {body.duration_min} min",
        "applied": body.settings,
    }

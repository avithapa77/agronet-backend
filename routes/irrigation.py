"""
routes/irrigation.py

GET  /api/irrigation              — schedules + rules
POST /api/irrigation/run          — run a zone immediately
PUT  /api/irrigation/schedule     — update days/time for a zone
POST /api/irrigation/rules        — add automation rule
PUT  /api/irrigation/rules/{id}   — toggle rule on/off
"""

import uuid
from typing import List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from state.farm_state import farm_state
from services.websocket_manager import manager

router = APIRouter(prefix="/api/irrigation", tags=["irrigation"])


class RunRequest(BaseModel):
    zone: str


class ScheduleUpdate(BaseModel):
    zone: str
    days: List[str]
    time: str


class NewRule(BaseModel):
    description: str


class RuleToggle(BaseModel):
    enabled: bool


@router.get("/")
def get_irrigation():
    return farm_state["irrigation"]


@router.post("/run")
async def run_now(body: RunRequest):
    from datetime import date
    schedule = next((s for s in farm_state["irrigation"]["schedules"] if s["zone"] == body.zone[0].upper()), None)
    if schedule:
        schedule["last_run"] = date.today().isoformat()

    # In production: send command to irrigation controller via MQTT
    print(f"[IRRIGATION] Running drip now for zone {body.zone}")

    await manager.broadcast({"type": "IRRIGATION_RUN", "payload": {"zone": body.zone}})
    return {"message": f"Irrigation started for zone {body.zone}"}


@router.put("/schedule")
async def update_schedule(body: ScheduleUpdate):
    schedule = next((s for s in farm_state["irrigation"]["schedules"] if s["zone"] == body.zone), None)
    if not schedule:
        raise HTTPException(status_code=404, detail="Zone schedule not found")

    schedule["days"]   = body.days
    schedule["time"]   = body.time
    schedule["status"] = "scheduled"
    schedule.pop("suggestion", None)

    await manager.broadcast({"type": "SCHEDULE_UPDATE", "payload": schedule})
    return {"message": f"Schedule updated for zone {body.zone}", "schedule": schedule}


@router.post("/rules", status_code=201)
async def add_rule(body: NewRule):
    rule = {"id": str(uuid.uuid4()), "description": body.description, "enabled": True}
    farm_state["irrigation"]["rules"].append(rule)
    await manager.broadcast({"type": "RULE_ADDED", "payload": rule})
    return rule


@router.put("/rules/{rule_id}")
async def toggle_rule(rule_id: str, body: RuleToggle):
    rule = next((r for r in farm_state["irrigation"]["rules"] if r["id"] == rule_id), None)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule["enabled"] = body.enabled
    await manager.broadcast({"type": "RULE_UPDATED", "payload": rule})
    return rule

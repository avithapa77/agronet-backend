"""
routes/automation.py

GET  /api/automation              — all rules + action log + engine status
POST /api/automation/rules        — create a new rule
PUT  /api/automation/rules/{id}   — update/enable/disable a rule
DELETE /api/automation/rules/{id} — delete a rule
POST /api/automation/fire/{id}    — manually fire a rule right now (test mode)
PUT  /api/automation/toggle       — enable/disable the entire engine
GET  /api/automation/log          — recent action log
"""

import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from state.farm_state import farm_state
from services.websocket_manager import manager

router = APIRouter(prefix="/api/automation", tags=["automation"])


# ── Models ──────────────────────────────────────────────────────

class RuleTrigger(BaseModel):
    type: str            # sensor | weather | fleet | schedule | compound
    sensor: Optional[str] = None
    condition: Optional[str] = None
    operator: Optional[str] = None
    threshold: Optional[float] = None
    cron: Optional[str] = None
    conditions: Optional[List[dict]] = None


class RuleAction(BaseModel):
    type: str            # dispatch_drone | dispatch_robot | cancel_spray_missions | return_to_dock
    drone: Optional[str] = None
    robot: Optional[str] = None
    mode: Optional[str] = None
    head: Optional[str] = None
    payload: Optional[str] = None


class NewRule(BaseModel):
    name: str
    description: str
    trigger: RuleTrigger
    action: RuleAction
    enabled: bool = True


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None


class EngineToggle(BaseModel):
    enabled: bool


# ── GET /api/automation ─────────────────────────────────────────

@router.get("/")
def get_automation():
    return farm_state["automation"]


# ── GET /api/automation/log ─────────────────────────────────────

@router.get("/log")
def get_log():
    return {"log": farm_state["automation"]["action_log"]}


# ── PUT /api/automation/toggle ──────────────────────────────────

@router.put("/toggle")
async def toggle_engine(body: EngineToggle):
    farm_state["automation"]["enabled"] = body.enabled
    status = "enabled" if body.enabled else "disabled"
    await manager.broadcast({"type": "AUTOMATION_ENGINE_TOGGLE", "payload": {"enabled": body.enabled}})
    return {"message": f"Automation engine {status}", "enabled": body.enabled}


# ── POST /api/automation/rules ──────────────────────────────────

@router.post("/rules", status_code=201)
async def create_rule(body: NewRule):
    rule = {
        "id":          f"auto-{uuid.uuid4().hex[:6]}",
        "name":        body.name,
        "description": body.description,
        "trigger":     body.trigger.dict(exclude_none=True),
        "action":      body.action.dict(exclude_none=True),
        "enabled":     body.enabled,
        "last_fired":  None,
    }
    farm_state["automation"]["rules"].append(rule)
    await manager.broadcast({"type": "AUTOMATION_RULE_ADDED", "payload": rule})
    return rule


# ── PUT /api/automation/rules/{id} ─────────────────────────────

@router.put("/rules/{rule_id}")
async def update_rule(rule_id: str, body: RuleUpdate):
    rule = next((r for r in farm_state["automation"]["rules"] if r["id"] == rule_id), None)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    if body.name        is not None: rule["name"]        = body.name
    if body.description is not None: rule["description"] = body.description
    if body.enabled     is not None: rule["enabled"]     = body.enabled

    await manager.broadcast({"type": "AUTOMATION_RULE_UPDATED", "payload": rule})
    return rule


# ── DELETE /api/automation/rules/{id} ──────────────────────────

@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str):
    rules = farm_state["automation"]["rules"]
    idx   = next((i for i, r in enumerate(rules) if r["id"] == rule_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    deleted = rules.pop(idx)
    await manager.broadcast({"type": "AUTOMATION_RULE_DELETED", "payload": {"id": rule_id}})
    return {"message": "Rule deleted", "rule": deleted}


# ── POST /api/automation/fire/{id} ─────────────────────────────

@router.post("/fire/{rule_id}")
async def fire_rule(rule_id: str):
    """Manually trigger a rule (test / override mode)."""
    rule = next((r for r in farm_state["automation"]["rules"] if r["id"] == rule_id), None)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    # Log it
    log_entry = {
        "time":    datetime.utcnow().strftime("%H:%M"),
        "rule":    rule["id"],
        "name":    rule["name"],
        "message": f"[Manual trigger] {rule['description']}",
        "status":  "manual",
    }
    farm_state["automation"]["action_log"].append(log_entry)
    rule["last_fired"] = datetime.utcnow().isoformat()

    await manager.broadcast({"type": "AUTOMATION_FIRED", "payload": log_entry})
    return {"message": f"Rule '{rule['name']}' fired manually", "log": log_entry}

"""
routes/automation.py — v6

CRUD for automation rules + engine controls.
Fixed:
  - fire_rule() now actually executes the rule's action via the engine
  - NewRule model supports all trigger types (indoor_sensor, indoor_multi,
    compound, etc.) and all action types (indoor_actuator, vpd_correction, etc.)
  - RuleUpdate allows updating trigger/action too
  - GET / returns engine status including outdoor/indoor loop info

GET    /api/automation/           — all rules + log + engine status
GET    /api/automation/log        — recent action log (last 100)
GET    /api/automation/rules      — just the rules list
POST   /api/automation/rules      — create a new rule
PUT    /api/automation/rules/{id} — update a rule (name/desc/enabled/trigger/action)
DELETE /api/automation/rules/{id} — delete a rule
POST   /api/automation/fire/{id}  — manually fire a rule RIGHT NOW (actually executes it)
PUT    /api/automation/toggle     — enable/disable entire engine
PUT    /api/automation/mode       — switch mode: outdoor | indoor | both
GET    /api/automation/stats      — counts, fired today, cooldown status
"""

import uuid
from datetime import datetime
from typing import Optional, List, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from state.farm_state import farm_state
from services.websocket_manager import manager

router = APIRouter(prefix="/api/automation", tags=["automation"])


# ── Models ──────────────────────────────────────────────────────

class RuleTrigger(BaseModel):
    type: str                          # sensor|weather|fleet|schedule|compound|indoor_sensor|indoor_multi
    # Sensor / weather / fleet triggers
    sensor: Optional[str]    = None   # e.g. "outdoor.sensors.soil_moisture"
    condition: Optional[str] = None   # e.g. "rain_forecast_mm"
    operator: Optional[str]  = None   # < | > | <= | >= | == | outside_range
    threshold: Optional[float] = None
    # Schedule triggers
    cron: Optional[str] = None        # e.g. "0 7 * * *"
    # Compound triggers (outdoor)
    conditions: Optional[List[dict]] = None
    # Indoor triggers
    room: Optional[str]      = None   # e.g. "GH-1"
    reading: Optional[str]   = None   # e.g. "temp_c"
    tolerance: Optional[float] = None # for indoor_multi drift checks
    min: Optional[float]     = None   # for outside_range
    max: Optional[float]     = None


class RuleAction(BaseModel):
    type: str                          # dispatch_drone|dispatch_robot|cancel_spray_missions|
                                       # return_to_dock|indoor_actuator|indoor_actuator_multi|
                                       # indoor_robot|night_mode|lights_on|vpd_correction
    # Outdoor drone actions
    drone: Optional[str]   = None     # UAV-1 | UAV-2 | UAV-3
    mode: Optional[str]    = None     # survey | spray | pollination
    payload: Optional[str] = None     # e.g. "fungicide"
    # Outdoor robot actions
    robot: Optional[str]   = None     # MPAR-1 | MPAR-2 | MPAR-3 | RAIL-1 | DOSER-1
    head: Optional[str]    = None     # harvester | weeder | drip-irrigator | ...
    command: Optional[str] = None     # for indoor robots
    # Indoor actuator actions
    room: Optional[str]    = None     # GH-1 | GH-2 | VF-1 | SEED-1
    actuator: Optional[str] = None    # hvac | co2_injector | led_rig | ...
    actuator_command: Optional[dict] = None  # e.g. {"mode": "cool", "setpoint_c": 24}


class SecondaryAction(BaseModel):
    type: str
    room: Optional[str]    = None
    actuator: Optional[str] = None
    actuator_command: Optional[dict] = None


class NewRule(BaseModel):
    name: str
    description: str
    env: str = "outdoor"               # outdoor | indoor
    trigger: RuleTrigger
    action: RuleAction
    also: Optional[SecondaryAction] = None   # fire a second actuator simultaneously
    enabled: bool = True


class RuleUpdate(BaseModel):
    name: Optional[str]        = None
    description: Optional[str] = None
    enabled: Optional[bool]    = None
    trigger: Optional[dict]    = None  # replace trigger wholesale
    action: Optional[dict]     = None  # replace action wholesale


class EngineToggle(BaseModel):
    enabled: bool


class ModeUpdate(BaseModel):
    mode: str   # outdoor | indoor | both


# ── GET /api/automation/ ────────────────────────────────────────

@router.get("/")
def get_automation():
    auto = farm_state["automation"]
    return {
        "enabled":      auto["enabled"],
        "mode":         auto["mode"],
        "total_rules":  len(auto["rules"]),
        "active_rules": len([r for r in auto["rules"] if r["enabled"]]),
        "outdoor_rules": len([r for r in auto["rules"] if r.get("env") == "outdoor"]),
        "indoor_rules":  len([r for r in auto["rules"] if r.get("env") == "indoor"]),
        "rules":         auto["rules"],
        "action_log":    auto["action_log"][-50:],
    }


# ── GET /api/automation/log ─────────────────────────────────────

@router.get("/log")
def get_log():
    return {"log": farm_state["automation"]["action_log"]}


# ── GET /api/automation/rules ───────────────────────────────────

@router.get("/rules")
def get_rules():
    return farm_state["automation"]["rules"]


# ── GET /api/automation/stats ───────────────────────────────────

@router.get("/stats")
def get_stats():
    from services.autonomous_engine import _cooldowns, COOLDOWN_MINUTES
    auto = farm_state["automation"]
    now  = datetime.utcnow()
    on_cd = {rid: str(ts) for rid, ts in _cooldowns.items()
             if (now - ts).seconds < COOLDOWN_MINUTES * 60}
    return {
        "enabled":         auto["enabled"],
        "mode":            auto["mode"],
        "total_rules":     len(auto["rules"]),
        "enabled_rules":   len([r for r in auto["rules"] if r["enabled"]]),
        "outdoor_rules":   len([r for r in auto["rules"] if r.get("env") == "outdoor"]),
        "indoor_rules":    len([r for r in auto["rules"] if r.get("env") == "indoor"]),
        "log_entries":     len(auto["action_log"]),
        "rules_on_cooldown": on_cd,
        "cooldown_minutes":  COOLDOWN_MINUTES,
    }


# ── PUT /api/automation/toggle ──────────────────────────────────

@router.put("/toggle")
async def toggle_engine(body: EngineToggle):
    farm_state["automation"]["enabled"] = body.enabled
    status = "enabled" if body.enabled else "disabled"
    await manager.broadcast({"type": "AUTOMATION_ENGINE_TOGGLE", "payload": {"enabled": body.enabled}})
    return {"message": f"Automation engine {status}", "enabled": body.enabled}


# ── PUT /api/automation/mode ────────────────────────────────────

@router.put("/mode")
async def set_mode(body: ModeUpdate):
    if body.mode not in ("outdoor", "indoor", "both"):
        raise HTTPException(422, "mode must be 'outdoor', 'indoor', or 'both'")
    farm_state["automation"]["mode"] = body.mode
    farm_state["config"]["mode"] = body.mode
    await manager.broadcast({"type": "AUTOMATION_MODE_CHANGED", "payload": {"mode": body.mode}})
    return {"message": f"Automation mode set to '{body.mode}'", "mode": body.mode}


# ── POST /api/automation/rules ──────────────────────────────────

@router.post("/rules", status_code=201)
async def create_rule(body: NewRule):
    # Build action dict, mapping actuator_command → command for indoor actuator actions
    action_dict = body.action.dict(exclude_none=True)
    if "actuator_command" in action_dict:
        action_dict["command"] = action_dict.pop("actuator_command")

    also_dict = None
    if body.also:
        also_dict = body.also.dict(exclude_none=True)
        if "actuator_command" in also_dict:
            also_dict["command"] = also_dict.pop("actuator_command")

    rule = {
        "id":          f"rule-{uuid.uuid4().hex[:6]}",
        "env":         body.env,
        "name":        body.name,
        "description": body.description,
        "trigger":     body.trigger.dict(exclude_none=True),
        "action":      action_dict,
        "enabled":     body.enabled,
        "last_fired":  None,
        "created_at":  datetime.utcnow().isoformat(),
    }
    if also_dict:
        rule["also"] = also_dict

    farm_state["automation"]["rules"].append(rule)
    await manager.broadcast({"type": "AUTOMATION_RULE_ADDED", "payload": rule})
    return rule


# ── PUT /api/automation/rules/{id} ─────────────────────────────

@router.put("/rules/{rule_id}")
async def update_rule(rule_id: str, body: RuleUpdate):
    rule = next((r for r in farm_state["automation"]["rules"] if r["id"] == rule_id), None)
    if not rule:
        raise HTTPException(404, "Rule not found")

    if body.name        is not None: rule["name"]        = body.name
    if body.description is not None: rule["description"] = body.description
    if body.enabled     is not None: rule["enabled"]     = body.enabled
    if body.trigger     is not None: rule["trigger"]     = body.trigger
    if body.action      is not None: rule["action"]      = body.action

    await manager.broadcast({"type": "AUTOMATION_RULE_UPDATED", "payload": rule})
    return rule


# ── DELETE /api/automation/rules/{id} ──────────────────────────

@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str):
    rules = farm_state["automation"]["rules"]
    idx   = next((i for i, r in enumerate(rules) if r["id"] == rule_id), None)
    if idx is None:
        raise HTTPException(404, "Rule not found")
    deleted = rules.pop(idx)
    await manager.broadcast({"type": "AUTOMATION_RULE_DELETED", "payload": {"id": rule_id}})
    return {"message": "Rule deleted", "rule": deleted}


# ── POST /api/automation/fire/{id} ─────────────────────────────

@router.post("/fire/{rule_id}")
async def fire_rule(rule_id: str):
    """
    Manually fire a rule RIGHT NOW — bypasses cooldown and actually
    executes the action (dispatches drone/robot, adjusts actuator, etc.)
    This is the test/override button in the UI.
    """
    rule = next((r for r in farm_state["automation"]["rules"] if r["id"] == rule_id), None)
    if not rule:
        raise HTTPException(404, "Rule not found")

    # Import the engine's action maps and execute for real
    from services.autonomous_engine import OUTDOOR_ACTIONS, INDOOR_ACTIONS, _log_and_broadcast

    action   = rule["action"]
    act_type = action.get("type")
    executor = OUTDOOR_ACTIONS.get(act_type) or INDOOR_ACTIONS.get(act_type)

    if executor:
        result = await executor(action, "manual-trigger")

        # Fire secondary "also" action if present
        if "also" in rule:
            also_exec = INDOOR_ACTIONS.get(rule["also"].get("type"))
            if also_exec:
                await also_exec(rule["also"], "manual-trigger")
    else:
        result = f"[Manual] {rule['description']} (no executor for '{act_type}')"

    # Override cooldown for manual fires — log without setting cooldown
    entry = {
        "time":    datetime.utcnow().strftime("%H:%M"),
        "rule":    rule["id"],
        "env":     rule.get("env", "?"),
        "name":    rule["name"],
        "message": result,
        "status":  "manual",
    }
    farm_state["automation"]["action_log"].append(entry)
    farm_state["automation"]["action_log"] = farm_state["automation"]["action_log"][-100:]
    rule["last_fired"] = datetime.utcnow().isoformat()

    await manager.broadcast({"type": "AUTOMATION_FIRED", "payload": entry})
    return {"message": f"Rule '{rule['name']}' fired manually", "result": result, "log": entry}

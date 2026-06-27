"""
services/automation_engine.py

The automation engine runs every 60 seconds and evaluates every enabled rule
against live sensor + weather data. When a rule fires it:
  1. Dispatches drones or robots
  2. Logs the action to farm_state["automation"]["action_log"]
  3. Broadcasts a WS message so the dashboard updates instantly
  4. Calls Claude to generate a human-readable explanation (optional)

RULE TYPES
----------
sensor     — compare a sensor reading to a threshold for a specific zone
weather    — compare an environment field to a threshold
fleet      — check any/all drone batteries
schedule   — cron-style (evaluated by checking current time window)
compound   — all sub-conditions must pass
"""

import asyncio
import uuid
from datetime import datetime, time as dtime

from state.farm_state import farm_state
from services.websocket_manager import manager


# ── helpers ──────────────────────────────────────────────────────

def _compare(value, operator, threshold):
    if operator == "<":  return value < threshold
    if operator == ">":  return value > threshold
    if operator == "<=": return value <= threshold
    if operator == ">=": return value >= threshold
    if operator == "==": return value == threshold
    return False


def _eval_sensor(trigger: dict) -> tuple[bool, str]:
    """Returns (fired, zone_or_context)."""
    sensor_map = farm_state["sensors"]
    sensor_key = trigger["sensor"]
    readings = sensor_map.get(sensor_key, {})
    fired_zones = []
    for zone, value in readings.items():
        if _compare(value, trigger["operator"], trigger["threshold"]):
            fired_zones.append(zone)
    if fired_zones:
        return True, ",".join(fired_zones)
    return False, ""


def _eval_weather(trigger: dict) -> tuple[bool, str]:
    env = farm_state["environment"]
    value = env.get(trigger["condition"], 0)
    fired = _compare(value, trigger["operator"], trigger["threshold"])
    return fired, f"{trigger['condition']}={value}"


def _eval_fleet(trigger: dict) -> tuple[bool, str]:
    drones = farm_state["drones"]
    if trigger["condition"] == "any_drone_battery":
        for drone_id, d in drones.items():
            if _compare(d["battery_pct"], trigger["operator"], trigger["threshold"]):
                return True, f"{drone_id} battery={d['battery_pct']}"
    return False, ""


def _eval_schedule(trigger: dict) -> tuple[bool, str]:
    """Very simplified — checks if 'now' matches the cron hour+minute."""
    cron = trigger.get("cron", "")  # e.g. "0 7 * * *"
    parts = cron.split()
    if len(parts) < 2:
        return False, ""
    try:
        minute, hour = int(parts[0]), int(parts[1])
        now = datetime.utcnow()
        # Fire if we're in the correct minute window
        if now.hour == hour and now.minute == minute:
            return True, f"schedule hit {hour:02d}:{minute:02d}"
    except (ValueError, IndexError):
        pass
    return False, ""


def _eval_compound(trigger: dict) -> tuple[bool, str]:
    env = farm_state["environment"]
    for cond in trigger.get("conditions", []):
        key = cond["sensor"]
        value = env.get(key, 0)
        if cond["operator"] == "between":
            if not (cond["min"] <= value <= cond["max"]):
                return False, ""
        else:
            if not _compare(value, cond["operator"], cond["threshold"]):
                return False, ""
    return True, "all conditions met"


# ── action executors ─────────────────────────────────────────────

async def _execute_dispatch_drone(action: dict, zone_ctx: str):
    drone_id = action.get("drone", "UAV-1")
    drone = farm_state["drones"].get(drone_id)
    if not drone or drone["battery_pct"] < 20:
        return f"{drone_id} unavailable (low battery)"

    mission = {
        "id":     str(uuid.uuid4()),
        "mode":   action["mode"],
        "zones":  zone_ctx.split(",") if zone_ctx else ["all"],
        "payload": action.get("payload", ""),
        "status": "queued",
        "auto":   True,
        "created_at": datetime.utcnow().isoformat(),
    }
    drone["mission_queue"].append(mission)
    await manager.broadcast({"type": "DRONE_QUEUE_UPDATE", "payload": {"drone_id": drone_id, "queue": drone["mission_queue"]}})
    return f"Dispatched {drone_id} {action['mode']} → zones {zone_ctx}"


async def _execute_dispatch_robot(action: dict, zone_ctx: str):
    robot_id = action.get("robot", "MPAR-1")
    robot = farm_state["robots"].get(robot_id)
    if not robot:
        return f"{robot_id} not found"

    job = {
        "id":   str(uuid.uuid4()),
        "head": action["head"],
        "zone": zone_ctx or "auto",
        "task": f"Auto-triggered: {action['head']} → zone {zone_ctx}",
        "status": "queued",
        "auto":   True,
    }
    robot["head_queue"].append(job)
    await manager.broadcast({"type": "ROBOT_QUEUE_UPDATE", "payload": {"robot_id": robot_id, "queue": robot["head_queue"]}})
    return f"Dispatched {robot_id} {action['head']} → zone {zone_ctx}"


async def _execute_cancel_spray(action: dict, zone_ctx: str):
    cancelled = 0
    for drone in farm_state["drones"].values():
        for mission in drone["mission_queue"]:
            if mission.get("mode") == "spray" and mission["status"] == "queued":
                mission["status"] = "cancelled-rain"
                cancelled += 1
    await manager.broadcast({"type": "SPRAY_MISSIONS_CANCELLED", "payload": {"count": cancelled}})
    return f"Cancelled {cancelled} queued spray missions (rain forecast)"


async def _execute_return_to_dock(action: dict, zone_ctx: str):
    recalled = []
    for drone_id, drone in farm_state["drones"].items():
        if drone["status"] in ("flying", "spraying"):
            drone["status"] = "returning"
            drone["current_task"] = "Returning to dock — low battery"
            recalled.append(drone_id)
    await manager.broadcast({"type": "DRONES_RECALLED", "payload": {"drones": recalled}})
    return f"Recalled: {', '.join(recalled)}"


ACTION_MAP = {
    "dispatch_drone":       _execute_dispatch_drone,
    "dispatch_robot":       _execute_dispatch_robot,
    "cancel_spray_missions": _execute_cancel_spray,
    "return_to_dock":       _execute_return_to_dock,
}


# ── main loop ─────────────────────────────────────────────────────

async def automation_loop():
    """Runs forever, evaluating all rules every 60 seconds."""
    while True:
        await asyncio.sleep(60)
        if not farm_state["automation"]["enabled"]:
            continue

        for rule in farm_state["automation"]["rules"]:
            if not rule["enabled"]:
                continue

            trigger = rule["trigger"]
            t_type  = trigger["type"]

            try:
                if t_type == "sensor":
                    fired, ctx = _eval_sensor(trigger)
                elif t_type == "weather":
                    fired, ctx = _eval_weather(trigger)
                elif t_type == "fleet":
                    fired, ctx = _eval_fleet(trigger)
                elif t_type == "schedule":
                    fired, ctx = _eval_schedule(trigger)
                elif t_type == "compound":
                    fired, ctx = _eval_compound(trigger)
                else:
                    continue

                if not fired:
                    continue

                # Execute action
                action = rule["action"]
                executor = ACTION_MAP.get(action["type"])
                if not executor:
                    continue

                result_msg = await executor(action, ctx)
                timestamp  = datetime.utcnow().strftime("%H:%M")

                log_entry = {
                    "time":    timestamp,
                    "rule":    rule["id"],
                    "name":    rule["name"],
                    "message": result_msg,
                    "status":  "success",
                }
                farm_state["automation"]["action_log"].append(log_entry)
                rule["last_fired"] = datetime.utcnow().isoformat()

                # Keep log to last 50 entries
                farm_state["automation"]["action_log"] = farm_state["automation"]["action_log"][-50:]

                await manager.broadcast({"type": "AUTOMATION_FIRED", "payload": log_entry})

            except Exception as e:
                print(f"[AUTOMATION] Rule {rule['id']} error: {e}")

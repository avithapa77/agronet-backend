"""
services/autonomous_engine.py — AgroNet v6

THE BRAIN of the autonomous farm.

Runs TWO parallel loops:
  1. outdoor_loop()  — evaluates outdoor rules every 60 s
  2. indoor_loop()   — evaluates indoor climate rules every 15 s
                       (indoor systems need faster response)

OUTDOOR RULE TYPES:
  sensor    — compare farm_state sensor dict values to threshold
  weather   — compare environment readings (wind, rain, temp)
  fleet     — check drone/robot battery levels
  schedule  — cron-style time matching (hour:minute)
  compound  — ALL sub-conditions must pass simultaneously

INDOOR RULE TYPES:
  indoor_sensor  — compare a single room's reading to a threshold
  indoor_multi   — check the same reading across ALL rooms
  schedule       — same cron system as outdoor

ACTIONS:
  Outdoor:  dispatch_drone, dispatch_robot, cancel_spray_missions, return_to_dock
  Indoor:   indoor_actuator, indoor_actuator_multi, indoor_robot,
            night_mode, lights_on, vpd_correction

Every fired rule:
  1. Executes its action (modifies farm_state)
  2. Appends to automation.action_log
  3. Broadcasts a WebSocket message → all dashboards update instantly
  4. Never fires twice in the same 5-minute window (cooldown guard)
"""

import asyncio
import uuid
import math
from datetime import datetime, timedelta

from state.farm_state import farm_state
from services.websocket_manager import manager


# ─────────────────────────────────────────────────────────────────
# COOLDOWN GUARD — prevents a rule from firing every minute
# ─────────────────────────────────────────────────────────────────
_cooldowns: dict[str, datetime] = {}
COOLDOWN_MINUTES = 5

def _on_cooldown(rule_id: str) -> bool:
    last = _cooldowns.get(rule_id)
    if last and datetime.utcnow() - last < timedelta(minutes=COOLDOWN_MINUTES):
        return True
    return False

def _set_cooldown(rule_id: str):
    _cooldowns[rule_id] = datetime.utcnow()


# ─────────────────────────────────────────────────────────────────
# SHARED HELPERS
# ─────────────────────────────────────────────────────────────────

def _cmp(value, operator, threshold):
    ops = {"<": value < threshold, ">": value > threshold,
           "<=": value <= threshold, ">=": value >= threshold,
           "==": value == threshold}
    return ops.get(operator, False)


async def _log_and_broadcast(rule: dict, message: str, status: str = "success"):
    entry = {
        "time":    datetime.utcnow().strftime("%H:%M"),
        "rule":    rule["id"],
        "env":     rule.get("env", "?"),
        "name":    rule["name"],
        "message": message,
        "status":  status,
    }
    log = farm_state["automation"]["action_log"]
    log.append(entry)
    farm_state["automation"]["action_log"] = log[-100:]   # keep last 100
    rule["last_fired"] = datetime.utcnow().isoformat()
    _set_cooldown(rule["id"])
    await manager.broadcast({"type": "AUTOMATION_FIRED", "payload": entry})


# ─────────────────────────────────────────────────────────────────
# ── OUTDOOR TRIGGER EVALUATORS ────────────────────────────────────
# ─────────────────────────────────────────────────────────────────

def _eval_outdoor_sensor(trigger: dict) -> tuple[bool, str]:
    """
    trigger.sensor = dotted path like "outdoor.sensors.soil_moisture"
    Reads all zone values in that sensor dict and checks each against threshold.
    Returns (True, "C5,A4") if any zone fires.
    """
    sensor_key = trigger["sensor"].split(".")[-1]   # e.g. "soil_moisture"
    readings = farm_state["outdoor"]["sensors"].get(sensor_key, {})
    fired = []
    for zone, value in readings.items():
        if isinstance(value, (int, float)) and _cmp(value, trigger["operator"], trigger["threshold"]):
            fired.append(zone)
    return (bool(fired), ",".join(fired))


def _eval_outdoor_weather(trigger: dict) -> tuple[bool, str]:
    env = farm_state["outdoor"]["environment"]
    # Special: check rain_forecast_mm from forecast list
    if trigger["condition"] == "rain_forecast_mm":
        forecast_rain = sum(
            d["rain_mm"] for d in farm_state["outdoor"]["weather_forecast"][:2]   # next 2 days
        )
        fired = _cmp(forecast_rain, trigger["operator"], trigger["threshold"])
        return fired, f"forecast_rain={forecast_rain}mm"
    value = env.get(trigger["condition"], 0)
    return _cmp(value, trigger["operator"], trigger["threshold"]), f"{trigger['condition']}={value}"


def _eval_outdoor_fleet(trigger: dict) -> tuple[bool, str]:
    if trigger["condition"] == "any_drone_battery":
        for did, d in farm_state["outdoor"]["drones"].items():
            if _cmp(d["battery_pct"], trigger["operator"], trigger["threshold"]):
                return True, f"{did} battery={d['battery_pct']:.0f}%"
    return False, ""


def _eval_schedule(trigger: dict) -> tuple[bool, str]:
    """Matches cron "minute hour * * weekday(optional)" against UTC now."""
    cron = trigger.get("cron", "")
    parts = cron.split()
    if len(parts) < 2:
        return False, ""
    try:
        minute = int(parts[0]) if parts[0] != "*" else None
        hour   = int(parts[1]) if parts[1] != "*" else None
        # Handle */N syntax (e.g. "*/4")
        if parts[0].startswith("*/"):
            step = int(parts[0][2:])
            now = datetime.utcnow()
            if now.minute == 0 and now.hour % step == 0:
                return True, f"every {step}h at :00"
            return False, ""
        now = datetime.utcnow()
        if (hour is None or now.hour == hour) and (minute is None or now.minute == minute):
            # Day-of-week filter (parts[4] if present)
            if len(parts) >= 5 and parts[4] != "*":
                allowed_days = [int(d) for d in parts[4].split(",")]
                if now.weekday() not in allowed_days:   # Mon=0 in Python, Mon=1 in cron
                    return False, ""
            return True, f"schedule {hour:02d}:{minute:02d}"
    except Exception:
        pass
    return False, ""


def _eval_outdoor_compound(trigger: dict) -> tuple[bool, str]:
    env = farm_state["outdoor"]["environment"]
    for cond in trigger.get("conditions", []):
        value = env.get(cond["sensor"], 0)
        if cond["operator"] == "between":
            if not (cond["min"] <= value <= cond["max"]):
                return False, ""
        else:
            if not _cmp(value, cond["operator"], cond["threshold"]):
                return False, ""
    return True, "all conditions met"


# ─────────────────────────────────────────────────────────────────
# ── OUTDOOR ACTION EXECUTORS ──────────────────────────────────────
# ─────────────────────────────────────────────────────────────────

async def _act_dispatch_drone(action: dict, ctx: str) -> str:
    drone_id = action.get("drone", "UAV-1")
    drone = farm_state["outdoor"]["drones"].get(drone_id)
    if not drone:
        return f"{drone_id} not found"
    if drone["battery_pct"] < 20:
        # Try fallback drone
        for alt_id, alt in farm_state["outdoor"]["drones"].items():
            if alt_id != drone_id and alt["battery_pct"] >= 30:
                drone_id = alt_id
                drone = alt
                break
        else:
            return f"All drones low battery — mission queued for later"

    # Block spray in high wind
    if action.get("mode") == "spray":
        wind = farm_state["outdoor"]["environment"]["wind_speed_kmh"]
        if wind > 15:
            return f"Spray blocked — wind {wind} km/h > 15 limit"

    mission = {
        "id":       str(uuid.uuid4())[:8],
        "mode":     action["mode"],
        "zones":    ctx.split(",") if ctx else ["all"],
        "payload":  action.get("payload",""),
        "status":   "queued",
        "auto":     True,
        "created":  datetime.utcnow().isoformat(),
    }
    drone["mission_queue"].append(mission)
    await manager.broadcast({"type":"DRONE_QUEUE_UPDATE","payload":{"drone_id":drone_id,"queue":drone["mission_queue"]}})
    return f"Dispatched {drone_id} {action['mode']} → zones [{ctx}]"


async def _act_dispatch_robot(action: dict, ctx: str) -> str:
    robot_id = action.get("robot","MPAR-1")
    robot = farm_state["outdoor"]["robots"].get(robot_id)
    if not robot:
        return f"{robot_id} not found"
    job = {
        "id":     str(uuid.uuid4())[:8],
        "head":   action["head"],
        "zone":   ctx or "auto",
        "task":   f"Auto: {action['head']} → {ctx}",
        "status": "queued","auto": True,
    }
    robot["head_queue"].append(job)
    await manager.broadcast({"type":"ROBOT_QUEUE_UPDATE","payload":{"robot_id":robot_id,"queue":robot["head_queue"]}})
    return f"Dispatched {robot_id} {action['head']} → zone [{ctx}]"


async def _act_cancel_spray(action: dict, ctx: str) -> str:
    n = 0
    for drone in farm_state["outdoor"]["drones"].values():
        for m in drone["mission_queue"]:
            if m.get("mode") == "spray" and m["status"] == "queued":
                m["status"] = "cancelled-rain"
                n += 1
    await manager.broadcast({"type":"SPRAY_CANCELLED","payload":{"count":n,"reason":"rain"}})
    return f"Cancelled {n} spray missions — rain forecast"


async def _act_return_to_dock(action: dict, ctx: str) -> str:
    recalled = []
    for did, d in farm_state["outdoor"]["drones"].items():
        if d["status"] in ("flying","spraying"):
            d["status"] = "returning"
            d["current_task"] = "Return to dock — low battery"
            recalled.append(did)
    await manager.broadcast({"type":"FLEET_RECALLED","payload":{"drones":recalled}})
    return f"Recalled: {', '.join(recalled) or 'none in flight'}"


OUTDOOR_ACTIONS = {
    "dispatch_drone":        _act_dispatch_drone,
    "dispatch_robot":        _act_dispatch_robot,
    "cancel_spray_missions": _act_cancel_spray,
    "return_to_dock":        _act_return_to_dock,
}


# ─────────────────────────────────────────────────────────────────
# ── INDOOR TRIGGER EVALUATORS ─────────────────────────────────────
# ─────────────────────────────────────────────────────────────────

def _eval_indoor_sensor(trigger: dict) -> tuple[bool, str]:
    room_id = trigger["room"]
    reading = trigger["reading"]
    room = farm_state["indoor"]["rooms"].get(room_id)
    if not room:
        return False, ""
    value = room["readings"].get(reading)
    if value is None:
        return False, ""
    fired = _cmp(value, trigger["operator"], trigger["threshold"])
    return fired, f"{room_id}.{reading}={value}"


def _eval_indoor_multi(trigger: dict) -> tuple[bool, str]:
    """Check the same reading across all rooms. Returns rooms that breach."""
    reading   = trigger["reading"]
    tolerance = trigger.get("tolerance")
    operator  = trigger.get("operator","outside_range")
    fired_rooms = []

    for room_id, room in farm_state["indoor"]["rooms"].items():
        value  = room["readings"].get(reading)
        target = room["targets"].get(f"ph_target" if reading=="ph" else
                                     f"ec_target_ms" if reading=="ec_ms" else reading)
        if value is None:
            continue

        if tolerance is not None and target is not None:
            if abs(value - target) > tolerance:
                fired_rooms.append(f"{room_id}({value:.2f} vs {target})")
        elif operator == "outside_range":
            mn, mx = trigger.get("min",0), trigger.get("max",999)
            if not (mn <= value <= mx):
                fired_rooms.append(f"{room_id}({value:.2f})")
        elif operator and "threshold" in trigger:
            if _cmp(value, operator, trigger["threshold"]):
                fired_rooms.append(f"{room_id}({value:.2f})")

    return bool(fired_rooms), ", ".join(fired_rooms)


# ─────────────────────────────────────────────────────────────────
# ── INDOOR ACTION EXECUTORS ───────────────────────────────────────
# ─────────────────────────────────────────────────────────────────

async def _act_indoor_actuator(action: dict, ctx: str) -> str:
    room_id  = action["room"]
    actuator = action["actuator"]
    command  = action["command"]
    room_acts = farm_state["indoor"]["actuators"].get(room_id, {})
    if actuator not in room_acts:
        return f"{room_id}.{actuator} not found"
    room_acts[actuator].update(command)
    # Fire the "also" sub-action if present (handled by caller)
    await manager.broadcast({"type":"INDOOR_ACTUATOR","payload":{"room":room_id,"actuator":actuator,"state":room_acts[actuator]}})
    return f"{room_id} {actuator} → {command}"


async def _act_indoor_actuator_multi(action: dict, ctx: str) -> str:
    actuator = action["actuator"]
    command  = action["command"]
    updated  = []
    for room_id, room_acts in farm_state["indoor"]["actuators"].items():
        if actuator in room_acts:
            room_acts[actuator].update(command)
            updated.append(room_id)
    await manager.broadcast({"type":"INDOOR_ACTUATOR_MULTI","payload":{"actuator":actuator,"rooms":updated,"state":command}})
    return f"All rooms {actuator} → {command}"


async def _act_indoor_robot(action: dict, ctx: str) -> str:
    robot_id = action["robot"]
    command  = action["command"]
    robot = farm_state["indoor"]["indoor_robots"].get(robot_id)
    if not robot:
        return f"{robot_id} not found"
    robot["status"] = "active"
    robot["current_task"] = f"Auto: {command}"
    await manager.broadcast({"type":"INDOOR_ROBOT","payload":{"robot_id":robot_id,"command":command,"ctx":ctx}})
    return f"{robot_id} executing {command}"


async def _act_night_mode(action: dict, ctx: str) -> str:
    """Set all rooms to night temperature target."""
    for room_id, room in farm_state["indoor"]["rooms"].items():
        night_temp = room["targets"].get("temp_night_c", 18)
        acts = farm_state["indoor"]["actuators"].get(room_id, {})
        if "hvac" in acts:
            acts["hvac"]["setpoint_c"] = night_temp
        # Close roof vents at night
        if "roof_vents" in acts:
            acts["roof_vents"]["open_pct"] = 10
    await manager.broadcast({"type":"NIGHT_MODE","payload":{"active":True}})
    return "Night mode activated — all rooms at night targets"


async def _act_lights_on(action: dict, ctx: str) -> str:
    """Turn on LEDs in all rooms at their scheduled intensity."""
    for room_id, acts in farm_state["indoor"]["actuators"].items():
        if "led_rig" in acts:
            acts["led_rig"]["status"] = "on"
    await manager.broadcast({"type":"LIGHTS_ON","payload":{"rooms":"all"}})
    return "Lights on — all rooms"


async def _act_vpd_correction(action: dict, ctx: str) -> str:
    """
    VPD = (1 - RH/100) × SVP where SVP = 0.6108 × e^(17.27×T/(T+237.3))
    If VPD too high → mist more / reduce temp
    If VPD too low  → reduce humidity / increase temp
    """
    corrected = []
    for room_id, room in farm_state["indoor"]["rooms"].items():
        vpd   = room["readings"].get("vpd_kpa", 1.0)
        mn    = room["targets"].get("vpd_kpa", 1.0) - 0.2
        mx    = room["targets"].get("vpd_kpa", 1.0) + 0.2
        acts  = farm_state["indoor"]["actuators"].get(room_id, {})
        if vpd < mn:          # too humid → increase temp or reduce misting
            if "misting" in acts: acts["misting"]["status"] = "off"
            if "hvac" in acts:
                acts["hvac"]["setpoint_c"] = min(acts["hvac"].get("setpoint_c",22)+1,30)
            corrected.append(f"{room_id}↑temp")
        elif vpd > mx:        # too dry → add humidity
            if "misting" in acts: acts["misting"]["status"] = "on"
            corrected.append(f"{room_id}↑mist")
    if corrected:
        await manager.broadcast({"type":"VPD_CORRECTION","payload":{"rooms":corrected}})
    return f"VPD corrected: {', '.join(corrected) or 'none needed'}"


INDOOR_ACTIONS = {
    "indoor_actuator":       _act_indoor_actuator,
    "indoor_actuator_multi": _act_indoor_actuator_multi,
    "indoor_robot":          _act_indoor_robot,
    "night_mode":            _act_night_mode,
    "lights_on":             _act_lights_on,
    "vpd_correction":        _act_vpd_correction,
}


# ─────────────────────────────────────────────────────────────────
# ── MAIN LOOPS ────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────

async def _evaluate_rule(rule: dict):
    """Evaluate one rule's trigger and fire its action if it passes."""
    if not rule["enabled"]:
        return
    if _on_cooldown(rule["id"]):
        return

    trigger = rule["trigger"]
    t_type  = trigger["type"]
    env     = rule.get("env","outdoor")

    try:
        # ── Trigger evaluation ──────────────────────────────
        if t_type == "sensor":
            fired, ctx = _eval_outdoor_sensor(trigger)
        elif t_type == "weather":
            fired, ctx = _eval_outdoor_weather(trigger)
        elif t_type == "fleet":
            fired, ctx = _eval_outdoor_fleet(trigger)
        elif t_type == "schedule":
            fired, ctx = _eval_schedule(trigger)
        elif t_type == "compound":
            fired, ctx = _eval_outdoor_compound(trigger)
        elif t_type == "indoor_sensor":
            fired, ctx = _eval_indoor_sensor(trigger)
        elif t_type == "indoor_multi":
            fired, ctx = _eval_indoor_multi(trigger)
        else:
            return

        if not fired:
            return

        # ── Action execution ────────────────────────────────
        action   = rule["action"]
        act_type = action["type"]

        executor = OUTDOOR_ACTIONS.get(act_type) or INDOOR_ACTIONS.get(act_type)
        if not executor:
            return

        result = await executor(action, ctx)

        # Fire secondary "also" action if defined (e.g. HVAC + open vents)
        if "also" in rule:
            also_act = rule["also"]
            also_exec = INDOOR_ACTIONS.get(also_act["type"])
            if also_exec:
                await also_exec(also_act, ctx)

        await _log_and_broadcast(rule, result)

    except Exception as e:
        print(f"[AUTO] Rule {rule['id']} error: {e}")


async def outdoor_loop():
    """Evaluate outdoor rules every 60 seconds."""
    print("[AUTO] Outdoor loop started")
    while True:
        await asyncio.sleep(60)
        if not farm_state["automation"]["enabled"]:
            continue
        mode = farm_state["automation"]["mode"]
        if mode not in ("outdoor","both"):
            continue
        for rule in farm_state["automation"]["rules"]:
            if rule.get("env") in ("outdoor","both") or rule.get("env") is None:
                await _evaluate_rule(rule)


async def indoor_loop():
    """Evaluate indoor climate rules every 15 seconds (faster response needed)."""
    print("[AUTO] Indoor loop started")
    while True:
        await asyncio.sleep(15)
        if not farm_state["automation"]["enabled"]:
            continue
        mode = farm_state["automation"]["mode"]
        if mode not in ("indoor","both"):
            continue
        for rule in farm_state["automation"]["rules"]:
            if rule.get("env") == "indoor":
                await _evaluate_rule(rule)

        # Always recalculate VPD from temp + humidity (physics update)
        for room in farm_state["indoor"]["rooms"].values():
            r = room["readings"]
            T = r.get("temp_c", 25)
            RH = r.get("humidity_pct", 60)
            svp = 0.6108 * math.exp(17.27 * T / (T + 237.3))
            r["vpd_kpa"] = round(svp * (1 - RH / 100), 2)

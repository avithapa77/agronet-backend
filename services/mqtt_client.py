"""
mqtt_client.py — v6

Updated to write into the correct v6 nested state paths:
  farm_state["outdoor"]["sensors"]   (was farm_state["sensors"])
  farm_state["outdoor"]["zones"]     (was farm_state["zones"])
  farm_state["outdoor"]["environment"] (was farm_state["environment"])
  farm_state["outdoor"]["drones"]    (was farm_state["drone"])
  farm_state["outdoor"]["robots"]    (was farm_state["robot"])

Also handles indoor MQTT topics:
  agronet/{farm_id}/indoor/{room_id}/{reading}  →  updates room readings
  agronet/{farm_id}/indoor/{room_id}/actuator/{actuator}  →  updates actuator state

Full topic schema:
  agronet/{farm_id}/sensor/{type}/{zone}    →  outdoor sensor
  agronet/{farm_id}/environment             →  outdoor environment
  agronet/{farm_id}/drone/{drone_id}        →  drone telemetry
  agronet/{farm_id}/robot/{robot_id}        →  robot telemetry
  agronet/{farm_id}/indoor/{room_id}/sensor →  indoor room readings
  agronet/{farm_id}/indoor/{room_id}/actuator/{name} → actuator state
  agronet/{farm_id}/alert/{alert_id}        →  push a new alert
"""

import json
import asyncio
import os
import paho.mqtt.client as mqtt

from state.farm_state import farm_state
from services.websocket_manager import manager

FARM_ID = os.getenv("FARM_ID", "farm-001")

# Alert thresholds — outdoor
MOISTURE_THRESHOLD  = 45   # % — below → drought alert
NITROGEN_THRESHOLD  = 50   # ppm — below → nutrient alert
PEST_THRESHOLD      = 30   # catches/day — above → pest alert
LEAF_WET_THRESHOLD  = 0.8  # 0-1 — above → fungal risk

# Alert thresholds — indoor
TEMP_TOLERANCE      = 3.0  # °C — deviation from target → alert
HUMIDITY_TOLERANCE  = 10   # %  — deviation from target → alert
CO2_MIN             = 400  # ppm — below → alert
PH_TOLERANCE        = 0.5  # pH units — deviation from target → alert
EC_TOLERANCE        = 0.5  # ms/cm

_loop: asyncio.AbstractEventLoop = None


def set_event_loop(loop):
    global _loop
    _loop = loop


def _broadcast(message: dict):
    if _loop:
        asyncio.run_coroutine_threadsafe(manager.broadcast(message), _loop)


# ── Connection ──────────────────────────────────────────────────

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        host = os.getenv("MQTT_BROKER_HOST", "localhost")
        print(f"[MQTT] Connected to {host}")
        client.subscribe(f"agronet/{FARM_ID}/#")
        print(f"[MQTT] Subscribed to agronet/{FARM_ID}/#")
    else:
        print(f"[MQTT] Connection failed, code {rc}")


# ── Message router ──────────────────────────────────────────────

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
    except Exception:
        return

    parts = msg.topic.split("/")
    # Minimum: agronet / farm_id / category
    if len(parts) < 3:
        return

    category = parts[2]

    if category == "sensor" and len(parts) >= 5:
        # agronet/{farm_id}/sensor/{type}/{zone}
        _handle_outdoor_sensor(parts[3], parts[4], payload)

    elif category == "environment":
        # agronet/{farm_id}/environment
        farm_state["outdoor"]["environment"].update(payload)
        _broadcast({"type": "SENSOR", "payload": {"category": "environment", "data": payload}})

    elif category == "drone" and len(parts) >= 4:
        # agronet/{farm_id}/drone/{drone_id}
        drone_id = parts[3].upper()
        drone = farm_state["outdoor"]["drones"].get(drone_id)
        if drone:
            drone.update({k: v for k, v in payload.items() if k in drone})
            _broadcast({"type": "TELEMETRY", "payload": {
                "outdoor": {"drones": {drone_id: drone}}
            }})

    elif category == "robot" and len(parts) >= 4:
        # agronet/{farm_id}/robot/{robot_id}
        robot_id = parts[3].upper()
        robot = farm_state["outdoor"]["robots"].get(robot_id)
        if robot:
            robot.update({k: v for k, v in payload.items() if k in robot})
            _broadcast({"type": "TELEMETRY", "payload": {
                "outdoor": {"robots": {robot_id: robot}}
            }})

    elif category == "indoor" and len(parts) >= 5:
        room_id = parts[3].upper()
        sub     = parts[4]

        if sub == "sensor":
            # agronet/{farm_id}/indoor/{room_id}/sensor  payload = {reading: value, ...}
            _handle_indoor_sensor(room_id, payload)

        elif sub == "actuator" and len(parts) >= 6:
            # agronet/{farm_id}/indoor/{room_id}/actuator/{name}
            actuator_name = parts[5]
            _handle_indoor_actuator(room_id, actuator_name, payload)

    elif category == "alert" and len(parts) >= 4:
        # agronet/{farm_id}/alert/{alert_id}
        _upsert_alert(parts[3], **payload)


# ── Outdoor sensor handlers ─────────────────────────────────────

def _handle_outdoor_sensor(sensor_type: str, zone: str, payload: dict):
    value = payload.get("value")
    if value is None:
        return

    sensors = farm_state["outdoor"]["sensors"]
    zones   = farm_state["outdoor"]["zones"]

    if sensor_type == "soil_moisture":
        sensors["soil_moisture"][zone] = value
        if zone in zones:
            zones[zone]["moisture"] = value
        _check_moisture(zone, value)

    elif sensor_type == "nitrogen":
        sensors["nitrogen"][zone] = value
        _check_nitrogen(zone, value)

    elif sensor_type == "phosphorus":
        sensors["phosphorus"][zone] = value

    elif sensor_type == "potassium":
        sensors["potassium"][zone] = value

    elif sensor_type == "ph":
        sensors["ph"][zone] = value

    elif sensor_type == "compaction":
        sensors["compaction"][zone] = value

    elif sensor_type == "pest_trap":
        sensors["pest_traps"][zone] = value
        _check_pest(zone, value)

    elif sensor_type == "leaf_wetness":
        sensors["leaf_wetness"][zone] = value
        _check_leaf_wetness(zone, value)

    elif sensor_type == "ndvi":
        if zone in zones:
            zones[zone]["ndvi"] = value

    _broadcast({"type": "SENSOR", "payload": {
        "env": "outdoor", "sensor_type": sensor_type, "zone": zone, "value": value
    }})


# ── Indoor sensor handler ───────────────────────────────────────

def _handle_indoor_sensor(room_id: str, payload: dict):
    """Update indoor room readings from a sensor payload dict."""
    room = farm_state["indoor"]["rooms"].get(room_id)
    if not room:
        return

    readings = room["readings"]
    targets  = room["targets"]
    updated  = {}

    for reading, value in payload.items():
        if reading in readings:
            readings[reading] = value
            updated[reading] = value
            _check_indoor_reading(room_id, room, reading, value)

    if updated:
        _broadcast({"type": "SENSOR", "payload": {
            "env": "indoor", "room": room_id, "readings": updated
        }})


def _check_indoor_reading(room_id: str, room: dict, reading: str, value: float):
    """Create or clear an alert if a reading is outside acceptable range."""
    targets = room["targets"]

    if reading == "temp_c":
        target = targets.get("temp_day_c", 25)
        aid = f"indoor-temp-{room_id}"
        if abs(value - target) > TEMP_TOLERANCE:
            _upsert_room_alert(room, aid, "medium", "climate",
                f"Temp {value}°C (target {target}°C)", "Check HVAC")
        else:
            _clear_room_alert(room, aid)

    elif reading == "humidity_pct":
        target = targets.get("humidity_pct", 65)
        aid = f"indoor-humidity-{room_id}"
        if abs(value - target) > HUMIDITY_TOLERANCE:
            _upsert_room_alert(room, aid, "medium", "climate",
                f"Humidity {value}% (target {target}%)", "Adjust misting/ventilation")
        else:
            _clear_room_alert(room, aid)

    elif reading == "co2_ppm":
        aid = f"indoor-co2-{room_id}"
        if value < CO2_MIN:
            _upsert_room_alert(room, aid, "medium", "climate",
                f"CO₂ {value} ppm (low)", "Check CO₂ injector")
        else:
            _clear_room_alert(room, aid)

    elif reading == "ph":
        target = targets.get("ph_target", 6.0)
        aid = f"indoor-ph-{room_id}"
        if abs(value - target) > PH_TOLERANCE:
            _upsert_room_alert(room, aid, "high", "nutrient",
                f"pH {value:.2f} (target {target})", "DOSER-1 pH correction needed")
        else:
            _clear_room_alert(room, aid)

    elif reading == "ec_ms":
        target = targets.get("ec_target_ms", 2.0)
        aid = f"indoor-ec-{room_id}"
        if abs(value - target) > EC_TOLERANCE:
            _upsert_room_alert(room, aid, "medium", "nutrient",
                f"EC {value:.2f} ms/cm (target {target})", "DOSER-1 EC correction needed")
        else:
            _clear_room_alert(room, aid)


def _upsert_room_alert(room: dict, aid: str, severity: str, atype: str, message: str, action: str):
    existing = next((a for a in room["alerts"] if a["id"] == aid), None)
    if not existing:
        alert = {"id": aid, "severity": severity, "type": atype, "message": message, "action": action}
        room["alerts"].append(alert)
        _broadcast({"type": "ALERT_NEW", "payload": {"env": "indoor", **alert}})


def _clear_room_alert(room: dict, aid: str):
    before = len(room["alerts"])
    room["alerts"] = [a for a in room["alerts"] if a["id"] != aid]
    if len(room["alerts"]) < before:
        _broadcast({"type": "ALERT_CLEAR", "payload": {"id": aid}})


# ── Indoor actuator handler ─────────────────────────────────────

def _handle_indoor_actuator(room_id: str, actuator_name: str, payload: dict):
    """Update actuator state from hardware feedback."""
    acts = farm_state["indoor"]["actuators"].get(room_id, {})
    if actuator_name in acts:
        acts[actuator_name].update(payload)
        _broadcast({"type": "INDOOR_ACTUATOR", "payload": {
            "room": room_id, "actuator": actuator_name, "state": acts[actuator_name]
        }})


# ── Outdoor alert helpers ───────────────────────────────────────

def _upsert_alert(aid, severity="medium", type="unknown", zones=None,
                  message="", action="", **kwargs):
    alerts = farm_state["alerts"]
    if not any(a["id"] == aid for a in alerts):
        alert = {"id": aid, "severity": severity, "type": type,
                 "zones": zones or [], "message": message, "action": action}
        alerts.append(alert)
        _broadcast({"type": "ALERT_NEW", "payload": alert})


def _clear_alert(aid):
    before = len(farm_state["alerts"])
    farm_state["alerts"] = [a for a in farm_state["alerts"] if a["id"] != aid]
    if len(farm_state["alerts"]) < before:
        _broadcast({"type": "ALERT_CLEAR", "payload": {"id": aid}})


def _check_moisture(zone, value):
    aid = f"moisture-{zone}"
    if value < MOISTURE_THRESHOLD:
        _upsert_alert(aid, "medium", "moisture", [zone],
            f"Drought stress {value}%", "Auto: MPAR-3 drip irrigation")
    else:
        _clear_alert(aid)


def _check_nitrogen(zone, value):
    aid = f"nitrogen-{zone}"
    if value < NITROGEN_THRESHOLD:
        _upsert_alert(aid, "medium", "nutrient", [zone],
            f"Nitrogen {value} ppm (low)", "Auto: UAV-1 foliar nitrogen")
    else:
        _clear_alert(aid)


def _check_pest(zone, value):
    aid = f"pest-{zone}"
    if value > PEST_THRESHOLD:
        _upsert_alert(aid, "high", "pest", [zone],
            f"Pest trap {value} catches/24h", "Auto: UAV-2 fungicide spray")
    else:
        _clear_alert(aid)


def _check_leaf_wetness(zone, value):
    aid = f"leaf-wet-{zone}"
    if value > LEAF_WET_THRESHOLD:
        _upsert_alert(aid, "medium", "disease_risk", [zone],
            f"Leaf wetness {value:.2f} (fungal risk)", "Auto: UAV-2 preventive copper")
    else:
        _clear_alert(aid)


# ── Startup ─────────────────────────────────────────────────────

def start_mqtt():
    client = mqtt.Client()   # paho-mqtt 1.x API

    username = os.getenv("MQTT_USERNAME")
    password = os.getenv("MQTT_PASSWORD")
    if username:
        client.username_pw_set(username, password)

    client.on_connect = on_connect
    client.on_message = on_message

    host = os.getenv("MQTT_BROKER_HOST", "localhost")
    port = int(os.getenv("MQTT_BROKER_PORT", 1883))

    try:
        client.connect(host, port, keepalive=60)
        client.loop_start()
        print(f"[MQTT] Client started — connecting to {host}:{port}")
    except Exception as e:
        print(f"[MQTT] Could not connect to {host}:{port}: {e} — continuing without MQTT")

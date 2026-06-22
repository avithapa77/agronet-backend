"""
mqtt_client.py

Connects to the MQTT broker where all field sensors publish readings.
Runs in a background thread so it doesn't block FastAPI's async event loop.

TOPIC STRUCTURE
───────────────
agronet/{farm_id}/sensor/soil_moisture/{zone}   → {"value": 39}
agronet/{farm_id}/sensor/nitrogen/{zone}        → {"value": 42}
agronet/{farm_id}/sensor/ph/{zone}              → {"value": 5.8}
agronet/{farm_id}/sensor/compaction/{zone}      → {"value": 2.1}
agronet/{farm_id}/sensor/pest_trap/{zone}       → {"value": 48}
agronet/{farm_id}/sensor/environment            → {"air_temp_c": 27, "humidity_pct": 71, ...}
agronet/{farm_id}/drone/telemetry               → {"battery_pct": 78, "status": "flying", ...}
agronet/{farm_id}/robot/telemetry               → {"battery_pct": 82, "status": "active", ...}
"""

import json
import asyncio
import os
import paho.mqtt.client as mqtt

from state.farm_state import farm_state
from services.websocket_manager import manager

FARM_ID = os.getenv("FARM_ID", "farm-001")

# Alert thresholds
MOISTURE_THRESHOLD  = 45   # % — alert below
NITROGEN_THRESHOLD  = 50   # ppm — alert below
PEST_THRESHOLD      = 30   # catches/24h — alert above

# We need a reference to the running asyncio loop so the MQTT callback
# (which runs in a thread) can schedule a coroutine on it
_loop: asyncio.AbstractEventLoop = None


def set_event_loop(loop: asyncio.AbstractEventLoop):
    global _loop
    _loop = loop


def _broadcast(message: dict):
    """Thread-safe way to call the async broadcast from a sync MQTT callback."""
    if _loop:
        asyncio.run_coroutine_threadsafe(manager.broadcast(message), _loop)


# ── MQTT callbacks ─────────────────────────────────────────────

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"MQTT connected — broker: {os.getenv('MQTT_BROKER_HOST', 'localhost')}")
        client.subscribe(f"agronet/{FARM_ID}/#")
    else:
        print(f"MQTT connection failed, code {rc}")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
    except Exception:
        return  # Ignore malformed messages

    parts = msg.topic.split("/")
    # parts: [agronet, farm_id, category, type, zone?]
    if len(parts) < 4:
        return

    category = parts[2]
    msg_type = parts[3]
    zone     = parts[4] if len(parts) > 4 else None

    if category == "sensor":
        _handle_sensor(msg_type, zone, payload)
    elif category == "drone":
        _handle_drone_telemetry(payload)
    elif category == "robot":
        _handle_robot_telemetry(payload)


# ── Sensor handlers ────────────────────────────────────────────

def _handle_sensor(sensor_type: str, zone: str | None, payload: dict):
    value = payload.get("value")
    if value is None:
        return

    if sensor_type == "soil_moisture" and zone:
        farm_state["sensors"]["soil_moisture"][zone] = value
        if zone in farm_state["zones"]:
            farm_state["zones"][zone]["moisture"] = value
        _check_moisture_alert(zone, value)

    elif sensor_type == "nitrogen" and zone:
        farm_state["sensors"]["nitrogen"][zone] = value
        _check_nitrogen_alert(zone, value)

    elif sensor_type == "ph" and zone:
        farm_state["sensors"]["ph"][zone] = value

    elif sensor_type == "compaction" and zone:
        farm_state["sensors"]["compaction"][zone] = value

    elif sensor_type == "pest_trap" and zone:
        farm_state["sensors"]["pest_traps"][zone] = value
        _check_pest_alert(zone, value)

    elif sensor_type == "environment":
        farm_state["environment"].update(payload)

    _broadcast({"type": "SENSOR", "payload": {"sensor_type": sensor_type, "zone": zone, "value": value}})


def _handle_drone_telemetry(payload: dict):
    farm_state["drone"].update(payload)
    _broadcast({"type": "TELEMETRY", "payload": {"drone": farm_state["drone"]}})


def _handle_robot_telemetry(payload: dict):
    farm_state["robot"].update(payload)
    _broadcast({"type": "TELEMETRY", "payload": {"robot": farm_state["robot"]}})


# ── Alert threshold checks ─────────────────────────────────────

def _upsert_alert(alert_id, severity, alert_type, zones, message, action):
    existing = next((a for a in farm_state["alerts"] if a["id"] == alert_id), None)
    if not existing:
        alert = {"id": alert_id, "severity": severity, "type": alert_type,
                 "zones": zones, "message": message, "action": action}
        farm_state["alerts"].append(alert)
        _broadcast({"type": "ALERT_NEW", "payload": alert})


def _clear_alert(alert_id):
    before = len(farm_state["alerts"])
    farm_state["alerts"] = [a for a in farm_state["alerts"] if a["id"] != alert_id]
    if len(farm_state["alerts"]) < before:
        _broadcast({"type": "ALERT_CLEAR", "payload": {"id": alert_id}})


def _check_moisture_alert(zone, value):
    aid = f"moisture-{zone}"
    if value < MOISTURE_THRESHOLD:
        _upsert_alert(aid, "medium", "moisture", [zone],
                      f"Drought stress {value}% (threshold {MOISTURE_THRESHOLD}%)",
                      "Schedule drip irrigation")
    else:
        _clear_alert(aid)


def _check_nitrogen_alert(zone, value):
    aid = f"nitrogen-{zone}"
    if value < NITROGEN_THRESHOLD:
        _upsert_alert(aid, "medium", "nutrient", [zone],
                      f"Nitrogen {value} ppm (low, threshold {NITROGEN_THRESHOLD} ppm)",
                      "Schedule foliar N spray")
    else:
        _clear_alert(aid)


def _check_pest_alert(zone, value):
    aid = f"pest-{zone}"
    if value > PEST_THRESHOLD:
        _upsert_alert(aid, "high", "pest", [zone],
                      f"Pest trap {value} catches/24h",
                      "Dispatch UAV-1 spray mode")
    else:
        _clear_alert(aid)


# ── Start function ─────────────────────────────────────────────

def start_mqtt():
    """Called once at startup — connects and starts the network loop in a thread."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    username = os.getenv("MQTT_USERNAME")
    password = os.getenv("MQTT_PASSWORD")
    if username:
        client.username_pw_set(username, password)

    client.on_connect = on_connect
    client.on_message = on_message

    broker_host = os.getenv("MQTT_BROKER_HOST", "localhost")
    broker_port = int(os.getenv("MQTT_BROKER_PORT", 1883))

    try:
        client.connect(broker_host, broker_port, keepalive=60)
        client.loop_start()   # Runs in a background thread
        print(f"MQTT client started — connecting to {broker_host}:{broker_port}")
    except Exception as e:
        print(f"MQTT could not connect: {e} (continuing without MQTT — use sensor simulation)")

"""
mqtt_client.py — paho-mqtt 1.6.x compatible
"""

import json
import asyncio
import os
import paho.mqtt.client as mqtt

from state.farm_state import farm_state
from services.websocket_manager import manager

FARM_ID = os.getenv("FARM_ID", "farm-001")

MOISTURE_THRESHOLD = 45
NITROGEN_THRESHOLD = 50
PEST_THRESHOLD     = 30

_loop: asyncio.AbstractEventLoop = None


def set_event_loop(loop):
    global _loop
    _loop = loop


def _broadcast(message: dict):
    if _loop:
        asyncio.run_coroutine_threadsafe(manager.broadcast(message), _loop)


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"MQTT connected to {os.getenv('MQTT_BROKER_HOST', 'localhost')}")
        client.subscribe(f"agronet/{FARM_ID}/#")
    else:
        print(f"MQTT connection failed, code {rc}")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
    except Exception:
        return

    parts    = msg.topic.split("/")
    if len(parts) < 4:
        return

    category = parts[2]
    msg_type = parts[3]
    zone     = parts[4] if len(parts) > 4 else None

    if category == "sensor":
        _handle_sensor(msg_type, zone, payload)
    elif category == "drone":
        farm_state["drone"].update(payload)
        _broadcast({"type": "TELEMETRY", "payload": {"drone": farm_state["drone"]}})
    elif category == "robot":
        farm_state["robot"].update(payload)
        _broadcast({"type": "TELEMETRY", "payload": {"robot": farm_state["robot"]}})


def _handle_sensor(sensor_type, zone, payload):
    value = payload.get("value")
    if value is None:
        return

    if sensor_type == "soil_moisture" and zone:
        farm_state["sensors"]["soil_moisture"][zone] = value
        if zone in farm_state["zones"]:
            farm_state["zones"][zone]["moisture"] = value
        _check_moisture(zone, value)
    elif sensor_type == "nitrogen" and zone:
        farm_state["sensors"]["nitrogen"][zone] = value
        _check_nitrogen(zone, value)
    elif sensor_type == "ph" and zone:
        farm_state["sensors"]["ph"][zone] = value
    elif sensor_type == "compaction" and zone:
        farm_state["sensors"]["compaction"][zone] = value
    elif sensor_type == "pest_trap" and zone:
        farm_state["sensors"]["pest_traps"][zone] = value
        _check_pest(zone, value)
    elif sensor_type == "environment":
        farm_state["environment"].update(payload)

    _broadcast({"type": "SENSOR", "payload": {"sensor_type": sensor_type, "zone": zone, "value": value}})


def _upsert_alert(aid, severity, atype, zones, message, action):
    if not any(a["id"] == aid for a in farm_state["alerts"]):
        alert = {"id": aid, "severity": severity, "type": atype,
                 "zones": zones, "message": message, "action": action}
        farm_state["alerts"].append(alert)
        _broadcast({"type": "ALERT_NEW", "payload": alert})


def _clear_alert(aid):
    before = len(farm_state["alerts"])
    farm_state["alerts"] = [a for a in farm_state["alerts"] if a["id"] != aid]
    if len(farm_state["alerts"]) < before:
        _broadcast({"type": "ALERT_CLEAR", "payload": {"id": aid}})


def _check_moisture(zone, value):
    aid = f"moisture-{zone}"
    if value < MOISTURE_THRESHOLD:
        _upsert_alert(aid, "medium", "moisture", [zone], f"Drought stress {value}%", "Schedule drip irrigation")
    else:
        _clear_alert(aid)


def _check_nitrogen(zone, value):
    aid = f"nitrogen-{zone}"
    if value < NITROGEN_THRESHOLD:
        _upsert_alert(aid, "medium", "nutrient", [zone], f"Nitrogen {value} ppm (low)", "Schedule foliar N spray")
    else:
        _clear_alert(aid)


def _check_pest(zone, value):
    aid = f"pest-{zone}"
    if value > PEST_THRESHOLD:
        _upsert_alert(aid, "high", "pest", [zone], f"Pest trap {value} catches/24h", "Dispatch UAV-1 spray mode")
    else:
        _clear_alert(aid)


def start_mqtt():
    client = mqtt.Client()  # paho-mqtt 1.x API

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
        print(f"MQTT client started — connecting to {host}:{port}")
    except Exception as e:
        print(f"MQTT could not connect: {e} — continuing without MQTT")

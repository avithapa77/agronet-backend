"""
main.py — AgroNet Autonomous v6

Starts:
  1. MQTT listener (IoT sensors → farm_state)
  2. outdoor_loop() — outdoor automation, every 60 s
  3. indoor_loop()  — indoor climate control, every 15 s
  4. telemetry_loop() — WebSocket broadcast, every 3 s
  5. FastAPI HTTP + WebSocket server

Endpoints:
  /health                   — system status
  /ws                       — WebSocket (full state on connect, live updates)
  /api/telemetry/*          — read-only snapshots
  /api/dispatch/*           — send drones/robots on missions
  /api/indoor/*             — control actuators, read rooms
  /api/automation/*         — CRUD rules, toggle engine, manual fire
  /api/irrigation/*         — outdoor irrigation
  /api/ai/*                 — Claude-powered chat, crop plan, rule suggestions
  /api/tasks/*              — approve/defer/dismiss tasks
  /api/harvest/*            — log and schedule harvests
  /api/equipment/*          — service bookings
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from state.farm_state import farm_state
from services.websocket_manager import manager
from services.mqtt_client import start_mqtt, set_event_loop
from services.autonomous_engine import outdoor_loop, indoor_loop

from routes.telemetry   import router as telemetry_router
from routes.dispatch    import router as dispatch_router
from routes.indoor      import router as indoor_router
from routes.irrigation  import router as irrigation_router
from routes.automation  import router as automation_router
from routes.ai          import router as ai_router
from routes.tasks       import router as tasks_router
from routes.harvest     import router as harvest_router
from routes.equipment   import router as equipment_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()
    set_event_loop(loop)
    start_mqtt()
    asyncio.create_task(outdoor_loop())
    asyncio.create_task(indoor_loop())
    asyncio.create_task(telemetry_loop())
    yield


app = FastAPI(
    title="AgroNet Autonomous API v6",
    description="Fully autonomous outdoor + indoor smart farm",
    version="6.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "*")],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(telemetry_router)
app.include_router(dispatch_router)
app.include_router(indoor_router)
app.include_router(irrigation_router)
app.include_router(automation_router)
app.include_router(ai_router)
app.include_router(tasks_router)
app.include_router(harvest_router)
app.include_router(equipment_router)


@app.get("/health")
def health():
    outdoor = farm_state["outdoor"]
    return {
        "status":  "ok",
        "version": "6.0.0",
        "farm":    farm_state["config"]["farm_name"],
        "mode":    farm_state["config"]["mode"],
        "automation": farm_state["automation"]["enabled"],
        "outdoor": {
            "drones": {k: v["status"] for k, v in outdoor["drones"].items()},
            "robots": {k: v["status"] for k, v in outdoor["robots"].items()},
            "alerts": len(farm_state["alerts"]),
        },
        "indoor": {
            "rooms":  {k: v["status"] for k, v in farm_state["indoor"]["rooms"].items()},
            "robots": {k: v["status"] for k, v in farm_state["indoor"]["indoor_robots"].items()},
        },
        "instance": os.getenv("K_REVISION", "local"),
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        await ws.send_text(json.dumps({"type": "FULL_STATE", "payload": farm_state}))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


async def telemetry_loop():
    """Push compact live telemetry to all connected browsers every 3 s."""
    while True:
        await asyncio.sleep(3)
        if not manager.connections:
            continue

        # Simulate outdoor drone progress
        for drone in farm_state["outdoor"]["drones"].values():
            if drone["status"] in ("flying","spraying"):
                drone["battery_pct"] = max(0.0, drone["battery_pct"] - 0.05)
                drone["mission_progress_pct"] = min(100.0, drone["mission_progress_pct"] + 0.2)
            elif drone["status"] == "charging":
                drone["battery_pct"] = min(100.0, drone["battery_pct"] + 0.5)

        # Simulate outdoor robot progress
        for robot in farm_state["outdoor"]["robots"].values():
            if robot["status"] == "active" and robot["mission_progress_pct"] < 100:
                robot["mission_progress_pct"] = min(100.0, robot["mission_progress_pct"] + 0.1)
                robot["mission_eta_min"] = max(0, robot["mission_eta_min"] - 1)

        await manager.broadcast({
            "type": "TELEMETRY",
            "payload": {
                "outdoor": {
                    "drones": {
                        did: {k: d[k] for k in ("battery_pct","status","current_mode",
                                                 "current_task","mission_progress_pct",
                                                 "mission_eta_min","gps","tank_pct")}
                        for did, d in farm_state["outdoor"]["drones"].items()
                    },
                    "robots": {
                        rid: {k: r[k] for k in ("battery_pct","status","current_head",
                                                 "current_task","mission_progress_pct",
                                                 "mission_eta_min")}
                        for rid, r in farm_state["outdoor"]["robots"].items()
                    },
                    "environment": farm_state["outdoor"]["environment"],
                },
                "indoor": {
                    "rooms": {
                        rid: room["readings"]
                        for rid, room in farm_state["indoor"]["rooms"].items()
                    },
                    "actuators": farm_state["indoor"]["actuators"],
                },
                "alerts":           len(farm_state["alerts"]),
                "automation_on":    farm_state["automation"]["enabled"],
                "last_auto_action": (farm_state["automation"]["action_log"][-1]
                                     if farm_state["automation"]["action_log"] else None),
            }
        })

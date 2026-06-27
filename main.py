"""
main.py — AgroNet v5

What's new vs v4:
- 3 drones (UAV-1, UAV-2, UAV-3) + 3 robots (MPAR-1, MPAR-2, MPAR-3)
- Automation engine (services/automation_engine.py) runs as a background task
- /api/automation routes for rule CRUD + manual fire
- /api/dispatch accepts drone_id / robot_id so you can target any unit
- Telemetry loop broadcasts status for ALL 6 machines every 3 s
- Legacy farm_state["drone"] / farm_state["robot"] still work (proxy to UAV-1 / MPAR-1)
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
from services.automation_engine import automation_loop

from routes.telemetry  import router as telemetry_router
from routes.dispatch   import router as dispatch_router
from routes.irrigation import router as irrigation_router
from routes.harvest    import router as harvest_router
from routes.equipment  import router as equipment_router
from routes.ai         import router as ai_router
from routes.tasks      import router as tasks_router
from routes.automation import router as automation_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()
    set_event_loop(loop)
    start_mqtt()
    asyncio.create_task(telemetry_loop())
    asyncio.create_task(automation_loop())   # NEW: automation engine
    yield


app = FastAPI(
    title="AgroNet API v5",
    description="3 drones · 3 robots · full automation engine",
    version="5.0.0",
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
app.include_router(irrigation_router)
app.include_router(harvest_router)
app.include_router(equipment_router)
app.include_router(ai_router)
app.include_router(tasks_router)
app.include_router(automation_router)   # NEW


@app.get("/health")
def health():
    drones = farm_state["drones"]
    robots = farm_state["robots"]
    return {
        "status":   "ok",
        "farm":     os.getenv("FARM_NAME", "Kisan — AgroNet v5"),
        "drones":   {k: v["status"] for k, v in drones.items()},
        "robots":   {k: v["status"] for k, v in robots.items()},
        "automation": farm_state["automation"]["enabled"],
        "instance": os.getenv("K_REVISION", "local"),
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        # Send full state on connect
        await ws.send_text(json.dumps({"type": "FULL_STATE", "payload": farm_state}))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


async def telemetry_loop():
    """Broadcast live telemetry for all 6 machines every 3 seconds."""
    while True:
        await asyncio.sleep(3)
        if not manager.connections:
            continue

        # Simulate drone progress (real telemetry comes via MQTT in production)
        for drone in farm_state["drones"].values():
            if drone["status"] in ("flying", "spraying"):
                drone["battery_pct"] = max(0.0, drone["battery_pct"] - 0.05)
                if drone["mission_progress_pct"] < 100:
                    drone["mission_progress_pct"] = min(100.0, drone["mission_progress_pct"] + 0.2)
            elif drone["status"] == "charging":
                drone["battery_pct"] = min(100.0, drone["battery_pct"] + 0.5)

        # Simulate robot progress
        for robot in farm_state["robots"].values():
            if robot["status"] == "active":
                if robot["mission_progress_pct"] < 100:
                    robot["mission_progress_pct"] = min(100.0, robot["mission_progress_pct"] + 0.1)
                    if robot["mission_eta_min"] > 0:
                        robot["mission_eta_min"] = max(0, robot["mission_eta_min"] - 1)

        # Build compact telemetry payload (all 3 drones + all 3 robots)
        await manager.broadcast({
            "type": "TELEMETRY",
            "payload": {
                "drones": {
                    did: {
                        "battery_pct":          d["battery_pct"],
                        "status":               d["status"],
                        "current_mode":         d["current_mode"],
                        "current_task":         d["current_task"],
                        "mission_progress_pct": d["mission_progress_pct"],
                        "mission_eta_min":      d["mission_eta_min"],
                        "gps":                  d["gps"],
                        "tank_pct":             d["tank_pct"],
                    }
                    for did, d in farm_state["drones"].items()
                },
                "robots": {
                    rid: {
                        "battery_pct":          r["battery_pct"],
                        "status":               r["status"],
                        "current_head":         r["current_head"],
                        "current_task":         r["current_task"],
                        "mission_progress_pct": r["mission_progress_pct"],
                        "mission_eta_min":      r["mission_eta_min"],
                    }
                    for rid, r in farm_state["robots"].items()
                },
                "environment":  farm_state["environment"],
                "alert_count":  len(farm_state["alerts"]),
                "automation_enabled": farm_state["automation"]["enabled"],
            }
        })

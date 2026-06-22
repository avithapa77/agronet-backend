"""
main.py — AgroNet backend, Cloud Run ready

Changes vs local version:
- Reads PORT from environment (Cloud Run injects this as 8080)
- FRONTEND_URL defaults to * so the deployed frontend can connect
- WebSocket path is /ws — Cloud Run forwards it transparently
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

from routes.telemetry  import router as telemetry_router
from routes.dispatch   import router as dispatch_router
from routes.irrigation import router as irrigation_router
from routes.harvest    import router as harvest_router
from routes.equipment  import router as equipment_router
from routes.ai         import router as ai_router
from routes.tasks      import router as tasks_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()
    set_event_loop(loop)
    start_mqtt()
    asyncio.create_task(telemetry_loop())
    yield


app = FastAPI(
    title="AgroNet API",
    description="AgroNet v4 backend — Cloud Run deployment",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow the frontend origin (set FRONTEND_URL in Cloud Run env vars)
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


@app.get("/health")
def health():
    return {
        "status": "ok",
        "farm": os.getenv("FARM_NAME", "AgroNet"),
        "drone": farm_state["drone"]["status"],
        "instance": os.getenv("K_REVISION", "local"),  # K_REVISION is set by Cloud Run
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
    while True:
        await asyncio.sleep(3)
        if not manager.connections:
            continue

        # Simulate battery drain (remove once real UAV-1 is connected via MQTT)
        if farm_state["drone"]["status"] in ("flying", "spraying"):
            farm_state["drone"]["battery_pct"] = max(0.0, farm_state["drone"]["battery_pct"] - 0.05)
        if farm_state["drone"]["mission_progress_pct"] < 100:
            farm_state["drone"]["mission_progress_pct"] = min(100.0, farm_state["drone"]["mission_progress_pct"] + 0.2)

        await manager.broadcast({
            "type": "TELEMETRY",
            "payload": {
                "drone": {
                    "battery_pct":          farm_state["drone"]["battery_pct"],
                    "status":               farm_state["drone"]["status"],
                    "current_mode":         farm_state["drone"]["current_mode"],
                    "current_task":         farm_state["drone"]["current_task"],
                    "mission_progress_pct": farm_state["drone"]["mission_progress_pct"],
                    "mission_eta_min":      farm_state["drone"]["mission_eta_min"],
                    "gps":                  farm_state["drone"]["gps"],
                    "tank_pct":             farm_state["drone"]["tank_pct"],
                },
                "robot": {
                    "battery_pct":          farm_state["robot"]["battery_pct"],
                    "status":               farm_state["robot"]["status"],
                    "current_head":         farm_state["robot"]["current_head"],
                    "current_task":         farm_state["robot"]["current_task"],
                    "mission_progress_pct": farm_state["robot"]["mission_progress_pct"],
                    "mission_eta_min":      farm_state["robot"]["mission_eta_min"],
                },
                "environment":  farm_state["environment"],
                "alert_count":  len(farm_state["alerts"]),
            }
        })

"""
main.py

Entry point for the AgroNet backend.
Run with:  uvicorn main:app --reload --port 8000
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


# ── Startup / shutdown ──────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Give the MQTT service a reference to the running event loop
    # so its thread-based callbacks can schedule coroutines safely
    loop = asyncio.get_event_loop()
    set_event_loop(loop)
    start_mqtt()

    # Push telemetry to all browsers every 3 seconds
    asyncio.create_task(telemetry_loop())

    yield  # Server is running

    # Cleanup on shutdown (nothing needed for in-memory state)


# ── App ─────────────────────────────────────────────────────────

app = FastAPI(
    title="AgroNet API",
    description="Backend for the AgroNet v4 autonomous farm management platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "*")],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount routers ───────────────────────────────────────────────

app.include_router(telemetry_router)
app.include_router(dispatch_router)
app.include_router(irrigation_router)
app.include_router(harvest_router)
app.include_router(equipment_router)
app.include_router(ai_router)
app.include_router(tasks_router)


# ── Health check ─────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "farm": os.getenv("FARM_NAME", "AgroNet"), "drone": farm_state["drone"]["status"]}


# ── WebSocket endpoint ───────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        # Send the full farm state immediately so the UI populates on connect
        await ws.send_text(json.dumps({"type": "FULL_STATE", "payload": farm_state}))
        # Keep the connection alive by reading (the browser rarely sends anything)
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ── Background telemetry loop ────────────────────────────────────

async def telemetry_loop():
    """Push a TELEMETRY frame to all browser tabs every 3 seconds."""
    while True:
        await asyncio.sleep(3)
        if not manager.connections:
            continue

        # Simulate slow battery drain while flying (remove once real drone is connected)
        if farm_state["drone"]["status"] in ("flying", "spraying"):
            farm_state["drone"]["battery_pct"] = max(0.0, farm_state["drone"]["battery_pct"] - 0.05)

        # Simulate mission progress ticking (remove once real drone is connected)
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

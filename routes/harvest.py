"""
routes/harvest.py

GET  /api/harvest          — full log
GET  /api/harvest/today    — today's entries + total kg
POST /api/harvest          — manually log an entry
POST /api/harvest/schedule — schedule a future harvest
"""

from datetime import date
from fastapi import APIRouter
from pydantic import BaseModel

from state.farm_state import farm_state
from services.websocket_manager import manager

router = APIRouter(prefix="/api/harvest", tags=["harvest"])


class HarvestEntry(BaseModel):
    crop: str
    kg: float


class HarvestSchedule(BaseModel):
    crop: str
    scheduled_date: str   # YYYY-MM-DD


@router.get("/")
def get_harvest_log():
    return farm_state["harvest_log"]


@router.get("/today")
def get_today():
    today_str = date.today().isoformat()
    today_log = next((d for d in farm_state["harvest_log"] if d["date"] == today_str), None)
    entries   = today_log["entries"] if today_log else []
    total_kg  = sum(e["kg"] for e in entries)
    return {"date": today_str, "entries": entries, "total_kg": total_kg}


@router.post("/", status_code=201)
async def log_harvest(entry: HarvestEntry):
    today_str = date.today().isoformat()
    day_log   = next((d for d in farm_state["harvest_log"] if d["date"] == today_str), None)
    if not day_log:
        day_log = {"date": today_str, "entries": []}
        farm_state["harvest_log"].append(day_log)

    record = {"crop": entry.crop, "kg": entry.kg}
    day_log["entries"].append(record)

    await manager.broadcast({"type": "HARVEST_LOGGED", "payload": {"date": today_str, "entry": record}})
    return {"message": "Harvest logged", "date": today_str, "entry": record}


@router.post("/schedule", status_code=201)
def schedule_harvest(body: HarvestSchedule):
    # In production: write to harvest_schedule table in DB
    print(f"[HARVEST] {body.crop} scheduled for {body.scheduled_date}")
    return {"message": f"{body.crop} harvest scheduled for {body.scheduled_date}"}

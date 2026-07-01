"""
routes/equipment.py

GET  /api/equipment         — service records for UAV-1 and MPAR-1
POST /api/equipment/service — book a service appointment
"""

from fastapi import APIRouter
from pydantic import BaseModel

from state.farm_state import farm_state
from services.websocket_manager import manager

router = APIRouter(prefix="/api/equipment", tags=["equipment"])


class ServiceBooking(BaseModel):
    unit: str            # UAV-1 | MPAR-1
    preferred_date: str  # YYYY-MM-DD


@router.get("/")
def get_equipment():
    return {
        "drone": {
            "id":               farm_state["outdoor"]["drones"]["UAV-1"]["id"],
            "flight_hours":     farm_state["outdoor"]["drones"]["UAV-1"]["flight_hours_total"],
            "battery_pct":      farm_state["outdoor"]["drones"]["UAV-1"]["battery_pct"],
            "last_service":     farm_state["outdoor"]["drones"]["UAV-1"]["last_service"],
            "next_service":     farm_state["outdoor"]["drones"]["UAV-1"]["next_service"],
            "payload_modules":  ["Survey head (multispectral + thermal)", "Spray tank 12 L", "Pollination head"],
        },
        "robot": {
            "id":        farm_state["outdoor"]["robots"]["MPAR-1"]["id"],
            "op_hours":  farm_state["outdoor"]["robots"]["MPAR-1"]["op_hours_total"],
            "battery_pct": farm_state["outdoor"]["robots"]["MPAR-1"]["battery_pct"],
            "tool_heads": ["Harvester head", "Weeder head", "Seeder head"],
        },
    }


@router.post("/service", status_code=201)
async def book_service(body: ServiceBooking):
    if body.unit == "UAV-1":
        farm_state["outdoor"]["drones"]["UAV-1"]["service_booking"] = {"date": body.preferred_date, "status": "booked"}

    print(f"[EQUIPMENT] Service booked for {body.unit} on {body.preferred_date}")
    await manager.broadcast({"type": "SERVICE_BOOKED", "payload": {"unit": body.unit, "date": body.preferred_date}})
    return {"message": f"Service booked for {body.unit} on {body.preferred_date}"}

"""
routes/telemetry.py

Read-only GET endpoints. The frontend calls these on page load to
populate the UI before the WebSocket takes over for live updates.
"""

from datetime import date
from fastapi import APIRouter
from state.farm_state import farm_state

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


@router.get("/dashboard")
def get_dashboard():
    """Aggregated summary for the top metric cards on the Dashboard page."""
    today_str = date.today().isoformat()
    today_log = next((d for d in farm_state["harvest_log"] if d["date"] == today_str), None)
    total_kg  = sum(e["kg"] for e in today_log["entries"]) if today_log else 0

    return {
        "active_alerts":    len(farm_state["alerts"]),
        "drone_status":     farm_state["drone"]["status"],
        "drone_battery_pct": farm_state["drone"]["battery_pct"],
        "robot_status":     farm_state["robot"]["status"],
        "robot_head":       farm_state["robot"]["current_head"],
        "harvest_kg_today": total_kg,
        "weather_today":    farm_state["weather"][0],
        "irrigation_alerts": sum(1 for s in farm_state["irrigation"]["schedules"] if s.get("alert")),
    }


@router.get("/zones")
def get_zones():
    """All 24 zone objects — used by the Field Map grid."""
    return farm_state["zones"]


@router.get("/zones/{zone_id}")
def get_zone(zone_id: str):
    """Single zone detail — shown in the tooltip on zone hover."""
    zone = farm_state["zones"].get(zone_id.upper())
    if not zone:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Zone not found")
    return zone


@router.get("/sensors")
def get_sensors():
    """All sensor readings — used by the Sensors page."""
    return {
        "actionable":  farm_state["sensors"],
        "environment": farm_state["environment"],
    }


@router.get("/drone")
def get_drone():
    """UAV-1 full state — used by the Drone page."""
    return farm_state["drone"]


@router.get("/robot")
def get_robot():
    """MPAR-1 full state — used by the Robot page."""
    return farm_state["robot"]


@router.get("/weather")
def get_weather():
    """7-day forecast strip."""
    return farm_state["weather"]


@router.get("/alerts")
def get_alerts():
    """All active alerts."""
    return farm_state["alerts"]


@router.get("/spray-log")
def get_spray_log():
    """Spray history — used by the Spray & Seed page history table."""
    return farm_state["spray_log"]

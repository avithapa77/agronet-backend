"""
routes/telemetry.py — v6

Fixed: all lookups now use the v6 nested state structure:
  farm_state["outdoor"]["zones"]     (was farm_state["zones"])
  farm_state["outdoor"]["sensors"]   (was farm_state["sensors"])
  farm_state["outdoor"]["environment"] (was farm_state["environment"])
  farm_state["outdoor"]["weather_forecast"] (was farm_state["weather"])
  farm_state["outdoor"]["drones"]    (was farm_state["drone"])
  farm_state["outdoor"]["robots"]    (was farm_state["robot"])
  farm_state["outdoor"]["harvest_log"] (was farm_state["harvest_log"])
  farm_state["outdoor"]["spray_log"] (was farm_state["spray_log"])

Read-only GET endpoints. Called by the frontend on page load to populate
the UI before the WebSocket takes over for live updates.
"""

from datetime import date, datetime
from fastapi import APIRouter, HTTPException
from state.farm_state import farm_state

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


@router.get("/dashboard")
def get_dashboard():
    """Aggregated summary for the top metric cards on the Dashboard page."""
    outdoor = farm_state["outdoor"]
    indoor  = farm_state["indoor"]
    auto    = farm_state["automation"]

    today_str = date.today().isoformat()
    today_log = next((d for d in outdoor["harvest_log"] if d["date"] == today_str), None)
    total_kg  = sum(e["kg"] for e in today_log["entries"]) if today_log else 0

    # Fleet summary
    drones_flying  = sum(1 for d in outdoor["drones"].values() if d["status"] in ("flying","spraying"))
    robots_active  = sum(1 for r in outdoor["robots"].values() if r["status"] == "active")
    indoor_ok      = sum(1 for r in indoor["rooms"].values() if r["status"] == "ok")

    return {
        # Outdoor
        "active_alerts":      len(farm_state["alerts"]),
        "drones_flying":      drones_flying,
        "robots_active":      robots_active,
        "harvest_kg_today":   total_kg,
        "weather_today":      outdoor["weather_forecast"][0] if outdoor["weather_forecast"] else {},
        # Each drone summary
        "drones": {
            did: {"status": d["status"], "battery_pct": d["battery_pct"], "current_task": d["current_task"]}
            for did, d in outdoor["drones"].items()
        },
        # Each robot summary
        "robots": {
            rid: {"status": r["status"], "battery_pct": r["battery_pct"], "current_task": r["current_task"]}
            for rid, r in outdoor["robots"].items()
        },
        # Indoor
        "indoor_rooms_ok":    indoor_ok,
        "indoor_rooms_total": len(indoor["rooms"]),
        # Automation
        "automation_enabled": auto["enabled"],
        "automation_rules":   len([r for r in auto["rules"] if r["enabled"]]),
        "last_auto_action":   auto["action_log"][-1] if auto["action_log"] else None,
    }


@router.get("/zones")
def get_zones():
    """All 24 outdoor zone objects — used by the Field Map grid."""
    return farm_state["outdoor"]["zones"]


@router.get("/zones/{zone_id}")
def get_zone(zone_id: str):
    """Single zone detail — shown in tooltip on hover."""
    zone = farm_state["outdoor"]["zones"].get(zone_id.upper())
    if not zone:
        raise HTTPException(404, "Zone not found")
    return zone


@router.get("/sensors")
def get_sensors():
    """All outdoor sensor readings — used by the Sensors page."""
    return {
        "actionable":  farm_state["outdoor"]["sensors"],
        "environment": farm_state["outdoor"]["environment"],
    }


@router.get("/drones")
def get_drones():
    """All 3 drones — full state."""
    return farm_state["outdoor"]["drones"]


@router.get("/drones/{drone_id}")
def get_drone(drone_id: str):
    drone = farm_state["outdoor"]["drones"].get(drone_id.upper())
    if not drone:
        raise HTTPException(404, f"Drone {drone_id} not found")
    return drone


@router.get("/robots")
def get_robots():
    """All 3 ground robots — full state."""
    return farm_state["outdoor"]["robots"]


@router.get("/robots/{robot_id}")
def get_robot(robot_id: str):
    robot = farm_state["outdoor"]["robots"].get(robot_id.upper())
    if not robot:
        raise HTTPException(404, f"Robot {robot_id} not found")
    return robot


# Legacy single-unit endpoints (kept for backward compat with old frontend)
@router.get("/drone")
def get_drone_legacy():
    """UAV-1 — legacy single-drone endpoint."""
    return farm_state["outdoor"]["drones"]["UAV-1"]


@router.get("/robot")
def get_robot_legacy():
    """MPAR-1 — legacy single-robot endpoint."""
    return farm_state["outdoor"]["robots"]["MPAR-1"]


@router.get("/weather")
def get_weather():
    """7-day forecast strip."""
    return farm_state["outdoor"]["weather_forecast"]


@router.get("/alerts")
def get_alerts():
    """All active alerts (outdoor + indoor merged)."""
    outdoor_alerts = farm_state["alerts"]
    indoor_alerts  = []
    for rid, room in farm_state["indoor"]["rooms"].items():
        for a in room.get("alerts", []):
            indoor_alerts.append({"room": rid, "env": "indoor", **a})
    return outdoor_alerts + indoor_alerts


@router.get("/spray-log")
def get_spray_log():
    """Spray history — used by the Spray & Seed page."""
    return farm_state["outdoor"]["spray_log"]


@router.get("/harvest-log")
def get_harvest_log():
    """Harvest history."""
    return farm_state["outdoor"]["harvest_log"]


@router.get("/fleet")
def get_fleet():
    """Complete fleet snapshot — outdoor + indoor robots."""
    return {
        "outdoor": {
            "drones": farm_state["outdoor"]["drones"],
            "robots": farm_state["outdoor"]["robots"],
        },
        "indoor": farm_state["indoor"]["indoor_robots"],
    }


@router.get("/automation")
def get_automation_snapshot():
    """Quick snapshot of automation status for the dashboard banner."""
    auto = farm_state["automation"]
    return {
        "enabled":      auto["enabled"],
        "mode":         auto["mode"],
        "total_rules":  len(auto["rules"]),
        "active_rules": len([r for r in auto["rules"] if r["enabled"]]),
        "fired_today":  len([
            e for e in auto["action_log"]
            if e.get("time", "")  # all log entries are from today in-memory
        ]),
        "last_action":  auto["action_log"][-1] if auto["action_log"] else None,
    }

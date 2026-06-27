"""
routes/ai.py — v5

Updated to include all 3 drones + 3 robots + automation state in the farm context
so Claude gives advice that's aware of the full fleet.
"""

import os
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import anthropic

from state.farm_state import farm_state

router = APIRouter(prefix="/api/ai", tags=["ai"])


def get_client():
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")
    return anthropic.Anthropic(api_key=key)


def build_farm_context() -> str:
    e = farm_state["environment"]

    alert_lines = "\n".join(
        f"- {','.join(a['zones'])}: {a['message']} ({a['action']})"
        for a in farm_state["alerts"]
    ) or "- No active alerts"

    weather_line = " | ".join(
        f"{w['day']} {w['temp_c']}°C {w['rain_mm']}mm"
        for w in farm_state["weather"]
    )

    drone_lines = "\n".join(
        f"- {did} ({d['name']}): {d['status']}, {d['battery_pct']:.0f}% battery, "
        f"mode: {d['current_mode']}, task: {d['current_task']}"
        for did, d in farm_state["drones"].items()
    )

    robot_lines = "\n".join(
        f"- {rid} ({r['name']}): {r['status']}, {r['battery_pct']}% battery, "
        f"head: {r['current_head']}, task: {r['current_task']}"
        for rid, r in farm_state["robots"].items()
    )

    auto = farm_state["automation"]
    active_rules = [r["name"] for r in auto["rules"] if r["enabled"]]
    recent_auto  = auto["action_log"][-3:] if auto["action_log"] else []
    auto_log_str = "\n".join(f"  {e['time']} [{e['name']}]: {e['message']}" for e in recent_auto)

    return f"""You are AgroNet AI, an expert precision-farming advisor with live access to a smart farm.

FLEET STATUS:
Drones (3 total):
{drone_lines}

Robots (3 total):
{robot_lines}

ACTIVE ALERTS:
{alert_lines}

KEY ZONE SENSORS:
- Zone A4: nitrogen {farm_state['sensors']['nitrogen'].get('A4', '?')} ppm (threshold: 50 ppm)
- Zone C5: soil moisture {farm_state['sensors']['soil_moisture'].get('C5', '?')}% (threshold: 45%)
- Zone D6: empty, pH {farm_state['sensors']['ph'].get('D6', '?')}, 0.4 ha ready to plant
- Zone B3/B4: pest trap {farm_state['sensors']['pest_traps'].get('B3', '?')}/day (threshold: 30)

ENVIRONMENT:
Temperature: {e['air_temp_c']}°C, Humidity: {e['humidity_pct']}%, 
Wind: {e['wind_speed_kmh']} km/h {e['wind_dir_label']}, Rainfall today: {e['rainfall_mm_today']} mm

7-DAY WEATHER: {weather_line}

AUTOMATION ENGINE: {'ENABLED' if auto['enabled'] else 'DISABLED'}
Active rules: {', '.join(active_rules)}
Recent auto-actions:
{auto_log_str or '  None today'}

Field avg soil pH: {farm_state['sensors']['ph'].get('field_avg', '?')}

Respond with specific, actionable advice. Reference which drone/robot to use by ID.
Use metric units. Be concise."""


class ChatRequest(BaseModel):
    message: str


class CropPlanRequest(BaseModel):
    zone: str
    season: str
    constraints: Optional[str] = None


class AutomationSuggestRequest(BaseModel):
    goal: str   # e.g. "reduce water usage by 20%"


@router.post("/chat")
def ai_chat(body: ChatRequest):
    client = get_client()
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=build_farm_context(),
            messages=[{"role": "user", "content": body.message}],
        )
        return {"reply": response.content[0].text}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")


@router.post("/crop-plan")
def crop_plan(body: CropPlanRequest):
    client = get_client()
    zone_data = farm_state["zones"].get(body.zone.upper())
    if not zone_data:
        raise HTTPException(status_code=404, detail="Zone not found")

    ph    = farm_state["sensors"]["ph"].get(body.zone.upper(), farm_state["sensors"]["ph"].get("field_avg", "?"))
    moist = zone_data.get("moisture", "unknown")

    prompt = f"""Recommend 3 crops for this zone.

Zone: {body.zone}
Current: {zone_data['crop']}, health: {zone_data['health']}
Soil pH: {ph}, Moisture: {moist}%
Season: {body.season}
Constraints: {body.constraints or 'none'}

Return ONLY a JSON array:
[{{"crop": "", "yield_kg_ha": 0, "planting_window": "", "rationale": ""}}]"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw  = response.content[0].text.strip()
        recs = json.loads(raw)
        return {"zone": body.zone, "season": body.season, "recommendations": recs}
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="AI returned invalid JSON")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")


@router.post("/suggest-automation")
def suggest_automation(body: AutomationSuggestRequest):
    """Ask Claude to suggest automation rules in JSON format for a given goal."""
    client = get_client()
    prompt = f"""You are an automation rule designer for a precision farm with this equipment:
- 3 drones: UAV-1 (survey+spray+pollination), UAV-2 (heavy spray), UAV-3 (pollination)
- 3 robots: MPAR-1 (harvester), MPAR-2 (weeder+soil-probe), MPAR-3 (drip-irrigator+fertigation)
- Sensors: soil_moisture, nitrogen, phosphorus, potassium, ph, compaction, pest_traps
- Environment: air_temp_c, humidity_pct, wind_speed_kmh, rainfall_mm_today

Farmer's goal: {body.goal}

Design 2–3 automation rules as JSON. Return ONLY a JSON array:
[{{
  "name": "",
  "description": "",
  "trigger": {{"type": "sensor|weather|fleet|schedule|compound", "sensor": "", "operator": "<|>|==", "threshold": 0}},
  "action": {{"type": "dispatch_drone|dispatch_robot|cancel_spray_missions|return_to_dock", "drone": "UAV-1|UAV-2|UAV-3", "mode": "", "payload": ""}}
}}]"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw   = response.content[0].text.strip()
        rules = json.loads(raw)
        return {"goal": body.goal, "suggested_rules": rules}
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="AI returned invalid JSON")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")

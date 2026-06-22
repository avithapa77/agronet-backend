"""
routes/ai.py

The most important security improvement over the prototype.
In agronet-v4.html the Anthropic API key was called directly from
the browser — anyone who opened DevTools could steal it.

Here the key lives in .env on the server. The browser sends the
user's message to /api/ai/chat; we add the live farm context and
forward to Anthropic. The key never touches the browser.

POST /api/ai/chat       — AI Advisor conversation
POST /api/ai/crop-plan  — Crop Planner recommendations for a zone
"""

import os
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import anthropic

from state.farm_state import farm_state

router = APIRouter(prefix="/api/ai", tags=["ai"])
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


# ── Build live farm context from farmState ──────────────────────

def build_farm_context() -> str:
    d = farm_state["drone"]
    r = farm_state["robot"]
    e = farm_state["environment"]

    alert_lines = "\n".join(
        f"- {','.join(a['zones'])}: {a['message']} ({a['action']})"
        for a in farm_state["alerts"]
    ) or "- No active alerts"

    weather_line = " | ".join(
        f"{w['day']} {w['temp_c']}°C {w['rain_mm']}mm"
        for w in farm_state["weather"]
    )

    return f"""You are AgroNet AI, an expert farming advisor with access to live farm data.

LIVE FARM STATE:
Alerts:
{alert_lines}

Key zones:
- Zone A4: nitrogen {farm_state['sensors']['nitrogen'].get('A4', '?')} ppm (alert threshold: 50 ppm)
- Zone C5: soil moisture {farm_state['sensors']['soil_moisture'].get('C5', '?')}% (alert threshold: 45%)
- Zone D6: empty, pH {farm_state['sensors']['ph'].get('D6', '?')}, 0.4 ha ready to plant

UAV-1: {d['status']}, {d['battery_pct']:.0f}% battery, mode: {d['current_mode']}, task: {d['current_task']}
MPAR-1: {r['status']}, {r['battery_pct']}% battery, head: {r['current_head']}, task: {r['current_task']}

Weather: {e['air_temp_c']}°C, humidity {e['humidity_pct']}%, wind {e['wind_speed_kmh']} km/h {e['wind_dir_label']}
7-day: {weather_line}

Soil pH field avg: {farm_state['sensors']['ph'].get('field_avg', '?')}
CO₂: {e['co2_ppm']} ppm

Give specific, actionable advice using this data. Be concise — farmers are busy. Use metric units."""


# ── Request models ──────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str


class CropPlanRequest(BaseModel):
    zone: str
    season: str
    constraints: Optional[str] = None


# ── POST /api/ai/chat ───────────────────────────────────────────

@router.post("/chat")
def ai_chat(body: ChatRequest):
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=build_farm_context(),
            messages=[{"role": "user", "content": body.message}],
        )
        return {"reply": response.content[0].text}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")


# ── POST /api/ai/crop-plan ──────────────────────────────────────

@router.post("/crop-plan")
def crop_plan(body: CropPlanRequest):
    zone_data = farm_state["zones"].get(body.zone.upper())
    if not zone_data:
        raise HTTPException(status_code=404, detail="Zone not found")

    ph    = farm_state["sensors"]["ph"].get(body.zone.upper(), farm_state["sensors"]["ph"].get("field_avg", "?"))
    moist = zone_data.get("moisture", "unknown")

    prompt = f"""You are an expert agronomist. Recommend 3 crops for this zone.

Zone: {body.zone}
Current state: {zone_data['crop']}, health: {zone_data['health']}
Soil pH: {ph}
Soil moisture: {moist}%
Area: 0.4 ha
Season: {body.season}
Constraints: {body.constraints or 'none'}

For each crop return:
- Crop name
- Expected yield (kg/ha)
- Planting window
- 2-sentence agronomic rationale

Return ONLY a JSON array, no other text:
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
        raise HTTPException(status_code=502, detail="AI returned invalid JSON for crop plan")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")

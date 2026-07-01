"""
routes/ai.py — v6

Claude has full context of both outdoor field and indoor rooms.
Three endpoints:
  POST /api/ai/chat              — free-form farming advice
  POST /api/ai/crop-plan         — zone/room crop recommendations
  POST /api/ai/suggest-automation — generate automation rules from a plain-English goal
"""

import os, json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import anthropic

from state.farm_state import farm_state

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _client():
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(500, "ANTHROPIC_API_KEY not configured")
    return anthropic.Anthropic(api_key=key)


def build_context() -> str:
    out  = farm_state["outdoor"]
    ind  = farm_state["indoor"]
    auto = farm_state["automation"]
    e    = out["environment"]

    drone_lines = "\n".join(
        f"  {did} ({d['name']}): {d['status']}, {d['battery_pct']:.0f}% bat, {d['current_task']}"
        for did, d in out["drones"].items()
    )
    robot_lines = "\n".join(
        f"  {rid} ({r['name']}): {r['status']}, head={r['current_head']}, {r['current_task']}"
        for rid, r in out["robots"].items()
    )
    room_lines = "\n".join(
        f"  {rid} ({r['name']}): temp={r['readings']['temp_c']}°C "
        f"RH={r['readings']['humidity_pct']}% CO₂={r['readings']['co2_ppm']}ppm "
        f"pH={r['readings']['ph']} EC={r['readings']['ec_ms']}ms/cm VPD={r['readings']['vpd_kpa']}kPa"
        for rid, r in ind["rooms"].items()
    )
    alert_lines = "\n".join(
        f"  [{a['severity'].upper()}] {','.join(a['zones'])}: {a['message']}"
        for a in farm_state["alerts"]
    ) or "  None"
    rule_names = ", ".join(r["name"] for r in auto["rules"] if r["enabled"])
    recent_log = "\n".join(
        f"  {e['time']} [{e['env']}] {e['name']}: {e['message']}"
        for e in auto["action_log"][-5:]
    ) or "  None"

    return f"""You are AgroNet AI — expert advisor for an autonomous farm with OUTDOOR fields and INDOOR greenhouses/vertical farm.

OUTDOOR FLEET:
Drones:
{drone_lines}
Ground robots:
{robot_lines}

OUTDOOR SENSORS (critical zones):
- C5 soil moisture: {out['sensors']['soil_moisture'].get('C5','?')}% (alert <45%)
- A4 nitrogen: {out['sensors']['nitrogen'].get('A4','?')} ppm (alert <50 ppm)
- B3/B4 pest traps: {out['sensors']['pest_traps'].get('B3','?')}/day (alert >30)
- B3/B4 leaf wetness: {out['sensors']['leaf_wetness'].get('B3','?')} (alert >0.8)

OUTDOOR ENVIRONMENT:
Temp {e['air_temp_c']}°C | Humidity {e['humidity_pct']}% | Wind {e['wind_speed_kmh']} km/h {e['wind_dir_label']}
Rain today {e['rainfall_mm_today']}mm | UV {e.get('uv_index','?')} | Soil temp {e['soil_temp_c']}°C

INDOOR ROOMS:
{room_lines}

ACTIVE ALERTS:
{alert_lines}

AUTOMATION ENGINE: {'ON' if auto['enabled'] else 'OFF'} | Mode: {auto['mode']}
Active rules: {rule_names}
Recent actions:
{recent_log}

You can advise on:
- Which drones/robots to dispatch and when
- Indoor climate adjustments (HVAC, CO₂, LED, nutrients, pH, EC, VPD)
- Crop planning for any zone or room
- New automation rules (give as JSON)
- Pest/disease diagnosis and treatment
- Harvest timing and yield optimization

Be specific. Reference equipment by ID. Use metric units."""


class ChatRequest(BaseModel):
    message: str

class CropPlanRequest(BaseModel):
    location: str        # zone ID like "A1" or room ID like "GH-1"
    season: str
    constraints: Optional[str] = None

class AutoSuggestRequest(BaseModel):
    goal: str


@router.post("/chat")
def ai_chat(body: ChatRequest):
    client = _client()
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=build_context(),
            messages=[{"role":"user","content":body.message}],
        )
        return {"reply": resp.content[0].text}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"AI error: {e}")


@router.post("/crop-plan")
def crop_plan(body: CropPlanRequest):
    client = _client()
    loc = body.location.upper()
    # Determine if outdoor zone or indoor room
    if loc in farm_state["outdoor"]["zones"]:
        zone = farm_state["outdoor"]["zones"][loc]
        context = f"Outdoor zone {loc}: crop={zone['crop']}, health={zone['health']}, moisture={zone['moisture']}%, pH={farm_state['outdoor']['sensors']['ph'].get(loc, farm_state['outdoor']['sensors']['ph']['field_avg'])}"
    elif loc in farm_state["indoor"]["rooms"]:
        room = farm_state["indoor"]["rooms"][loc]
        context = f"Indoor room {loc} ({room['type']}): current crop={room['crop']}, stage={room['stage']}, area={room.get('area_m2','?')}m²"
    else:
        raise HTTPException(404, f"Location {loc} not found")

    prompt = f"""{context}
Season: {body.season}
Constraints: {body.constraints or 'none'}

Recommend 3 crops. Return ONLY a JSON array:
[{{"crop":"","yield_kg_ha":0,"planting_window":"","rationale":""}}]"""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=1000,
            messages=[{"role":"user","content":prompt}],
        )
        return {"location": loc, "recommendations": json.loads(resp.content[0].text.strip())}
    except json.JSONDecodeError:
        raise HTTPException(502, "AI returned invalid JSON")
    except Exception as e:
        raise HTTPException(502, f"AI error: {e}")


@router.post("/suggest-automation")
def suggest_automation(body: AutoSuggestRequest):
    client = _client()
    prompt = f"""Design 2-3 automation rules for this goal: "{body.goal}"

Farm equipment:
OUTDOOR: UAV-1(survey/spray/pollination), UAV-2(spray), UAV-3(pollination), MPAR-1(harvester), MPAR-2(weeder/soil-probe), MPAR-3(drip/fertigation)
INDOOR: RAIL-1(harvest/transplant VF-1), SPRAY-BOT-1(foliar/prune GH-1), DOSER-1(nutrients/pH/EC all rooms)
Outdoor sensors: soil_moisture, nitrogen, pest_traps, leaf_wetness, ph, compaction
Indoor sensors (per room): temp_c, humidity_pct, co2_ppm, vpd_kpa, ph, ec_ms
Trigger types: sensor, weather, fleet, schedule, compound, indoor_sensor, indoor_multi
Action types: dispatch_drone, dispatch_robot, indoor_actuator, indoor_robot, night_mode, lights_on, vpd_correction

Return ONLY a JSON array of rules. Each rule needs: name, description, env (outdoor/indoor), trigger(dict), action(dict)."""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=1500,
            messages=[{"role":"user","content":prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:-1])
        return {"goal": body.goal, "suggested_rules": json.loads(raw)}
    except json.JSONDecodeError:
        raise HTTPException(502, "AI returned invalid JSON")
    except Exception as e:
        raise HTTPException(502, f"AI error: {e}")

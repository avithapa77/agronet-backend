"""
farm_state.py

The single in-memory store for all live farm data.
Every MQTT message updates this. Every API response reads from this.
Every WebSocket push serialises this.

In production you would swap this for a PostgreSQL / TimescaleDB database
and a Redis cache. For now everything lives in one Python dict so the
entire codebase has one place to read and write.
"""

from copy import deepcopy

farm_state = {

    # ── Zones ─────────────────────────────────────────────────────
    # 4 rows (A-D) × 6 columns (1-6) = 24 zones
    # health: healthy | stressed | alert | irrigating | empty
    "zones": {
        "A1": {"crop": "Tomatoes", "health": "healthy",  "ndvi": 0.80, "moisture": 64, "notes": "Harvest in ~18 days"},
        "A2": {"crop": "Tomatoes", "health": "healthy",  "ndvi": 0.78, "moisture": 62, "notes": ""},
        "A3": {"crop": "Tomatoes", "health": "healthy",  "ndvi": 0.81, "moisture": 65, "notes": ""},
        "A4": {"crop": "Peppers",  "health": "stressed", "ndvi": None, "moisture": 58, "notes": "N 42 ppm (low)"},
        "A5": {"crop": "Peppers",  "health": "healthy",  "ndvi": None, "moisture": 60, "notes": ""},
        "A6": {"crop": "Peppers",  "health": "healthy",  "ndvi": None, "moisture": 61, "notes": ""},
        "B1": {"crop": "Spinach",  "health": "healthy",  "ndvi": None, "moisture": 55, "notes": ""},
        "B2": {"crop": "Spinach",  "health": "healthy",  "ndvi": None, "moisture": 53, "notes": ""},
        "B3": {"crop": "Spinach",  "health": "alert",    "ndvi": None, "moisture": 50, "notes": "Fungal blight — UAV-1 treating"},
        "B4": {"crop": "Spinach",  "health": "alert",    "ndvi": None, "moisture": 51, "notes": "Fungal blight — UAV-1 treating"},
        "B5": {"crop": "Spinach",  "health": "healthy",  "ndvi": None, "moisture": 54, "notes": ""},
        "C1": {"crop": "Carrots",  "health": "healthy",  "ndvi": None, "moisture": 68, "notes": ""},
        "C2": {"crop": "Carrots",  "health": "healthy",  "ndvi": None, "moisture": 69, "notes": ""},
        "C3": {"crop": "Carrots",  "health": "healthy",  "ndvi": None, "moisture": 70, "notes": "Compaction 2.1 MPa — monitor"},
        "C4": {"crop": "Carrots",  "health": "healthy",  "ndvi": None, "moisture": 71, "notes": ""},
        "C5": {"crop": "Carrots",  "health": "stressed", "ndvi": None, "moisture": 39, "notes": "Drought stress — drip queued 14:30"},
        "C6": {"crop": "Carrots",  "health": "healthy",  "ndvi": None, "moisture": 66, "notes": ""},
        "D1": {"crop": "Empty",    "health": "empty",    "ndvi": None, "moisture": None, "notes": ""},
        "D2": {"crop": "Empty",    "health": "empty",    "ndvi": None, "moisture": None, "notes": ""},
        "D3": {"crop": "Beans",    "health": "healthy",  "ndvi": None, "moisture": 41, "notes": ""},
        "D4": {"crop": "Beans",    "health": "healthy",  "ndvi": None, "moisture": 42, "notes": ""},
        "D5": {"crop": "Beans",    "health": "healthy",  "ndvi": None, "moisture": 40, "notes": ""},
        "D6": {"crop": "Empty",    "health": "empty",    "ndvi": None, "moisture": None, "notes": "pH 5.8 — lime needed; 0.4 ha ready"},
    },

    # ── Soil sensors (actionable — trigger alerts) ─────────────────
    "sensors": {
        "soil_moisture": {"C5": 39},           # % — alert if < 45
        "nitrogen":      {"A4": 42},           # ppm — alert if < 50
        "phosphorus":    {"A4": 28},           # ppm
        "potassium":     {"A4": 180},          # ppm
        "ph":            {"D6": 5.8, "field_avg": 6.8},
        "compaction":    {"C3": 2.1},          # MPa — warn if > 2.0
        "pest_traps":    {"B3": 48, "B4": 48}, # catches/24h — alert if > 30
    },

    # ── Environmental sensors (read-only, inform spray timing) ─────
    "environment": {
        "air_temp_c":       27,
        "humidity_pct":     71,
        "co2_ppm":          412,
        "wind_speed_kmh":   8,
        "wind_dir_deg":     218,
        "wind_dir_label":   "SSW",
        "rainfall_mm_today": 0,
        "solar_rad_wm2":    680,
        "soil_temp_c":      19,
    },

    # ── UAV-1 ──────────────────────────────────────────────────────
    "drone": {
        "id":                    "UAV-1",
        "battery_pct":           78.0,
        "status":                "flying",     # flying | spraying | charging | idle | returning
        "current_mode":          "survey",     # survey | spray | pollination
        "current_task":          "NDVI multispectral scan · Zones C–D",
        "mission_progress_pct":  61.0,
        "mission_eta_min":       15,
        "gps":                   {"lat": 27.7172, "lng": 85.3240, "alt_m": 22},
        "tank_pct":              68,
        "flight_hours_total":    247,
        "last_service_date":     "2025-06-01",
        "next_service_date":     "2025-08-01",
        "mission_queue": [
            {"mode": "survey",      "zones": ["C3","C4","C5","C6"], "payload": "multispectral",  "status": "active"},
            {"mode": "spray",       "zones": ["B3","B4"],           "payload": "fungicide",      "status": "queued"},
            {"mode": "spray",       "zones": ["A4"],                "payload": "foliar-nitrogen","status": "queued"},
            {"mode": "pollination", "zones": ["A1","A2","A3"],      "payload": "vibration",      "status": "queued", "scheduled_time": "07:00"},
        ],
    },

    # ── MPAR-1 ─────────────────────────────────────────────────────
    "robot": {
        "id":                   "MPAR-1",
        "battery_pct":          82,
        "status":               "active",      # active | idle | charging | swapping-head
        "current_head":         "harvester",   # harvester | weeder | seeder
        "current_task":         "Harvesting tomatoes · Row 7 of 18",
        "mission_progress_pct": 39.0,
        "mission_eta_min":      134,
        "op_hours_total":       421,
        "gps":                  {"lat": 27.7169, "lng": 85.3235},
        "head_queue": [
            {"head": "harvester", "zone": "A1-A3", "task": "Harvest tomatoes rows 7-18",    "status": "active"},
            {"head": "weeder",    "zone": "C",     "task": "Inter-row mechanical weeding",  "status": "queued"},
            {"head": "seeder",    "zone": "D6",    "task": "Replanting Zone D6",            "status": "queued", "scheduled_time": "16:00"},
        ],
    },

    # ── Irrigation ──────────────────────────────────────────────────
    "irrigation": {
        "schedules": [
            {"zone": "A", "days": ["Mon","Thu"], "time": "06:00", "last_run": "2025-06-19", "status": "scheduled"},
            {"zone": "B", "days": ["Tue","Fri"], "time": "06:30", "last_run": "2025-06-20", "status": "scheduled"},
            {"zone": "C", "days": ["Mon","Thu"], "time": "14:30", "last_run": "2025-06-18", "status": "scheduled", "alert": "C5 drought stress — run today"},
            {"zone": "D", "days": [],            "time": None,    "last_run": None,          "status": "not-scheduled", "suggestion": "Mon 06:00"},
        ],
        "rules": [
            {"id": "rule-1", "description": "If soil moisture < 45%, trigger drip for 30 min", "enabled": True},
            {"id": "rule-2", "description": "Skip irrigation if rain forecast > 5mm within 24h", "enabled": True},
            {"id": "rule-3", "description": "Notify farmer if Zone C moisture < 35%", "enabled": True},
        ],
    },

    # ── Active alerts ───────────────────────────────────────────────
    "alerts": [
        {"id": "alert-1", "severity": "high",   "type": "pest",     "zones": ["B3","B4"], "message": "Fungal blight detected",   "action": "UAV-1 dispatched"},
        {"id": "alert-2", "severity": "medium", "type": "nutrient", "zones": ["A4"],      "message": "Nitrogen 42 ppm (low)",    "action": "Foliar feed scheduled 11:00"},
        {"id": "alert-3", "severity": "medium", "type": "moisture", "zones": ["C5"],      "message": "Drought stress 39%",       "action": "Drip queued 14:30"},
    ],

    # ── Harvest log ─────────────────────────────────────────────────
    "harvest_log": [
        {"date": "2025-06-15", "entries": [{"crop": "Tomatoes", "kg": 148}, {"crop": "Peppers", "kg": 62}]},
        {"date": "2025-06-16", "entries": [{"crop": "Tomatoes", "kg": 162}, {"crop": "Spinach", "kg": 83}]},
        {"date": "2025-06-17", "entries": [{"crop": "Tomatoes", "kg": 110}, {"crop": "Peppers", "kg": 78}]},
        {"date": "2025-06-18", "entries": [{"crop": "Tomatoes", "kg": 185}, {"crop": "Peppers", "kg": 117}]},
        {"date": "2025-06-19", "entries": [{"crop": "Tomatoes", "kg": 148}, {"crop": "Spinach", "kg": 41}, {"crop": "Lettuce", "kg": 78}]},
        {"date": "2025-06-20", "entries": [{"crop": "Tomatoes", "kg": 152}, {"crop": "Peppers", "kg": 89}]},
        {"date": "2025-06-21", "entries": [
            {"crop": "Tomatoes", "kg": 148},
            {"crop": "Peppers",  "kg": 62},
            {"crop": "Spinach",  "kg": 41},
            {"crop": "Lettuce",  "kg": 28},
        ]},
    ],

    # ── Spray log ───────────────────────────────────────────────────
    "spray_log": [
        {"date": "2025-06-21", "zones": "B3-B4", "payload": "Copper fungicide — blight",   "vehicle": "UAV-1", "status": "ongoing"},
        {"date": "2025-06-18", "zones": "A4",    "payload": "Foliar nitrogen",              "vehicle": "UAV-1", "status": "effective"},
        {"date": "2025-06-14", "zones": "C1-C3", "payload": "Neem oil — whitefly",          "vehicle": "UAV-1", "status": "effective"},
        {"date": "2025-06-09", "zones": "All",   "payload": "Preventive copper spray",      "vehicle": "UAV-1", "status": "effective"},
    ],

    # ── 7-day weather forecast ──────────────────────────────────────
    "weather": [
        {"day": "Today", "icon": "⛅", "temp_c": 27, "rain_mm": 0},
        {"day": "Mon",   "icon": "☀️",  "temp_c": 29, "rain_mm": 0},
        {"day": "Tue",   "icon": "⛅", "temp_c": 28, "rain_mm": 1},
        {"day": "Wed",   "icon": "🌧️",  "temp_c": 24, "rain_mm": 10},
        {"day": "Thu",   "icon": "🌧️",  "temp_c": 23, "rain_mm": 8},
        {"day": "Fri",   "icon": "⛅", "temp_c": 26, "rain_mm": 2},
        {"day": "Sat",   "icon": "☀️",  "temp_c": 28, "rain_mm": 0},
    ],

    # ── Tasks queue ─────────────────────────────────────────────────
    "tasks": [
        {"id": "task-1", "text": "UAV-1 NDVI morning scan",                          "status": "done",             "time": "07:42"},
        {"id": "task-2", "text": "Deploy UAV-1 (spray mode) to B3–B4 fungicide",     "status": "done",             "time": "08:15"},
        {"id": "task-3", "text": "Foliar nitrogen — Zone A4 via UAV-1",               "status": "in-progress",      "time": "11:00"},
        {"id": "task-4", "text": "MPAR-1 mechanical weeding — Zone C (weeder head)",  "status": "in-progress",      "time": ""},
        {"id": "task-5", "text": "UAV-1 thermal anomaly scan",                        "status": "queued",           "time": "14:30"},
        {"id": "task-6", "text": "MPAR-1 replanting prep — Zone D6 (seeder head)",    "status": "queued",           "time": "16:00"},
        {"id": "task-7", "text": "Zone C irrigation rescheduled (rain Wed forecast)",  "status": "pending-approval", "time": ""},
    ],
}

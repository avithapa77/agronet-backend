"""
farm_state.py — AgroNet v5
Extended to support 3 drones (UAV-1, UAV-2, UAV-3) and 3 robots (MPAR-1, MPAR-2, MPAR-3)
plus a full automation engine with rules, triggers, and an action log.
"""

farm_state = {

    # ── Zones ─────────────────────────────────────────────────────
    "zones": {
        "A1": {"crop": "Tomatoes", "health": "healthy",  "ndvi": 0.80, "moisture": 64, "notes": "Harvest in ~18 days"},
        "A2": {"crop": "Tomatoes", "health": "healthy",  "ndvi": 0.78, "moisture": 62, "notes": ""},
        "A3": {"crop": "Tomatoes", "health": "healthy",  "ndvi": 0.81, "moisture": 65, "notes": ""},
        "A4": {"crop": "Peppers",  "health": "stressed", "ndvi": None, "moisture": 58, "notes": "N 42 ppm (low)"},
        "A5": {"crop": "Peppers",  "health": "healthy",  "ndvi": None, "moisture": 60, "notes": ""},
        "A6": {"crop": "Peppers",  "health": "healthy",  "ndvi": None, "moisture": 61, "notes": ""},
        "B1": {"crop": "Spinach",  "health": "healthy",  "ndvi": None, "moisture": 55, "notes": ""},
        "B2": {"crop": "Spinach",  "health": "healthy",  "ndvi": None, "moisture": 53, "notes": ""},
        "B3": {"crop": "Spinach",  "health": "alert",    "ndvi": None, "moisture": 50, "notes": "Fungal blight — UAV-2 treating"},
        "B4": {"crop": "Spinach",  "health": "alert",    "ndvi": None, "moisture": 51, "notes": "Fungal blight — UAV-2 treating"},
        "B5": {"crop": "Spinach",  "health": "healthy",  "ndvi": None, "moisture": 54, "notes": ""},
        "C1": {"crop": "Carrots",  "health": "healthy",  "ndvi": None, "moisture": 68, "notes": ""},
        "C2": {"crop": "Carrots",  "health": "healthy",  "ndvi": None, "moisture": 69, "notes": ""},
        "C3": {"crop": "Carrots",  "health": "healthy",  "ndvi": None, "moisture": 70, "notes": "Compaction 2.1 MPa — monitor"},
        "C4": {"crop": "Carrots",  "health": "healthy",  "ndvi": None, "moisture": 71, "notes": ""},
        "C5": {"crop": "Carrots",  "health": "stressed", "ndvi": None, "moisture": 39, "notes": "Drought stress — MPAR-3 irrigating"},
        "C6": {"crop": "Carrots",  "health": "healthy",  "ndvi": None, "moisture": 66, "notes": ""},
        "D1": {"crop": "Empty",    "health": "empty",    "ndvi": None, "moisture": None, "notes": ""},
        "D2": {"crop": "Empty",    "health": "empty",    "ndvi": None, "moisture": None, "notes": ""},
        "D3": {"crop": "Beans",    "health": "healthy",  "ndvi": None, "moisture": 41, "notes": ""},
        "D4": {"crop": "Beans",    "health": "healthy",  "ndvi": None, "moisture": 42, "notes": ""},
        "D5": {"crop": "Beans",    "health": "healthy",  "ndvi": None, "moisture": 40, "notes": ""},
        "D6": {"crop": "Empty",    "health": "empty",    "ndvi": None, "moisture": None, "notes": "pH 5.8 — lime needed; 0.4 ha ready"},
    },

    # ── Soil sensors ───────────────────────────────────────────────
    "sensors": {
        "soil_moisture": {"C5": 39},
        "nitrogen":      {"A4": 42},
        "phosphorus":    {"A4": 28},
        "potassium":     {"A4": 180},
        "ph":            {"D6": 5.8, "field_avg": 6.8},
        "compaction":    {"C3": 2.1},
        "pest_traps":    {"B3": 48, "B4": 48},
    },

    # ── Environment ────────────────────────────────────────────────
    "environment": {
        "air_temp_c":        27,
        "humidity_pct":      71,
        "co2_ppm":           412,
        "wind_speed_kmh":    8,
        "wind_dir_deg":      218,
        "wind_dir_label":    "SSW",
        "rainfall_mm_today": 0,
        "solar_rad_wm2":     680,
        "soil_temp_c":       19,
    },

    # ── Fleet: 3 drones ───────────────────────────────────────────
    "drones": {
        "UAV-1": {
            "id": "UAV-1", "name": "Scout & Sprayer",
            "battery_pct": 78.0, "status": "flying",
            "current_mode": "survey",
            "current_task": "NDVI multispectral scan · Zones C–D",
            "mission_progress_pct": 61.0, "mission_eta_min": 15,
            "gps": {"lat": 27.7172, "lng": 85.3240, "alt_m": 22},
            "tank_pct": 68, "flight_hours_total": 247,
            "last_service_date": "2025-06-01", "next_service_date": "2025-08-01",
            "capabilities": ["survey", "spray", "pollination"],
            "mission_queue": [
                {"mode": "survey",      "zones": ["C3","C4","C5","C6"], "payload": "multispectral",   "status": "active"},
                {"mode": "spray",       "zones": ["A4"],                "payload": "foliar-nitrogen", "status": "queued"},
                {"mode": "pollination", "zones": ["A1","A2","A3"],      "payload": "vibration",       "status": "queued", "scheduled_time": "07:00"},
            ],
        },
        "UAV-2": {
            "id": "UAV-2", "name": "Heavy Sprayer",
            "battery_pct": 43.0, "status": "charging",
            "current_mode": "spray",
            "current_task": "Charging — last flight: fungicide B3–B4",
            "mission_progress_pct": 100.0, "mission_eta_min": 0,
            "gps": {"lat": 27.7165, "lng": 85.3230, "alt_m": 0},
            "tank_pct": 15, "flight_hours_total": 183,
            "last_service_date": "2025-05-15", "next_service_date": "2025-07-15",
            "capabilities": ["spray", "seed-drop"],
            "mission_queue": [
                {"mode": "spray", "zones": ["B3","B4"], "payload": "fungicide", "status": "done"},
            ],
        },
        "UAV-3": {
            "id": "UAV-3", "name": "Pollinator",
            "battery_pct": 100.0, "status": "standby",
            "current_mode": "pollination",
            "current_task": "Standby — scheduled Zone A1-A3 tomorrow 06:30",
            "mission_progress_pct": 0.0, "mission_eta_min": 0,
            "gps": {"lat": 27.7160, "lng": 85.3225, "alt_m": 0},
            "tank_pct": 100, "flight_hours_total": 94,
            "last_service_date": "2025-06-10", "next_service_date": "2025-08-10",
            "capabilities": ["pollination", "survey"],
            "mission_queue": [
                {"mode": "pollination", "zones": ["A1","A2","A3"], "payload": "vibration", "status": "queued", "scheduled_time": "06:30"},
            ],
        },
    },

    # ── Fleet: 3 robots ───────────────────────────────────────────
    "robots": {
        "MPAR-1": {
            "id": "MPAR-1", "name": "Harvester",
            "battery_pct": 82, "status": "active",
            "current_head": "harvester",
            "current_task": "Harvesting tomatoes · Row 7 of 18",
            "mission_progress_pct": 39.0, "mission_eta_min": 134,
            "op_hours_total": 421,
            "gps": {"lat": 27.7169, "lng": 85.3235},
            "capabilities": ["harvester", "weeder", "seeder"],
            "head_queue": [
                {"head": "harvester", "zone": "A1-A3", "task": "Harvest tomatoes rows 7-18",   "status": "active"},
                {"head": "weeder",    "zone": "C",     "task": "Inter-row mechanical weeding", "status": "queued"},
                {"head": "seeder",    "zone": "D6",    "task": "Replanting Zone D6",           "status": "queued", "scheduled_time": "16:00"},
            ],
        },
        "MPAR-2": {
            "id": "MPAR-2", "name": "Weeder & Scout",
            "battery_pct": 67, "status": "active",
            "current_head": "weeder",
            "current_task": "Mechanical weeding Zone C · Row 1 of 22",
            "mission_progress_pct": 8.0, "mission_eta_min": 210,
            "op_hours_total": 298,
            "gps": {"lat": 27.7175, "lng": 85.3228},
            "capabilities": ["weeder", "harvester", "soil-probe"],
            "head_queue": [
                {"head": "weeder",      "zone": "C",  "task": "Mechanical weed control Zone C", "status": "active"},
                {"head": "soil-probe",  "zone": "D",  "task": "Full soil survey Zone D",        "status": "queued"},
            ],
        },
        "MPAR-3": {
            "id": "MPAR-3", "name": "Irrigation Runner",
            "battery_pct": 91, "status": "active",
            "current_head": "drip-irrigator",
            "current_task": "Micro-drip irrigation Zone A6 · 14 min remaining",
            "mission_progress_pct": 63.0, "mission_eta_min": 14,
            "op_hours_total": 156,
            "gps": {"lat": 27.7180, "lng": 85.3242},
            "capabilities": ["drip-irrigator", "seeder", "fertigation"],
            "head_queue": [
                {"head": "drip-irrigator", "zone": "A6", "task": "Precision drip 192L",            "status": "active"},
                {"head": "fertigation",    "zone": "A4", "task": "Liquid nitrogen injection A4",    "status": "queued"},
                {"head": "drip-irrigator", "zone": "C5", "task": "Emergency drought relief C5",    "status": "queued"},
            ],
        },
    },

    # ── Legacy single-drone/robot keys (kept for backward compat) ──
    # These proxy to UAV-1 / MPAR-1 so old frontend code still works
    "drone": None,  # will be patched in main.py to reference drones["UAV-1"]
    "robot": None,  # will be patched to reference robots["MPAR-1"]

    # ── Automation rules ───────────────────────────────────────────
    "automation": {
        "enabled": True,
        "rules": [
            {
                "id": "auto-1",
                "name": "Drought relief",
                "description": "If soil moisture < 45% → assign MPAR-3 drip irrigator to that zone",
                "trigger": {"type": "sensor", "sensor": "soil_moisture", "operator": "<", "threshold": 45},
                "action":  {"type": "dispatch_robot", "robot": "MPAR-3", "head": "drip-irrigator"},
                "enabled": True, "last_fired": "2025-06-21T14:28:00",
            },
            {
                "id": "auto-2",
                "name": "Pest spray",
                "description": "If pest trap count > 30 → dispatch UAV-1 spray (fungicide) to affected zone",
                "trigger": {"type": "sensor", "sensor": "pest_traps", "operator": ">", "threshold": 30},
                "action":  {"type": "dispatch_drone", "drone": "UAV-1", "mode": "spray", "payload": "fungicide"},
                "enabled": True, "last_fired": "2025-06-21T08:15:00",
            },
            {
                "id": "auto-3",
                "name": "Low nitrogen spray",
                "description": "If nitrogen < 50 ppm → schedule UAV-1 foliar nitrogen spray",
                "trigger": {"type": "sensor", "sensor": "nitrogen", "operator": "<", "threshold": 50},
                "action":  {"type": "dispatch_drone", "drone": "UAV-1", "mode": "spray", "payload": "foliar-nitrogen"},
                "enabled": True, "last_fired": "2025-06-18T11:00:00",
            },
            {
                "id": "auto-4",
                "name": "Morning NDVI scan",
                "description": "Every day at 07:00 → dispatch UAV-1 full-farm NDVI survey",
                "trigger": {"type": "schedule", "cron": "0 7 * * *"},
                "action":  {"type": "dispatch_drone", "drone": "UAV-1", "mode": "survey", "payload": "multispectral"},
                "enabled": True, "last_fired": "2025-06-21T07:00:00",
            },
            {
                "id": "auto-5",
                "name": "Weed control cycle",
                "description": "Every Monday at 09:00 → assign MPAR-2 weeder head to all crop zones",
                "trigger": {"type": "schedule", "cron": "0 9 * * 1"},
                "action":  {"type": "dispatch_robot", "robot": "MPAR-2", "head": "weeder"},
                "enabled": True, "last_fired": "2025-06-16T09:00:00",
            },
            {
                "id": "auto-6",
                "name": "Rain guard",
                "description": "If rain forecast > 5mm within 24h → cancel all spray missions",
                "trigger": {"type": "weather", "condition": "rain_forecast_mm", "operator": ">", "threshold": 5},
                "action":  {"type": "cancel_spray_missions"},
                "enabled": True, "last_fired": None,
            },
            {
                "id": "auto-7",
                "name": "Pollination window",
                "description": "If wind < 10 km/h and temp 20–35°C at 06:30 → launch UAV-3 pollination",
                "trigger": {"type": "compound", "conditions": [
                    {"sensor": "wind_speed_kmh", "operator": "<", "threshold": 10},
                    {"sensor": "air_temp_c",     "operator": "between", "min": 20, "max": 35},
                ]},
                "action":  {"type": "dispatch_drone", "drone": "UAV-3", "mode": "pollination", "payload": "vibration"},
                "enabled": True, "last_fired": None,
            },
            {
                "id": "auto-8",
                "name": "Low battery return",
                "description": "If any drone battery < 20% → abort mission and return to dock",
                "trigger": {"type": "fleet", "condition": "any_drone_battery", "operator": "<", "threshold": 20},
                "action":  {"type": "return_to_dock"},
                "enabled": True, "last_fired": None,
            },
        ],

        # Log of automation actions taken today
        "action_log": [
            {"time": "07:00", "rule": "auto-4", "message": "Dispatched UAV-1 NDVI scan — all zones", "status": "success"},
            {"time": "08:15", "rule": "auto-2", "message": "Pest trap B3/B4 hit 48 (threshold 30) — dispatched UAV-2 fungicide spray", "status": "success"},
            {"time": "14:28", "rule": "auto-1", "message": "Zone C5 moisture 39% (threshold 45%) — dispatched MPAR-3 drip irrigation", "status": "success"},
        ],
    },

    # ── Irrigation ─────────────────────────────────────────────────
    "irrigation": {
        "schedules": [
            {"zone": "A", "days": ["Mon","Thu"], "time": "06:00", "last_run": "2025-06-19", "status": "scheduled"},
            {"zone": "B", "days": ["Tue","Fri"], "time": "06:30", "last_run": "2025-06-20", "status": "scheduled"},
            {"zone": "C", "days": ["Mon","Thu"], "time": "14:30", "last_run": "2025-06-18", "status": "scheduled", "alert": "C5 drought stress — run today"},
            {"zone": "D", "days": [],            "time": None,    "last_run": None,          "status": "not-scheduled", "suggestion": "Mon 06:00"},
        ],
        "rules": [
            {"id": "rule-1", "description": "If soil moisture < 45%, trigger drip for 30 min", "enabled": True},
            {"id": "rule-2", "description": "Skip irrigation if rain forecast > 5mm within 24h",  "enabled": True},
            {"id": "rule-3", "description": "Notify farmer if Zone C moisture < 35%",             "enabled": True},
        ],
    },

    # ── Alerts ─────────────────────────────────────────────────────
    "alerts": [
        {"id": "alert-1", "severity": "high",   "type": "pest",     "zones": ["B3","B4"], "message": "Fungal blight detected",  "action": "UAV-2 dispatched (auto-2)"},
        {"id": "alert-2", "severity": "medium",  "type": "nutrient", "zones": ["A4"],      "message": "Nitrogen 42 ppm (low)",   "action": "Foliar feed scheduled 11:00"},
        {"id": "alert-3", "severity": "medium",  "type": "moisture", "zones": ["C5"],      "message": "Drought stress 39%",      "action": "MPAR-3 dispatched (auto-1)"},
    ],

    # ── Harvest log ────────────────────────────────────────────────
    "harvest_log": [
        {"date": "2025-06-15", "entries": [{"crop": "Tomatoes", "kg": 148}, {"crop": "Peppers", "kg": 62}]},
        {"date": "2025-06-16", "entries": [{"crop": "Tomatoes", "kg": 162}, {"crop": "Spinach", "kg": 83}]},
        {"date": "2025-06-17", "entries": [{"crop": "Tomatoes", "kg": 110}, {"crop": "Peppers", "kg": 78}]},
        {"date": "2025-06-18", "entries": [{"crop": "Tomatoes", "kg": 185}, {"crop": "Peppers", "kg": 117}]},
        {"date": "2025-06-19", "entries": [{"crop": "Tomatoes", "kg": 148}, {"crop": "Spinach", "kg": 41}, {"crop": "Lettuce", "kg": 78}]},
        {"date": "2025-06-20", "entries": [{"crop": "Tomatoes", "kg": 152}, {"crop": "Peppers", "kg": 89}]},
        {"date": "2025-06-21", "entries": [
            {"crop": "Tomatoes", "kg": 148}, {"crop": "Peppers", "kg": 62},
            {"crop": "Spinach",  "kg": 41},  {"crop": "Lettuce", "kg": 28},
        ]},
    ],

    # ── Spray log ──────────────────────────────────────────────────
    "spray_log": [
        {"date": "2025-06-21", "zones": "B3-B4", "payload": "Copper fungicide — blight",  "vehicle": "UAV-2", "status": "ongoing"},
        {"date": "2025-06-18", "zones": "A4",    "payload": "Foliar nitrogen",             "vehicle": "UAV-1", "status": "effective"},
        {"date": "2025-06-14", "zones": "C1-C3", "payload": "Neem oil — whitefly",         "vehicle": "UAV-1", "status": "effective"},
        {"date": "2025-06-09", "zones": "All",   "payload": "Preventive copper spray",     "vehicle": "UAV-1", "status": "effective"},
    ],

    # ── Weather ────────────────────────────────────────────────────
    "weather": [
        {"day": "Today", "icon": "⛅", "temp_c": 27, "rain_mm": 0},
        {"day": "Mon",   "icon": "☀️",  "temp_c": 29, "rain_mm": 0},
        {"day": "Tue",   "icon": "⛅", "temp_c": 28, "rain_mm": 1},
        {"day": "Wed",   "icon": "🌧️",  "temp_c": 24, "rain_mm": 10},
        {"day": "Thu",   "icon": "🌧️",  "temp_c": 23, "rain_mm": 8},
        {"day": "Fri",   "icon": "⛅", "temp_c": 26, "rain_mm": 2},
        {"day": "Sat",   "icon": "☀️",  "temp_c": 28, "rain_mm": 0},
    ],

    # ── Tasks ──────────────────────────────────────────────────────
    "tasks": [
        {"id": "task-1", "text": "UAV-1 NDVI morning scan",                         "status": "done",             "time": "07:00", "automated": True},
        {"id": "task-2", "text": "UAV-2 fungicide spray B3–B4 (pest auto-trigger)", "status": "done",             "time": "08:15", "automated": True},
        {"id": "task-3", "text": "Foliar nitrogen — Zone A4 via UAV-1",              "status": "in-progress",      "time": "11:00", "automated": False},
        {"id": "task-4", "text": "MPAR-1 mechanical weeding — Zone C",               "status": "in-progress",      "time": "",      "automated": False},
        {"id": "task-5", "text": "MPAR-3 drip irrigation Zone C5 (drought trigger)","status": "in-progress",      "time": "14:28", "automated": True},
        {"id": "task-6", "text": "UAV-1 thermal anomaly scan",                       "status": "queued",           "time": "14:30", "automated": False},
        {"id": "task-7", "text": "MPAR-1 replanting prep — Zone D6 (seeder head)",  "status": "queued",           "time": "16:00", "automated": False},
        {"id": "task-8", "text": "Zone C irrigation (rain Wed — postpone?)",         "status": "pending-approval", "time": "",      "automated": True},
    ],
}

# Patch legacy keys so old code still works without changes
farm_state["drone"] = farm_state["drones"]["UAV-1"]
farm_state["robot"] = farm_state["robots"]["MPAR-1"]

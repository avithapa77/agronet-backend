"""
state/farm_state.py — AgroNet Autonomous v6

Supports BOTH:
  - OUTDOOR field (zones A-D, drones, ground robots, weather)
  - INDOOR greenhouse / vertical farm (grow rooms, LED rigs, hydroponic rails,
    climate controllers, nutrient dosers)

Everything is in one dict. No database needed for prototyping.
In production, patch this with a Redis or PostgreSQL loader.
"""

farm_state = {

    # ─────────────────────────────────────────────────────────────
    # SYSTEM CONFIG
    # ─────────────────────────────────────────────────────────────
    "config": {
        "farm_name":   "Kisan Autonomous Farm",
        "farm_id":     "farm-001",
        "location":    {"lat": 27.7172, "lng": 85.3240, "timezone": "Asia/Kathmandu"},
        "mode":        "both",          # "outdoor" | "indoor" | "both"
        "auto_master": True,            # kill-switch for ALL automation
        "version":     "6.0.0",
    },

    # ─────────────────────────────────────────────────────────────
    # OUTDOOR — zones, sensors, fleet
    # ─────────────────────────────────────────────────────────────
    "outdoor": {

        "zones": {
            "A1": {"crop":"Tomatoes","health":"healthy","ndvi":0.80,"moisture":64,"temp_c":22,"notes":"Harvest ~18 days"},
            "A2": {"crop":"Tomatoes","health":"healthy","ndvi":0.78,"moisture":62,"temp_c":22,"notes":""},
            "A3": {"crop":"Tomatoes","health":"healthy","ndvi":0.81,"moisture":65,"temp_c":21,"notes":""},
            "A4": {"crop":"Peppers", "health":"stressed","ndvi":None,"moisture":58,"temp_c":23,"notes":"N 42 ppm low"},
            "A5": {"crop":"Peppers", "health":"healthy","ndvi":None,"moisture":60,"temp_c":22,"notes":""},
            "A6": {"crop":"Peppers", "health":"healthy","ndvi":None,"moisture":61,"temp_c":22,"notes":""},
            "B1": {"crop":"Spinach", "health":"healthy","ndvi":None,"moisture":55,"temp_c":20,"notes":""},
            "B2": {"crop":"Spinach", "health":"healthy","ndvi":None,"moisture":53,"temp_c":20,"notes":""},
            "B3": {"crop":"Spinach", "health":"alert",  "ndvi":None,"moisture":50,"temp_c":21,"notes":"Fungal blight"},
            "B4": {"crop":"Spinach", "health":"alert",  "ndvi":None,"moisture":51,"temp_c":21,"notes":"Fungal blight"},
            "B5": {"crop":"Spinach", "health":"healthy","ndvi":None,"moisture":54,"temp_c":20,"notes":""},
            "C1": {"crop":"Carrots", "health":"healthy","ndvi":None,"moisture":68,"temp_c":19,"notes":""},
            "C2": {"crop":"Carrots", "health":"healthy","ndvi":None,"moisture":69,"temp_c":19,"notes":""},
            "C3": {"crop":"Carrots", "health":"healthy","ndvi":None,"moisture":70,"temp_c":19,"notes":"Compaction 2.1 MPa"},
            "C4": {"crop":"Carrots", "health":"healthy","ndvi":None,"moisture":71,"temp_c":18,"notes":""},
            "C5": {"crop":"Carrots", "health":"stressed","ndvi":None,"moisture":39,"temp_c":24,"notes":"Drought stress"},
            "C6": {"crop":"Carrots", "health":"healthy","ndvi":None,"moisture":66,"temp_c":19,"notes":""},
            "D1": {"crop":"Empty",   "health":"empty",  "ndvi":None,"moisture":None,"temp_c":None,"notes":""},
            "D2": {"crop":"Empty",   "health":"empty",  "ndvi":None,"moisture":None,"temp_c":None,"notes":""},
            "D3": {"crop":"Beans",   "health":"healthy","ndvi":None,"moisture":41,"temp_c":21,"notes":""},
            "D4": {"crop":"Beans",   "health":"healthy","ndvi":None,"moisture":42,"temp_c":21,"notes":""},
            "D5": {"crop":"Beans",   "health":"healthy","ndvi":None,"moisture":40,"temp_c":21,"notes":""},
            "D6": {"crop":"Empty",   "health":"empty",  "ndvi":None,"moisture":None,"temp_c":None,"notes":"pH 5.8 ready"},
        },

        "sensors": {
            "soil_moisture": {"C5":39,"A4":58,"B3":50,"B4":51},
            "nitrogen":      {"A4":42},
            "phosphorus":    {"A4":28},
            "potassium":     {"A4":180},
            "ph":            {"D6":5.8,"field_avg":6.8},
            "compaction":    {"C3":2.1},
            "pest_traps":    {"B3":48,"B4":48},
            "leaf_wetness":  {"B3":0.9,"B4":0.88},   # 0-1, >0.7 = fungal risk
            "solar_rad":     {"field":680},            # W/m²
            "co2":           {"field":412},            # ppm
        },

        "environment": {
            "air_temp_c":        27,
            "humidity_pct":      71,
            "wind_speed_kmh":    8,
            "wind_dir_label":    "SSW",
            "wind_dir_deg":      218,
            "rainfall_mm_today": 0,
            "solar_rad_wm2":     680,
            "soil_temp_c":       19,
            "uv_index":          6,
            "dew_point_c":       20,
        },

        "weather_forecast": [
            {"day":"Today","icon":"⛅","temp_c":27,"rain_mm":0,"wind_kmh":8},
            {"day":"Mon",  "icon":"☀️", "temp_c":29,"rain_mm":0,"wind_kmh":6},
            {"day":"Tue",  "icon":"⛅","temp_c":28,"rain_mm":1,"wind_kmh":10},
            {"day":"Wed",  "icon":"🌧️", "temp_c":24,"rain_mm":10,"wind_kmh":14},
            {"day":"Thu",  "icon":"🌧️", "temp_c":23,"rain_mm":8,"wind_kmh":12},
            {"day":"Fri",  "icon":"⛅","temp_c":26,"rain_mm":2,"wind_kmh":9},
            {"day":"Sat",  "icon":"☀️", "temp_c":28,"rain_mm":0,"wind_kmh":7},
        ],

        # ── Drones ──────────────────────────────────────────────
        "drones": {
            "UAV-1": {
                "id":"UAV-1","name":"Scout & Sprayer",
                "battery_pct":78.0,"status":"flying",
                "current_mode":"survey","current_task":"NDVI scan Zones C–D",
                "mission_progress_pct":61.0,"mission_eta_min":15,
                "gps":{"lat":27.7172,"lng":85.3240,"alt_m":22},
                "tank_pct":68,"flight_hours_total":247,
                "capabilities":["survey","spray","pollination"],
                "last_service":"2025-06-01","next_service":"2025-08-01",
                "mission_queue":[
                    {"mode":"survey","zones":["C3","C4","C5","C6"],"payload":"multispectral","status":"active"},
                    {"mode":"spray","zones":["A4"],"payload":"foliar-nitrogen","status":"queued"},
                ],
            },
            "UAV-2": {
                "id":"UAV-2","name":"Heavy Sprayer",
                "battery_pct":43.0,"status":"charging",
                "current_mode":"spray","current_task":"Charging — last: fungicide B3–B4",
                "mission_progress_pct":100.0,"mission_eta_min":0,
                "gps":{"lat":27.7165,"lng":85.3230,"alt_m":0},
                "tank_pct":15,"flight_hours_total":183,
                "capabilities":["spray","seed-drop"],
                "last_service":"2025-05-15","next_service":"2025-07-15",
                "mission_queue":[],
            },
            "UAV-3": {
                "id":"UAV-3","name":"Pollinator",
                "battery_pct":100.0,"status":"standby",
                "current_mode":"pollination","current_task":"Standby — pollination A1-A3 @ 06:30",
                "mission_progress_pct":0.0,"mission_eta_min":0,
                "gps":{"lat":27.7160,"lng":85.3225,"alt_m":0},
                "tank_pct":100,"flight_hours_total":94,
                "capabilities":["pollination","survey"],
                "last_service":"2025-06-10","next_service":"2025-08-10",
                "mission_queue":[
                    {"mode":"pollination","zones":["A1","A2","A3"],"payload":"vibration","status":"queued","scheduled_time":"06:30"},
                ],
            },
        },

        # ── Ground robots ────────────────────────────────────────
        "robots": {
            "MPAR-1": {
                "id":"MPAR-1","name":"Harvester",
                "battery_pct":82,"status":"active",
                "current_head":"harvester","current_task":"Harvesting tomatoes Row 7/18",
                "mission_progress_pct":39.0,"mission_eta_min":134,
                "op_hours_total":421,
                "gps":{"lat":27.7169,"lng":85.3235},
                "capabilities":["harvester","weeder","seeder"],
                "head_queue":[
                    {"head":"harvester","zone":"A1-A3","task":"Harvest tomatoes rows 7-18","status":"active"},
                    {"head":"weeder","zone":"C","task":"Mechanical weeding Zone C","status":"queued"},
                    {"head":"seeder","zone":"D6","task":"Replant D6","status":"queued","scheduled_time":"16:00"},
                ],
            },
            "MPAR-2": {
                "id":"MPAR-2","name":"Weeder & Scout",
                "battery_pct":67,"status":"active",
                "current_head":"weeder","current_task":"Weeding Zone C Row 1/22",
                "mission_progress_pct":8.0,"mission_eta_min":210,
                "op_hours_total":298,
                "gps":{"lat":27.7175,"lng":85.3228},
                "capabilities":["weeder","harvester","soil-probe"],
                "head_queue":[
                    {"head":"weeder","zone":"C","task":"Weed control Zone C","status":"active"},
                    {"head":"soil-probe","zone":"D","task":"Soil survey Zone D","status":"queued"},
                ],
            },
            "MPAR-3": {
                "id":"MPAR-3","name":"Irrigation Runner",
                "battery_pct":91,"status":"active",
                "current_head":"drip-irrigator","current_task":"Drip irrigation A6 — 14 min left",
                "mission_progress_pct":63.0,"mission_eta_min":14,
                "op_hours_total":156,
                "gps":{"lat":27.7180,"lng":85.3242},
                "capabilities":["drip-irrigator","seeder","fertigation"],
                "head_queue":[
                    {"head":"drip-irrigator","zone":"A6","task":"Precision drip 192L","status":"active"},
                    {"head":"fertigation","zone":"A4","task":"Liquid N injection","status":"queued"},
                    {"head":"drip-irrigator","zone":"C5","task":"Emergency drought C5","status":"queued"},
                ],
            },
        },

        "irrigation": {
            "schedules": [
                {"zone":"A","days":["Mon","Thu"],"time":"06:00","last_run":"2025-06-19","status":"scheduled"},
                {"zone":"B","days":["Tue","Fri"],"time":"06:30","last_run":"2025-06-20","status":"scheduled"},
                {"zone":"C","days":["Mon","Thu"],"time":"14:30","last_run":"2025-06-18","status":"scheduled","alert":"C5 drought — run today"},
                {"zone":"D","days":[],"time":None,"last_run":None,"status":"not-scheduled","suggestion":"Mon 06:00"},
            ],
            "rules": [
                {"id":"irule-1","description":"If soil moisture < 45%, drip 30 min","enabled":True},
                {"id":"irule-2","description":"Skip if rain forecast > 5mm within 24h","enabled":True},
                {"id":"irule-3","description":"Alert if Zone C moisture < 35%","enabled":True},
            ],
        },

        "spray_log": [
            {"date":"2025-06-21","zones":"B3-B4","payload":"Copper fungicide","vehicle":"UAV-2","status":"ongoing"},
            {"date":"2025-06-18","zones":"A4",   "payload":"Foliar nitrogen", "vehicle":"UAV-1","status":"effective"},
        ],
        "harvest_log": [
            {"date":"2025-06-21","entries":[{"crop":"Tomatoes","kg":148},{"crop":"Peppers","kg":62},{"crop":"Spinach","kg":41}]},
            {"date":"2025-06-20","entries":[{"crop":"Tomatoes","kg":152},{"crop":"Peppers","kg":89}]},
        ],
    },

    # ─────────────────────────────────────────────────────────────
    # INDOOR — greenhouses + vertical farm rooms
    # ─────────────────────────────────────────────────────────────
    "indoor": {

        "rooms": {
            "GH-1": {
                "id":"GH-1","name":"Greenhouse A — Tomatoes","type":"greenhouse",
                "crop":"Cherry Tomatoes","stage":"fruiting","area_m2":120,
                # Climate targets
                "targets": {
                    "temp_day_c":26,"temp_night_c":18,
                    "humidity_pct":65,"co2_ppm":800,
                    "vpd_kpa":1.1,          # Vapour Pressure Deficit
                    "light_hours":16,"light_intensity_umol":400,
                    "ph_target":6.2,"ec_target_ms":2.8,
                },
                # Live readings (updated by sensors/MQTT)
                "readings": {
                    "temp_c":27.2,"humidity_pct":68,"co2_ppm":780,
                    "vpd_kpa":1.0,"light_umol":395,
                    "ph":6.1,"ec_ms":2.9,
                    "water_temp_c":22,"do_mg_l":8.2,  # dissolved oxygen
                },
                "status":"ok",
                "alerts":[],
            },
            "GH-2": {
                "id":"GH-2","name":"Greenhouse B — Herbs","type":"greenhouse",
                "crop":"Basil / Coriander / Mint","stage":"vegetative","area_m2":80,
                "targets": {
                    "temp_day_c":24,"temp_night_c":16,
                    "humidity_pct":60,"co2_ppm":700,
                    "vpd_kpa":0.9,"light_hours":14,"light_intensity_umol":300,
                    "ph_target":6.0,"ec_target_ms":1.8,
                },
                "readings": {
                    "temp_c":24.1,"humidity_pct":62,"co2_ppm":695,
                    "vpd_kpa":0.88,"light_umol":298,
                    "ph":6.0,"ec_ms":1.85,
                    "water_temp_c":20,"do_mg_l":8.8,
                },
                "status":"ok",
                "alerts":[],
            },
            "VF-1": {
                "id":"VF-1","name":"Vertical Farm — Leafy Greens","type":"vertical_farm",
                "crop":"Lettuce / Spinach / Kale","stage":"vegetative","area_m2":40,
                "rack_levels":8,"plants_per_level":48,"total_plants":384,
                "targets": {
                    "temp_day_c":22,"temp_night_c":18,
                    "humidity_pct":70,"co2_ppm":1000,
                    "vpd_kpa":0.8,"light_hours":18,"light_intensity_umol":250,
                    "ph_target":5.8,"ec_target_ms":1.4,
                },
                "readings": {
                    "temp_c":22.3,"humidity_pct":71,"co2_ppm":985,
                    "vpd_kpa":0.79,"light_umol":248,
                    "ph":5.85,"ec_ms":1.42,
                    "water_temp_c":19,"do_mg_l":9.1,
                },
                "status":"ok",
                "alerts":[],
            },
            "SEED-1": {
                "id":"SEED-1","name":"Seedling Nursery","type":"nursery",
                "crop":"Mixed seedlings","stage":"germination","area_m2":20,
                "targets": {
                    "temp_day_c":28,"temp_night_c":24,
                    "humidity_pct":85,"co2_ppm":500,
                    "vpd_kpa":0.4,"light_hours":12,"light_intensity_umol":150,
                    "ph_target":5.5,"ec_target_ms":0.6,
                },
                "readings": {
                    "temp_c":28.1,"humidity_pct":84,"co2_ppm":498,
                    "vpd_kpa":0.41,"light_umol":149,
                    "ph":5.5,"ec_ms":0.62,
                    "water_temp_c":25,"do_mg_l":9.5,
                },
                "status":"ok",
                "alerts":[],
            },
        },

        # Actuators — controllable hardware per room
        "actuators": {
            "GH-1": {
                "hvac":{"status":"on","mode":"cool","setpoint_c":26},
                "co2_injector":{"status":"on","target_ppm":800},
                "led_rig":{"status":"on","intensity_pct":80,"spectrum":"full","schedule":"06:00-22:00"},
                "nutrient_doser":{"status":"on","recipe":"tomato-fruiting","dosing_ml_hr":120},
                "circulation_pump":{"status":"on","flow_lpm":45},
                "misting":{"status":"off","interval_min":60},
                "shade_cloth":{"status":"retracted","cover_pct":0},
                "roof_vents":{"status":"open","open_pct":40},
            },
            "GH-2": {
                "hvac":{"status":"on","mode":"cool","setpoint_c":24},
                "co2_injector":{"status":"on","target_ppm":700},
                "led_rig":{"status":"on","intensity_pct":60,"spectrum":"veg","schedule":"07:00-21:00"},
                "nutrient_doser":{"status":"on","recipe":"herb-veg","dosing_ml_hr":80},
                "circulation_pump":{"status":"on","flow_lpm":30},
                "misting":{"status":"on","interval_min":30},
                "shade_cloth":{"status":"retracted","cover_pct":0},
                "roof_vents":{"status":"open","open_pct":30},
            },
            "VF-1": {
                "hvac":{"status":"on","mode":"cool","setpoint_c":22},
                "co2_injector":{"status":"on","target_ppm":1000},
                "led_rig":{"status":"on","intensity_pct":65,"spectrum":"full","schedule":"05:00-23:00"},
                "nutrient_doser":{"status":"on","recipe":"leafy-nft","dosing_ml_hr":200},
                "circulation_pump":{"status":"on","flow_lpm":80},
                "misting":{"status":"off","interval_min":0},
                "uv_steriliser":{"status":"on"},
                "rack_motor":{"status":"idle"},
            },
            "SEED-1": {
                "hvac":{"status":"on","mode":"heat","setpoint_c":28},
                "co2_injector":{"status":"off","target_ppm":500},
                "led_rig":{"status":"on","intensity_pct":30,"spectrum":"propagation","schedule":"07:00-19:00"},
                "nutrient_doser":{"status":"on","recipe":"seedling","dosing_ml_hr":20},
                "circulation_pump":{"status":"on","flow_lpm":10},
                "heat_mat":{"status":"on","setpoint_c":26},
                "humidity_pad":{"status":"on"},
            },
        },

        # Indoor robots / rail systems
        "indoor_robots": {
            "RAIL-1": {
                "id":"RAIL-1","name":"VF Harvest Rail","room":"VF-1",
                "type":"overhead_rail","status":"idle",
                "current_task":"Standby","battery_pct":100,
                "capabilities":["harvest","transplant","inspection"],
                "last_harvest":"2025-06-20","next_scheduled":"2025-06-22 06:00",
            },
            "SPRAY-BOT-1": {
                "id":"SPRAY-BOT-1","name":"GH Spray Robot","room":"GH-1",
                "type":"ground_rail","status":"active",
                "current_task":"Foliar spray row 3/8","battery_pct":74,
                "capabilities":["foliar_spray","pruning","pollination"],
            },
            "DOSER-1": {
                "id":"DOSER-1","name":"Nutrient Auto-doser","room":"all",
                "type":"fixed","status":"active",
                "current_task":"Continuous NFT dosing — all rooms",
                "capabilities":["nutrient_dose","ph_adjust","ec_adjust"],
            },
        },
    },

    # ─────────────────────────────────────────────────────────────
    # AUTOMATION ENGINE — shared for outdoor + indoor
    # ─────────────────────────────────────────────────────────────
    "automation": {
        "enabled": True,
        "mode":    "both",    # "outdoor" | "indoor" | "both"

        "rules": [
            # ── OUTDOOR ──────────────────────────────────────
            {
                "id":"auto-1","env":"outdoor","enabled":True,
                "name":"Drought relief",
                "description":"Soil moisture < 45% → MPAR-3 drip irrigation",
                "trigger":{"type":"sensor","sensor":"outdoor.sensors.soil_moisture","operator":"<","threshold":45},
                "action":{"type":"dispatch_robot","robot":"MPAR-3","head":"drip-irrigator"},
                "last_fired":"2025-06-21T14:28:00",
            },
            {
                "id":"auto-2","env":"outdoor","enabled":True,
                "name":"Pest spray",
                "description":"Pest trap > 30 → UAV-2 fungicide spray",
                "trigger":{"type":"sensor","sensor":"outdoor.sensors.pest_traps","operator":">","threshold":30},
                "action":{"type":"dispatch_drone","drone":"UAV-2","mode":"spray","payload":"fungicide"},
                "last_fired":"2025-06-21T08:15:00",
            },
            {
                "id":"auto-3","env":"outdoor","enabled":True,
                "name":"Nitrogen spray",
                "description":"Nitrogen < 50 ppm → UAV-1 foliar nitrogen",
                "trigger":{"type":"sensor","sensor":"outdoor.sensors.nitrogen","operator":"<","threshold":50},
                "action":{"type":"dispatch_drone","drone":"UAV-1","mode":"spray","payload":"foliar-nitrogen"},
                "last_fired":"2025-06-18T11:00:00",
            },
            {
                "id":"auto-4","env":"outdoor","enabled":True,
                "name":"Morning NDVI scan",
                "description":"Every day 07:00 → UAV-1 full-farm survey",
                "trigger":{"type":"schedule","cron":"0 7 * * *"},
                "action":{"type":"dispatch_drone","drone":"UAV-1","mode":"survey","payload":"multispectral"},
                "last_fired":"2025-06-21T07:00:00",
            },
            {
                "id":"auto-5","env":"outdoor","enabled":True,
                "name":"Weed cycle (Monday)",
                "description":"Every Monday 09:00 → MPAR-2 weed all crop zones",
                "trigger":{"type":"schedule","cron":"0 9 * * 1"},
                "action":{"type":"dispatch_robot","robot":"MPAR-2","head":"weeder"},
                "last_fired":"2025-06-16T09:00:00",
            },
            {
                "id":"auto-6","env":"outdoor","enabled":True,
                "name":"Rain guard",
                "description":"Rain forecast > 5mm → cancel all spray missions",
                "trigger":{"type":"weather","condition":"rain_forecast_mm","operator":">","threshold":5},
                "action":{"type":"cancel_spray_missions"},
                "last_fired":None,
            },
            {
                "id":"auto-7","env":"outdoor","enabled":True,
                "name":"Pollination window",
                "description":"Wind < 10 km/h AND temp 20-35°C → UAV-3 pollination",
                "trigger":{"type":"compound","conditions":[
                    {"sensor":"wind_speed_kmh","operator":"<","threshold":10},
                    {"sensor":"air_temp_c","operator":"between","min":20,"max":35},
                ]},
                "action":{"type":"dispatch_drone","drone":"UAV-3","mode":"pollination","payload":"vibration"},
                "last_fired":None,
            },
            {
                "id":"auto-8","env":"outdoor","enabled":True,
                "name":"Low battery recall",
                "description":"Any drone battery < 20% → return to dock",
                "trigger":{"type":"fleet","condition":"any_drone_battery","operator":"<","threshold":20},
                "action":{"type":"return_to_dock"},
                "last_fired":None,
            },
            {
                "id":"auto-9","env":"outdoor","enabled":True,
                "name":"Leaf wetness fungal guard",
                "description":"Leaf wetness > 0.8 for 2+ hours → preventive fungicide UAV-2",
                "trigger":{"type":"sensor","sensor":"outdoor.sensors.leaf_wetness","operator":">","threshold":0.8},
                "action":{"type":"dispatch_drone","drone":"UAV-2","mode":"spray","payload":"preventive-copper"},
                "last_fired":None,
            },
            {
                "id":"auto-10","env":"outdoor","enabled":True,
                "name":"Afternoon soil survey",
                "description":"Every day 15:00 → MPAR-2 soil probe all D zones",
                "trigger":{"type":"schedule","cron":"0 15 * * *"},
                "action":{"type":"dispatch_robot","robot":"MPAR-2","head":"soil-probe"},
                "last_fired":None,
            },
            # ── INDOOR ───────────────────────────────────────
            {
                "id":"in-1","env":"indoor","enabled":True,
                "name":"GH-1 temp high",
                "description":"GH-1 temp > 28°C → HVAC cool mode + open roof vents",
                "trigger":{"type":"indoor_sensor","room":"GH-1","reading":"temp_c","operator":">","threshold":28},
                "action":{"type":"indoor_actuator","room":"GH-1","actuator":"hvac","command":{"mode":"cool","setpoint_c":26}},
                "also":{"type":"indoor_actuator","room":"GH-1","actuator":"roof_vents","command":{"open_pct":80}},
                "last_fired":None,
            },
            {
                "id":"in-2","env":"indoor","enabled":True,
                "name":"GH-1 CO₂ low",
                "description":"GH-1 CO₂ < 600 ppm during lights-on → boost injector",
                "trigger":{"type":"indoor_sensor","room":"GH-1","reading":"co2_ppm","operator":"<","threshold":600},
                "action":{"type":"indoor_actuator","room":"GH-1","actuator":"co2_injector","command":{"target_ppm":900}},
                "last_fired":None,
            },
            {
                "id":"in-3","env":"indoor","enabled":True,
                "name":"pH drift correction",
                "description":"Any room pH outside ±0.3 of target → trigger DOSER-1 pH adjust",
                "trigger":{"type":"indoor_multi","reading":"ph","tolerance":0.3},
                "action":{"type":"indoor_robot","robot":"DOSER-1","command":"ph_adjust"},
                "last_fired":None,
            },
            {
                "id":"in-4","env":"indoor","enabled":True,
                "name":"EC correction",
                "description":"Any room EC outside ±0.3 ms/cm of target → adjust nutrient dose",
                "trigger":{"type":"indoor_multi","reading":"ec_ms","tolerance":0.3},
                "action":{"type":"indoor_robot","robot":"DOSER-1","command":"ec_adjust"},
                "last_fired":None,
            },
            {
                "id":"in-5","env":"indoor","enabled":True,
                "name":"VF-1 harvest schedule",
                "description":"Every Tue & Fri 06:00 → RAIL-1 harvest VF-1",
                "trigger":{"type":"schedule","cron":"0 6 * * 2,5"},
                "action":{"type":"indoor_robot","robot":"RAIL-1","command":"harvest"},
                "last_fired":None,
            },
            {
                "id":"in-6","env":"indoor","enabled":True,
                "name":"GH humidity high",
                "description":"Any GH humidity > 80% → open vents + reduce misting",
                "trigger":{"type":"indoor_multi","reading":"humidity_pct","operator":">","threshold":80},
                "action":{"type":"indoor_actuator_multi","actuator":"roof_vents","command":{"open_pct":100}},
                "last_fired":None,
            },
            {
                "id":"in-7","env":"indoor","enabled":True,
                "name":"Night temp drop",
                "description":"After lights-off: reduce HVAC setpoint to night target for each room",
                "trigger":{"type":"schedule","cron":"0 22 * * *"},
                "action":{"type":"night_mode"},
                "last_fired":None,
            },
            {
                "id":"in-8","env":"indoor","enabled":True,
                "name":"Morning lights-on",
                "description":"06:00 → LEDs on for all rooms at scheduled intensity",
                "trigger":{"type":"schedule","cron":"0 6 * * *"},
                "action":{"type":"lights_on"},
                "last_fired":None,
            },
            {
                "id":"in-9","env":"indoor","enabled":True,
                "name":"VPD guard",
                "description":"VPD outside 0.6-1.4 kPa → adjust HVAC + misting to correct",
                "trigger":{"type":"indoor_multi","reading":"vpd_kpa","operator":"outside_range","min":0.6,"max":1.4},
                "action":{"type":"vpd_correction"},
                "last_fired":None,
            },
            {
                "id":"in-10","env":"indoor","enabled":True,
                "name":"Seedling watering",
                "description":"Every 4 hours → DOSER-1 gentle seedling nutrient cycle",
                "trigger":{"type":"schedule","cron":"0 */4 * * *"},
                "action":{"type":"indoor_robot","robot":"DOSER-1","command":"seedling_cycle","room":"SEED-1"},
                "last_fired":None,
            },
        ],

        "action_log": [
            {"time":"07:00","rule":"auto-4","env":"outdoor","name":"Morning NDVI scan","message":"Dispatched UAV-1 full-farm survey","status":"success"},
            {"time":"08:15","rule":"auto-2","env":"outdoor","name":"Pest spray","message":"Pest trap B3/B4 = 48 → UAV-2 fungicide","status":"success"},
            {"time":"09:00","rule":"in-8", "env":"indoor", "name":"Morning lights-on","message":"LEDs on — GH-1, GH-2, VF-1, SEED-1","status":"success"},
            {"time":"14:28","rule":"auto-1","env":"outdoor","name":"Drought relief","message":"C5 moisture 39% → MPAR-3 drip","status":"success"},
        ],
    },

    # ─────────────────────────────────────────────────────────────
    # SHARED — alerts, tasks, notifications
    # ─────────────────────────────────────────────────────────────
    "alerts": [
        {"id":"alert-1","env":"outdoor","severity":"high","type":"pest","zones":["B3","B4"],"message":"Fungal blight","action":"UAV-2 treating (auto-2)"},
        {"id":"alert-2","env":"outdoor","severity":"medium","type":"nutrient","zones":["A4"],"message":"N 42 ppm low","action":"Foliar spray queued"},
        {"id":"alert-3","env":"outdoor","severity":"medium","type":"moisture","zones":["C5"],"message":"Drought 39%","action":"MPAR-3 irrigating"},
    ],

    "tasks": [
        {"id":"t-1","env":"outdoor","text":"UAV-1 NDVI morning scan","status":"done","time":"07:00","automated":True},
        {"id":"t-2","env":"outdoor","text":"UAV-2 fungicide B3-B4","status":"done","time":"08:15","automated":True},
        {"id":"t-3","env":"indoor","text":"GH-1 nutrient top-up","status":"in-progress","time":"10:00","automated":True},
        {"id":"t-4","env":"outdoor","text":"MPAR-3 drip C5","status":"in-progress","time":"14:28","automated":True},
        {"id":"t-5","env":"indoor","text":"VF-1 harvest (Tue)","status":"queued","time":"06:00","automated":True},
        {"id":"t-6","env":"outdoor","text":"MPAR-1 replant D6","status":"queued","time":"16:00","automated":False},
        {"id":"t-7","env":"indoor","text":"GH-2 pH manual check","status":"pending-approval","time":"","automated":False},
    ],

    # Legacy proxy keys (backward compat)
    "drone": None,
    "robot": None,
}

# Patch legacy keys
farm_state["drone"] = farm_state["outdoor"]["drones"]["UAV-1"]
farm_state["robot"] = farm_state["outdoor"]["robots"]["MPAR-1"]

# AgroNet Backend (Python)

FastAPI backend for the AgroNet v4 farm management platform.

---

## Folder structure

```
agronet-backend/
├── main.py                        ← Entry point — FastAPI app, WebSocket, startup
├── requirements.txt
├── .env.example                   ← Copy to .env and fill in values
│
├── state/
│   └── farm_state.py              ← Single dict of all live farm data
│
├── services/
│   ├── websocket_manager.py       ← Tracks browser connections, broadcasts messages
│   └── mqtt_client.py             ← Receives sensor data from IoT field devices
│
└── routes/
    ├── telemetry.py               ← GET endpoints — dashboard, zones, sensors
    ├── dispatch.py                ← POST drone + robot missions
    ├── irrigation.py              ← GET/POST/PUT schedules + rules
    ├── harvest.py                 ← GET/POST harvest log
    ├── equipment.py               ← GET service records, POST booking
    ├── ai.py                      ← POST AI chat + crop planner (Anthropic API)
    └── tasks.py                   ← GET/PUT task queue approval
```

---

## Setup (step by step)

### 1. Install Python 3.11+

```bash
# Check your version first
python3 --version

# macOS
brew install python@3.11

# Ubuntu
sudo apt install python3.11 python3.11-venv python3-pip
```

### 2. Create a virtual environment

A virtual environment keeps these packages separate from your system Python.

```bash
cd agronet-backend
python3 -m venv venv

# Activate it
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows

# Your terminal prompt should now show (venv)
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables

```bash
cp .env.example .env
```

Open `.env` and set:
- `ANTHROPIC_API_KEY` — from https://console.anthropic.com
- `FRONTEND_URL` — where your HTML file is served, e.g. `http://localhost:8080`

### 5. Start a local MQTT broker

The backend subscribes to sensor data over MQTT. For development, run a
local broker in a separate terminal:

```bash
pip install hbmqtt
hbmqtt
```

Or with Docker (easier):
```bash
docker run -p 1883:1883 eclipse-mosquitto
```

### 6. Run the backend

```bash
uvicorn main:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
MQTT client started — connecting to localhost:1883
```

### 7. Open the interactive API docs

FastAPI generates these automatically:
```
http://localhost:8000/docs
```

Every endpoint is listed there. You can test them by clicking "Try it out".

---

## Connect the frontend

Open `agronet-v4.html` and make two changes:

**Change 1 — Move the AI call to the backend** (removes the API key from the browser):

Find:
```js
const res = await fetch('https://api.anthropic.com/v1/messages', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ model: 'claude-sonnet-4-6', ... })
});
const data = await res.json();
const reply = data.content?.[0]?.text;
```

Replace with:
```js
const res = await fetch('http://localhost:8000/api/ai/chat', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ message: userMsg })
});
const data = await res.json();
const reply = data.reply;
```

**Change 2 — Add a WebSocket connection** for live telemetry:

Add this before `</body>`:
```js
const ws = new WebSocket('ws://localhost:8000/ws');
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  if (msg.type === 'TELEMETRY') {
    const { drone, robot } = msg.payload;
    // Update drone battery bar
    document.querySelector('.bat-fill').style.width = drone.battery_pct + '%';
    // Update robot progress
    document.querySelector('.prog-fill').style.width = robot.mission_progress_pct + '%';
  }

  if (msg.type === 'ALERT_NEW') {
    console.log('New alert:', msg.payload.message);
    // Add to alert list in the UI
  }
};
```

---

## API reference

### Telemetry (page load data)

| Method | URL | What it returns |
|--------|-----|-----------------|
| GET | /api/telemetry/dashboard | Metric card values |
| GET | /api/telemetry/zones | All 24 zone objects |
| GET | /api/telemetry/zones/{id} | Single zone tooltip data |
| GET | /api/telemetry/sensors | All sensor readings |
| GET | /api/telemetry/drone | UAV-1 full status |
| GET | /api/telemetry/robot | MPAR-1 full status |
| GET | /api/telemetry/weather | 7-day forecast |
| GET | /api/telemetry/alerts | Active alerts |
| GET | /api/telemetry/spray-log | Spray history |

### Dispatch

```bash
# Send UAV-1 to spray fungicide
curl -X POST http://localhost:8000/api/dispatch/drone \
  -H "Content-Type: application/json" \
  -d '{"mode": "spray", "zones": ["B3","B4"], "payload": "fungicide"}'

# Assign MPAR-1 weeder head to Zone C
curl -X POST http://localhost:8000/api/dispatch/robot \
  -H "Content-Type: application/json" \
  -d '{"head": "weeder", "zone": "C", "task": "Inter-row mechanical weeding"}'
```

### AI

```bash
# Ask the AI Advisor a question
curl -X POST http://localhost:8000/api/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What should I spray today?"}'

# Get crop recommendations for Zone D6
curl -X POST http://localhost:8000/api/ai/crop-plan \
  -H "Content-Type: application/json" \
  -d '{"zone": "D6", "season": "monsoon"}'
```

### Tasks

```bash
# Approve task-7 (reschedule irrigation)
curl -X PUT http://localhost:8000/api/tasks/task-7 \
  -H "Content-Type: application/json" \
  -d '{"action": "approve"}'
```

---

## Simulating sensor data (no hardware needed)

With the MQTT broker running, publish fake readings from a terminal:

```bash
pip install paho-mqtt

python3 - << 'EOF'
import paho.mqtt.publish as publish
import json

# Simulate drought stress in Zone C5
publish.single(
    "agronet/farm-001/sensor/soil_moisture/C5",
    json.dumps({"value": 28}),
    hostname="localhost"
)

# Simulate high pest count in Zone B3
publish.single(
    "agronet/farm-001/sensor/pest_trap/B3",
    json.dumps({"value": 62}),
    hostname="localhost"
)

# Simulate UAV-1 telemetry
publish.single(
    "agronet/farm-001/drone/telemetry",
    json.dumps({"battery_pct": 45, "status": "spraying", "mission_progress_pct": 72}),
    hostname="localhost"
)
EOF
```

Each message flows into `farm_state`, triggers threshold checks, and
broadcasts an `ALERT_NEW` to the browser via WebSocket.

---

## WebSocket message types

| Type | When sent | Key payload fields |
|------|-----------|--------------------|
| `FULL_STATE` | On browser connect | Entire farm_state |
| `TELEMETRY` | Every 3 seconds | drone, robot, environment, alert_count |
| `SENSOR` | MQTT reading arrives | sensor_type, zone, value |
| `ALERT_NEW` | Threshold crossed | id, severity, zone, message |
| `ALERT_CLEAR` | Alert resolved | id |
| `DRONE_QUEUE_UPDATE` | Mission dispatched | Full mission queue |
| `ROBOT_QUEUE_UPDATE` | Task assigned | Full head queue |
| `IRRIGATION_RUN` | Run-now triggered | zone |
| `HARVEST_LOGGED` | Manual entry added | date, entry |
| `TASK_UPDATE` | Task actioned | Full task object |

---

## How it all connects

```
Browser (agronet-v4.html)
    │
    ├── GET  /api/telemetry/*      on page load (zones, sensors, drone, robot)
    ├── POST /api/dispatch/drone   when a spray/survey button is clicked
    ├── POST /api/dispatch/robot   when a harvest/weed/seed task is assigned
    ├── POST /api/ai/chat          when the AI Advisor send button is clicked
    ├── POST /api/ai/crop-plan     when the Crop Planner runs
    ├── PUT  /api/tasks/{id}       when Approve/Defer is clicked
    └── WebSocket ws://localhost:8000/ws  ← live telemetry every 3s

agronet-backend (this server)
    │
    ├── MQTT subscribe  ← soil sensors, weather station, pest traps
    ├── MQTT subscribe  ← UAV-1 telemetry (once real drone connected)
    ├── MQTT subscribe  ← MPAR-1 telemetry (once real robot connected)
    └── HTTPS POST      → Anthropic API (AI chat + crop planner)
```

---

## Production checklist

- [ ] Replace `farm_state` dict with PostgreSQL + TimescaleDB for sensor history
- [ ] Add JWT authentication (`pip install python-jose`)
- [ ] Move ANTHROPIC_API_KEY to a secrets manager (AWS Secrets Manager / HashiCorp Vault)
- [ ] Replace GCS stub in `dispatch.py` with real MAVLink GCS HTTP call
- [ ] Replace robot stub with ROS 2 action client (`pip install rclpy`)
- [ ] Deploy with `gunicorn -w 1 -k uvicorn.workers.UvicornWorker main:app` (keep 1 worker — state is in-memory)
- [ ] Put Nginx in front with HTTPS + SSL certificate (Let's Encrypt)
- [ ] Run on a Raspberry Pi 5 on the farm LAN for low-latency hardware control

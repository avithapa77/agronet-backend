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

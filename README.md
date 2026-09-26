# Vehicle API Simulator

A simple vehicle API simulator built with Python and FastAPI.

This project provides a virtual vehicle environment that exposes vehicle information through REST APIs.

The project is intended for learning and experimentation with:

* Vehicle APIs
* REST APIs
* FastAPI
* Python
* Docker
* MQTT
* Vehicle data simulation
* Middleware and distributed systems

## Architecture

```text
┌─────────────────────────┐
│   Vehicle API Simulator │
│                         │
│  Speed                  │
│  Battery                │
│  Position               │
│  Steering               │
└────────────┬────────────┘
             │
             │ REST API
             ▼
┌─────────────────────────┐
│        FastAPI          │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ API Client / Web Browser │
└─────────────────────────┘
```

## Requirements

* Python 3.9+
* pip
* Git

## Setup

Clone the repository:

```bash
git clone https://github.com/naosyke/vehicle-api-simulator.git
cd vehicle-api-simulator
```

Create a virtual environment:

```bash
python3 -m venv .venv
```

Activate the virtual environment.

### macOS / Linux

```bash
source .venv/bin/activate
```

### Windows PowerShell

```powershell
.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Start the Server

Run:

```bash
uvicorn app.main:app --reload
```

The server will start at:

```text
http://127.0.0.1:8000
```

## API Documentation

FastAPI automatically provides interactive API documentation.

Open:

```text
http://127.0.0.1:8000/docs
```

You can execute API requests directly from the browser.

## Available APIs

All request and response bodies are JSON. Invalid values return `422`, and
commands that are not allowed in the current vehicle state return `409`.

### Vehicle State

| Method | Path | Description |
|---|---|---|
| GET | `/vehicle` | Full vehicle state |
| GET | `/vehicle/speed` | Current and target speed (km/h) |
| POST | `/vehicle/speed` | Set the speed immediately `{"speed": 30}` |
| POST | `/vehicle/target-speed` | Accelerate / decelerate toward a speed `{"speed": 60}` |
| GET / POST | `/vehicle/steering` | Road wheel angle in degrees, -35 to 35, left positive `{"angle": 10}` |
| GET / POST | `/vehicle/position` | Position in meters `{"x": 0, "y": 0}` |
| GET | `/vehicle/doors` | All doors |
| GET / POST | `/vehicle/doors/{door_id}` | `front_left`, `front_right`, `rear_left`, `rear_right` `{"open": true, "locked": false}` |
| GET / POST | `/vehicle/lights` | `{"headlights": "off" \| "low" \| "high", "hazard": false}` |
| GET / POST | `/vehicle/battery` | State of charge in percent `{"level": 80}` |
| POST | `/vehicle/charging` | Start / stop charging `{"charging": true}` |

Example response of `GET /vehicle`:

```json
{
  "speed": 32.7,
  "target_speed": 60.0,
  "battery": 99.9957,
  "charging": false,
  "position": {"x": 13.336, "y": 3.03},
  "heading": 25.6,
  "steering": 5.0,
  "odometer": 0.0138,
  "doors": {
    "front_left": {"open": false, "locked": true},
    "front_right": {"open": false, "locked": true},
    "rear_left": {"open": false, "locked": true},
    "rear_right": {"open": false, "locked": true}
  },
  "lights": {"headlights": "off", "hazard": false}
}
```

### Vehicle Rules

* A locked door cannot be opened (unlock it in the same or an earlier request).
* Doors cannot be opened while the vehicle is moving.
* The vehicle cannot drive with a door open, while charging, or with an empty battery.
* Charging is not allowed while moving and stops automatically at 100 %.
* When the battery reaches 0 %, the vehicle decelerates to a stop.

### Simulation

| Method | Path | Description |
|---|---|---|
| GET | `/simulation` | Whether the periodic update loop is running, tick interval, elapsed time |
| POST | `/simulation/step` | Advance the simulation manually `{"seconds": 1.0}` |
| POST | `/simulation/reset` | Reset the vehicle to its initial state |

The vehicle moves with a kinematic bicycle model:

| Parameter | Value |
|---|---|
| Wheelbase | 2.7 m |
| Acceleration / deceleration | 3.0 / 6.0 m/s² |
| Max speed | 180 km/h |
| Battery | 60 kWh, 0.15 kWh/km, 0.5 kW idle |
| Charging power | 50 kW |

Coordinates: `x` = east, `y` = north, heading 0° = east, counter-clockwise positive.

### Configuration

| Environment variable | Default | Description |
|---|---|---|
| `SIM_AUTO_UPDATE` | `1` | Set to `0` to disable the periodic update loop and use `/simulation/step` only |
| `SIM_TICK_SECONDS` | `0.1` | Periodic update interval in seconds |

## Run Tests

Run:

```bash
python -m pytest
```

## Project Structure

```text
vehicle-api-simulator/
│
├── app/
│   ├── __init__.py
│   ├── main.py        # REST API and periodic update loop
│   ├── models.py      # Request / response models
│   └── simulator.py   # Vehicle state and physics
│
├── tests/
│   ├── conftest.py
│   ├── test_main.py
│   └── test_simulator.py
│
├── .gitignore
├── README.md
└── requirements.txt
```

## Roadmap

### Phase 1 - REST API

* [x] Basic vehicle API
* [x] Vehicle state model
* [x] API documentation
* [x] Basic tests

### Phase 2 - Vehicle Control

* [x] Change vehicle speed
* [x] Change steering
* [x] Change vehicle position
* [x] Door state
* [x] Lights
* [x] Battery state

### Phase 3 - Vehicle Simulation

* [x] Automatic vehicle movement
* [x] Acceleration / deceleration
* [x] Vehicle physics
* [x] Periodic state updates

### Phase 4 - Docker

* [ ] Dockerfile
* [ ] Docker Compose
* [ ] Containerized development environment

### Phase 5 - MQTT

* [ ] MQTT broker
* [ ] Vehicle telemetry
* [ ] Vehicle event publishing
* [ ] Subscriber

### Phase 6 - Dashboard

* [ ] Real-time vehicle monitoring
* [ ] Speed graph
* [ ] Battery graph
* [ ] Position visualization

### Phase 7 - AI

* [ ] Driving data analysis
* [ ] Abnormal behavior detection
* [ ] AI vehicle assistant
* [ ] AI agent integration

## Disclaimer

This project is an independent learning and development project.

It does not contain proprietary source code, specifications, or confidential information from any employer or third party.

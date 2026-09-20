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

* Python 3.10+
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

### Get Vehicle Information

```http
GET /vehicle
```

Example response:

```json
{
  "speed": 0.0,
  "battery": 100.0,
  "position": {
    "x": 0.0,
    "y": 0.0
  },
  "steering": 0.0
}
```

### Get Vehicle Speed

```http
GET /vehicle/speed
```

Example response:

```json
{
  "speed": 0.0
}
```

### Get Vehicle Position

```http
GET /vehicle/position
```

Example response:

```json
{
  "x": 0.0,
  "y": 0.0
}
```

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
│   └── main.py
│
├── tests/
│   └── test_main.py
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

* [ ] Change vehicle speed
* [ ] Change steering
* [ ] Change vehicle position
* [ ] Door state
* [ ] Lights
* [ ] Battery state

### Phase 3 - Vehicle Simulation

* [ ] Automatic vehicle movement
* [ ] Acceleration / deceleration
* [ ] Vehicle physics
* [ ] Periodic state updates

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

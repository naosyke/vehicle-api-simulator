# Architecture

This document describes how the Vehicle API Simulator is deployed with Docker,
how its components communicate, and how data flows through the system.

## 1. System Overview

Two containers run on a Docker Compose network. Clients on the host talk to
the simulator over REST and receive vehicle data from the broker over MQTT.
The host ports shown are the defaults (`API_PORT`, `MQTT_PORT`).

```mermaid
flowchart LR
    browser["Web browser / API client<br/>curl, /docs"]
    dashboard["Dashboard<br/>/dashboard"]
    subscriber["Subscriber<br/>tools/subscriber.py"]
    ai["AI assistant<br/>Claude Desktop / Claude Code"]
    mcp["MCP server<br/>mcp_server/server.py"]

    subgraph compose["Docker Compose network: vehicle-api-simulator_default"]
        direction LR
        api["vehicle-api<br/>FastAPI + simulator<br/>container port 8000"]
        broker["mosquitto<br/>eclipse-mosquitto:2<br/>container port 1883"]
    end

    browser -- "HTTP REST<br/>localhost:8000" --> api
    dashboard -- "REST commands + WebSocket /ws<br/>localhost:8000" --> api
    ai -- "MCP over stdio<br/>(launched by the client)" --> mcp
    mcp -- "HTTP REST<br/>VEHICLE_API_URL" --> api
    api -- "MQTT publish<br/>mosquitto:1883" --> broker
    broker -- "MQTT subscribe<br/>localhost:1883" --> subscriber
```

| Container | Image | Role | Host port → container port |
|---|---|---|---|
| `vehicle-api` | Built from `Dockerfile` (python:3.12-slim) | REST API, vehicle simulation, MQTT publisher | `${API_PORT:-8000}` → `8000` |
| `mosquitto` | `eclipse-mosquitto:2` | MQTT broker | `${MQTT_PORT:-1883}` → `1883` |

Inside the Compose network, `vehicle-api` reaches the broker by its service
name (`MQTT_HOST=mosquitto`). Clients on the host use `localhost` and the
published ports.

## 2. Docker Configuration

```mermaid
flowchart TB
    subgraph repo["Repository (host)"]
        appdir["./app"]
        testsdir["./tests"]
        conf["./mosquitto/mosquitto.conf"]
        dockerfile["Dockerfile"]
    end

    subgraph api["vehicle-api container (user: appuser)"]
        appmount["/app/app"]
        testsmount["/app/tests"]
        uvicorn["uvicorn app.main:app --reload"]
    end

    subgraph broker["mosquitto container"]
        confmount["/mosquitto/config/mosquitto.conf"]
        mosq["mosquitto"]
    end

    dockerfile -- "docker compose build" --> api
    appdir -- "bind mount" --> appmount
    testsdir -- "bind mount" --> testsmount
    conf -- "bind mount (read-only)" --> confmount
    appmount --> uvicorn
    confmount --> mosq
```

- `app/` is mounted into the container, and uvicorn reloads it when files change.
- `vehicle-api` starts after `mosquitto` (`depends_on`). It also works if the
  broker becomes available later, because the MQTT client keeps reconnecting.
- The broker allows anonymous connections without TLS. This setup is for local
  development only.

## 3. Components inside vehicle-api

```mermaid
flowchart LR
    client["REST client / Dashboard"]
    broker["mosquitto"]

    subgraph process["vehicle-api process"]
        direction LR
        endpoints["FastAPI endpoints<br/>(thread pool)"]

        subgraph loops["asyncio event loop"]
            direction TB
            simloop["Simulation loop<br/>every 0.1 s"]
            telloop["Telemetry loop<br/>every 1.0 s"]
        end

        sim["VehicleSimulator<br/>state · physics · rules<br/>(protected by a lock)"]
        publisher["MqttPublisher"]
        paho["paho-mqtt<br/>network thread"]
        hub["WebSocketHub"]
        ws["WebSocket /ws<br/>state every 0.2 s + events"]
    end

    client -- "HTTP" --> endpoints
    endpoints -- "commands /<br/>snapshot()" --> sim
    simloop -- "step(dt)" --> sim
    telloop -- "snapshot()" --> sim
    sim -- "events<br/>(listener)" --> publisher
    telloop -- "publish_telemetry()" --> publisher
    publisher --> paho
    paho -- "MQTT" --> broker
    sim -- "events<br/>(listener)" --> hub
    hub --> ws
    ws -- "WebSocket" --> client
```

| Component | File | Responsibility |
|---|---|---|
| FastAPI endpoints | `app/main.py` | REST API, validation (`422`), state errors (`409`) |
| Background loops | `app/main.py` | Run the simulation and publish telemetry periodically |
| VehicleSimulator | `app/simulator.py` | Vehicle state, physics, state rules, events |
| MqttPublisher | `app/mqtt_publisher.py` | Send telemetry, events and online/offline status to MQTT |
| WebSocketHub | `app/websocket_hub.py` | Deliver events to each WebSocket client's queue from any thread |
| Dashboard | `app/static/dashboard.html` | Browser UI: tiles, charts, trajectory, controls, event log |
| Models | `app/models.py` | Request and response schemas |

Thread safety: endpoints run in a thread pool and the loops run on the event
loop, so `VehicleSimulator` protects its state with a lock. Events are
collected while the lock is held and delivered to listeners after it is
released, so a slow listener never blocks the simulation.

## 4. Data Flow

### Command → event → subscriber

```mermaid
sequenceDiagram
    autonumber
    participant C as REST client
    participant A as FastAPI endpoint
    participant S as VehicleSimulator
    participant P as MqttPublisher
    participant B as mosquitto
    participant Sub as Subscriber

    C->>A: POST /vehicle/doors/front_left {"open": true, "locked": false}
    A->>S: update_door()
    alt Vehicle is moving or door is locked
        S-->>A: VehicleStateError
        A-->>C: 409 Conflict
    else Allowed
        S->>S: Update state (under lock)
        S-->>A: Door
        A-->>C: 200 OK
        S->>P: door_opened, door_unlocked (after the lock is released)
        P->>B: PUBLISH vehicle/sim-001/events (QoS 1)
        B->>Sub: door_opened, door_unlocked
    end
```

### Periodic telemetry

```mermaid
sequenceDiagram
    participant L as Simulation loop (0.1 s)
    participant T as Telemetry loop (1.0 s)
    participant S as VehicleSimulator
    participant P as MqttPublisher
    participant B as mosquitto
    participant Sub as Subscriber

    loop every 0.1 s
        L->>S: step(dt)
        S->>S: Update speed, position, heading, battery
        opt State threshold crossed
            S->>P: vehicle_started / vehicle_stopped / battery_low ...
            P->>B: PUBLISH vehicle/sim-001/events (QoS 1)
        end
    end
    loop every 1.0 s
        T->>S: snapshot()
        T->>P: publish_telemetry()
        P->>B: PUBLISH vehicle/sim-001/telemetry (QoS 0)
        B->>Sub: telemetry
    end
```

### Connection status (Last Will)

```mermaid
sequenceDiagram
    participant P as MqttPublisher
    participant B as mosquitto
    participant Sub as Subscriber

    P->>B: CONNECT (will: vehicle/sim-001/status = "offline", retained)
    P->>B: PUBLISH vehicle/sim-001/status = "online" (retained)
    B->>Sub: online
    Note over P,B: vehicle-api stops or the connection drops
    B->>Sub: offline (published by the broker or on clean shutdown)
    Note over B,Sub: New subscribers get the last status immediately (retained)
```

### Dashboard (WebSocket)

The dashboard is served by the API and does not depend on the broker.
Each WebSocket client gets its own queue, so a slow browser drops events
instead of slowing down the simulator.

```mermaid
sequenceDiagram
    participant D as Dashboard (browser)
    participant A as FastAPI
    participant H as WebSocketHub
    participant S as VehicleSimulator

    D->>A: GET /dashboard
    D->>A: WebSocket /ws
    A->>H: subscribe()
    loop every 0.2 s
        A->>S: snapshot()
        A-->>D: {"kind": "state", "vehicle": ...}
    end
    D->>A: POST /vehicle/lights {"hazard": true}
    A->>S: update_lights()
    S->>H: lights_changed
    H-->>A: event via the client's queue
    A-->>D: {"kind": "event", "type": "lights_changed", ...}
```

### AI assistant (MCP)

The MCP server runs on the host, launched by the AI client as a subprocess
and connected over stdio. It is a thin adapter: every tool maps to one REST
call, so the vehicle rules are enforced by the simulator, not by the AI.

```mermaid
sequenceDiagram
    actor U as User
    participant C as Claude (Desktop / Code)
    participant M as MCP server
    participant A as vehicle-api

    U->>C: "Open the front left door"
    C->>M: call_tool set_door {door: front_left, open: true}
    M->>A: POST /vehicle/doors/front_left {"open": true}
    A-->>M: 409 Door front_left is locked
    M-->>C: is_error: "Rejected by the vehicle: Door front_left is locked"
    C->>U: "The door is locked. Shall I unlock it and open it?"
    U->>C: "Yes"
    C->>M: call_tool set_door {door: front_left, open: true, locked: false}
    M->>A: POST /vehicle/doors/front_left
    A-->>M: 200 {"open": true, "locked": false}
    M-->>C: result
    C->>U: "Unlocked and opened the front left door."
```

| Tool type | Tools | MCP annotation |
|---|---|---|
| Read | `get_vehicle_status`, `get_recent_events`, `get_simulation_status` | `readOnlyHint` |
| Control | `set_target_speed`, `set_steering`, `set_door`, `set_lights`, `set_charging`, `advance_simulation` | - |
| Destructive | `reset_simulation` | `destructiveHint` |

## 5. MQTT Topics

| Topic | Direction | QoS | Retained | Payload |
|---|---|---|---|---|
| `vehicle/{vehicle_id}/telemetry` | simulator → broker | 0 | No | Full vehicle state + `vehicle_id`, `timestamp` |
| `vehicle/{vehicle_id}/events` | simulator → broker | 1 | No | `{"vehicle_id", "timestamp", "type", "data"}` |
| `vehicle/{vehicle_id}/status` | simulator / broker → subscribers | 1 | Yes | `online` or `offline` |

Telemetry uses QoS 0 because a newer sample replaces a lost one. Events use
QoS 1 so that state changes such as `door_opened` are delivered at least once.

Subscribers can use wildcards, for example `vehicle/+/events` for events from
all vehicles.

## 6. Ports and Configuration

| Setting | Default | Where | Description |
|---|---|---|---|
| `API_PORT` | `8000` | host (Compose) | Host port for the REST API |
| `MQTT_PORT` | `1883` | host (Compose) | Host port for the broker |
| `MQTT_PORT` | `1883` | container | Broker port the simulator connects to (set in `docker-compose.yml`) |
| `MQTT_HOST` | unset (`mosquitto` in Compose) | container | Broker host. MQTT is disabled when unset |
| `VEHICLE_ID` | `sim-001` | container | Vehicle ID used in topics |
| `SIM_AUTO_UPDATE` | `1` | container | `0` disables the simulation loop |
| `SIM_TICK_SECONDS` | `0.1` | container | Simulation step interval |
| `TELEMETRY_INTERVAL_SECONDS` | `1.0` | container | Telemetry publish interval |
| `WS_INTERVAL_SECONDS` | `0.2` | container | Dashboard WebSocket state interval |

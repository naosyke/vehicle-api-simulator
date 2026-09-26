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
    subscriber["Subscriber<br/>tools/subscriber.py"]

    subgraph compose["Docker Compose network: vehicle-api-simulator_default"]
        direction LR
        api["vehicle-api<br/>FastAPI + simulator<br/>container port 8000"]
        broker["mosquitto<br/>eclipse-mosquitto:2<br/>container port 1883"]
    end

    browser -- "HTTP REST<br/>localhost:8000" --> api
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
    client["REST client"]
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
    end

    client -- "HTTP" --> endpoints
    endpoints -- "commands /<br/>snapshot()" --> sim
    simloop -- "step(dt)" --> sim
    telloop -- "snapshot()" --> sim
    sim -- "events<br/>(listener)" --> publisher
    telloop -- "publish_telemetry()" --> publisher
    publisher --> paho
    paho -- "MQTT" --> broker
```

| Component | File | Responsibility |
|---|---|---|
| FastAPI endpoints | `app/main.py` | REST API, validation (`422`), state errors (`409`) |
| Background loops | `app/main.py` | Run the simulation and publish telemetry periodically |
| VehicleSimulator | `app/simulator.py` | Vehicle state, physics, state rules, events |
| MqttPublisher | `app/mqtt_publisher.py` | Send telemetry, events and online/offline status to MQTT |
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

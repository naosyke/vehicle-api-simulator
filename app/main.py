import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse

from app.models import (
    BatteryRequest,
    ChargingRequest,
    Door,
    DoorId,
    DoorRequest,
    Lights,
    LightsRequest,
    Position,
    SimulationStatus,
    SpeedRequest,
    SteeringRequest,
    StepRequest,
    Vehicle,
)
from app.mqtt_publisher import MqttPublisher
from app.simulator import VehicleSimulator, VehicleStateError
from app.websocket_hub import WebSocketHub


VERSION = "0.4.0"

# Set SIM_AUTO_UPDATE=0 to disable the background loop and drive the
# simulation only through POST /simulation/step.
AUTO_UPDATE = os.getenv("SIM_AUTO_UPDATE", "1") != "0"
TICK_SECONDS = float(os.getenv("SIM_TICK_SECONDS", "0.1"))

# MQTT publishing is enabled when MQTT_HOST is set.
MQTT_HOST = os.getenv("MQTT_HOST")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
VEHICLE_ID = os.getenv("VEHICLE_ID", "sim-001")
TELEMETRY_INTERVAL_SECONDS = float(os.getenv("TELEMETRY_INTERVAL_SECONDS", "1.0"))

# Interval of state updates pushed to dashboard WebSocket clients.
WS_INTERVAL_SECONDS = float(os.getenv("WS_INTERVAL_SECONDS", "0.2"))

STATIC_DIR = Path(__file__).parent / "static"


simulator = VehicleSimulator()
simulation_running = False
mqtt_publisher = None

websocket_hub = WebSocketHub()
simulator.add_listener(
    lambda event_type, data: websocket_hub.publish({
        "kind": "event",
        "timestamp": time.time(),
        "type": event_type,
        "data": data,
    })
)


async def run_simulation_loop():
    last = time.monotonic()
    while True:
        await asyncio.sleep(TICK_SECONDS)
        now = time.monotonic()
        simulator.step(now - last)
        last = now


async def run_telemetry_loop(publisher):
    while True:
        publisher.publish_telemetry(simulator.snapshot())
        await asyncio.sleep(TELEMETRY_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app):
    global simulation_running, mqtt_publisher

    tasks = []
    if AUTO_UPDATE:
        tasks.append(asyncio.create_task(run_simulation_loop()))
        simulation_running = True

    if MQTT_HOST:
        mqtt_publisher = MqttPublisher(MQTT_HOST, MQTT_PORT, VEHICLE_ID)
        mqtt_publisher.start()
        simulator.add_listener(mqtt_publisher.publish_event)
        tasks.append(asyncio.create_task(run_telemetry_loop(mqtt_publisher)))

    yield

    for task in tasks:
        task.cancel()
    simulation_running = False

    if mqtt_publisher is not None:
        simulator.remove_listener(mqtt_publisher.publish_event)
        mqtt_publisher.stop()
        mqtt_publisher = None


app = FastAPI(
    title="Vehicle API Simulator",
    description="A simple vehicle API simulator",
    version=VERSION,
    lifespan=lifespan,
)


def conflict(error):
    return HTTPException(status_code=409, detail=str(error))


@app.get("/")
def root():
    return {
        "message": "Vehicle API Simulator",
        "version": VERSION,
    }


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.websocket("/ws")
async def vehicle_stream(websocket: WebSocket):
    """Stream vehicle state every WS_INTERVAL_SECONDS and events as they happen.

    Messages are JSON objects with "kind" set to "state" or "event".
    """
    await websocket.accept()
    queue = websocket_hub.subscribe()
    loop = asyncio.get_running_loop()

    try:
        next_state_at = loop.time()
        while True:
            timeout = next_state_at - loop.time()
            if timeout <= 0:
                await websocket.send_json({
                    "kind": "state",
                    "timestamp": time.time(),
                    "vehicle": simulator.snapshot().model_dump(mode="json"),
                })
                next_state_at = loop.time() + WS_INTERVAL_SECONDS
                continue

            try:
                event = await asyncio.wait_for(queue.get(), timeout)
            except asyncio.TimeoutError:
                continue
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        websocket_hub.unsubscribe(queue)


@app.get("/vehicle", response_model=Vehicle)
def get_vehicle():
    return simulator.snapshot()


@app.get("/vehicle/speed")
def get_speed():
    vehicle = simulator.snapshot()
    return {
        "speed": vehicle.speed,
        "target_speed": vehicle.target_speed,
    }


@app.post("/vehicle/speed")
def set_speed(request: SpeedRequest):
    """Set the speed immediately."""
    try:
        simulator.set_speed(request.speed)
    except VehicleStateError as error:
        raise conflict(error)

    return {
        "speed": simulator.snapshot().speed
    }


@app.post("/vehicle/target-speed")
def set_target_speed(request: SpeedRequest):
    """Accelerate or decelerate toward the given speed."""
    try:
        simulator.set_target_speed(request.speed)
    except VehicleStateError as error:
        raise conflict(error)

    return {
        "target_speed": simulator.snapshot().target_speed
    }


@app.get("/vehicle/steering")
def get_steering():
    return {
        "steering": simulator.snapshot().steering
    }


@app.post("/vehicle/steering")
def set_steering(request: SteeringRequest):
    simulator.set_steering(request.angle)

    return {
        "steering": simulator.snapshot().steering
    }


@app.get("/vehicle/position", response_model=Position)
def get_position():
    return simulator.snapshot().position


@app.post("/vehicle/position", response_model=Position)
def set_position(request: Position):
    simulator.set_position(request.x, request.y)
    return simulator.snapshot().position


@app.get("/vehicle/doors")
def get_doors():
    return simulator.snapshot().doors


@app.get("/vehicle/doors/{door_id}", response_model=Door)
def get_door(door_id: DoorId):
    return simulator.snapshot().doors[door_id]


@app.post("/vehicle/doors/{door_id}", response_model=Door)
def update_door(door_id: DoorId, request: DoorRequest):
    try:
        return simulator.update_door(door_id, open=request.open, locked=request.locked)
    except VehicleStateError as error:
        raise conflict(error)


@app.get("/vehicle/lights", response_model=Lights)
def get_lights():
    return simulator.snapshot().lights


@app.post("/vehicle/lights", response_model=Lights)
def update_lights(request: LightsRequest):
    return simulator.update_lights(headlights=request.headlights, hazard=request.hazard)


@app.get("/vehicle/battery")
def get_battery():
    vehicle = simulator.snapshot()
    return {
        "battery": vehicle.battery,
        "charging": vehicle.charging,
    }


@app.post("/vehicle/battery")
def set_battery(request: BatteryRequest):
    simulator.set_battery(request.level)
    return get_battery()


@app.post("/vehicle/charging")
def set_charging(request: ChargingRequest):
    try:
        simulator.set_charging(request.charging)
    except VehicleStateError as error:
        raise conflict(error)
    return get_battery()


@app.get("/simulation", response_model=SimulationStatus)
def get_simulation():
    return SimulationStatus(
        running=simulation_running,
        tick_seconds=TICK_SECONDS,
        elapsed_seconds=round(simulator.elapsed_seconds, 3),
        mqtt_enabled=mqtt_publisher is not None,
        mqtt_connected=mqtt_publisher is not None and mqtt_publisher.connected,
    )


@app.post("/simulation/step", response_model=Vehicle)
def step_simulation(request: StepRequest):
    """Advance the simulation manually. Useful for tests and scripted scenarios."""
    simulator.step(request.seconds)
    return simulator.snapshot()


@app.post("/simulation/reset", response_model=Vehicle)
def reset_simulation():
    simulator.reset()
    return simulator.snapshot()

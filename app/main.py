import asyncio
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

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
from app.simulator import VehicleSimulator, VehicleStateError


VERSION = "0.2.0"

# Set SIM_AUTO_UPDATE=0 to disable the background loop and drive the
# simulation only through POST /simulation/step.
AUTO_UPDATE = os.getenv("SIM_AUTO_UPDATE", "1") != "0"
TICK_SECONDS = float(os.getenv("SIM_TICK_SECONDS", "0.1"))


simulator = VehicleSimulator()
simulation_running = False


async def run_simulation_loop():
    last = time.monotonic()
    while True:
        await asyncio.sleep(TICK_SECONDS)
        now = time.monotonic()
        simulator.step(now - last)
        last = now


@asynccontextmanager
async def lifespan(app):
    global simulation_running

    task = None
    if AUTO_UPDATE:
        task = asyncio.create_task(run_simulation_loop())
        simulation_running = True

    yield

    if task is not None:
        task.cancel()
        simulation_running = False


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

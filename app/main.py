from fastapi import FastAPI
from pydantic import BaseModel


app = FastAPI(
    title="Vehicle API Simulator",
    description="A simple vehicle API simulator",
    version="0.1.0",
)


class Position(BaseModel):
    x: float
    y: float


class Vehicle(BaseModel):
    speed: float
    battery: float
    position: Position
    steering: float


vehicle = Vehicle(
    speed=0.0,
    battery=100.0,
    position=Position(x=0.0, y=0.0),
    steering=0.0,
)


@app.get("/")
def root():
    return {
        "message": "Vehicle API Simulator",
        "version": "0.1.0",
    }


@app.get("/vehicle", response_model=Vehicle)
def get_vehicle():
    return vehicle


@app.get("/vehicle/speed")
def get_speed():
    return {
        "speed": vehicle.speed
    }


@app.get("/vehicle/position")
def get_position():
    return vehicle.position
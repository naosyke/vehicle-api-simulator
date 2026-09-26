from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, Field


MAX_SPEED_KMH = 180.0
MAX_STEERING_DEG = 35.0


class Position(BaseModel):
    x: float = Field(0.0, description="East position in meters")
    y: float = Field(0.0, description="North position in meters")


class DoorId(str, Enum):
    front_left = "front_left"
    front_right = "front_right"
    rear_left = "rear_left"
    rear_right = "rear_right"


class Door(BaseModel):
    open: bool = False
    locked: bool = True


class HeadlightMode(str, Enum):
    off = "off"
    low = "low"
    high = "high"


class Lights(BaseModel):
    headlights: HeadlightMode = HeadlightMode.off
    hazard: bool = False


class Vehicle(BaseModel):
    speed: float = Field(description="Current speed in km/h")
    target_speed: float = Field(description="Speed the vehicle is accelerating toward, in km/h")
    battery: float = Field(description="State of charge in percent")
    charging: bool
    position: Position
    heading: float = Field(description="Heading in degrees, 0 = east, counter-clockwise positive")
    steering: float = Field(description="Road wheel angle in degrees, left positive")
    odometer: float = Field(description="Total distance travelled in km")
    doors: Dict[DoorId, Door]
    lights: Lights


class SpeedRequest(BaseModel):
    speed: float = Field(ge=0.0, le=MAX_SPEED_KMH)


class SteeringRequest(BaseModel):
    angle: float = Field(ge=-MAX_STEERING_DEG, le=MAX_STEERING_DEG)


class DoorRequest(BaseModel):
    open: Optional[bool] = None
    locked: Optional[bool] = None


class LightsRequest(BaseModel):
    headlights: Optional[HeadlightMode] = None
    hazard: Optional[bool] = None


class BatteryRequest(BaseModel):
    level: float = Field(ge=0.0, le=100.0)


class ChargingRequest(BaseModel):
    charging: bool


class StepRequest(BaseModel):
    seconds: float = Field(gt=0.0, le=3600.0)


class SimulationStatus(BaseModel):
    running: bool
    tick_seconds: float
    elapsed_seconds: float

import math

import pytest

from app.models import DoorId
from app.simulator import (
    ACCELERATION_MPS2,
    WHEELBASE_M,
    VehicleSimulator,
    VehicleStateError,
)


def test_straight_line_distance():
    sim = VehicleSimulator()
    sim.set_speed(36)  # 10 m/s

    sim.step(10)
    state = sim.snapshot()

    assert abs(state.position.x - 100) < 1e-6
    assert abs(state.position.y) < 1e-6
    assert state.heading == 0


def test_acceleration_distance():
    sim = VehicleSimulator()
    sim.set_target_speed(180)

    sim.step(5)
    state = sim.snapshot()

    # s = a * t^2 / 2
    assert abs(state.position.x - ACCELERATION_MPS2 * 25 / 2) < 1e-6


def test_deceleration_stops():
    sim = VehicleSimulator()
    sim.set_speed(60)
    sim.set_target_speed(0)

    sim.step(10)

    assert sim.snapshot().speed == 0


def test_turning_follows_circle():
    sim = VehicleSimulator()
    steering_deg = 20.0
    sim.set_steering(steering_deg)
    sim.set_speed(18)  # 5 m/s

    radius = WHEELBASE_M / math.tan(math.radians(steering_deg))
    half_circle_seconds = math.pi * radius / 5.0
    sim.step(half_circle_seconds)
    state = sim.snapshot()

    # After half a circle turning left, the car is 2R north of the start, heading west.
    assert abs(state.position.x) < 0.01
    assert abs(state.position.y - 2 * radius) < 0.01
    assert abs(state.heading - 180) < 0.01


def test_empty_battery_stops_vehicle():
    sim = VehicleSimulator()
    sim.set_speed(100)
    sim.set_battery(0.001)

    sim.step(30)
    state = sim.snapshot()

    assert state.battery == 0
    assert state.speed == 0
    assert state.target_speed == 0


def test_charging_stops_when_full():
    sim = VehicleSimulator()
    sim.set_battery(99.99)
    sim.set_charging(True)

    # 50 kW fills the last 0.01 % in under a second.
    sim.step(1)
    state = sim.snapshot()

    assert state.battery > 99.999
    assert state.charging is False


def record_events(sim):
    events = []
    sim.add_listener(lambda event_type, data: events.append((event_type, data)))
    return events


def test_door_events():
    sim = VehicleSimulator()
    events = record_events(sim)

    sim.update_door(DoorId.front_left, open=True, locked=False)
    sim.update_door(DoorId.front_left, open=False)

    assert events == [
        ("door_opened", {"door": "front_left"}),
        ("door_unlocked", {"door": "front_left"}),
        ("door_closed", {"door": "front_left"}),
    ]


def test_rejected_command_emits_no_event():
    sim = VehicleSimulator()
    events = record_events(sim)

    with pytest.raises(VehicleStateError):
        sim.update_door(DoorId.front_left, open=True)

    assert events == []


def test_start_and_stop_events():
    sim = VehicleSimulator()
    events = record_events(sim)

    sim.set_target_speed(30)
    sim.step(1)
    sim.set_target_speed(0)
    sim.step(10)

    assert [event_type for event_type, _ in events] == ["vehicle_started", "vehicle_stopped"]


def test_battery_events():
    sim = VehicleSimulator()
    sim.set_battery(20.001)
    events = record_events(sim)

    sim.set_speed(100)
    sim.step(1)
    sim.set_battery(0.0001)
    sim.step(10)

    types = [event_type for event_type, _ in events]
    assert types == ["vehicle_started", "battery_low", "battery_empty", "vehicle_stopped"]


def test_charging_events():
    sim = VehicleSimulator()
    sim.set_battery(99.99)
    events = record_events(sim)

    sim.set_charging(True)
    sim.step(1)

    assert [event_type for event_type, _ in events] == ["charging_started", "charging_stopped"]


def test_lights_event_only_on_change():
    sim = VehicleSimulator()
    events = record_events(sim)

    sim.update_lights(hazard=True)
    sim.update_lights(hazard=True)

    assert events == [("lights_changed", {"headlights": "off", "hazard": True})]

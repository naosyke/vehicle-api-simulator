import math

from app.simulator import (
    ACCELERATION_MPS2,
    WHEELBASE_M,
    VehicleSimulator,
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

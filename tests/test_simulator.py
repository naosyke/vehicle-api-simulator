import math

import pytest

from app.models import DoorId
from app.simulator import (
    ACCELERATION_MPS2,
    ANOMALY_EVENTS,
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


def anomaly_types(events):
    return [event_type for event_type, _ in events if event_type in ANOMALY_EVENTS]


def test_normal_stop_is_not_harsh_braking():
    sim = VehicleSimulator()
    sim.set_speed(100)
    events = record_events(sim)

    sim.set_target_speed(0)
    sim.step(15)

    assert sim.snapshot().speed == 0
    assert anomaly_types(events) == []


def test_emergency_brake_is_harsh_braking():
    sim = VehicleSimulator()
    sim.set_speed(100)
    events = record_events(sim)

    sim.emergency_brake()
    sim.step(3.4)
    assert sim.snapshot().speed > 0
    sim.step(0.2)

    # 100 km/h at 8 m/s^2 stops in about 3.5 s.
    assert sim.snapshot().speed == 0
    assert anomaly_types(events) == ["harsh_braking"]
    harsh = dict(events)["harsh_braking"]
    assert harsh["deceleration_mps2"] == 8.0
    assert harsh["speed"] > 90
    assert ("emergency_brake", {"speed": 100}) in events


def test_emergency_brake_when_stopped_does_nothing():
    sim = VehicleSimulator()
    events = record_events(sim)

    sim.emergency_brake()
    sim.step(1)

    assert events == []


def test_new_target_speed_cancels_emergency_braking():
    sim = VehicleSimulator()
    sim.set_speed(100)
    sim.emergency_brake()
    sim.step(1)
    sim.set_target_speed(0)
    events = record_events(sim)

    sim.step(1)

    # Back to normal deceleration (3 m/s^2), so no new harsh braking.
    assert anomaly_types(events) == []


def test_sharp_turn():
    sim = VehicleSimulator()
    sim.set_speed(50)
    events = record_events(sim)

    sim.set_steering(35)
    sim.step(1)

    assert anomaly_types(events) == ["sharp_turn"]
    assert dict(events)["sharp_turn"]["lateral_acceleration_mps2"] > 4


def test_gentle_turn_is_not_sharp():
    sim = VehicleSimulator()
    sim.set_speed(10)
    sim.set_steering(10)
    events = record_events(sim)

    sim.step(5)

    assert anomaly_types(events) == []


def test_overspeed_after_grace_period():
    sim = VehicleSimulator(speed_limit_kmh=100)
    sim.set_speed(120)
    events = record_events(sim)

    sim.step(2.5)
    assert anomaly_types(events) == []

    sim.step(1.5)
    assert anomaly_types(events) == ["overspeed"]
    assert abs(sim.driving_summary()["overspeed_seconds"] - 1.0) < 0.01

    # Slowing down ends the episode; speeding again is a new one.
    sim.set_speed(90)
    sim.step(1)
    sim.set_speed(120)
    sim.step(4)
    assert anomaly_types(events) == ["overspeed", "overspeed"]


def test_driving_summary():
    sim = VehicleSimulator()
    sim.set_speed(36)  # 10 m/s

    sim.step(100)
    summary = sim.driving_summary()

    assert summary["distance_km"] == 1.0
    assert summary["driving_seconds"] == 100
    assert summary["average_speed_kmh"] == 36
    assert summary["max_speed_kmh"] == 36
    # 0.15 kWh/km for driving plus 0.5 kW idle load for 100 s.
    assert summary["efficiency_kwh_per_100km"] == 16.39
    assert summary["anomalies"] == {"harsh_braking": 0, "sharp_turn": 0, "overspeed": 0}
    assert summary["score"] == 100
    assert summary["rating"] == "excellent"


def test_summary_before_driving():
    summary = VehicleSimulator().driving_summary()

    assert summary["distance_km"] == 0
    assert summary["average_speed_kmh"] == 0
    assert summary["efficiency_kwh_per_100km"] is None
    assert summary["score"] == 100


def test_score_penalties():
    sim = VehicleSimulator()
    sim.set_speed(100)
    sim.emergency_brake()
    sim.step(5)
    sim.set_speed(50)
    sim.set_steering(35)
    sim.step(1)

    summary = sim.driving_summary()

    assert summary["anomalies"]["harsh_braking"] == 1
    assert summary["anomalies"]["sharp_turn"] == 1
    assert summary["score"] == 92
    assert summary["rating"] == "excellent"


def test_charged_energy():
    sim = VehicleSimulator()
    sim.set_battery(50)
    sim.set_charging(True)

    sim.step(36)  # 50 kW for 0.01 h

    assert abs(sim.driving_summary()["energy_charged_kwh"] - 0.5) < 1e-6


def test_reset_clears_summary():
    sim = VehicleSimulator()
    sim.set_speed(100)
    sim.emergency_brake()
    sim.step(5)

    sim.reset()

    summary = sim.driving_summary()
    assert summary["distance_km"] == 0
    assert summary["anomalies"]["harsh_braking"] == 0


def test_rating_matches_rounded_score():
    sim = VehicleSimulator(speed_limit_kmh=100)
    sim.set_speed(120)
    # 3 s grace + 51 s over the limit = 10.2 penalty points -> 89.8 -> 90.
    sim.step(54)

    summary = sim.driving_summary()

    assert summary["score"] == 90
    assert summary["rating"] == "excellent"

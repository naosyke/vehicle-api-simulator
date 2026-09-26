import math
import threading
from contextlib import contextmanager

from app.models import (
    MAX_SPEED_KMH,
    Door,
    DoorId,
    HeadlightMode,
    Lights,
    Position,
    Vehicle,
)


WHEELBASE_M = 2.7
ACCELERATION_MPS2 = 3.0
DECELERATION_MPS2 = 3.0
EMERGENCY_DECELERATION_MPS2 = 8.0

BATTERY_CAPACITY_KWH = 60.0
CONSUMPTION_KWH_PER_KM = 0.15
IDLE_CONSUMPTION_KW = 0.5
CHARGING_POWER_KW = 50.0
LOW_BATTERY_PERCENT = 20.0

# Longer steps are split so the kinematic model stays accurate on turns.
MAX_SUBSTEP_SECONDS = 0.1

# Anomaly detection thresholds.
HARSH_BRAKING_MPS2 = 4.5
SHARP_TURN_LATERAL_MPS2 = 4.0
DEFAULT_SPEED_LIMIT_KMH = 100.0
OVERSPEED_GRACE_SECONDS = 3.0

ANOMALY_EVENTS = ("harsh_braking", "sharp_turn", "overspeed")

# Driving score: 100 minus these penalties, floored at 0.
SCORE_PENALTY_HARSH_BRAKING = 5.0
SCORE_PENALTY_SHARP_TURN = 3.0
SCORE_PENALTY_PER_OVERSPEED_SECOND = 0.2


class VehicleStateError(Exception):
    """Raised when a command is not allowed in the current vehicle state."""


def _kwh_to_percent(kwh):
    return kwh / BATTERY_CAPACITY_KWH * 100.0


def _rating(score):
    if score >= 90:
        return "excellent"
    if score >= 75:
        return "good"
    if score >= 50:
        return "fair"
    return "poor"


class VehicleSimulator:
    """Holds the vehicle state and advances it with a simple kinematic bicycle model.

    All public methods are thread-safe: FastAPI runs sync endpoints in a
    thread pool while the periodic update loop runs on the event loop.

    State changes such as a door opening are reported to listeners
    registered with add_listener() as (event_type, data) calls.
    """

    def __init__(self, speed_limit_kmh=DEFAULT_SPEED_LIMIT_KMH):
        self.speed_limit_kmh = speed_limit_kmh
        self._lock = threading.Lock()
        self._listeners = []
        self._pending_events = []
        self.reset()

    def add_listener(self, listener):
        self._listeners.append(listener)

    def remove_listener(self, listener):
        self._listeners.remove(listener)

    @contextmanager
    def _transaction(self):
        """Hold the state lock, then deliver events emitted inside it after releasing."""
        with self._lock:
            try:
                yield
            finally:
                events = self._pending_events
                self._pending_events = []
        for event_type, data in events:
            for listener in list(self._listeners):
                listener(event_type, data)

    def _emit(self, event_type, **data):
        self._pending_events.append((event_type, data))

    def reset(self):
        with self._transaction():
            self._speed = 0.0
            self._target_speed = 0.0
            self._battery = 100.0
            self._charging = False
            self._x = 0.0
            self._y = 0.0
            self._heading = 0.0
            self._steering = 0.0
            self._odometer_km = 0.0
            self._doors = {door_id: Door() for door_id in DoorId}
            self._lights = Lights()
            self._emergency_braking = False
            self.elapsed_seconds = 0.0

            # Anomaly detection state: whether each condition is currently active.
            self._braking_hard = False
            self._turning_sharply = False
            self._overspeed_seconds_current = 0.0

            # Trip statistics since the last reset.
            self._driving_seconds = 0.0
            self._max_speed = 0.0
            self._driving_energy_kwh = 0.0
            self._charged_energy_kwh = 0.0
            self._overspeed_seconds_total = 0.0
            self._anomaly_counts = {name: 0 for name in ANOMALY_EVENTS}

            self._emit("simulation_reset")

    def snapshot(self):
        with self._lock:
            return Vehicle(
                speed=round(self._speed, 3),
                target_speed=self._target_speed,
                battery=round(self._battery, 4),
                charging=self._charging,
                position=Position(x=round(self._x, 3), y=round(self._y, 3)),
                heading=round(math.degrees(self._heading) % 360.0, 3),
                steering=self._steering,
                odometer=round(self._odometer_km, 4),
                doors={k: v.model_copy() for k, v in self._doors.items()},
                lights=self._lights.model_copy(),
            )

    # --- commands -----------------------------------------------------

    def set_speed(self, speed):
        """Set the speed immediately (and hold it)."""
        with self._transaction():
            self._check_can_drive(speed)
            was_moving = self._speed > 0.0
            self._speed = speed
            self._target_speed = speed
            self._emit_motion_change(was_moving)

    def set_target_speed(self, speed):
        """Accelerate or decelerate toward the given speed over time."""
        with self._transaction():
            self._check_can_drive(speed)
            self._target_speed = speed
            self._emergency_braking = False

    def emergency_brake(self):
        """Brake as hard as possible until the vehicle stops."""
        with self._transaction():
            self._target_speed = 0.0
            if self._speed > 0.0:
                self._emergency_braking = True
                self._emit("emergency_brake", speed=round(self._speed, 3))

    def driving_summary(self):
        """Statistics and a driving score for the trip since the last reset."""
        with self._lock:
            distance_km = self._odometer_km
            hours = self._driving_seconds / 3600.0
            penalty = (
                self._anomaly_counts["harsh_braking"] * SCORE_PENALTY_HARSH_BRAKING
                + self._anomaly_counts["sharp_turn"] * SCORE_PENALTY_SHARP_TURN
                + self._overspeed_seconds_total * SCORE_PENALTY_PER_OVERSPEED_SECOND
            )
            # Rate the rounded score so the number and the rating always agree.
            score = round(max(0.0, 100.0 - penalty))
            return {
                "elapsed_seconds": round(self.elapsed_seconds, 1),
                "driving_seconds": round(self._driving_seconds, 1),
                "distance_km": round(distance_km, 4),
                "average_speed_kmh": round(distance_km / hours, 1) if hours > 0 else 0.0,
                "max_speed_kmh": round(self._max_speed, 1),
                "energy_used_kwh": round(self._driving_energy_kwh, 4),
                "energy_charged_kwh": round(self._charged_energy_kwh, 4),
                "efficiency_kwh_per_100km": (
                    round(self._driving_energy_kwh / distance_km * 100.0, 2) if distance_km > 0.01 else None
                ),
                "speed_limit_kmh": self.speed_limit_kmh,
                "overspeed_seconds": round(self._overspeed_seconds_total, 1),
                "anomalies": dict(self._anomaly_counts),
                "score": score,
                "rating": _rating(score),
            }

    def set_steering(self, angle):
        with self._transaction():
            self._steering = angle

    def set_position(self, x, y):
        with self._transaction():
            self._x = x
            self._y = y

    def update_door(self, door_id, open=None, locked=None):
        with self._transaction():
            door = self._doors[door_id]
            new_open = door.open if open is None else open
            new_locked = door.locked if locked is None else locked

            if new_open and not door.open:
                if door.locked and locked is not False:
                    raise VehicleStateError(f"Door {door_id.value} is locked")
                if self._speed > 0.0:
                    raise VehicleStateError("Cannot open a door while the vehicle is moving")
            if new_open and new_locked:
                raise VehicleStateError("Cannot lock an open door")

            if new_open != door.open:
                self._emit("door_opened" if new_open else "door_closed", door=door_id.value)
            if new_locked != door.locked:
                self._emit("door_locked" if new_locked else "door_unlocked", door=door_id.value)

            door.open = new_open
            door.locked = new_locked
            return door.model_copy()

    def update_lights(self, headlights=None, hazard=None):
        with self._transaction():
            before = self._lights.model_copy()
            if headlights is not None:
                self._lights.headlights = HeadlightMode(headlights)
            if hazard is not None:
                self._lights.hazard = hazard
            if self._lights != before:
                self._emit("lights_changed", **self._lights.model_dump(mode="json"))
            return self._lights.model_copy()

    def set_battery(self, level):
        with self._transaction():
            before = self._battery
            self._battery = level
            self._emit_battery_thresholds(before)
            if level <= 0.0:
                self._target_speed = 0.0

    def set_charging(self, charging):
        with self._transaction():
            if charging and (self._speed > 0.0 or self._target_speed > 0.0):
                raise VehicleStateError("Cannot charge while the vehicle is moving")
            if charging != self._charging:
                self._emit(
                    "charging_started" if charging else "charging_stopped",
                    battery=round(self._battery, 4),
                )
            self._charging = charging

    # --- simulation ---------------------------------------------------

    def step(self, seconds):
        """Advance the simulation by the given number of seconds."""
        with self._transaction():
            remaining = seconds
            while remaining > 0.0:
                dt = min(remaining, MAX_SUBSTEP_SECONDS)
                self._step_once(dt)
                remaining -= dt
            self.elapsed_seconds += seconds

    def _step_once(self, dt):
        was_moving = self._speed > 0.0
        start_mps = self._speed / 3.6
        speed_mps = self._update_speed(dt)
        self._emit_motion_change(was_moving)
        distance_m = speed_mps * dt
        yaw_rate = 0.0

        if speed_mps > 0.0:
            self._driving_seconds += dt
            yaw_rate = speed_mps / WHEELBASE_M * math.tan(math.radians(self._steering))
            # Integrate using the mid-point heading for better accuracy on curves.
            mid_heading = self._heading + yaw_rate * dt / 2.0
            self._x += distance_m * math.cos(mid_heading)
            self._y += distance_m * math.sin(mid_heading)
            self._heading = (self._heading + yaw_rate * dt) % (2.0 * math.pi)
            self._odometer_km += distance_m / 1000.0

        self._max_speed = max(self._max_speed, self._speed)
        self._detect_anomalies(dt, start_mps, yaw_rate)
        self._update_battery(dt, distance_m)

    def _detect_anomalies(self, dt, start_mps, yaw_rate):
        end_mps = self._speed / 3.6
        deceleration = (start_mps - end_mps) / dt
        lateral = abs(end_mps * yaw_rate)

        # Each condition is reported once when it starts, not on every step.
        braking_hard = deceleration >= HARSH_BRAKING_MPS2
        if braking_hard and not self._braking_hard:
            self._report_anomaly("harsh_braking", deceleration_mps2=round(deceleration, 2))
        self._braking_hard = braking_hard

        turning_sharply = lateral >= SHARP_TURN_LATERAL_MPS2
        if turning_sharply and not self._turning_sharply:
            self._report_anomaly("sharp_turn", lateral_acceleration_mps2=round(lateral, 2))
        self._turning_sharply = turning_sharply

        if self._speed > self.speed_limit_kmh:
            before = self._overspeed_seconds_current
            self._overspeed_seconds_current += dt
            if before < OVERSPEED_GRACE_SECONDS <= self._overspeed_seconds_current:
                self._report_anomaly("overspeed", speed_limit_kmh=self.speed_limit_kmh)
            # Count only the time past the grace period.
            self._overspeed_seconds_total += max(
                0.0, self._overspeed_seconds_current - max(before, OVERSPEED_GRACE_SECONDS)
            )
        else:
            self._overspeed_seconds_current = 0.0

        if self._emergency_braking and self._speed <= 0.0:
            self._emergency_braking = False

    def _report_anomaly(self, anomaly_type, **data):
        self._anomaly_counts[anomaly_type] += 1
        self._emit(
            anomaly_type,
            speed=round(self._speed, 3),
            x=round(self._x, 3),
            y=round(self._y, 3),
            **data,
        )

    def _update_speed(self, dt):
        """Move speed toward the target and return the average speed in m/s over dt."""
        start_mps = self._speed / 3.6
        target_mps = self._target_speed / 3.6

        if target_mps > start_mps:
            end_mps = min(target_mps, start_mps + ACCELERATION_MPS2 * dt)
        else:
            deceleration = EMERGENCY_DECELERATION_MPS2 if self._emergency_braking else DECELERATION_MPS2
            end_mps = max(target_mps, start_mps - deceleration * dt)

        self._speed = end_mps * 3.6
        return (start_mps + end_mps) / 2.0

    def _update_battery(self, dt, distance_m):
        before = self._battery
        hours = dt / 3600.0

        if self._charging:
            charged_kwh = min(CHARGING_POWER_KW * hours, (100.0 - self._battery) / 100.0 * BATTERY_CAPACITY_KWH)
            self._charged_energy_kwh += charged_kwh
            self._battery += _kwh_to_percent(charged_kwh)
        else:
            used_kwh = CONSUMPTION_KWH_PER_KM * distance_m / 1000.0 + IDLE_CONSUMPTION_KW * hours
            if distance_m > 0.0:
                self._driving_energy_kwh += used_kwh
            self._battery -= _kwh_to_percent(used_kwh)

        self._battery = min(100.0, max(0.0, self._battery))
        self._emit_battery_thresholds(before)
        if self._battery >= 100.0 and self._charging:
            self._charging = False
            self._emit("charging_stopped", battery=100.0)
        if self._battery <= 0.0:
            self._target_speed = 0.0

    def _emit_motion_change(self, was_moving):
        is_moving = self._speed > 0.0
        if is_moving and not was_moving:
            self._emit("vehicle_started")
        elif was_moving and not is_moving:
            self._emit("vehicle_stopped", x=round(self._x, 3), y=round(self._y, 3))

    def _emit_battery_thresholds(self, before):
        if before > LOW_BATTERY_PERCENT >= self._battery > 0.0:
            self._emit("battery_low", battery=round(self._battery, 4))
        if before > 0.0 >= self._battery:
            self._emit("battery_empty")

    def _check_can_drive(self, speed):
        if speed <= 0.0:
            return
        if speed > MAX_SPEED_KMH:
            raise VehicleStateError(f"Speed must be at most {MAX_SPEED_KMH} km/h")
        if self._battery <= 0.0:
            raise VehicleStateError("Battery is empty")
        if self._charging:
            raise VehicleStateError("Cannot drive while charging")
        if any(door.open for door in self._doors.values()):
            raise VehicleStateError("Cannot drive with a door open")

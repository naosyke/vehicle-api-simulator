from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_root():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["message"] == "Vehicle API Simulator"


def test_get_vehicle():
    response = client.get("/vehicle")

    assert response.status_code == 200

    data = response.json()

    assert "speed" in data
    assert "battery" in data
    assert "position" in data
    assert "steering" in data


def test_get_speed():
    response = client.get("/vehicle/speed")

    assert response.status_code == 200
    assert "speed" in response.json()


def test_get_position():
    response = client.get("/vehicle/position")

    assert response.status_code == 200
    assert "x" in response.json()
    assert "y" in response.json()

def test_set_speed():
    response = client.post(
        "/vehicle/speed",
        json={"speed": 30}
    )

    assert response.status_code == 200
    assert response.json()["speed"] == 30

    response = client.get("/vehicle/speed")

    assert response.status_code == 200
    assert response.json()["speed"] == 30

def test_set_speed_out_of_range():
    response = client.post("/vehicle/speed", json={"speed": 500})

    assert response.status_code == 422


def test_target_speed_accelerates_over_time():
    response = client.post("/vehicle/target-speed", json={"speed": 54})

    assert response.status_code == 200
    assert client.get("/vehicle/speed").json()["speed"] == 0

    # 3 m/s^2 for 2 s -> 6 m/s = 21.6 km/h
    data = client.post("/simulation/step", json={"seconds": 2}).json()

    assert abs(data["speed"] - 21.6) < 0.01
    assert data["position"]["x"] > 0

    data = client.post("/simulation/step", json={"seconds": 10}).json()

    assert data["speed"] == 54


def test_steering():
    response = client.post("/vehicle/steering", json={"angle": 10})

    assert response.status_code == 200
    assert client.get("/vehicle/steering").json()["steering"] == 10

    response = client.post("/vehicle/steering", json={"angle": 90})

    assert response.status_code == 422


def test_set_position():
    response = client.post("/vehicle/position", json={"x": 12.5, "y": -3})

    assert response.status_code == 200
    assert client.get("/vehicle/position").json() == {"x": 12.5, "y": -3}


def test_door_must_be_unlocked_to_open():
    response = client.post("/vehicle/doors/front_left", json={"open": True})

    assert response.status_code == 409

    response = client.post(
        "/vehicle/doors/front_left",
        json={"open": True, "locked": False},
    )

    assert response.status_code == 200
    assert response.json() == {"open": True, "locked": False}


def test_cannot_drive_with_door_open():
    client.post("/vehicle/doors/rear_right", json={"open": True, "locked": False})

    response = client.post("/vehicle/target-speed", json={"speed": 30})

    assert response.status_code == 409


def test_cannot_open_door_while_moving():
    client.post("/vehicle/doors/front_right", json={"locked": False})
    client.post("/vehicle/speed", json={"speed": 20})

    response = client.post("/vehicle/doors/front_right", json={"open": True})

    assert response.status_code == 409


def test_unknown_door():
    response = client.get("/vehicle/doors/trunk")

    assert response.status_code == 422


def test_lights():
    response = client.post("/vehicle/lights", json={"headlights": "low"})

    assert response.status_code == 200
    assert response.json() == {"headlights": "low", "hazard": False}

    response = client.post("/vehicle/lights", json={"hazard": True})

    assert response.json() == {"headlights": "low", "hazard": True}


def test_battery_drains_while_driving():
    client.post("/vehicle/speed", json={"speed": 100})

    data = client.post("/simulation/step", json={"seconds": 60}).json()

    assert data["battery"] < 100
    assert abs(data["odometer"] - 100 / 60) < 0.01


def test_charging():
    client.post("/vehicle/battery", json={"level": 50})

    response = client.post("/vehicle/charging", json={"charging": True})

    assert response.status_code == 200
    assert response.json()["charging"] is True

    data = client.post("/simulation/step", json={"seconds": 60}).json()

    assert data["battery"] > 50

    response = client.post("/vehicle/target-speed", json={"speed": 30})

    assert response.status_code == 409


def test_cannot_charge_while_moving():
    client.post("/vehicle/speed", json={"speed": 30})

    response = client.post("/vehicle/charging", json={"charging": True})

    assert response.status_code == 409


def test_simulation_status_and_reset():
    client.post("/vehicle/speed", json={"speed": 30})
    client.post("/simulation/step", json={"seconds": 1.5})

    status = client.get("/simulation").json()

    assert status["elapsed_seconds"] == 1.5

    data = client.post("/simulation/reset").json()

    assert data["speed"] == 0
    assert data["position"] == {"x": 0, "y": 0}


def test_events_history_newest_first():
    client.post("/vehicle/lights", json={"headlights": "low"})
    client.post("/vehicle/doors/front_left", json={"locked": False})

    events = client.get("/events").json()

    assert [e["type"] for e in events] == ["door_unlocked", "lights_changed"]
    assert events[0]["data"] == {"door": "front_left"}
    assert "timestamp" in events[0]


def test_events_limit():
    for hazard in [True, False, True]:
        client.post("/vehicle/lights", json={"hazard": hazard})

    assert len(client.get("/events", params={"limit": 2}).json()) == 2
    assert client.get("/events", params={"limit": 0}).status_code == 422

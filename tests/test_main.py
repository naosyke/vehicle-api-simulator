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
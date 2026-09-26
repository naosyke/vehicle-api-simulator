from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_dashboard_page():
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>Vehicle Dashboard</title>" in response.text


def test_websocket_sends_state():
    client.post("/vehicle/speed", json={"speed": 25})

    with client.websocket_connect("/ws") as websocket:
        message = websocket.receive_json()

    assert message["kind"] == "state"
    assert message["vehicle"]["speed"] == 25
    assert "timestamp" in message


def test_websocket_sends_events():
    with client.websocket_connect("/ws") as websocket:
        assert websocket.receive_json()["kind"] == "state"

        client.post("/vehicle/lights", json={"hazard": True})

        # State messages keep arriving; skip them until the event shows up.
        for _ in range(20):
            message = websocket.receive_json()
            if message["kind"] == "event":
                break

    assert message["type"] == "lights_changed"
    assert message["data"] == {"headlights": "off", "hazard": True}

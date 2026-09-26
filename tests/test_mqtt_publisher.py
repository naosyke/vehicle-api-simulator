import json

from app.mqtt_publisher import MqttPublisher
from app.simulator import VehicleSimulator


class FakeReasonCode:
    def __init__(self, is_failure=False):
        self.is_failure = is_failure


class FakeMessageInfo:
    def wait_for_publish(self, timeout=None):
        pass


class FakeClient:
    def __init__(self):
        self.published = []
        self.will = None

    def will_set(self, topic, payload, qos, retain):
        self.will = (topic, payload, qos, retain)

    def connect_async(self, host, port):
        pass

    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def disconnect(self):
        pass

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, qos, retain))
        return FakeMessageInfo()


def connected_publisher():
    client = FakeClient()
    publisher = MqttPublisher("broker", vehicle_id="car-1", client=client)
    publisher.start()
    publisher._on_connect(client, None, None, FakeReasonCode(), None)
    return publisher, client


def test_last_will_and_online_status():
    publisher, client = connected_publisher()

    assert client.will == ("vehicle/car-1/status", "offline", 1, True)
    assert client.published == [("vehicle/car-1/status", "online", 1, True)]
    assert publisher.connected


def test_nothing_published_before_connect():
    client = FakeClient()
    publisher = MqttPublisher("broker", vehicle_id="car-1", client=client)

    publisher.publish_telemetry(VehicleSimulator().snapshot())
    publisher.publish_event("door_opened", {"door": "front_left"})

    assert client.published == []


def test_publish_telemetry():
    publisher, client = connected_publisher()
    sim = VehicleSimulator()
    sim.set_speed(42)

    publisher.publish_telemetry(sim.snapshot())

    topic, payload, qos, retain = client.published[-1]
    data = json.loads(payload)
    assert topic == "vehicle/car-1/telemetry"
    assert qos == 0
    assert data["vehicle_id"] == "car-1"
    assert data["speed"] == 42
    assert data["doors"]["front_left"] == {"open": False, "locked": True}
    assert "timestamp" in data


def test_simulator_events_are_published():
    publisher, client = connected_publisher()
    sim = VehicleSimulator()
    sim.add_listener(publisher.publish_event)

    sim.update_lights(headlights="low")

    topic, payload, qos, retain = client.published[-1]
    data = json.loads(payload)
    assert topic == "vehicle/car-1/events"
    assert qos == 1
    assert data["type"] == "lights_changed"
    assert data["data"] == {"headlights": "low", "hazard": False}


def test_disconnect_stops_publishing():
    publisher, client = connected_publisher()
    publisher._on_disconnect(client, None, None, FakeReasonCode(), None)

    publisher.publish_event("door_opened", {"door": "front_left"})

    assert len(client.published) == 1

import json
import logging
import time

import paho.mqtt.client as mqtt


logger = logging.getLogger(__name__)


class MqttPublisher:
    """Publishes vehicle telemetry and events to an MQTT broker.

    Topics:
        vehicle/{vehicle_id}/telemetry  full vehicle state (QoS 0)
        vehicle/{vehicle_id}/events     state change events (QoS 1)
        vehicle/{vehicle_id}/status     "online" / "offline" (retained, last will)
    """

    def __init__(self, host, port=1883, vehicle_id="sim-001", client=None):
        self.host = host
        self.port = port
        self.vehicle_id = vehicle_id
        self.telemetry_topic = f"vehicle/{vehicle_id}/telemetry"
        self.events_topic = f"vehicle/{vehicle_id}/events"
        self.status_topic = f"vehicle/{vehicle_id}/status"

        if client is None:
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"vehicle-api-simulator-{vehicle_id}",
            )
        self._client = client
        self._client.will_set(self.status_topic, "offline", qos=1, retain=True)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self.connected = False

    def start(self):
        # connect_async + loop_start keep retrying in the background,
        # so the API also starts when the broker is not up yet.
        self._client.connect_async(self.host, self.port)
        self._client.loop_start()

    def stop(self):
        if self.connected:
            self._client.publish(self.status_topic, "offline", qos=1, retain=True).wait_for_publish(1.0)
        self._client.disconnect()
        self._client.loop_stop()

    def publish_telemetry(self, vehicle):
        payload = {
            "vehicle_id": self.vehicle_id,
            "timestamp": time.time(),
            **vehicle.model_dump(mode="json"),
        }
        self._publish(self.telemetry_topic, payload, qos=0)

    def publish_event(self, event_type, data):
        payload = {
            "vehicle_id": self.vehicle_id,
            "timestamp": time.time(),
            "type": event_type,
            "data": data,
        }
        self._publish(self.events_topic, payload, qos=1)

    def _publish(self, topic, payload, qos):
        if not self.connected:
            return
        self._client.publish(topic, json.dumps(payload), qos=qos)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            logger.warning("MQTT connection to %s:%s failed: %s", self.host, self.port, reason_code)
            return
        logger.info("Connected to MQTT broker %s:%s", self.host, self.port)
        self.connected = True
        client.publish(self.status_topic, "online", qos=1, retain=True)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected = False
        logger.warning("Disconnected from MQTT broker: %s", reason_code)

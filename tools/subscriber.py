"""Print vehicle telemetry and events published by the simulator.

Usage:
    python tools/subscriber.py
    python tools/subscriber.py --host 127.0.0.1 --vehicle sim-001 --events-only
"""

import argparse
import json
from datetime import datetime

import paho.mqtt.client as mqtt


def format_telemetry(data):
    position = data["position"]
    return (
        f"speed={data['speed']:6.1f} km/h  "
        f"battery={data['battery']:6.2f} %  "
        f"pos=({position['x']:8.1f}, {position['y']:8.1f})  "
        f"heading={data['heading']:5.1f}"
    )


def format_event(data):
    details = " ".join(f"{k}={v}" for k, v in data["data"].items())
    return f"EVENT {data['type']} {details}".rstrip()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--vehicle", default="+", help="Vehicle ID, or + for all vehicles")
    parser.add_argument("--events-only", action="store_true")
    args = parser.parse_args()

    kinds = ["events", "status"] if args.events_only else ["telemetry", "events", "status"]
    topics = [f"vehicle/{args.vehicle}/{kind}" for kind in kinds]

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"Connection failed: {reason_code}")
            return
        print(f"Connected to {args.host}:{args.port}, subscribing to {', '.join(topics)}")
        for topic in topics:
            client.subscribe(topic, qos=1)

    def on_message(client, userdata, message):
        _, vehicle_id, kind = message.topic.split("/", 2)
        payload = message.payload.decode()
        now = datetime.now().strftime("%H:%M:%S")

        if kind == "status":
            line = f"STATUS {payload}"
        elif kind == "telemetry":
            line = format_telemetry(json.loads(payload))
        else:
            line = format_event(json.loads(payload))

        print(f"{now} [{vehicle_id}] {line}", flush=True)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.host, args.port)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        client.disconnect()


if __name__ == "__main__":
    main()

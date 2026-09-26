import httpx
import pytest
from mcp import Client

from app.main import app, simulator
from server import create_server


pytestmark = pytest.mark.anyio


def in_process_server():
    # Calls the FastAPI app directly, without a network or a running uvicorn.
    return create_server("http://vehicle", transport=httpx.ASGITransport(app=app))


async def call(client, name, arguments=None):
    return await client.call_tool(name, arguments or {})


async def test_lists_tools_with_annotations():
    async with Client(in_process_server()) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert set(tools) == {
        "get_vehicle_status",
        "get_recent_events",
        "get_driving_summary",
        "emergency_brake",
        "set_target_speed",
        "set_steering",
        "set_door",
        "set_lights",
        "set_charging",
        "get_simulation_status",
        "advance_simulation",
        "reset_simulation",
    }
    assert tools["get_vehicle_status"].annotations.read_only_hint is True
    assert tools["reset_simulation"].annotations.destructive_hint is True
    assert tools["set_door"].input_schema["properties"]["door"]["enum"] == [
        "front_left", "front_right", "rear_left", "rear_right",
    ]


async def test_get_vehicle_status():
    simulator.set_speed(42)

    async with Client(in_process_server()) as client:
        result = await call(client, "get_vehicle_status")

    assert not result.is_error
    assert result.structured_content["speed"] == 42
    assert result.structured_content["doors"]["front_left"] == {"open": False, "locked": True}


async def test_drive_and_advance():
    async with Client(in_process_server()) as client:
        await call(client, "set_target_speed", {"speed_kmh": 36})
        result = await call(client, "advance_simulation", {"seconds": 10})

    assert result.structured_content["speed"] == 36
    assert result.structured_content["position"]["x"] > 0


async def test_rejected_command_is_a_readable_tool_error():
    async with Client(in_process_server()) as client:
        result = await call(client, "set_door", {"door": "front_left", "open": True})

    assert result.is_error
    assert "Rejected by the vehicle: Door front_left is locked" in result.content[0].text


async def test_unlock_and_open_door_then_events():
    async with Client(in_process_server()) as client:
        opened = await call(client, "set_door", {"door": "rear_left", "open": True, "locked": False})
        events = await call(client, "get_recent_events", {"limit": 5})

    assert opened.structured_content == {"open": True, "locked": False}
    types = [event["type"] for event in events.structured_content["result"]]
    assert types == ["door_unlocked", "door_opened"]


async def test_set_door_requires_a_change():
    async with Client(in_process_server()) as client:
        result = await call(client, "set_door", {"door": "rear_left"})

    assert result.is_error
    assert "at least one" in result.content[0].text


async def test_invalid_value():
    async with Client(in_process_server()) as client:
        result = await call(client, "set_steering", {"angle_deg": 90})

    assert result.is_error
    assert "Invalid value" in result.content[0].text


async def test_lights_and_charging():
    async with Client(in_process_server()) as client:
        lights = await call(client, "set_lights", {"headlights": "high"})
        charging = await call(client, "set_charging", {"charging": True})

    assert lights.structured_content == {"headlights": "high", "hazard": False}
    assert charging.structured_content["charging"] is True


async def test_api_unreachable():
    server = create_server("http://127.0.0.1:9")

    async with Client(server) as client:
        result = await call(client, "get_vehicle_status")

    assert result.is_error
    assert "Cannot reach the vehicle API" in result.content[0].text


async def test_reset():
    simulator.set_speed(50)

    async with Client(in_process_server()) as client:
        result = await call(client, "reset_simulation")

    assert result.structured_content["speed"] == 0


async def test_emergency_brake_shows_up_in_summary():
    simulator.set_speed(80)

    async with Client(in_process_server()) as client:
        braked = await call(client, "emergency_brake")
        await call(client, "advance_simulation", {"seconds": 5})
        summary = await call(client, "get_driving_summary")

    assert braked.structured_content["target_speed"] == 0
    assert summary.structured_content["anomalies"]["harsh_braking"] == 1
    assert summary.structured_content["score"] == 95

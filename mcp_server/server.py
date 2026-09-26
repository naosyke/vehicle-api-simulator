"""MCP server that lets AI assistants read and control the vehicle simulator.

It wraps the simulator's REST API as MCP tools and talks to MCP clients
(Claude Desktop, Claude Code, ...) over stdio.

Usage:
    VEHICLE_API_URL=http://127.0.0.1:8000 python mcp_server/server.py
"""

import logging
import os
from typing import Any, Literal, Optional

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations


DEFAULT_API_URL = "http://127.0.0.1:8000"

INSTRUCTIONS = """\
Tools for a simulated electric vehicle (not a real car).
Speeds are km/h, steering is the road wheel angle in degrees (left positive,
-35 to 35), battery is percent, positions are meters (x = east, y = north).
The vehicle enforces rules, e.g. locked doors cannot be opened, doors cannot
be opened while moving, and it cannot drive with a door open or while charging.
When a command is rejected, explain the reason to the user and suggest the
steps that would make it possible instead of retrying the same command.
"""

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
CONTROL = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)

Door = Literal["front_left", "front_right", "rear_left", "rear_right"]
Headlights = Literal["off", "low", "high"]


def create_server(api_url=None, transport=None):
    """Create the MCP server.

    `transport` is an optional httpx transport, used by tests to call the
    FastAPI app in-process instead of over the network.
    """
    api_url = api_url or os.getenv("VEHICLE_API_URL", DEFAULT_API_URL)

    async def request(method, path, json=None, params=None):
        try:
            async with httpx.AsyncClient(base_url=api_url, transport=transport, timeout=10.0) as client:
                response = await client.request(method, path, json=json, params=params)
        except httpx.HTTPError as error:
            raise ToolError(
                f"Cannot reach the vehicle API at {api_url} ({error.__class__.__name__}). "
                "Is the simulator running?"
            ) from error

        if response.status_code == 409:
            raise ToolError(f"Rejected by the vehicle: {response.json()['detail']}")
        if response.status_code == 422:
            raise ToolError(f"Invalid value: {response.json()['detail']}")
        if response.is_error:
            raise ToolError(f"Vehicle API error: HTTP {response.status_code}")
        return response.json()

    server = MCPServer(
        name="vehicle-simulator",
        title="Vehicle Simulator",
        instructions=INSTRUCTIONS,
        version="0.1.0",
    )

    @server.tool(annotations=READ_ONLY)
    async def get_vehicle_status() -> dict[str, Any]:
        """Get the full vehicle state: speed, target speed, battery, charging,
        position, heading, steering, odometer, doors and lights."""
        return await request("GET", "/vehicle")

    @server.tool(annotations=READ_ONLY)
    async def get_recent_events(limit: int = 20) -> list[dict[str, Any]]:
        """Get recent vehicle events, newest first (e.g. door_opened,
        vehicle_started, vehicle_stopped, battery_low, charging_started).

        Args:
            limit: Number of events to return, 1 to 200.
        """
        return await request("GET", "/events", params={"limit": limit})

    @server.tool(annotations=CONTROL)
    async def set_target_speed(speed_kmh: float) -> dict[str, Any]:
        """Accelerate or decelerate the vehicle toward a speed.

        Args:
            speed_kmh: Target speed in km/h, 0 to 180. 0 brings the vehicle to a stop.
        """
        return await request("POST", "/vehicle/target-speed", json={"speed": speed_kmh})

    @server.tool(annotations=CONTROL)
    async def set_steering(angle_deg: float) -> dict[str, Any]:
        """Set the road wheel angle.

        Args:
            angle_deg: Degrees, -35 to 35. Positive turns left, 0 goes straight.
        """
        return await request("POST", "/vehicle/steering", json={"angle": angle_deg})

    @server.tool(annotations=CONTROL)
    async def set_door(
        door: Door,
        open: Optional[bool] = None,
        locked: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Open, close, lock or unlock a door. Omitted fields stay unchanged.
        To open a locked door, pass open=true and locked=false together.

        Args:
            door: Which door.
            open: true to open, false to close.
            locked: true to lock, false to unlock.
        """
        body = {key: value for key, value in {"open": open, "locked": locked}.items() if value is not None}
        if not body:
            raise ToolError("Pass at least one of open or locked.")
        return await request("POST", f"/vehicle/doors/{door}", json=body)

    @server.tool(annotations=CONTROL)
    async def set_lights(
        headlights: Optional[Headlights] = None,
        hazard: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Change the headlights and/or hazard lights. Omitted fields stay unchanged.

        Args:
            headlights: off, low or high.
            hazard: true to turn the hazard lights on.
        """
        body = {key: value for key, value in {"headlights": headlights, "hazard": hazard}.items() if value is not None}
        if not body:
            raise ToolError("Pass at least one of headlights or hazard.")
        return await request("POST", "/vehicle/lights", json=body)

    @server.tool(annotations=CONTROL)
    async def set_charging(charging: bool) -> dict[str, Any]:
        """Start or stop charging. The vehicle must be stopped to start charging.

        Args:
            charging: true to start, false to stop.
        """
        return await request("POST", "/vehicle/charging", json={"charging": charging})

    @server.tool(annotations=READ_ONLY)
    async def get_simulation_status() -> dict[str, Any]:
        """Get whether the simulation loop is running, elapsed time and MQTT status."""
        return await request("GET", "/simulation")

    @server.tool(annotations=CONTROL)
    async def advance_simulation(seconds: float) -> dict[str, Any]:
        """Advance the simulation instantly by the given time and return the
        resulting vehicle state. Useful to answer "what happens after N seconds".

        Args:
            seconds: Simulated time to advance, up to 3600.
        """
        return await request("POST", "/simulation/step", json={"seconds": seconds})

    @server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False))
    async def reset_simulation() -> dict[str, Any]:
        """Reset the vehicle to its initial state (stopped at the origin, full
        battery, doors locked). Discards the current state."""
        return await request("POST", "/simulation/reset")

    return server


if __name__ == "__main__":
    # httpx logs every request at INFO; keep the client's log view readable.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    create_server().run()

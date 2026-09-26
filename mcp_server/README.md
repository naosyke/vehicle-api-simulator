# Vehicle Simulator MCP Server

An [MCP](https://modelcontextprotocol.io/) server that lets AI assistants such as
Claude Desktop and Claude Code read and control the vehicle simulator in plain language:

> "What's the battery level?" / "Unlock and open the front left door." /
> "Drive at 40 km/h for a minute and tell me where the car ends up." /
> "How was my driving? Any dangerous moments?"

The server wraps the simulator's REST API as tools and communicates with the
MCP client over stdio. The vehicle rules still apply: when a command is
rejected (for example opening a locked door), the assistant receives the
reason and can explain it.

## Tools

| Tool | Type | Description |
|---|---|---|
| `get_vehicle_status` | read | Speed, battery, position, heading, doors, lights, ... |
| `get_recent_events` | read | Recent events, newest first |
| `get_driving_summary` | read | Trip statistics, anomaly counts and driving score |
| `get_simulation_status` | read | Simulation loop, elapsed time, MQTT status |
| `set_target_speed` | control | Accelerate / decelerate toward a speed (0 stops) |
| `emergency_brake` | control | Brake as hard as possible (recorded as harsh braking) |
| `set_steering` | control | Road wheel angle, -35 to 35 degrees |
| `set_door` | control | Open / close / lock / unlock a door |
| `set_lights` | control | Headlights and hazard lights |
| `set_charging` | control | Start / stop charging |
| `advance_simulation` | control | Jump the simulation forward by N seconds |
| `reset_simulation` | destructive | Reset the vehicle to its initial state |

Read-only and destructive tools are marked with MCP tool annotations, so
clients can decide which calls need confirmation.

## Setup

Requires Python 3.10+ (the MCP SDK does not support 3.9).

```bash
cd mcp_server
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Start the simulator (from the repository root):

```bash
docker compose up --build
```

## Connect to Claude Desktop

Add the server to `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS). Use absolute paths, and set `VEHICLE_API_URL` to the simulator's URL.

```json
{
  "mcpServers": {
    "vehicle-simulator": {
      "command": "/absolute/path/to/vehicle-api-simulator/mcp_server/.venv/bin/python",
      "args": ["/absolute/path/to/vehicle-api-simulator/mcp_server/server.py"],
      "env": {
        "VEHICLE_API_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

Restart Claude Desktop. The vehicle tools appear in the tools menu.

## Connect to Claude Code

```bash
claude mcp add vehicle-simulator \
  --env VEHICLE_API_URL=http://127.0.0.1:8000 \
  -- /absolute/path/to/vehicle-api-simulator/mcp_server/.venv/bin/python \
     /absolute/path/to/vehicle-api-simulator/mcp_server/server.py
```

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `VEHICLE_API_URL` | `http://127.0.0.1:8000` | Base URL of the vehicle simulator API |

## Tests

The tests run the MCP server against the FastAPI app in-process, so no
running simulator is needed.

```bash
cd mcp_server
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

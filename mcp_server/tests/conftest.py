import sys
from pathlib import Path

import pytest

# Import the FastAPI app (repository root) and the MCP server (mcp_server/).
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "mcp_server")]

from app.main import event_history, simulator  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def reset_simulator():
    simulator.reset()
    event_history.clear()
    yield
    simulator.reset()

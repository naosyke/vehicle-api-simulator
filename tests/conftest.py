import pytest

from app.main import event_history, simulator


@pytest.fixture(autouse=True)
def reset_simulator():
    simulator.reset()
    event_history.clear()
    yield
    simulator.reset()

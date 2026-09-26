import pytest

from app.main import simulator


@pytest.fixture(autouse=True)
def reset_simulator():
    simulator.reset()
    yield
    simulator.reset()

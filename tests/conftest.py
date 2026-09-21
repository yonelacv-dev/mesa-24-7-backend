import pytest

from tests.support.world import World


@pytest.fixture
def world() -> World:
    return World()

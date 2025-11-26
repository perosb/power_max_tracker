"""Test configuration for Power Max Tracker."""

import pytest


@pytest.fixture(autouse=True, scope="session")
def enable_event_loop_debug():
    """Override HA plugin's event loop debug to prevent issues."""
    # Do nothing to disable the problematic fixture
    pass
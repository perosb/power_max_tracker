import pytest


@pytest.fixture(autouse=True, scope="session")
def verify_cleanup():
    """Override HA plugin's verify_cleanup fixture to prevent event loop issues."""
    pass
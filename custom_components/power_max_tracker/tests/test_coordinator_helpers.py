"""Tests for PowerMaxCoordinator helper methods."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

# Test the helper method logic without importing the full coordinator
# We'll simulate the helper methods here for testing


def watts_to_kilowatts(watts: float) -> float:
    """Convert watts to kilowatts."""
    return watts / 1000.0


def update_max_values_with_timestamp(
    max_values,
    max_values_timestamps,
    new_value: float,
    timestamp: datetime,
    num_max_values: int,
):
    """Update max values list with a new value and its timestamp."""
    # Check if the new value is already in the list - if so, don't add it again
    if new_value in max_values:
        return max_values, max_values_timestamps, False

    old_max_values = max_values.copy()
    new_max_values = sorted(max_values + [new_value], reverse=True)[:num_max_values]

    # If the new list is the same as the old list, no change occurred
    if new_max_values == old_max_values:
        return max_values, max_values_timestamps, False

    new_timestamps = max_values_timestamps.copy()

    # The new value was added since it wasn't already in the list
    # Find where the new value was inserted
    insert_index = 0
    for i, val in enumerate(new_max_values):
        if val == new_value and (
            i >= len(old_max_values) or old_max_values[i] != new_value
        ):
            insert_index = i
            break

    # Shift timestamps and add new timestamp
    new_timestamps.insert(insert_index, timestamp)
    new_timestamps = new_timestamps[:num_max_values]

    return new_max_values, new_timestamps, True


class TestHelperMethods:
    """Test cases for helper methods that will be extracted."""

    @pytest.mark.asyncio
    async def test_watts_to_kilowatts_conversion(self):
        """Test watts to kilowatts conversion."""
        assert watts_to_kilowatts(1000) == 1.0
        assert watts_to_kilowatts(500) == 0.5
        assert watts_to_kilowatts(0) == 0.0
        assert watts_to_kilowatts(2500) == 2.5

    @pytest.mark.asyncio
    async def test_update_max_values_with_timestamp_new_value(self):
        """Test updating max values with a new value."""
        max_values = [0.0, 0.0]
        max_values_timestamps = [None, None]
        now = datetime.now()
        num_max_values = 2

        # Test adding first value
        new_max_values, new_timestamps, updated = update_max_values_with_timestamp(
            max_values, max_values_timestamps, 5.0, now, num_max_values
        )
        assert updated is True
        assert new_max_values == [5.0, 0.0]
        assert new_timestamps == [now, None]

        # Test adding second value
        new_max_values, new_timestamps, updated = update_max_values_with_timestamp(
            new_max_values, new_timestamps, 3.0, now, num_max_values
        )
        assert updated is True
        assert new_max_values == [5.0, 3.0]
        assert new_timestamps == [now, now]

        # Test adding higher value that replaces existing
        new_max_values, new_timestamps, updated = update_max_values_with_timestamp(
            new_max_values, new_timestamps, 7.0, now, num_max_values
        )
        assert updated is True
        assert new_max_values == [7.0, 5.0]
        assert new_timestamps == [now, now]

    @pytest.mark.asyncio
    async def test_update_max_values_with_timestamp_duplicate_value(self):
        """Test updating max values with duplicate values."""
        max_values = [5.0, 3.0]
        max_values_timestamps = [datetime.now(), datetime.now()]
        now = datetime.now()
        num_max_values = 2

        # Try to add the same value again - should not update
        new_max_values, new_timestamps, updated = update_max_values_with_timestamp(
            max_values, max_values_timestamps, 5.0, now, num_max_values
        )
        assert updated is False  # No change because value already exists
        assert new_max_values == [5.0, 3.0]

    @pytest.mark.asyncio
    async def test_update_max_values_with_timestamp_no_change(self):
        """Test updating max values with a value that doesn't make the top N."""
        max_values = [10.0, 8.0]
        max_values_timestamps = [datetime.now(), datetime.now()]
        now = datetime.now()
        num_max_values = 2

        # Try to add a low value that doesn't make the cut
        new_max_values, new_timestamps, updated = update_max_values_with_timestamp(
            max_values, max_values_timestamps, 1.0, now, num_max_values
        )
        assert updated is False
        assert new_max_values == [10.0, 8.0]


# Run tests if executed directly
if __name__ == "__main__":
    import sys

    test_instance = TestHelperMethods()

    test_methods = [
        method
        for method in dir(test_instance)
        if method.startswith("test_") and callable(getattr(test_instance, method))
    ]

    passed = 0
    failed = 0

    for test_method in test_methods:
        try:
            print(f"Running {test_method}...")
            getattr(test_instance, test_method)()
            print(f"✓ {test_method} PASSED")
            passed += 1
        except Exception as e:
            print(f"✗ {test_method} FAILED: {e}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")

    if failed > 0:
        sys.exit(1)

#!/bin/bash

# Script to run tests for Power Max Tracker Home Assistant integration

echo "Running tests for Power Max Tracker..."
python -m pytest custom_components/power_max_tracker/tests/ -v --asyncio-mode=auto
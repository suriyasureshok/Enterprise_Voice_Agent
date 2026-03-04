#!/usr/bin/env bash
# Start the VOXOPS logistics simulation standalone
cd "$(dirname "$0")/.."
source .venv/bin/activate
python -m voxops.simulation.route_simulator

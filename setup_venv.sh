#!/bin/bash
# Setup script for the renglo-cli virtual environment.
# Always installs from PyPI. A machine pip.conf pointed at CodeArtifact
# must not be used for this tool.
set -euo pipefail

cd "$(dirname "$0")"

PYPI_INDEX="https://pypi.org/simple"
VENV_NAME="${RENGLO_VENV_NAME:-renglo-venv}"

if [ ! -d "$VENV_NAME" ]; then
    echo "Creating virtual environment..."
    python3.12 -m venv "$VENV_NAME"
fi

# shellcheck disable=SC1091
source "$VENV_NAME/bin/activate"

echo "Installing dependencies from PyPI..."
pip install --isolated --index-url "$PYPI_INDEX" --upgrade pip
pip install --isolated --index-url "$PYPI_INDEX" -e ".[dev]"

echo "Setup complete! To activate the virtual environment, run:"
echo "  source ops/renglo-cli/$VENV_NAME/bin/activate"
echo ""
echo "Then run:"
echo "  renglo help"
echo "  renglo status"
echo "  renglo doctor"

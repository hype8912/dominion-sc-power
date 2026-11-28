#!/usr/bin/env bash
# Setup development environment

set -e

cd "$(dirname "$0")/.."

# Has this already been done?
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "No VIRTUAL_ENV set"
else
    echo "VIRTUAL_ENV is set"
    exit 1
fi

# Install dependencies with uv. This creates or updates .venv from
# pyproject.toml and uv.lock, including the development extra.
if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required. Install it from https://docs.astral.sh/uv/"
    exit 1
fi

uv sync --extra dev

echo ""
echo "✅ Setup complete!"
echo ""
echo "Available commands:"
echo "  ./scripts/lint        - Run linters and formatters"
echo "  ./scripts/test        - Run test suite"
echo ""
echo "Virtual environment: .venv/"
echo "To activate: source .venv/bin/activate"

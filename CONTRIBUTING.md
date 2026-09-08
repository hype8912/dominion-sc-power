# Contributing to dominion-sc-power

Thank you for your interest in contributing! This document provides guidelines for setting up your development environment and contributing to the project.

## Development Environment Setup

This project uses **[uv](https://docs.astral.sh/uv/)** as the package manager for fast, reliable dependency management.

### Prerequisites

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/getting-started/installation/) installed

### Quick Start

```bash
# Clone the repository
git clone https://github.com/sctigercat1/dominion-sc-power.git
cd dominion-sc-power

# Create virtual environment and install all dependencies (including dev)
uv sync --extra dev

# Activate the virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### Alternative: Manual Setup

If you prefer to create the environment and install the editable package
explicitly:

```bash
uv venv
source .venv/bin/activate  # On Windows: .venv\\Scripts\\activate
uv pip install -e ".[dev]"
```

## Dependency Management with uv

Project metadata is defined in `pyproject.toml`; `uv.lock` records the exact
resolved versions. Commit both files when changing dependencies.

### Add or Remove Dependencies

```bash
# Runtime dependency
uv add aiohttp
uv remove aiohttp

# Development-only dependency in the existing optional extra
uv add --dev pytest
uv remove --dev pytest
```

After changing dependencies, review the generated `pyproject.toml` and
`uv.lock`, then run `uv sync --extra dev`.

### Synchronize and Update Dependencies

```bash
# Install exactly what the lock file specifies
uv sync --extra dev --locked

# Re-resolve dependencies after changing project metadata
uv lock

# Check whether the lock file is current
uv lock --check

# Upgrade all compatible dependency versions and update uv.lock
uv lock --upgrade
uv sync --extra dev
```

Use `uv run <command>` for project commands. It automatically uses the
project environment, so activating `.venv` is optional.

## Testing and Code Quality

```bash
# Repository wrappers (recommended)
./scripts/lint
./scripts/test

# Direct uv commands
uv run ruff format .
uv run ruff check . --fix
uv run pytest

# Run one test module or a focused test
uv run pytest tests/test_dominionsc.py -v
uv run pytest -k "login" -v

# Type checking, when working on typed code
uv run mypy dominionsc
```

`./scripts/lint` formats the repository and applies safe Ruff fixes. Use
`uv run ruff check .` when you need a check-only command. The test script
runs pytest with coverage and writes the HTML report to `htmlcov/index.html`.

## Building the Package

```bash
# Build the wheel and source distribution
uv build

# Inspect the generated files
ls -lh dist/
```

The package uses setuptools as its build backend. Do not commit `dist/` or
other generated build artifacts.

## CI and Publishing

GitHub Actions currently installs dependencies with pip, while local
contributors should use uv. The CI workflows are the authoritative checks:

- `.github/workflows/lint.yml` runs Ruff lint and format checks.
- `.github/workflows/test.yaml` runs pytest with coverage on Python 3.13.
- `.github/workflows/python-publish.yaml` builds and publishes releases.

A release is published by GitHub Actions when a GitHub release is created.
Verify the package version and generated distributions before publishing.

## Troubleshooting

### Recreate the Environment

```bash
rm -rf .venv
uv sync --extra dev
```

### Refresh the uv Cache

```bash
uv cache clean
uv sync --extra dev
```

### Run Without Activation

If shell activation is unavailable, use `uv run` directly:

```bash
uv run python -m dominionsc --help
uv run pytest
```

## Contribution Checklist

Before opening a pull request:

1. Add or update tests for behavioral changes.
2. Update `README.md` for user-facing changes.
3. Update `CONTRIBUTING.md` when the developer workflow changes.
4. Update `uv.lock` when dependencies change.
5. Run `./scripts/lint` and `./scripts/test`.
6. Review the diff for credentials, tokens, generated files, and unrelated
   formatting changes.

Never commit Dominion credentials, MFA codes, login data, or files containing
account information. The repository ignores common local data-file names,
but verify `git status` before committing.

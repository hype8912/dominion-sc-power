# Deployment & Packaging Architecture

## Build & Package Structure (Grounded)

- `pyproject.toml` — package metadata, dependencies (`aiohttp`, etc.), dev extras, build-system (`setuptools`), tool configs (`ruff`, `pytest`).
- `uv.lock` — reproducible lockfile (27,710 bytes; committed).
- `.venv/` — virtualenv managed by `uv`; not committed (`.gitignore`).
- `scripts/setup` — setup helper.
- `src/dominionsc/` — source layout (not flat).

## CI/CD Pipeline Diagram

```mermaid
flowchart LR
    subgraph CI["GitHub Actions (.github/workflows/)"]
        Lint["lint.yml"]
        Test["test.yaml"]
        Publish["python-publish.yaml"]
    end

    subgraph Dev["Local Development"]
        UV["uv sync --extra dev"]
        Pytest["pytest"]
        Ruff["ruff check ."]
    end

    Push["git push"] --> CI
    CI --> Lint --> Pass?
    Pass? --> Test --> Pass2?
    Pass2? --> Publish --> PyPI

    Dev --> UV --> Pytest --> Ruff
```

## Deployment / Environment Diagram

```mermaid
flowchart TB
    subgraph Local["Developer Workstation"]
        Source["src/dominionsc/"]
        Venv[".venv (uv)"]
        Lock["uv.lock"]
    end

    subgraph Build["Build / CI"]
        Package["pyproject.toml + egg-info"]
        Wheel["built dist/"]
    end

    subgraph Registry["Distribution"]
        PyPI["pypi.org / dominion-sc-power"]
    end

    subgraph Consumer["Downstream"]
        HA_Integration["ha-dominion-sc (Home Assistant)"]
    end

    Source --> Package
    Lock --> Venv
    Venv --> Pytest
    Package --> Wheel --> PyPI --> HA_Integration
```

## Test Strategy (Grounded)

- `tests/` directory present; `pytest` used.
- Coverage reported (`.coverage`, `htmlcov/`).
- `test.yaml` runs on push/PR.
- `lint.yml` runs `ruff`.

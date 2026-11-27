# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). While the version is
0.x, a minor bump may include breaking changes.

## [0.3.0] - Unreleased

### Changed

- **Breaking:** Python 3.14 or newer is now required (was 3.11). Python 3.11-3.13
  can no longer install or import the package.
- Ruff and mypy now target Python 3.14, and CI lint, test and publish jobs run on 3.14.
- Added PyPI classifiers, including `Programming Language :: Python :: 3.14`.

### Fixed

- `typing.get_type_hints()` now works on every exported dataclass. `RatePlan`,
  `TimeOfUseRate`, `TimeWindow`, `TieredUsageCharge`, `TimeOfUseCharge` and
  `EligibilityRule` previously raised `NameError` because their field types were
  imported only for type checking.

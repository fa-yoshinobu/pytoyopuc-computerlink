# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- `read_many()` / `write_many()` and `relay_read_many()` / `relay_write_many()` now route through the high-level batching path where grouped relay/direct commands are available, while preserving input order.
- Direct high-level batching now uses `CMD=98` sparse extended reads, `CMD=99` sparse extended writes, `CMD=C4` sparse PC10 word reads, and `CMD=C5` sparse PC10 word writes where available.
- Extended multi-bit batch reads now unpack packed bit payloads correctly for batches larger than 8 points.
- `read_named()` bit-in-word helper parsing now accepts hexadecimal bit indices `A-F` as well as `0-9`, matching the .NET helper-layer behavior.
- Async helper wrappers now use per-client dedicated workers instead of the shared default executor.
- Transport and high-level layers cache relay hops, resolved devices, and compiled run plans to reduce repeated parsing and dispatch overhead.
- TCP receive and trace hot paths now allocate less during repeated polling.
- `run_ci.bat` now lint-checks `toyopuc/tests/scripts/samples`, compile-checks all `scripts/` and `samples/` entry points, and runs simulator-backed smoke tests through `scripts/run_sim_tests.bat`.
- Added `release_check.bat` to run CI and docs generation as one pre-release entry point.
- Added file-level regression tests that keep `samples/`, `scripts/`, and historical release templates aligned with the current repository layout.
- Documentation now consistently uses the current `scripts/` and `samples/` directories and points open-item references at `TODO.md`.

## [0.1.2] - 2026-03-22

### Changed
- Fixed Python version badge in `README.md` to match `requires-python = ">=3.10"`.
- Added `License :: OSI Approved :: MIT License` classifier consistency.

## [0.1.0] - 2026-03-19

### Added
- Initial Python client library for JTEKT TOYOPUC computer-link communication.
- `ToyopucDeviceClient` with TCP and UDP transport support.
- Model-aware addressing profiles and device catalog support.
- High-level `read`/`write` API for bit and word devices.
- Validation CLI and scripted hardware verification.
- Hardware verified against TOYOPUC-Plus and Nano 10GX targets.

### Notes
- First release under the `toyopuc-computerlink` PyPI package name.

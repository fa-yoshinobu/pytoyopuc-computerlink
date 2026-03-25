# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

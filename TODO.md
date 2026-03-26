# TODO: Toyopuc Computer Link Python

This file tracks the remaining tasks and known issues for the Toyopuc Computer Link Python library.

## 1. Protocol and Model Coverage
- [ ] **Extended Device Validation**: Expand verified coverage for newer Toyopuc model ranges and unresolved extended-device edge cases.
- [ ] **Addressing Matrix**: Convert the current probe knowledge into a maintained device/profile matrix that is easy to review before releases.

## 2. Testing and Validation
- [x] **Regression Automation**: Promoted the current `scripts/` probes into `run_ci.bat` with simulator-backed smoke coverage and explicit pass/fail handling.

## 3. Documentation and Quality
- [x] **Naming Sweep**: Audit the remaining docs and maintainer notes for stale wording after the `ToyopucDeviceClient` rename.
- [x] **Static Analysis Scope**: Keep `mypy` focused on `toyopuc/`, run `ruff` across `toyopuc/tests/scripts/samples`, and compile-check `scripts/` plus `samples/` in CI.



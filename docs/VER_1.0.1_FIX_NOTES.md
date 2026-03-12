# Ver1.0.1 Fix Notes

Created: 2026-03-12
Scope: Consolidated software fix memo based on the `bug/` folder notes.

## 1. Background

This memo consolidates the following source notes:

- `bug/PYTHON_DERIVED_ACCESS_CHECKLIST.md`
- `bug/PYTHON_PORTING_NOTES.md`
- `bug/PYTHON_PYTEST_CASE_MATRIX.md`

Main topics:

- Strict handling of bit-device derived notation (`W/H/L`) width and range
- Mandatory `P1-/P2-/P3-` prefix for `P/K/V/T/C/L/X/Y/M/S/N/R/D`
- Keep `GX` and `GY` explicit, do not use `GXY`

## 2. Ver1.0.1 Fix Items

### 2.1 Derived `W/H/L` notation hardening

- Separated bit notation and derived notation validation
- Added input digit preservation (`digits`) in `ParsedAddress`
- Validated derived access with derived ranges
- Rejected forbidden forms explicitly
  - examples: `M0000W`, `M0000L`, `EP0000W`, `GM1000W`, `P1-M0000W`
- Fixed `GM` word/byte base mapping to match hardware behavior
  - `GM` word base: `0x1000`
  - `GM` byte base: `0x2000`

Files:

- `toyopuc/address.py`
- `toyopuc/high_level.py`
- `tests/test_addressing_rules.py`

### 2.2 Prefix-required rule

- Enforced mandatory prefix for `P/K/V/T/C/L/X/Y/M/S/N/R/D` in high-level resolution
- Rejected unprefixed input with `ValueError`
  - examples: `D0000`, `M0000`, `D0000L`
- Accepted forms:
  - `P1-D0000`, `P2-M0000`, `P3-R0000`, `P1-D0000L`

Files:

- `toyopuc/high_level.py`
- `tests/test_addressing_rules.py`
- `tests/_internal/test_relay.py`

### 2.3 `GX` / `GY` naming consistency

- Kept `GX` and `GY` as explicit area names
- Removed synthetic `GXY` handling from public behavior

Files:

- `toyopuc/high_level.py`
- `tests/test_addressing_rules.py`

### 2.4 GUI input validation updates

- Added immediate validation in `device_monitor_gui` device input
- `P1-D0000-D000F` is accepted, `D0000` is rejected
- Forbidden forms (for example `M0000W`) are rejected in GUI as well

Files:

- `examples/device_monitor_gui.py`
- `tests/test_device_monitor_gui_input.py`
- `examples/device_monitor_gui.md`

### 2.5 Final edge 16-point consistency tooling

- Added `tools/final_whl_edge_test.py`
- Added `--write-mode bits|hl`
  - `bits`: write BIT16 contiguous points, then read `W/H/L`
  - `hl`: write `H/L`, then read back `W/BIT`
- Supports full pass over `P1/P2/P3` and basic/ext bit families
- Added matrix batch runner:
  - `tools/run_final_whl_edge_matrix.bat`

Files:

- `tools/final_whl_edge_test.py`
- `tools/run_final_whl_edge_matrix.bat`
- `tools/README.md`

### 2.6 Relay tool default alignment

- Updated relay high-level tool defaults to prefixed targets (`P1-...`)
- Prevented runtime failures caused by unprefixed defaults after rule change

Files:

- `tools/relay_block_test.py`
- `tools/relay_matrix_test.py`
- `tools/run_relay_block_test.bat`
- `tools/run_relay_matrix_test.bat`

## 3. Behavior Impact

Intentional behavior changes:

- Unprefixed forms such as `D0000` and `M0000` now fail
- Forbidden derived forms such as `M0000W` now fail
- `GX` and `GY` remain explicit; `GXY` is not accepted

## 4. Validation Summary

### 4.1 Static analysis and tests

- `mypy`: no errors on target files
- `pytest`: `76 passed`

### 4.2 Hardware verification (final edge WHL)

Verified points:

- `basic bit`: `P,K,V,T,C,L,X,Y,M` (`P1/P2/P3`)
- `ext bit`: `EP,EK,EV,ET,EC,EL,EX,EY,EM,GM,GX,GY`
- BIT16 contiguous write and `W/H/L` read consistency
- both `--write-mode bits` and `--write-mode hl`
- TCP and UDP paths

Final observed result: all targeted cases matched.

## 5. Source Notes

- `bug/PYTHON_DERIVED_ACCESS_CHECKLIST.md`
- `bug/PYTHON_PORTING_NOTES.md`
- `bug/PYTHON_PYTEST_CASE_MATRIX.md`

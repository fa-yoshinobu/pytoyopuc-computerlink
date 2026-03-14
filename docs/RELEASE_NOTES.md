# Release Notes

Related documents:

- [../README.md](../README.md)
- [TESTING.md](TESTING.md)
- [MODEL_RANGES.md](MODEL_RANGES.md)
- [COMPUTER_LINK_SPEC.md](COMPUTER_LINK_SPEC.md)
- [RELEASE.md](RELEASE.md)

## v1.0.3

Documentation and repository-link refresh release.

Release date:

- 2026-03-15

### Included

- updated GitHub repository links to:
  - `https://github.com/fa-yoshinobu/toyopuc-computer-link-python`
- updated GitHub Pages links to:
  - `https://fa-yoshinobu.github.io/toyopuc-computer-link-python/`
- added related repository note for the `.NET` implementation:
  - `https://github.com/fa-yoshinobu/toyopuc-computer-link-dotnet`
- refreshed generated API docs under `docs/api`

### Verification

- API docs:
  - `tools\build_api_docs.bat` passed
- package checks:
  - `python -m build` passed
  - `python -m twine check dist/*` passed

## v1.0.2

Regression-guard release for sparse `pc10-word` `read_many` behavior.

Release date:

- 2026-03-12

### Included

- added unit regression tests for sparse `pc10-word` reads:
  - `test_high_level_read_many_pc10_word_sparse_uses_block_read_only`
  - `test_high_level_relay_read_many_pc10_word_sparse_uses_block_read_only`
- documented the new regression guard in [TESTING.md](TESTING.md)

### Verification

- automated tests:
  - `python -m pytest tests/_internal/test_relay.py -q` passed (`24 passed`)

## v1.0.0

Initial public release of `toyopuc-computerlink`.

### Included

- low-level client: `ToyopucClient`
- high-level client: `ToyopucHighLevelClient`
- address parsing and encoding helpers
- TCP support
- UDP support with optional fixed local source port
- clock read / write
- CPU status read
- `W/H/L` addressing for bit-device word/byte access
- examples
- simulator smoke test tools
- generated API docs via `pdoc`

### Verified

Real hardware verified on:

- `TOYOPUC-Plus CPU (TCC-6740) + Plus EX2 (TCU-6858)`

Verified communication paths:

- TCP
- UDP with fixed `local_port`

Verified feature groups:

- basic device read / write
- prefixed `P1/P2/P3`
- extension bit / word access
- mixed `CMD=98/99`
- block access
- boundary checks
- recovery write / read checks
- high-level API
- clock read / write
- CPU status read
- relay command read / write
- `W/H/L` addressing

### Included Documents

- [../README.md](../README.md)
- [TESTING.md](TESTING.md)
- [COMPUTER_LINK_SPEC.md](COMPUTER_LINK_SPEC.md)
- [MODEL_RANGES.md](MODEL_RANGES.md)
- [PENDING.md](PENDING.md)
- [RELEASE.md](RELEASE.md)
- [../examples/README.md](../examples/README.md)

### Known Limitations

- `FR` is not part of the normal safe test path
- `CMD=60` is verified for single-hop read / write / FR commit on `P1-L2:N2`; selected two-hop / three-hop read paths; three-hop basic word write `CMD=1D` with readback; three-hop contiguous 8-word relay write/readback on `D0000-D0007`; three-hop relay `FR000000` read / write / commit path (`P1-L2:N4 -> P1-L2:N6 -> P1-L2:N2`); a three-hop relay high-level API sweep (`TOTAL: 24/24`); a broader three-hop relay matrix (`D/R/U` passed for counts `16/32`, `S` did not retain written patterns); relay low-level sweeps on both UDP and TCP; and relay abnormal-case sweeps showing timeout/no-reply behavior for missing station, broken path, out-of-range `D3000`, and relay write to `S0000`. Standalone relay `CMD=A0 / 01 10` still returned NAK on the verified Plus relay paths.
- high-level `read_many()` / `write_many()` still use simple per-item dispatch
- model-specific unsupported areas exist

### Model Notes

For `TOYOPUC-Plus CPU (TCC-6740) + Plus EX2 (TCU-6858)`:

- `B` is unsupported
- `EB` is not present
- `U08000-U1FFFF` does not exist on this model
- prefixed upper ranges such as `P1/P2/P3-D1000+` are unsupported

### Packaging

Verified before release:

- `python -m py_compile ...`
- `python -m build`
- `python -m twine check dist/*`

## v1.0.1

Addressing and validation hardening release focused on documented `W/H/L` behavior,
prefix-required high-level inputs, and end-to-end verification tooling.

Release date:

- 2026-03-12

### Included

- strict derived `W/H/L` validation for bit-device families
- preserved parsed input digit width in resolver flow
- explicit prefix-required rule for `P/K/V/T/C/L/X/Y/M/S/N/R/D` on high-level resolver input
- explicit `GX`/`GY` naming (no synthetic `GXY` area in public behavior)
- GUI immediate device-input validation for allowed and rejected forms
- final-edge consistency tool:
  - `tools/final_whl_edge_test.py` with `--write-mode bits|hl`
  - `tools/run_final_whl_edge_matrix.bat` for `TCP/UDP x P1/P2/P3 x bits/hl`
- relay high-level tool defaults aligned to prefixed targets (`P1-...`)
- generated API docs refresh (`docs/api/*`)

### Breaking Changes

- high-level resolver now rejects unprefixed forms for:
  - `P/K/V/T/C/L/X/Y/M/S/N/R/D`
- examples:
  - rejected: `D0000`, `M0000`, `D0000L`
  - accepted: `P1-D0000`, `P2-M0000`, `P3-R0000`, `P1-D0000L`
- forbidden derived forms are now rejected:
  - `M0000W`, `M0000L`, `EP0000W`, `GM1000W`, `P1-M0000W`

### Migration Notes

Update calls and scripts that used unprefixed basic families.

Before:

```python
plc.read("D0000")
plc.write("M0000", 1)
```

After:

```python
plc.read("P1-D0000")
plc.write("P1-M0000", 1)
```

For relay high-level tools, use prefixed targets by default:

```powershell
python examples/relay_basic.py --mode word-read --device P1-D0000
```

### Verification

- static/type checks:
  - `mypy` passed on target files
- automated tests:
  - `pytest` passed (`76 passed`)
- package checks:
  - `python -m build`
  - `python -m twine check dist/*`
- API docs:
  - `tools\build_api_docs.bat`
- hardware validation:
  - final-edge `W/H/L` consistency confirmed over TCP and UDP with both write modes

### Related Documents

- [VER_1.0.1_FIX_NOTES.md](VER_1.0.1_FIX_NOTES.md)
- [TESTING.md](TESTING.md)
- [COMPUTER_LINK_SPEC.md](COMPUTER_LINK_SPEC.md)


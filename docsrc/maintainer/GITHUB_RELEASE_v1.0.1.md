# GitHub Release Template: v1.0.1

Use this file as a copy-paste template for the GitHub Releases form.

## Release Settings

- Title: `v1.0.1`
- Tag: `v1.0.1`
- Target: `main`
- Set as latest release: `yes`
- Pre-release: `no`

## Release Body

Addressing and validation hardening release focused on documented `W/H/L`
behavior, prefix-required high-level inputs, and end-to-end verification tools.

## Highlights

- strict derived `W/H/L` validation for bit-device families
- mandatory `P1-/P2-/P3-` prefix for high-level
  `P/K/V/T/C/L/X/Y/M/S/N/R/D` inputs
- explicit `GX`/`GY` handling (no synthetic `GXY`)
- GUI immediate validation for valid/invalid device text
- final-edge consistency tool:
  - `tools/final_whl_edge_test.py` (`--write-mode bits|hl`)
  - `tools/run_final_whl_edge_matrix.bat`
- relay high-level defaults aligned to prefixed targets (`P1-...`)
- refreshed API docs under `docsrc/api`

## Breaking Changes

- high-level resolver now rejects unprefixed forms for:
  - `P/K/V/T/C/L/X/Y/M/S/N/R/D`
- examples:
  - rejected: `D0000`, `M0000`, `D0000L`
  - accepted: `P1-D0000`, `P2-M0000`, `P3-R0000`, `P1-D0000L`
- forbidden derived forms are now rejected:
  - `M0000W`, `M0000L`, `EP0000W`, `GM1000W`, `P1-M0000W`

## Migration Example

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

## Verification

- `python -m pytest -q` -> `76 passed`
- `python -m mypy ...` (target files) -> passed
- `python -m build` -> passed
- `python -m twine check dist/*` -> passed
- `tools\build_api_docs.bat` -> passed

Hardware note:

- final-edge `W/H/L` consistency was confirmed over TCP and UDP with both
  `--write-mode bits` and `--write-mode hl`.

## Included Documents

- `README.md`
- `docsrc/TESTING.md`
- `docsrc/COMPUTER_LINK_SPEC.md`
- `docsrc/MODEL_RANGES.md`
- `docsrc/RELEASE.md`
- `docsrc/RELEASE_NOTES.md`
- `docsrc/VER_1.0.1_FIX_NOTES.md`
- `examples/README.md`
- `tools/README.md`

## Assets

- wheel: `dist/toyopuc_computerlink-1.0.1-py3-none-any.whl`
- source tarball: `dist/toyopuc_computerlink-1.0.1.tar.gz`

## Upload Checklist

- attach `toyopuc_computerlink-1.0.1-py3-none-any.whl`
- attach `toyopuc_computerlink-1.0.1.tar.gz`
- confirm the title is `v1.0.1`
- confirm the tag is `v1.0.1`
- confirm release notes match [RELEASE_NOTES.md](RELEASE_NOTES.md)


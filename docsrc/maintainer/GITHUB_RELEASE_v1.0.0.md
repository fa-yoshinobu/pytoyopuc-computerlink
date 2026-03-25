# GitHub Release Template: v1.0.0

Use this file as a copy-paste template for the GitHub Releases form.

## Release Settings

- Title: `v1.0.0`
- Tag: `v1.0.0`
- Target: `main`
- Set as latest release: `yes`
- Pre-release: `no`

## Release Body

Initial public release of `toyopuc-computerlink`.

## Highlights

- low-level client: `ToyopucClient`
- high-level client: `ToyopucDeviceClient`
- TCP and UDP support
- clock read / write
- CPU status read
- `W/H/L` addressing
- relay command (`CMD=60`) helpers and examples
- FR read / write / commit helpers
- GUI monitor example and Windows executable build helper

## Verified Hardware

Verified on real hardware:

- `TOYOPUC-Plus CPU (TCC-6740) + Plus EX2 (TCU-6858)`
- `Nano 10GX (TUC-1157)`
- `PC3JX-D (TCC-6902)` in PC3 mode and Plus Expansion mode
- `PC10G CPU (TCC-6353)`

Verified communication paths:

- TCP
- UDP with fixed `local_port`

## Relay Summary

`CMD=60` relay support is verified for:

- single-hop read / write / FR commit on `P1-L2:N2`
- selected two-hop / three-hop read paths
- three-hop basic word write with readback
- three-hop contiguous 8-word relay write/readback on `D0000-D0007`
- three-hop relay `FR000000` read / write / commit path
- three-hop high-level API sweep (`TOTAL: 24/24`)
- three-hop relay matrix checks on `D/R/S/U`
- relay low-level sweeps on both UDP and TCP

Observed limitation:

- standalone relay `CMD=A0 / 01 10` returned NAK on the verified Plus relay paths

## Included Documents

- `README.md`
- `docsrc/TESTING.md`
- `docsrc/COMPUTER_LINK_SPEC.md`
- `docsrc/MODEL_RANGES.md`
- `docsrc/RELEASE.md`
- `docsrc/RELEASE_NOTES.md`
- `examples/README.md`
- `tools/README.md`

## Known Limitations

- `FR` is not part of the normal safe test path
- high-level `read_many()` / `write_many()` still use simple per-item dispatch
- model-specific unsupported areas remain

## Packaging

Checked before release:

- `python -m py_compile ...`
- `python -m ruff check toyopuc tools tests examples`
- `python -m compileall toyopuc tools tests examples`
- `python -m build`
- `python -m twine check dist/*`
- `python -m pdoc -o docsrc/api toyopuc`

## Assets

- wheel: `dist/toyopuc_computerlink-1.0.0-py3-none-any.whl`
- source tarball: `dist/toyopuc_computerlink-1.0.0.tar.gz`
- GUI executable: `dist/toyopuc-device-monitor/toyopuc-device-monitor.exe`

## Upload Checklist

- attach `toyopuc_computerlink-1.0.0-py3-none-any.whl`
- attach `toyopuc_computerlink-1.0.0.tar.gz`
- attach `toyopuc-device-monitor.exe` if distributing the GUI binary separately
- confirm the title is `v1.0.0`
- confirm the tag is `v1.0.0`
- confirm release notes match [RELEASE_NOTES.md](RELEASE_NOTES.md)


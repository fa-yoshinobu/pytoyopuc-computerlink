# Agent Guide: Toyopuc Computer Link Python

This repository is part of the PLC Communication Workspace and follows the global standards defined in `AGENTS.md`.

## 1. Project-Specific Context
- **Protocol**: TOYOPUC Computer Link (JTEKT)
- **Authoritative Source**: JTEKT/Toyoda specs 
- **Language**: Python (3.11+)
- **Role**: Core Communication Library for TOYOPUC-Plus, Nano 10GX, etc.

## 2. Mandatory Rules (Global Standards)
- **Language**: All code, comments, and documentation MUST be in **English**.
- **Encoding**: Use **UTF-8 (without BOM)** for all files to prevent Mojibake.
- **Mandatory Static Analysis**:
  - All changes must pass `ruff` (linting/formatting) and `mypy` (type checking).
  - Use `ruff check .` and `ruff format .` before committing.
- **Documentation Structure**: Follow the Modern Documentation Policy:
  - `docsrc/user/`: User manuals and API guides. [DIST]
  - `docsrc/maintainer/`: Protocol specs and internal logic. [REPO]
  - `docsrc/validation/`: Hardware QA reports and bug analysis. [REPO]
- **Distribution Control**: Ensure `pyproject.toml` excludes `docsrc/maintainer/`, `docsrc/validation/`, `tests/`, `tools/`, and `TODO.md` from PyPI/Wheel packages.

## 3. Reference Materials
- **Official Specs**: Refer to `internal_reference_library/JTEKT/` for authoritative English manuals (Local only).
- **Evidence**: Check `docsrc/validation/reports/` for verified communication results with TOYOPUC-Plus and Nano 10GX.

## 4. Development Workflow
- **Issue Tracking**: Log remaining tasks in `TODO.md`.
- **Change Tracking**: Update `CHANGELOG.md` for every fix or feature.
- **QA Requirement**: Every hardware-related fix must include an evidence report in `docsrc/validation/reports/`.

## 5. API Naming Policy

Detailed naming policy lives in `docsrc/maintainer/API_UNIFICATION_POLICY.md`.

Public API rules:

- Recommended client: `AsyncToyopucDeviceClient` (via `open_and_connect`) for high-level, async, string-based address access.
- For scripts or legacy environments, `ToyopucDeviceClient` (sync) is also available.
- Internal clients: `AsyncToyopucClient` and `ToyopucClient` for raw protocol-level access using 32-bit internal addresses.
- High-level string-device access uses `read`, `write`, `read_many`, etc.
- 32-bit helpers should use `read_dword`, `read_float32` style names.
- Method names should be consistent between sync and async classes.

Private or helper naming rules:

- Avoid vague helper names such as `_read_one`, `_write_one`, or `_offset`.
- Prefer names that describe the subject, such as `_read_resolved_device`, `_write_resolved_device`, and `_offset_resolved_device`.
- Keep protocol-family names explicit in helpers such as `_pack_pc10_multi_word_payload` or `_resolve_ext_bit`.
- 32-bit codec helpers should include both type and word order, for example `_pack_uint32_low_word_first` or `_unpack_float32_low_word_first`.



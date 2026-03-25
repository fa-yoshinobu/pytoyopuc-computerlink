# Toyopuc Computer Link Python

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Static Analysis: Ruff](https://img.shields.io/badge/Lint-Ruff-black.svg)](https://github.com/astral-sh/ruff)

A professional Python client library for JTEKT (Toyoda) TOYOPUC computer-link communication. Supporting TOYOPUC-Plus, Nano 10GX, and other compatible models.

## Key Features

- **Vendor Focused**: Tailored for JTEKT TOYOPUC protocol specifications.
- **High-Level API**: Simplified `read` and `write` methods for bits and words.
- **Robustness**: Built-in handling for Toyopuc-specific memory ranges and boundary behaviors.
- **Zero Mojibake**: Strictly English-based documentation and UTF-8 standards.
- **CI-Ready**: Automated quality checks and standalone CLI tool generation.

## Quick Start

### Installation
```bash
pip install toyopuc-computerlink
```

### Basic Usage
```python
from toyopuc import ToyopucDeviceClient

with ToyopucDeviceClient("192.168.1.5", 1025) as client:
    # Read D1000 (Word)
    val = client.read("D1000")
    print(f"Value: {val}")

    # Write to M0 (Bit)
    client.write("M0", True)
```

## Documentation

Follows the workspace-wide hierarchical documentation policy:

- [**User Guide**](user/USER_GUIDE.md): Detailed usage and connection setup.
- [**Model Ranges**](user/MODEL_RANGES.md): Supported device ranges for different Toyopuc models.
- [**QA Reports**](validation/reports/): Formal evidence of communication with real Toyopuc hardware.
- [**Protocol Spec**](maintainer/PROTOCOL_SPEC.md): Internal technical details of the computer-link protocol.

## Development & CI

Quality is managed via `run_ci.bat`.

### Quality Checks
- **Linting & Formatting**: [Ruff](https://ruff.rs/)
- **Type Checking**: [Mypy](http://mypy-lang.org/)
- **Unit Testing**: Python `unittest`

### Local CI Run
```bash
run_ci.bat
```
Validates the code and builds a standalone CLI tool in the `publish/` directory.

## License

Distributed under the [MIT License](LICENSE).




[![CI](https://github.com/fa-yoshinobu/plc-comm-computerlink-python/actions/workflows/ci.yml/badge.svg)](https://github.com/fa-yoshinobu/plc-comm-computerlink-python/actions/workflows/ci.yml)
[![Documentation](https://img.shields.io/badge/docs-GitHub_Pages-blue.svg)](https://fa-yoshinobu.github.io/plc-comm-computerlink-python/)
[![PyPI](https://img.shields.io/pypi/v/toyopuc-computerlink.svg)](https://pypi.org/project/toyopuc-computerlink/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Static Analysis: Ruff](https://img.shields.io/badge/Lint-Ruff-black.svg)](https://github.com/astral-sh/ruff)

# Computer Link Protocol for Python

![Illustration](https://raw.githubusercontent.com/fa-yoshinobu/plc-comm-computerlink-python/main/docsrc/assets/toyopuc.png)

A user-focused Python library for JTEKT TOYOPUC Computer Link communication.
The recommended entry points are the high-level `ToyopucDeviceClient` class and the async helper functions in `toyopuc`.

For asyncio code, prefer:

- `ToyopucConnectionOptions`
- `open_and_connect`
- `normalize_address`
- `read_named`
- `poll`
- `read_words_single_request`
- `read_dwords_single_request`
- `read_words_chunked`
- `read_dwords_chunked`

## Quick Start

### Installation

```bash
pip install toyopuc-computerlink
```

Latest release metadata and downloads are available at <https://pypi.org/project/toyopuc-computerlink/>.

### Synchronous Example

```python
from toyopuc import ToyopucDeviceClient

with ToyopucDeviceClient("192.168.250.100", 1025) as client:
    value = client.read("P1-D0000")
    print(f"P1-D0000 = {value}")

    client.write("P1-D0001", 1234)
    client.write("P1-M0000", 1)

    snapshot = client.read_many(["P1-D0000", "P1-D0001", "P1-M0000"])
    print(snapshot)
```

### Asynchronous Example

```python
import asyncio
from toyopuc import ToyopucConnectionOptions, open_and_connect, read_named, read_typed, write_typed

async def main() -> None:
    options = ToyopucConnectionOptions(host="192.168.250.100", port=1025, timeout=3.0, retries=0)
    async with await open_and_connect(options) as plc:
        speed = await read_typed(plc, "P1-D0100", "F")
        print(f"speed = {speed}")

        await write_typed(plc, "P1-D0200", "L", -500)

        values = await read_named(plc, ["P1-D0000", "P1-D0100:F", "P1-D0000.0"])
        print(values)

asyncio.run(main())
```

Basic area families `P/K/V/T/C/L/X/Y/M/S/N/R/D` require a `P1-`, `P2-`, or `P3-` prefix.

## Supported PLC Registers

Start with these public high-level families first:

- prefixed word/register areas: `P1-D0000`, `P1-S0000`, `P1-N0100`, `P1-R0000`
- prefixed bit/control areas: `P1-M0000`, `P1-X0000`, `P1-Y0000`
- extension areas: `ES0000`, `EN0000`
- FR storage: `FR000000`
- typed and bit views: `P1-D0100:S`, `P1-D0200:D`, `P1-D0300:F`, `P1-D0000.3`

See the full public table in [Supported PLC Registers](docsrc/user/SUPPORTED_REGISTERS.md).

## Public Docs

- [Getting Started](docsrc/user/GETTING_STARTED.md)
- [Supported PLC Registers](docsrc/user/SUPPORTED_REGISTERS.md)
- [Latest Communication Verification](docsrc/user/LATEST_COMMUNICATION_VERIFICATION.md)
- [User Guide](docsrc/user/USER_GUIDE.md)
- [Model Ranges](docsrc/user/MODEL_RANGES.md)
- [Sample Guide](samples/README.md)

Start with these sample programs:

- `samples/high_level_minimal.py`
- `samples/high_level_basic.py`
- `samples/high_level_all_sync.py`
- `samples/high_level_all_async.py`
- `samples/high_level_udp.py`

Maintainer-only notes and retained evidence live under `internal_docs/`.

## Common User Tasks

- normalize one address string: `normalize_address("p1-d0000", profile="TOYOPUC-Plus:Plus Standard mode")`
- read or write one device: `client.read("P1-D0000")`, `client.write("P1-M0000", 1)`
- read a mixed snapshot: `client.read_many([...])` or `await read_named(plc, [...])`
- read 32-bit or float values: `client.read_dword(...)`, `client.read_float32(...)`, `await read_typed(..., "D" / "L" / "F")`
- change one flag bit inside a word: `await write_bit_in_word(plc, "P1-D0100", bit_index=3, value=True)`
- read contiguous areas with explicit intent: `await read_words_single_request(...)`, `await read_words_chunked(...)`
- read or write FR storage: `client.read_fr(...)`, `client.write_fr(..., commit=True)`

## Development & CI

```bash
run_ci.bat
release_check.bat
```

## License

Distributed under the [MIT License](LICENSE).

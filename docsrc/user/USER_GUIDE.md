# User Guide: TOYOPUC Computer Link Python

This page explains the high-level Python API only.
Use it when you want to read and write TOYOPUC devices by device string such as `P1-D0000`, `P1-M0000`, `ES0000`, or `FR000000`.

## Installation

```bash
pip install .
```

## Choose an API

Use one of these two styles:

- `ToyopucDeviceClient`
  Best for scripts, tools, and desktop applications that want simple synchronous calls.
- `open_and_connect(...)` plus helper functions such as `read_typed`, `read_named`, and `poll`
  Best for asyncio applications.

## Quick start

### Synchronous workflow

```python
from toyopuc import ToyopucDeviceClient

with ToyopucDeviceClient("192.168.250.100", 1025) as plc:
    word_value = plc.read("P1-D0000")
    print(f"P1-D0000 = {word_value}")

    plc.write("P1-D0001", 1234)
    plc.write("P1-M0000", 1)

    snapshot = plc.read_many(["P1-D0000", "P1-D0001", "P1-M0000"])
    print(snapshot)
```

### Asynchronous workflow

```python
import asyncio
from toyopuc import open_and_connect, read_named, read_typed, write_typed

async def main() -> None:
    async with await open_and_connect("192.168.250.100", 1025) as plc:
        speed = await read_typed(plc, "P1-D0100", "F")
        print(f"speed = {speed}")

        await write_typed(plc, "P1-D0200", "L", -500)

        values = await read_named(plc, ["P1-D0000", "P1-D0100:F", "P1-D0000.0"])
        print(values)

asyncio.run(main())
```

## Device addressing

### Address format

```text
[Program]-[AreaType][Address]
```

- `Program`
  `P1`, `P2`, or `P3`
- `AreaType`
  device family such as `D`, `M`, `ES`, `FR`
- `Address`
  decimal or hexadecimal device number

When a profile is in use, basic families `P/K/V/T/C/L/X/Y/M/S/N/R/D` should be written as `P1-*`, `P2-*`, or `P3-*`.

### Common device families

| Area | Type | Example |
| --- | --- | --- |
| `D` | Data register (word) | `P1-D0100` |
| `S` | Special register (word) | `P1-S0000` |
| `N` | File register (word) | `P1-N0100` |
| `M` | Internal relay (bit) | `P1-M0100` |
| `P` | Shared relay (bit) | `P1-P0000` |
| `X` | Input relay (bit) | `P1-X0000` |
| `Y` | Output relay (bit) | `P1-Y0000` |
| `T` | Timer (bit) | `P1-T0000` |
| `C` | Counter (bit) | `P1-C0000` |
| `ES` | Extended special register (word) | `ES0000` |
| `EN` | Extended file register (word) | `EN0000` |
| `U` | Extended word area | `U00000` |
| `EB` | Extended block word area | `EB00000` |
| `FR` | File register flash area | `FR000000` |

Extended areas such as `ES`, `EN`, `H`, `U`, `EB`, and `FR` do not require a program prefix.

### Byte and packed-word suffixes

Append `L`, `H`, or `W` to bit-area addresses for byte or packed-word access:

```python
plc.read("P1-M0010W")   # M0010 as a packed 16-bit word
plc.read("P1-M0010L")   # low byte of the packed word
plc.read("P1-M0010H")   # high byte of the packed word
```

## Common tasks

### Read and write a single device

```python
value = plc.read("P1-D0000")
plc.write("P1-D0001", 1234)
plc.write("P1-M0000", 1)
```

### Read and write several devices together

```python
snapshot = plc.read_many(["P1-D0000", "P1-D0001", "P1-M0000"])
print(snapshot)

plc.write_many(
    {
        "P1-D0000": 10,
        "P1-D0001": 20,
        "P1-M0000": 0,
    }
)
```

### Read 32-bit and float values

Use `ToyopucDeviceClient` when you prefer synchronous methods:

```python
counter = plc.read_dword("P1-D0200")
temperature = plc.read_float32("P1-D0300")
values = plc.read_dwords("P1-D0200", 4)
```

Use async helper functions when you prefer explicit type codes:

| dtype | Type | Size |
| --- | --- | --- |
| `"U"` | unsigned 16-bit int | 1 word |
| `"S"` | signed 16-bit int | 1 word |
| `"D"` | unsigned 32-bit int | 2 words |
| `"L"` | signed 32-bit int | 2 words |
| `"F"` | float32 | 2 words |

```python
float_value = await read_typed(plc, "P1-D0100", "F")
signed_value = await read_typed(plc, "P1-D0200", "L")
await write_typed(plc, "P1-D0100", "F", 3.14)
await write_typed(plc, "P1-D0200", "S", -100)
```

### Read contiguous blocks

```python
from toyopuc import read_words, read_dwords

words = await read_words(plc, "P1-D0000", 10)
dwords = await read_dwords(plc, "P1-D0000", 4)
```

### Change one bit inside a word

```python
from toyopuc import write_bit_in_word

await write_bit_in_word(plc, "P1-D0100", bit_index=3, value=True)
```

### Read a typed snapshot by name

Address notation:

| Format | Meaning |
| --- | --- |
| `"P1-D0100"` | unsigned 16-bit word |
| `"P1-D0100:F"` | float32 |
| `"P1-D0100:S"` | signed 16-bit word |
| `"P1-D0100:D"` | unsigned 32-bit value |
| `"P1-D0100:L"` | signed 32-bit value |
| `"P1-D0100.3"` | bit 3 inside the word |

```python
from toyopuc import read_named

result = await read_named(
    plc,
    ["P1-D0100", "P1-D0101:F", "P1-D0102:S", "P1-D0100.3"],
)
print(result)
```

### Poll values repeatedly

`poll` yields a snapshot dictionary every interval.

```python
import asyncio
from toyopuc import open_and_connect, poll

async def main() -> None:
    async with await open_and_connect("192.168.250.100") as plc:
        count = 0
        async for snapshot in poll(plc, ["P1-D0100", "P1-D0101:F"], interval=1.0):
            print(snapshot)
            count += 1
            if count >= 3:
                break

asyncio.run(main())
```

### FR file register access

Use FR helpers when you need non-volatile file-register data.

```python
current_value = plc.read_fr("FR000000")
plc.write_fr("FR000000", 0x1234, commit=False)
plc.commit_fr("FR000000", wait=True)
```

Use `commit=True` only when you intentionally want to persist the modified FR block to flash.

### Relay access

Relay helpers are also available from `ToyopucDeviceClient`.

```python
status = plc.relay_read_cpu_status("P1-L2:N2")
word_value = plc.relay_read_words("P1-L2:N2", "P1-D0000", count=1)
plc.relay_write_words("P1-L2:N2", "P1-D0000", 0x1234)
```

## Error handling

| Exception | Condition |
| --- | --- |
| `ToyopucError` | PLC returned an error response |
| `ToyopucProtocolError` | Malformed or unexpected protocol data |
| `ToyopucTimeoutError` | Communication timeout |

```python
from toyopuc import ToyopucError, ToyopucProtocolError, ToyopucTimeoutError

try:
    value = await plc.read("P1-D0000")
except ToyopucTimeoutError:
    print("Timeout: check IP address and Computer Link port.")
except ToyopucProtocolError as exc:
    print(f"Protocol error: {exc}")
except ToyopucError as exc:
    print(f"PLC error: {exc}")
```

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `ToyopucTimeoutError` | Wrong IP or port | Default port is 1025. Confirm the Computer Link network settings. |
| `ToyopucProtocolError` | Invalid address format | Check the program prefix and the device family. |
| Wrong values | Word / byte mismatch | Recheck `W`, `L`, and `H` suffix usage. |

## Sample programs

Open these files when you want a complete working example:

- `samples/high_level_minimal.py`
  Smallest possible read / write workflow
- `samples/high_level_basic.py`
  Single reads, `read_many`, and `W/H/L` packed access
- `samples/high_level_all_sync.py`
  Sync cookbook for `ToyopucDeviceClient`
- `samples/high_level_all_async.py`
  Async cookbook for `open_and_connect`, `read_typed`, `read_named`, `poll`, and related helpers
- `samples/high_level_udp.py`
  UDP connection with `--local-port`
- `samples/fr_basic.py`
  FR read, write, and optional commit
- `samples/relay_basic.py`
  Relay CPU status, clock, word, and FR examples
- `samples/clock_and_status.py`
  PLC clock and CPU status decode
  Desktop monitor UI

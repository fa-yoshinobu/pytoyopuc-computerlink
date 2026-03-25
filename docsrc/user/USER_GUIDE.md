# User Guide: TOYOPUC Computer Link Python

Asynchronous Python client for JTEKT TOYOPUC PLCs using the Computer Link protocol.

## Installation

```bash
pip install .
```

---

## Quick Start

### Async client (Recommended)

The high-level `AsyncToyopucDeviceClient` provides string-based address access and is the recommended way to use this library.

```python
import asyncio
from toyopuc import open_and_connect

async def main():
    # Use 'open_and_connect' for automatic session management
    async with await open_and_connect("192.168.1.5", 1025) as plc:
        # Read word device P1-D0000
        val = await plc.read("P1-D0000")
        print(f"P1-D0000 = {val}")

        # Write word device P1-D0010
        await plc.write("P1-D0010", 1234)

asyncio.run(main())
```

### Synchronous client

For scripts or environments where `asyncio` is not available, a synchronous wrapper is provided.

```python
from toyopuc import ToyopucDeviceClient

with ToyopucDeviceClient("192.168.1.5", 1025) as plc:
    # Read word device P1-D0000
    val = plc.read("P1-D0000")
    print(f"P1-D0000 = {val}")
```

---

## Device Addressing

### Address Format

```
[Program]-[AreaType][Address]
```

- **Program**: `P1`, `P2`, `P3` — program number (required for basic areas)
- **AreaType**: device area code
- **Address**: decimal or hex device number

### Device Areas

| Area | Type | Example |
|------|------|---------|
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

Extended areas (`ES`, `EN`, `H`, `U`, `EB`, `FR`) do not require a program prefix.

### Byte / Word Suffixes

Append `L`, `H`, or `W` to bit-area addresses for byte or packed-word access:

```python
plc.read("P1-M0010W")   # M0010 as packed word (16 bits)
plc.read("P1-M0010L")   # low byte of packed word
plc.read("P1-M0010H")   # high byte of packed word
```

---

## Typed Read / Write

Utility functions handle type conversion automatically:

| dtype | Type | Size |
|-------|------|------|
| `"U"` | unsigned 16-bit int | 1 word |
| `"S"` | signed 16-bit int | 1 word |
| `"D"` | unsigned 32-bit int | 2 words |
| `"L"` | signed 32-bit int | 2 words |
| `"F"` | float32 | 2 words |

```python
import asyncio
from toyopuc import open_and_connect
from toyopuc import read_typed, write_typed

async def main():
    async with await open_and_connect("192.168.1.5") as plc:
        f = await read_typed(plc, "P1-D0100", "F")        # float32
        v = await read_typed(plc, "P1-D0200", "L")        # signed 32-bit
        await write_typed(plc, "P1-D0100", "F", 3.14)
        await write_typed(plc, "P1-D0200", "S", -100)

asyncio.run(main())
```

### Contiguous Array Read

```python
from toyopuc import read_words, read_dwords

# Read 10 words from P1-D0000 → list[int]
words = await read_words(plc, "P1-D0000", 10)

# Read 4 DWords (32-bit pairs) from P1-D0000 → list[int]
dwords = await read_dwords(plc, "P1-D0000", 4)
```

### Bit-in-Word Write

```python
from toyopuc import write_bit_in_word

# Set bit 3 of P1-D0100 (read-modify-write)
await write_bit_in_word(plc, "P1-D0100", bit_index=3, value=True)
```

---

## Named-Device Read

Read multiple devices in one call using address strings with optional type suffixes.

Address notation:

| Format | Meaning |
|--------|---------|
| `"P1-D0100"` | D0100 as unsigned 16-bit |
| `"P1-D0100:F"` | D0100 as float32 |
| `"P1-D0100:S"` | D0100 as signed 16-bit |
| `"P1-D0100:D"` | D0100–D0101 as unsigned 32-bit |
| `"P1-D0100:L"` | D0100–D0101 as signed 32-bit |
| `"P1-D0100.3"` | Bit 3 of D0100 (bool) |

```python
from toyopuc import read_named

result = await read_named(plc, ["P1-D0100", "P1-D0101:F", "P1-D0102:S", "P1-D0100.3"])
# result == {"P1-D0100": 42, "P1-D0101:F": 3.14, "P1-D0102:S": -1, "P1-D0100.3": True}
```

---

## Polling

`poll` yields device snapshots at a fixed interval until the loop is broken.

```python
import asyncio
from toyopuc import open_and_connect, poll

async def main():
    async with await open_and_connect("192.168.1.5") as plc:
        async for snapshot in poll(plc, ["P1-D0100", "P1-D0101:F"], interval=1.0):
            print(snapshot)
            # {"P1-D0100": 42, "P1-D0101:F": 3.14}

asyncio.run(main())
```

Press `Ctrl+C` to stop.

---

## Error Handling

| Exception | Condition |
|-----------|-----------|
| `ToyopucError` | PLC returned an error response |
| `ToyopucProtocolError` | Malformed or unexpected protocol data |
| `ToyopucTimeoutError` | Communication timeout |

```python
from toyopuc import ToyopucError, ToyopucProtocolError, ToyopucTimeoutError

try:
    val = await plc.read("P1-D0000")
except ToyopucTimeoutError:
    print("Timeout — check IP address and Computer Link port.")
except ToyopucProtocolError as e:
    print(f"Protocol error: {e}")
except ToyopucError as e:
    print(f"PLC error: {e}")
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ToyopucTimeoutError` | Wrong IP or port | Default port is 1025; confirm in TOYOPUC network settings |
| `ToyopucProtocolError` | Invalid address format | Ensure program prefix and device area are correct |
| Wrong values | Word/byte mismatch | Check `W`/`L`/`H` suffix usage for bit-area devices |

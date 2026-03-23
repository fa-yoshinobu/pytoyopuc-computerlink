# ruff: noqa: E402
"""
TOYOPUC Computer Link - High-Level Asynchronous API Sample
==========================================================
Demonstrates all high-level *async* utility helpers shipped with the
toyopuc package: open_and_connect, read_typed, write_typed, read_named,
read_words, read_dwords, write_bit_in_word, and poll.

Usage
-----
    python samples/high_level_all_async.py --host 192.168.250.100 [--port 1025]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toyopuc import (
    open_and_connect,
    poll,
    read_dwords,
    read_named,
    read_typed,
    read_words,
    write_bit_in_word,
    write_typed,
)
from toyopuc.errors import ToyopucError, ToyopucProtocolError, ToyopucTimeoutError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="TOYOPUC Computer Link asynchronous high-level API sample",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("--host", required=True, help="PLC IP address or hostname")
    p.add_argument(
        "--port",
        type=int,
        default=1025,
        help="Computer Link TCP port (default 1025)",
    )
    p.add_argument(
        "--poll-count",
        type=int,
        default=3,
        help="Number of poll snapshots to capture (default 3)",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Demos
# ---------------------------------------------------------------------------


async def demo_open_and_connect(host: str, port: int) -> None:
    """
    open_and_connect - create an AsyncToyopucDeviceClient and connect.

    Parameters:
        host  - TOYOPUC PLC IP / hostname
        port  - Computer Link port (default 1025 inside open_and_connect)

    Returns a connected AsyncToyopucDeviceClient used as async context manager.

    Use case: the simplest way to start an async session without manually
              constructing AsyncToyopucDeviceClient and calling connect().
    """
    async with await open_and_connect(host, port=port) as plc:
        print(f"[open_and_connect] Connected to {host}:{port}")
        val = await plc.read("P1-D0100")
        print(f"[open_and_connect] P1-D0100 = {val}")


async def demo_typed_rw(plc) -> None:
    """
    read_typed / write_typed - single device with automatic type conversion.

    dtype codes:
        "U"  unsigned 16-bit int  (1 word)
        "S"  signed 16-bit int    (1 word)
        "D"  unsigned 32-bit int  (2 words, low-word first)
        "L"  signed 32-bit int    (2 words)
        "F"  IEEE-754 float32     (2 words)

    Use case: writing a float32 temperature setpoint to P1-D0300-D0301
              from an asyncio-based recipe manager.
    """
    val_u = await read_typed(plc, "P1-D0100", "U")
    val_f = await read_typed(plc, "P1-D0300", "F")
    val_l = await read_typed(plc, "P1-D0200", "L")
    print(f"[read_typed] P1-D0100(U)={val_u}  P1-D0300(F)={val_f}  P1-D0200(L)={val_l}")

    await write_typed(plc, "P1-D0100", "U", 42)
    await write_typed(plc, "P1-D0300", "F", 3.14)
    await write_typed(plc, "P1-D0200", "L", -500)
    print("[write_typed] Wrote 42->P1-D0100, 3.14->P1-D0300, -500->P1-D0200")


async def demo_array_reads(plc) -> None:
    """
    read_words / read_dwords - read contiguous word / dword blocks.

    read_words(plc, device, count)  - returns list[int] (16-bit)
    read_dwords(plc, device, count) - returns list[int] (32-bit, uint)

    Use case: reading a block of 10 consecutive data registers in one
              Computer Link request for a periodic data logger.
    """
    words = await read_words(plc, "P1-D0000", 10)
    print(f"[read_words]  P1-D0000-D0009 = {words}")

    dwords = await read_dwords(plc, "P1-D0000", 4)
    print(f"[read_dwords] P1-D0000-D0007 (as 4 x uint32) = {dwords}")


async def demo_bit_in_word(plc) -> None:
    """
    write_bit_in_word - set/clear one bit inside a word device.

    Performs a read-modify-write: reads the word, flips bit_index, writes back.
    bit_index 0 = LSB, 15 = MSB.

    Use case: toggling a single command flag in a shared control word without
              disturbing the other flag bits (e.g., start/stop bit 0).
    """
    await write_bit_in_word(plc, "P1-D0100", bit_index=0, value=True)
    print("[write_bit_in_word] Set   bit 0 of P1-D0100")
    await write_bit_in_word(plc, "P1-D0100", bit_index=0, value=False)
    print("[write_bit_in_word] Clear bit 0 of P1-D0100")


async def demo_read_named(plc) -> None:
    """
    read_named - read multiple devices with mixed types in one call.

    Address notation (same as ToyopucDeviceClient):
        "P1-D0100"    unsigned 16-bit (default)
        "P1-D0100:F"  float32 (2 words)
        "P1-D0100:S"  signed 16-bit
        "P1-D0100:D"  unsigned 32-bit (2 words)
        "P1-D0100:L"  signed 32-bit
        "P1-D0100.3"  bit 3 inside P1-D0100 (bool)

    Use case: reading a heterogeneous process snapshot (float32 speed,
              signed error code, alarm bit) in a single asyncio step.
    """
    snapshot = await read_named(plc, [
        "P1-D0100",
        "P1-D0300:F",
        "P1-D0200:L",
        "P1-D0100.3",
    ])
    for addr, value in snapshot.items():
        print(f"[read_named] {addr} = {value!r}")


async def demo_poll(plc, count: int) -> None:
    """
    poll - async generator that yields a snapshot dict every *interval* seconds.

    Use case: asyncio-based background monitoring that feeds a historian
              or dashboard while other coroutines handle UI or alarms.
    """
    print(f"\nPolling {count} snapshots:")
    i = 0
    async for snap in poll(plc, ["P1-D0100", "P1-D0300:F", "P1-D0100.3"], interval=1.0):
        print(f"  [{i + 1}] {snap}")
        i += 1
        if i >= count:
            break


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def run(args: argparse.Namespace) -> None:
    # 1. open_and_connect shortcut
    await demo_open_and_connect(args.host, args.port)

    # 2-6. connect once, run all remaining demos
    async with await open_and_connect(args.host, port=args.port) as plc:
        await demo_typed_rw(plc)
        await demo_array_reads(plc)
        await demo_bit_in_word(plc)
        await demo_read_named(plc)
        await demo_poll(plc, args.poll_count)

    print("Done.")


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(run(args))
    except ToyopucTimeoutError as e:
        print(f"Timeout: {e}", file=sys.stderr)
        sys.exit(1)
    except ToyopucProtocolError as e:
        print(f"Protocol error: {e}", file=sys.stderr)
        sys.exit(1)
    except ToyopucError as e:
        print(f"PLC error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

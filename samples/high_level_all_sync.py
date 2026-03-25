# ruff: noqa: E402
"""
TOYOPUC Computer Link - High-Level Synchronous API Sample
=========================================================
Demonstrates all high-level methods of ToyopucDeviceClient (synchronous):
read, write, read_many, write_many, read_dword/dwords, read_float32/float32s,
write_dword/float32, and FR file register access.

Usage
-----
    python samples/high_level_all_sync.py --host 192.168.250.100 [--port 1025]
    python samples/high_level_all_sync.py --host 192.168.250.100 --port 1027 --transport udp

Default port: 1025 TCP / 1027 UDP  (TOYOPUC Computer Link default)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toyopuc import ToyopucDeviceClient
from toyopuc.errors import ToyopucError, ToyopucProtocolError, ToyopucTimeoutError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="TOYOPUC Computer Link synchronous high-level API sample",
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
        "--transport",
        choices=("tcp", "udp"),
        default="tcp",
        help="Transport protocol (default tcp)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=3.0,
        help="Socket timeout in seconds (default 3.0)",
    )
    p.add_argument(
        "--retries",
        type=int,
        default=0,
        help="Number of automatic retries on timeout (default 0)",
    )
    p.add_argument(
        "--retry-delay",
        type=float,
        default=0.2,
        help="Seconds to wait between retries (default 0.2)",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    args = parse_args()

    # ToyopucDeviceClient / ToyopucClient constructor options:
    #   host        - TOYOPUC PLC IP / hostname
    #   port        - Computer Link port (set in TOYOPUC network parameters;
    #                 default is 1025)
    #   transport   - "tcp" (default) or "udp"
    #   timeout     - socket timeout in seconds
    #   retries     - how many times to retry on ToyopucTimeoutError before
    #                 giving up; useful for networks with occasional drops
    #   retry_delay - wait time between retries in seconds
    #   local_port  - bind to a specific local UDP port (UDP only, rarely needed)
    #   trace_hook  - optional callback(ToyopucTraceFrame) for raw frame tracing
    with ToyopucDeviceClient(
        args.host,
        args.port,
        transport=args.transport,
        timeout=args.timeout,
        retries=args.retries,
        retry_delay=args.retry_delay,
    ) as plc:
        print(f"Connected to {args.host}:{args.port} via {args.transport}")

        # ---------------------------------------------------------------
        # 1. read / write - single device
        #
        # Address format: [Program]-[AreaType][Address]
        #   Program prefix P1/P2/P3 is required for basic device areas
        #   (D, S, N, M, X, Y, T, C, ...)
        #   Extended areas (ES, EN, H, U, EB, FR) do not need a prefix.
        #
        # Examples:
        #   "P1-D0100"  data register D0100 in program 1 (word)
        #   "P1-M0010"  internal relay M0010 (bit)
        #   "P1-M0010W" M0010 as packed word (16 bits)
        #   "ES0000"    extended special register (no prefix)
        #
        # Use case: reading and writing a single word or bit device.
        # ---------------------------------------------------------------
        val = plc.read("P1-D0100")
        print(f"[read]  P1-D0100 = {val}")

        plc.write("P1-D0100", 1234)
        print("[write] Wrote 1234 -> P1-D0100")

        bit = plc.read("P1-M0010")
        print(f"[read]  P1-M0010 (bit) = {bit}")

        plc.write("P1-M0010", 1)
        print("[write] Set P1-M0010 = 1")

        # ---------------------------------------------------------------
        # 2. read / write with byte/word suffixes on bit areas
        #
        # Append W, L, or H to a bit-area address for packed access:
        #   "P1-M0010W"  M0010 as a packed 16-bit word
        #   "P1-M0010L"  low byte of the packed word
        #   "P1-M0010H"  high byte of the packed word
        #
        # Use case: reading 16 relay bits as a single integer for display
        #           on an HMI or for masking operations.
        # ---------------------------------------------------------------
        packed_word = plc.read("P1-M0010W")
        print(f"[read W]  P1-M0010W (packed word) = {packed_word:#06x}")

        # ---------------------------------------------------------------
        # 3. read_many / write_many - batch access
        #
        # read_many(devices) - read an arbitrary list of devices in order.
        #     Returns list[object] in the same order as input.
        #
        # write_many(items)  - write a mapping of {device: value} in order.
        #
        # Use case: reading a multi-device snapshot (word registers, bits,
        #           special registers) without multiple round-trips.
        # ---------------------------------------------------------------
        values = plc.read_many(["P1-D0100", "P1-D0101", "P1-M0000"])
        print(f"[read_many]  P1-D0100={values[0]}  P1-D0101={values[1]}  P1-M0000={values[2]}")

        plc.write_many(
            {
                "P1-D0100": 10,
                "P1-D0101": 20,
                "P1-M0000": 0,
            }
        )
        print("[write_many] Wrote {P1-D0100: 10, P1-D0101: 20, P1-M0000: 0}")

        # ---------------------------------------------------------------
        # 4. read_dword / write_dword - 32-bit unsigned integer access
        #
        # Reads or writes two consecutive word registers as a single uint32.
        # TOYOPUC stores 32-bit values low-word first (little-endian word order).
        #
        # Use case: reading a 32-bit production counter from D0200-D0201.
        # ---------------------------------------------------------------
        dword = plc.read_dword("P1-D0200")
        print(f"[read_dword]  P1-D0200 = {dword}")

        plc.write_dword("P1-D0200", 0x12345678)
        print("[write_dword] Wrote 0x12345678 -> P1-D0200-D0201")

        # ---------------------------------------------------------------
        # 5. read_dwords - read multiple 32-bit values
        #
        # count - number of dwords (each dword = 2 consecutive words).
        #
        # Use case: reading an array of 32-bit position values from D0200+.
        # ---------------------------------------------------------------
        dwords = plc.read_dwords("P1-D0200", 4)
        print(f"[read_dwords] P1-D0200 x 4 = {dwords}")

        # ---------------------------------------------------------------
        # 6. read_float32 / write_float32 - single IEEE-754 float
        #
        # Reads or writes two consecutive word registers as a float32.
        #
        # Use case: reading a conveyor speed setpoint from D0300-D0301.
        # ---------------------------------------------------------------
        f32 = plc.read_float32("P1-D0300")
        print(f"[read_float32]  P1-D0300 = {f32}")

        plc.write_float32("P1-D0300", 3.14)
        print("[write_float32] Wrote 3.14 -> P1-D0300-D0301")

        # ---------------------------------------------------------------
        # 7. read_float32s - read multiple float32 values
        #
        # count - number of float values (each = 2 words).
        #
        # Use case: reading a recipe array of four float parameters.
        # ---------------------------------------------------------------
        floats = plc.read_float32s("P1-D0300", 4)
        print(f"[read_float32s] P1-D0300 x 4 = {[round(f, 4) for f in floats]}")

        # ---------------------------------------------------------------
        # 8. read_fr / write_fr - FR file register access
        #
        # FR is a large non-volatile file register area (up to 2 M words).
        # It requires a dedicated read/write path and optional commit step.
        #
        # write_fr options:
        #   commit       - write AND commit the changed block to flash;
        #                  False by default (write to RAM only)
        #   wait         - wait for commit to complete before returning;
        #                  defaults to True when commit=True
        #   timeout      - maximum time to wait for commit (seconds)
        #   poll_interval - how often to poll commit status (seconds)
        #
        # Use case: writing recipe data to non-volatile FR storage so it
        #           survives a PLC power cycle.
        # ---------------------------------------------------------------
        fr_val = plc.read_fr("FR000000")
        print(f"[read_fr]  FR000000 = {fr_val}")

        # Write to FR RAM without committing to flash (fast, temporary).
        plc.write_fr("FR000000", 999, commit=False)
        print("[write_fr] Wrote 999 -> FR000000 (RAM only, not committed)")

        # commit_fr explicitly flushes the modified block to flash.
        plc.commit_fr("FR000000", wait=False)
        print("[commit_fr] Committed FR000000 block (async, not waiting)")

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except ToyopucTimeoutError as e:
        print(f"Timeout: {e}", file=sys.stderr)
        sys.exit(1)
    except ToyopucProtocolError as e:
        print(f"Protocol error: {e}", file=sys.stderr)
        sys.exit(1)
    except ToyopucError as e:
        print(f"PLC error: {e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"Connection error: {e}", file=sys.stderr)
        sys.exit(1)

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toyopuc import ToyopucDeviceClient


def parse_int_auto(text: str) -> int:
    return int(text, 0)


def _emit(line: str, log_f: TextIO | None) -> None:
    print(line)
    if log_f is not None:
        log_f.write(line + "\n")
        log_f.flush()


def _pattern(
    count: int, base: int, step: int, loop_index: int, loop_step: int
) -> list[int]:
    values: list[int] = []
    start = (base + loop_index * loop_step) & 0xFFFF
    for i in range(count):
        values.append((start + i * step) & 0xFFFF)
    return values


def main() -> int:
    p = argparse.ArgumentParser(
        description="Relay contiguous word write/read verification"
    )
    p.add_argument("--host", required=True)
    p.add_argument("--port", required=True, type=int)
    p.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    p.add_argument("--local-port", type=int, default=0)
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument("--retries", type=int, default=0)
    p.add_argument(
        "--hops", required=True, help='relay hops, for example "P1-L2:N2,P1-L2:N4"'
    )
    p.add_argument("--device", default="P1-D0000", help="starting word device")
    p.add_argument(
        "--count", type=int, default=8, help="number of contiguous words per transfer"
    )
    p.add_argument("--loops", type=int, default=3, help="number of write/read cycles")
    p.add_argument(
        "--value",
        type=parse_int_auto,
        default=0x1000,
        help="starting word value for loop 1",
    )
    p.add_argument(
        "--step",
        type=parse_int_auto,
        default=1,
        help="per-word increment inside a block",
    )
    p.add_argument(
        "--loop-step", type=parse_int_auto, default=0x0100, help="per-loop increment"
    )
    p.add_argument("--log", help="optional text log path")
    args = p.parse_args()

    if args.count < 1:
        raise SystemExit("--count must be >= 1")
    if args.loops < 1:
        raise SystemExit("--loops must be >= 1")

    log_f = open(args.log, "w", encoding="utf-8") if args.log else None
    try:
        _emit(f"hops = {args.hops}", log_f)
        _emit(f"device = {args.device}", log_f)
        _emit(f"count = {args.count}", log_f)
        _emit(f"loops = {args.loops}", log_f)
        _emit(f"value = 0x{args.value & 0xFFFF:04X}", log_f)
        _emit(f"step = 0x{args.step & 0xFFFF:04X}", log_f)
        _emit(f"loop_step = 0x{args.loop_step & 0xFFFF:04X}", log_f)

        with ToyopucDeviceClient(
            args.host,
            args.port,
            protocol=args.protocol,
            local_port=args.local_port,
            timeout=args.timeout,
            retries=args.retries,
        ) as plc:
            ok_loops = 0
            for loop_index in range(args.loops):
                expected = _pattern(
                    args.count, args.value, args.step, loop_index, args.loop_step
                )
                plc.relay_write_words(args.hops, args.device, expected)
                actual = plc.relay_read_words(args.hops, args.device, count=args.count)
                if not isinstance(actual, list):
                    actual = [actual]
                matched = actual == expected
                if matched:
                    ok_loops += 1
                _emit(
                    f"loop {loop_index + 1}: "
                    f"write=[{', '.join(f'0x{x:04X}' for x in expected)}] "
                    f"read=[{', '.join(f'0x{x:04X}' for x in actual)}] "
                    f"ok={matched}",
                    log_f,
                )

        _emit(f"summary = {ok_loops}/{args.loops} loops passed", log_f)
        return 0 if ok_loops == args.loops else 1
    finally:
        if log_f is not None:
            log_f.close()


if __name__ == "__main__":
    raise SystemExit(main())

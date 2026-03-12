from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toyopuc import ToyopucHighLevelClient


def parse_int_auto(text: str) -> int:
    return int(text, 0)


def parse_datetime_iso(text: str) -> datetime:
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO datetime: {text!r}") from exc


def main() -> int:
    p = argparse.ArgumentParser(description="Simple relay example")
    p.add_argument("--host", required=True)
    p.add_argument("--port", required=True, type=int)
    p.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    p.add_argument("--local-port", type=int, default=0)
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument("--retries", type=int, default=0)
    p.add_argument("--hops", required=True, help='relay hops, for example "P1-L2:N2,P1-L2:N4"')
    p.add_argument(
        "--mode",
        choices=[
            "cpu-status",
            "cpu-status-a0",
            "clock-read",
            "clock-write",
            "word-read",
            "word-write",
            "fr-read",
            "fr-write",
            "fr-commit",
        ],
        default="cpu-status",
    )
    p.add_argument("--device", default="P1-D0000")
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--value", type=parse_int_auto, default=0x1234)
    p.add_argument("--clock-value", type=parse_datetime_iso, default=None, help="ISO datetime for --mode clock-write")
    p.add_argument("--commit", action="store_true", help="commit FR write after RAM update")
    p.add_argument("--wait", action="store_true", help="wait for FR commit completion")
    args = p.parse_args()

    with ToyopucHighLevelClient(
        args.host,
        args.port,
        protocol=args.protocol,
        local_port=args.local_port,
        timeout=args.timeout,
        retries=args.retries,
    ) as plc:
        print("hops =", args.hops)
        print("mode =", args.mode)

        if args.mode == "cpu-status":
            status = plc.relay_read_cpu_status(args.hops)
            print("cpu status raw =", status.raw_bytes_hex)
            print("RUN =", status.run)
            print("Alarm =", status.alarm)
            print("PC10 mode =", status.pc10_mode)
            return 0

        if args.mode == "cpu-status-a0":
            status = plc.relay_read_cpu_status_a0(args.hops)
            print("cpu status a0 raw =", status.raw_bytes_hex)
            print("RUN =", status.run)
            print("Alarm =", status.alarm)
            print("PC10 mode =", status.pc10_mode)
            return 0

        if args.mode == "clock-read":
            clock = plc.relay_read_clock(args.hops)
            print("clock raw =", clock)
            try:
                print("clock datetime =", clock.as_datetime())
            except ValueError as exc:
                print("clock datetime unavailable:", exc)
            return 0

        if args.mode == "clock-write":
            if args.clock_value is None:
                raise SystemExit("--mode clock-write requires --clock-value 2026-03-10T12:34:56")
            plc.relay_write_clock(args.hops, args.clock_value)
            readback = plc.relay_read_clock(args.hops)
            print("clock write value =", args.clock_value.isoformat(sep=" "))
            print("clock readback =", readback)
            try:
                print("clock readback datetime =", readback.as_datetime())
            except ValueError as exc:
                print("clock readback datetime unavailable:", exc)
            return 0

        if args.mode == "word-write":
            if args.count != 1:
                raise SystemExit("--mode word-write currently requires --count 1")
            plc.relay_write_words(args.hops, args.device, args.value)
            readback = plc.relay_read_words(args.hops, args.device, count=1)
            readback_word = readback[0] if isinstance(readback, list) else int(readback)
            print("word write device =", args.device)
            print("word write value =", f"0x{args.value & 0xFFFF:04X}")
            print("word readback =", f"0x{readback_word:04X}")
            return 0

        if args.mode == "fr-read":
            value = plc.relay_read_fr(args.hops, args.device, count=args.count)
            if isinstance(value, list):
                print("fr values =", ", ".join(f"0x{item:04X}" for item in value))
            else:
                print("fr value =", f"0x{value:04X}")
            return 0

        if args.mode == "fr-write":
            if args.count != 1:
                raise SystemExit("--mode fr-write currently requires --count 1")
            plc.relay_write_fr(args.hops, args.device, args.value, commit=args.commit, wait=args.wait or args.commit)
            readback = plc.relay_read_fr(args.hops, args.device, count=1)
            print("fr write device =", args.device)
            print("fr write value =", f"0x{args.value & 0xFFFF:04X}")
            print("fr commit =", args.commit)
            print("fr readback =", f"0x{readback:04X}")
            return 0

        if args.mode == "fr-commit":
            plc.relay_commit_fr(args.hops, args.device, count=args.count, wait=args.wait)
            print("fr commit device =", args.device)
            print("fr commit count =", args.count)
            print("fr commit wait =", args.wait)
            return 0

        values = plc.relay_read_words(args.hops, args.device, count=args.count)
        if isinstance(values, list):
            if args.count == 1:
                print("word value =", f"0x{values[0]:04X}")
            else:
                print("word values =", ", ".join(f"0x{item:04X}" for item in values))
        else:
            print("word value =", f"0x{int(values):04X}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

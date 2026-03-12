from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toyopuc import ToyopucHighLevelClient


def parse_int_auto(text: str) -> int:
    return int(text, 0)


def main() -> int:
    # FR example: read one FR word, write a new value, and optionally persist it.
    p = argparse.ArgumentParser(description="FR read/write example")
    p.add_argument("--host", required=True)
    p.add_argument("--port", required=True, type=int)
    p.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    p.add_argument("--local-port", type=int, default=0)
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument("--retries", type=int, default=0)
    p.add_argument("--target", default="FR000000", help="FR word device such as FR000000")
    p.add_argument("--value", type=parse_int_auto, default=0x1234, help="word value to write")
    p.add_argument("--commit", action="store_true", help="persist the written FR block to flash")
    args = p.parse_args()

    with ToyopucHighLevelClient(
        args.host,
        args.port,
        protocol=args.protocol,
        local_port=args.local_port,
        timeout=args.timeout,
        retries=args.retries,
    ) as plc:
        before = plc.read_fr(args.target)
        print("target =", args.target)
        print("before =", hex(before))
        print("write  =", hex(args.value & 0xFFFF))
        print("commit =", args.commit)
        plc.write_fr(args.target, args.value, commit=args.commit)
        after = plc.read_fr(args.target)
        print("after  =", hex(after))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

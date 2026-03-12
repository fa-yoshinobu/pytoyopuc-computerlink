from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toyopuc import ToyopucHighLevelClient


def main() -> int:
    # High-level UDP example with fixed local source port.
    p = argparse.ArgumentParser(description="High-level UDP example with fixed local port")
    p.add_argument("--host", required=True)
    p.add_argument("--port", required=True, type=int)
    p.add_argument("--local-port", type=int, required=True)
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument("--retries", type=int, default=2)
    args = p.parse_args()

    with ToyopucHighLevelClient(
        args.host,
        args.port,
        protocol="udp",
        local_port=args.local_port,
        timeout=args.timeout,
        retries=args.retries,
    ) as plc:
        plc.write("P1-D0000", 0x1234)
        print("P1-D0000 =", hex(plc.read("P1-D0000")))

        plc.write("P1-M0000", 1)
        print("P1-M0000 =", plc.read("P1-M0000"))

        print("CPU status =", plc.read_cpu_status())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

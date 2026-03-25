from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toyopuc import ToyopucDeviceClient


def main() -> int:
    # Basic high-level example including W/H/L addressing for bit-device families.
    p = argparse.ArgumentParser(description="Basic high-level Toyopuc client example")
    p.add_argument("--host", required=True)
    p.add_argument("--port", required=True, type=int)
    p.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    p.add_argument("--local-port", type=int, default=0)
    p.add_argument("--timeout", type=float, default=3.0)
    p.add_argument("--retries", type=int, default=0)
    args = p.parse_args()

    with ToyopucDeviceClient(
        args.host,
        args.port,
        protocol=args.protocol,
        local_port=args.local_port,
        timeout=args.timeout,
        retries=args.retries,
    ) as plc:
        plc.write("P1-D0000", 0x1234)
        print("P1-D0000 =", hex(plc.read("P1-D0000")))

        plc.write("P1-D0000L", 0x56)
        print("P1-D0000L =", hex(plc.read("P1-D0000L")))

        plc.write("P1-M0000", 1)
        print("P1-M0000 =", plc.read("P1-M0000"))

        plc.write("P1-D0000", 0x2222)
        print("P1-D0000 =", hex(plc.read("P1-D0000")))

        plc.write("ES0000", 0x3333)
        print("ES0000 =", hex(plc.read("ES0000")))

        values = plc.read_many(["P1-D0000", "P1-M0000", "P1-D0000L", "ES0000"])
        print("read_many =", values)

        plc.write("P1-M0010W", 0x1234)
        print("P1-M0010W =", hex(plc.read("P1-M0010W")))
        print("P1-M0010L =", hex(plc.read("P1-M0010L")))
        print("P1-M0010H =", hex(plc.read("P1-M0010H")))

        plc.write("EX0010L", 0xAB)
        print("EX0010L =", hex(plc.read("EX0010L")))
        print(
            "EX0100..EX0107 =",
            [plc.read(f"EX{index:04X}") for index in range(0x0100, 0x0108)],
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

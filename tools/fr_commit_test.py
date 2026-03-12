import argparse

from toyopuc import ToyopucHighLevelClient


def parse_int_auto(value: str) -> int:
    return int(value, 0)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Read or write/commit an FR word and print A0 status.")
    p.add_argument("--host", required=True)
    p.add_argument("--port", required=True, type=int)
    p.add_argument("--protocol", choices=("tcp", "udp"), default="tcp")
    p.add_argument("--local-port", type=int, default=0)
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument("--retries", type=int, default=0)
    p.add_argument("--mode", choices=("read", "write"), default="read")
    p.add_argument("--target", default="FR000000", help="FR word device such as FR000000")
    p.add_argument("--value", type=parse_int_auto, default=0x1234, help="word value for write mode")
    p.add_argument("--commit-timeout", type=float, default=30.0)
    p.add_argument("--poll-interval", type=float, default=0.2)
    p.add_argument("--try-a0", action="store_true", help="try reading A0 status after read/write")
    return p


def print_a0(prefix: str, status) -> None:
    print(f"{prefix} A0 raw = {status.raw_bytes_hex}")
    print(f"{prefix} under_writing_flash_register = {status.under_writing_flash_register}")
    print(f"{prefix} abnormal_write_flash_register = {status.abnormal_write_flash_register}")


def main() -> int:
    args = build_parser().parse_args()

    with ToyopucHighLevelClient(
        args.host,
        args.port,
        protocol=args.protocol,
        local_port=args.local_port,
        timeout=args.timeout,
        retries=args.retries,
    ) as plc:
        try:
            if args.mode == "read":
                value = plc.read_fr(args.target)
                print(f"target = {args.target}")
                print(f"value = {hex(value)}")
                if args.try_a0:
                    try:
                        a0 = plc.read_cpu_status_a0()
                        print_a0("read", a0)
                    except Exception as e:
                        print(f"read A0: unavailable ({e})")
                return 0

            before = plc.read_fr(args.target)
            print(f"target = {args.target}")
            print(f"before = {hex(before)}")
            print(f"write  = {hex(args.value & 0xFFFF)}")
            plc.write_fr(
                args.target,
                args.value,
                commit=True,
                wait=True,
            )
            after = plc.read_fr(args.target)
            print(f"after  = {hex(after)}")
            if args.try_a0:
                try:
                    a0 = plc.read_cpu_status_a0()
                    print_a0("write", a0)
                except Exception as e:
                    print(f"write A0: unavailable ({e})")
            return 0
        except Exception as e:
            print(f"ERR: {e}")
            if plc.last_tx is not None:
                print(f"LAST_TX {plc.last_tx.hex(' ').upper()}")
            if plc.last_rx is not None:
                print(f"LAST_RX {plc.last_rx.hex(' ').upper()}")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())

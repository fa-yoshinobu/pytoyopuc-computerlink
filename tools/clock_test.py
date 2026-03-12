import argparse
from datetime import datetime

from toyopuc import ToyopucClient


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Read or set PLC clock time.")
    p.add_argument("--host", required=True)
    p.add_argument("--port", required=True, type=int)
    p.add_argument("--protocol", choices=("tcp", "udp"), default="tcp")
    p.add_argument("--local-port", type=int, default=0)
    p.add_argument("--timeout", type=float, default=3.0)
    p.add_argument("--retries", type=int, default=0)
    p.add_argument("--set", dest="set_value", help="Set clock to 'YYYY-MM-DD HH:MM:SS'")
    p.add_argument("--set-now", action="store_true", help="Set clock to current local time")
    return p


def parse_set_value(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def main() -> int:
    args = build_parser().parse_args()
    if args.set_value and args.set_now:
        raise SystemExit("Use either --set or --set-now, not both.")

    dt_to_set = None
    if args.set_value:
        dt_to_set = parse_set_value(args.set_value)
    elif args.set_now:
        dt_to_set = datetime.now()

    with ToyopucClient(
        args.host,
        args.port,
        protocol=args.protocol,
        local_port=args.local_port,
        timeout=args.timeout,
        retries=args.retries,
    ) as plc:
        try:
            if dt_to_set is None:
                current = plc.read_clock()
                print(
                    f"raw: second={current.second:02d} minute={current.minute:02d} "
                    f"hour={current.hour:02d} day={current.day:02d} month={current.month:02d} "
                    f"year={current.year_2digit:02d} weekday={current.weekday}"
                )
                try:
                    print(f"datetime: {current.as_datetime().isoformat(sep=' ')}")
                except Exception as e:
                    print(f"datetime: unavailable ({e})")
                return 0

            print(f"setting: {dt_to_set.isoformat(sep=' ')}")
            plc.write_clock(dt_to_set)
            current = plc.read_clock()
            print(
                f"readback raw: second={current.second:02d} minute={current.minute:02d} "
                f"hour={current.hour:02d} day={current.day:02d} month={current.month:02d} "
                f"year={current.year_2digit:02d} weekday={current.weekday}"
            )
            try:
                print(f"readback datetime: {current.as_datetime().isoformat(sep=' ')}")
            except Exception as e:
                print(f"readback datetime: unavailable ({e})")
        except Exception as e:
            print(f"ERR: {e}")
            if plc.last_tx is not None:
                print(f"LAST_TX {plc.last_tx.hex(' ').upper()}")
            if plc.last_rx is not None:
                print(f"LAST_RX {plc.last_rx.hex(' ').upper()}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

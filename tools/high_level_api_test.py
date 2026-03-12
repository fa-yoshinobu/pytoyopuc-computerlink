import argparse
import random
from typing import Callable, Sequence

from toyopuc import ToyopucError, ToyopucHighLevelClient, resolve_device


def _write_log(log_f, line: str) -> None:
    if log_f:
        log_f.write(line + "\n")
        log_f.flush()


def _format_value(value) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        if value <= 0xFF:
            return f"0x{value:02X}"
        if value <= 0xFFFF:
            return f"0x{value:04X}"
        return f"0x{value:X}"
    return repr(value)


def _run_case(name: str, fn: Callable[[], tuple[int, int]], log_f) -> tuple[int, int]:
    header = f"=== {name} ==="
    print(header)
    _write_log(log_f, header)
    ok, total = fn()
    line = f"{name}: {ok}/{total}"
    print(line)
    _write_log(log_f, line)
    return ok, total


def _report_case_error(name: str, exc: Exception, log_f) -> tuple[int, int]:
    line = f"{name}: ERROR {type(exc).__name__}: {exc}"
    print(line)
    _write_log(log_f, line)
    return 0, 0


def _read(plc: ToyopucHighLevelClient, hops: str, addr: str, count: int = 1):
    if hops:
        return plc.relay_read(hops, addr, count=count)
    return plc.read(addr, count=count)


def _write(plc: ToyopucHighLevelClient, hops: str, addr: str, value) -> None:
    if hops:
        plc.relay_write(hops, addr, value)
        return
    plc.write(addr, value)


def _read_many(plc: ToyopucHighLevelClient, hops: str, devices: Sequence[str]):
    if hops:
        return plc.relay_read_many(hops, devices)
    return plc.read_many(devices)


def _write_many(plc: ToyopucHighLevelClient, hops: str, items: dict[str, int]) -> None:
    if hops:
        plc.relay_write_many(hops, items)
        return
    plc.write_many(items)


def _single_bit_case(plc: ToyopucHighLevelClient, hops: str, addr: str, log_f) -> tuple[int, int]:
    ok = 0
    total = 0
    scheme = resolve_device(addr).scheme
    for value in (0, 1):
        _write(plc, hops, addr, value)
        read_back = 1 if _read(plc, hops, addr) else 0
        line = f"{addr} [{scheme}] write={value} read={read_back}"
        print(line)
        _write_log(log_f, line)
        total += 1
        if read_back == value:
            ok += 1
    return ok, total


def _single_word_case(plc: ToyopucHighLevelClient, hops: str, addr: str, rng: random.Random, log_f) -> tuple[int, int]:
    ok = 0
    total = 0
    scheme = resolve_device(addr).scheme
    values = [rng.randint(0, 0xFFFF)]
    values.append(values[0] ^ 0xFFFF)
    for value in values:
        _write(plc, hops, addr, value)
        read_back = int(_read(plc, hops, addr))
        line = f"{addr} [{scheme}] write={_format_value(value)} read={_format_value(read_back)}"
        print(line)
        _write_log(log_f, line)
        total += 1
        if read_back == value:
            ok += 1
    return ok, total


def _single_byte_case(plc: ToyopucHighLevelClient, hops: str, addr: str, rng: random.Random, log_f) -> tuple[int, int]:
    ok = 0
    total = 0
    scheme = resolve_device(addr).scheme
    values = [rng.randint(0, 0xFF), rng.randint(0, 0xFF)]
    for value in values:
        _write(plc, hops, addr, value)
        read_back = int(_read(plc, hops, addr))
        line = f"{addr} [{scheme}] write={_format_value(value)} read={_format_value(read_back)}"
        print(line)
        _write_log(log_f, line)
        total += 1
        if read_back == value:
            ok += 1
    return ok, total


def _sequence_case(plc: ToyopucHighLevelClient, hops: str, base_addr: str, values: Sequence[int], log_f) -> tuple[int, int]:
    scheme = resolve_device(base_addr).scheme
    _write(plc, hops, base_addr, list(values))
    read_back = list(_read(plc, hops, base_addr, count=len(values)))
    line = f"{base_addr} [{scheme}] write={list(map(_format_value, values))} read={list(map(_format_value, read_back))}"
    print(line)
    _write_log(log_f, line)
    return (1, 1) if read_back == list(values) else (0, 1)


def _mixed_many_case(plc: ToyopucHighLevelClient, hops: str, items: dict[str, int], log_f) -> tuple[int, int]:
    _write_many(plc, hops, items)
    read_back = _read_many(plc, hops, list(items.keys()))
    ok = 0
    total = len(items)
    for (addr, expected), value in zip(items.items(), read_back):
        if isinstance(value, bool):
            actual = 1 if value else 0
        else:
            actual = int(value)
        line = f"{addr} write_many={_format_value(expected)} read_many={_format_value(actual)}"
        print(line)
        _write_log(log_f, line)
        if actual == expected:
            ok += 1
    return ok, total


def _fr_guard_case(plc: ToyopucHighLevelClient, hops: str, log_f) -> tuple[int, int]:
    if hops:
        line = "FR write guard: SKIP (relay mode uses explicit FR read/write path instead of generic write guard)"
        print(line)
        _write_log(log_f, line)
        return 0, 0

    total = 0
    ok = 0

    total += 1
    try:
        plc.write("FR000000", 0x1234)
    except ValueError as exc:
        line = f'FR generic write guard = OK ({exc})'
        print(line)
        _write_log(log_f, line)
        ok += 1
    else:
        line = "FR generic write guard = FAIL (write() unexpectedly accepted FR)"
        print(line)
        _write_log(log_f, line)

    total += 1
    try:
        plc.write_many({"FR000000": 0x1234, "D0000": 0x5678})
    except ValueError as exc:
        line = f'FR write_many guard = OK ({exc})'
        print(line)
        _write_log(log_f, line)
        ok += 1
    else:
        line = "FR write_many guard = FAIL (write_many() unexpectedly accepted FR)"
        print(line)
        _write_log(log_f, line)

    return ok, total


def main() -> int:
    p = argparse.ArgumentParser(description="High-level API verification tool for ToyopucHighLevelClient")
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    p.add_argument("--local-port", type=int, default=0)
    p.add_argument("--timeout", type=float, default=3.0)
    p.add_argument("--retries", type=int, default=0)
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--include-pc10-word", action="store_true")
    p.add_argument("--skip-errors", action="store_true")
    p.add_argument("--hops", default="", help='optional relay hops, for example "P1-L2:N2,P1-L2:N4"')
    p.add_argument("--log", default="")
    args = p.parse_args()

    rng = random.Random(args.seed)
    log_f = open(args.log, "w", encoding="utf-8") if args.log else None

    totals_ok = 0
    totals_all = 0
    error_cases = 0

    single_cases: list[tuple[str, Callable[[ToyopucHighLevelClient], tuple[int, int]]]] = [
        ("single bit/basic", lambda plc: _single_bit_case(plc, args.hops, "M0000", log_f)),
        ("single word/basic", lambda plc: _single_word_case(plc, args.hops, "D0000", rng, log_f)),
        ("single byte/basic", lambda plc: _single_byte_case(plc, args.hops, "D0000L", rng, log_f)),
        ("single bit/prefixed", lambda plc: _single_bit_case(plc, args.hops, "P1-M0000", log_f)),
        ("single word/prefixed", lambda plc: _single_word_case(plc, args.hops, "P1-D0000", rng, log_f)),
        ("single bit/extended", lambda plc: _single_bit_case(plc, args.hops, "EX0000", log_f)),
        ("single word/extended", lambda plc: _single_word_case(plc, args.hops, "ES0000", rng, log_f)),
    ]
    if args.include_pc10_word:
        single_cases.append(("single word/pc10", lambda plc: _single_word_case(plc, args.hops, "U08000", rng, log_f)))

    sequence_cases: list[tuple[str, str, Sequence[int]]] = [
        ("sequence words/basic", "D0000", [rng.randint(0, 0xFFFF) for _ in range(3)]),
        ("sequence bytes/basic", "D0000L", [rng.randint(0, 0xFF) for _ in range(4)]),
        ("sequence bits/basic", "M0000", [1, 0, 1, 1]),
    ]

    mixed_items = {
        "D0000": 0x1234,
        "M0000": 1,
        "P1-R0000": 0x5678,
        "ES0000": 0x9ABC,
    }
    if args.include_pc10_word:
        mixed_items["U08000"] = 0xDEF0

    with ToyopucHighLevelClient(
        args.host,
        args.port,
        protocol=args.protocol,
        local_port=args.local_port,
        timeout=args.timeout,
        retries=args.retries,
    ) as plc:
        for name, fn in single_cases:
            try:
                ok, total = _run_case(name, lambda fn=fn: fn(plc), log_f)
            except (ToyopucError, ValueError) as exc:
                error_cases += 1
                if not args.skip_errors:
                    _report_case_error(name, exc, log_f)
                    continue
                _report_case_error(name, exc, log_f)
                continue
            totals_ok += ok
            totals_all += total

        for name, addr, values in sequence_cases:
            try:
                ok, total = _run_case(name, lambda addr=addr, values=values: _sequence_case(plc, args.hops, addr, values, log_f), log_f)
            except (ToyopucError, ValueError) as exc:
                error_cases += 1
                if not args.skip_errors:
                    _report_case_error(name, exc, log_f)
                    continue
                _report_case_error(name, exc, log_f)
                continue
            totals_ok += ok
            totals_all += total

        try:
            ok, total = _run_case("mixed read_many/write_many", lambda: _mixed_many_case(plc, args.hops, mixed_items, log_f), log_f)
        except (ToyopucError, ValueError) as exc:
            error_cases += 1
            _report_case_error("mixed read_many/write_many", exc, log_f)
        else:
            totals_ok += ok
            totals_all += total

        try:
            ok, total = _run_case("FR write guard", lambda: _fr_guard_case(plc, args.hops, log_f), log_f)
        except (ToyopucError, ValueError) as exc:
            error_cases += 1
            _report_case_error("FR write guard", exc, log_f)
        else:
            totals_ok += ok
            totals_all += total

    summary = f"TOTAL: {totals_ok}/{totals_all}"
    print(summary)
    _write_log(log_f, summary)
    error_line = f"ERROR CASES: {error_cases}"
    print(error_line)
    _write_log(log_f, error_line)
    if log_f:
        log_f.close()
    return 0 if totals_ok == totals_all and error_cases == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

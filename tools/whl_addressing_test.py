import argparse
import random
from typing import Callable

from toyopuc import ToyopucError, ToyopucHighLevelClient, resolve_device


def _write_log(log_f, line: str) -> None:
    if log_f:
        log_f.write(line + "\n")
        log_f.flush()


def _format_value(value: int, width: int) -> str:
    return f"0x{value:0{width}X}"


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


def _single_word_case(plc: ToyopucHighLevelClient, addr: str, rng: random.Random, log_f) -> tuple[int, int]:
    ok = 0
    total = 0
    scheme = resolve_device(addr).scheme
    values = [rng.randint(0, 0xFFFF)]
    values.append(values[0] ^ 0xFFFF)
    for value in values:
        plc.write(addr, value)
        read_back = int(plc.read(addr))
        line = f"{addr} [{scheme}] write={_format_value(value, 4)} read={_format_value(read_back, 4)}"
        print(line)
        _write_log(log_f, line)
        total += 1
        if read_back == value:
            ok += 1
    return ok, total


def _single_byte_case(plc: ToyopucHighLevelClient, addr: str, rng: random.Random, log_f) -> tuple[int, int]:
    ok = 0
    total = 0
    scheme = resolve_device(addr).scheme
    values = [rng.randint(0, 0xFF), rng.randint(0, 0xFF)]
    for value in values:
        plc.write(addr, value)
        read_back = int(plc.read(addr))
        line = f"{addr} [{scheme}] write={_format_value(value, 2)} read={_format_value(read_back, 2)}"
        print(line)
        _write_log(log_f, line)
        total += 1
        if read_back == value:
            ok += 1
    return ok, total


def _paired_word_byte_case(
    plc: ToyopucHighLevelClient,
    word_addr: str,
    low_addr: str,
    high_addr: str,
    rng: random.Random,
    log_f,
) -> tuple[int, int]:
    value = rng.randint(0, 0xFFFF)
    expected_low = value & 0xFF
    expected_high = (value >> 8) & 0xFF
    plc.write(word_addr, value)
    read_word = int(plc.read(word_addr))
    read_low = int(plc.read(low_addr))
    read_high = int(plc.read(high_addr))
    line = (
        f"{word_addr} -> {low_addr}/{high_addr} "
        f"write={_format_value(value, 4)} "
        f"read_word={_format_value(read_word, 4)} "
        f"read_low={_format_value(read_low, 2)} "
        f"read_high={_format_value(read_high, 2)}"
    )
    print(line)
    _write_log(log_f, line)
    ok = int(read_word == value and read_low == expected_low and read_high == expected_high)
    return ok, 1


def _expected_bits_from_byte(value: int) -> list[int]:
    return [(value >> i) & 0x01 for i in range(8)]


def _bit_area_for_packed_byte(byte_addr: str) -> tuple[str, int]:
    text = byte_addr.upper()
    prefix = ""
    body = text
    if "-" in text:
        prefix, body = text.split("-", 1)
        prefix = prefix + "-"
    area = body[:-5]
    index = int(body[-5:-1], 16)
    suffix = body[-1]
    bit_start = index * 0x10 + (8 if suffix == "H" else 0)
    return f"{prefix}{area}{bit_start:04X}", bit_start


def _byte_to_bits_case(plc: ToyopucHighLevelClient, byte_addr: str, rng: random.Random, log_f) -> tuple[int, int]:
    value = rng.randint(0, 0xFF)
    plc.write(byte_addr, value)
    bit_addr, _ = _bit_area_for_packed_byte(byte_addr)
    read_bits = [1 if b else 0 for b in plc.read(bit_addr, count=8)]
    expected_bits = _expected_bits_from_byte(value)
    line = (
        f"{byte_addr} -> {bit_addr} "
        f"write={_format_value(value, 2)} "
        f"read_bits={read_bits} "
        f"expected_bits={expected_bits}"
    )
    print(line)
    _write_log(log_f, line)
    ok = int(read_bits == expected_bits)
    return ok, 1


def main() -> int:
    p = argparse.ArgumentParser(description="Packed word/byte access verification for bit-device families")
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    p.add_argument("--local-port", type=int, default=0)
    p.add_argument("--timeout", type=float, default=3.0)
    p.add_argument("--retries", type=int, default=0)
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--skip-errors", action="store_true")
    p.add_argument("--log", default="")
    args = p.parse_args()

    rng = random.Random(args.seed)
    log_f = open(args.log, "w", encoding="utf-8") if args.log else None

    totals_ok = 0
    totals_all = 0
    error_cases = 0

    cases: list[tuple[str, Callable[[ToyopucHighLevelClient], tuple[int, int]]]] = [
        ("W/H/L word/basic", lambda plc: _single_word_case(plc, "M0010W", rng, log_f)),
        ("W/H/L byte/basic low", lambda plc: _single_byte_case(plc, "X0010L", rng, log_f)),
        ("W/H/L byte/basic high", lambda plc: _single_byte_case(plc, "X0010H", rng, log_f)),
        ("W/H/L word/prefixed", lambda plc: _single_word_case(plc, "P1-M0010W", rng, log_f)),
        ("W/H/L byte/prefixed low", lambda plc: _single_byte_case(plc, "P1-X0010L", rng, log_f)),
        ("W/H/L byte/prefixed high", lambda plc: _single_byte_case(plc, "P1-X0010H", rng, log_f)),
        ("W/H/L word/extended", lambda plc: _single_word_case(plc, "EX0010W", rng, log_f)),
        ("W/H/L byte/extended low", lambda plc: _single_byte_case(plc, "EX0010L", rng, log_f)),
        ("W/H/L byte/extended high", lambda plc: _single_byte_case(plc, "EX0010H", rng, log_f)),
        ("W/H/L word/gx", lambda plc: _single_word_case(plc, "GX0010W", rng, log_f)),
        ("W/H/L byte/gx low", lambda plc: _single_byte_case(plc, "GX0010L", rng, log_f)),
        ("W/H/L byte/gx high", lambda plc: _single_byte_case(plc, "GX0010H", rng, log_f)),
        (
            "W/H/L word-byte relation basic",
            lambda plc: _paired_word_byte_case(plc, "M0010W", "M0010L", "M0010H", rng, log_f),
        ),
        (
            "W/H/L word-byte relation prefixed",
            lambda plc: _paired_word_byte_case(plc, "P1-M0010W", "P1-M0010L", "P1-M0010H", rng, log_f),
        ),
        (
            "W/H/L word-byte relation extended",
            lambda plc: _paired_word_byte_case(plc, "EX0010W", "EX0010L", "EX0010H", rng, log_f),
        ),
        ("W/H/L byte->bits basic low", lambda plc: _byte_to_bits_case(plc, "M0010L", rng, log_f)),
        ("W/H/L byte->bits basic high", lambda plc: _byte_to_bits_case(plc, "M0010H", rng, log_f)),
        ("W/H/L byte->bits prefixed low", lambda plc: _byte_to_bits_case(plc, "P1-M0010L", rng, log_f)),
        ("W/H/L byte->bits prefixed high", lambda plc: _byte_to_bits_case(plc, "P1-M0010H", rng, log_f)),
        ("W/H/L byte->bits extended low", lambda plc: _byte_to_bits_case(plc, "EX0010L", rng, log_f)),
        ("W/H/L byte->bits extended high", lambda plc: _byte_to_bits_case(plc, "EX0010H", rng, log_f)),
        ("W/H/L byte->bits gx low", lambda plc: _byte_to_bits_case(plc, "GX0010L", rng, log_f)),
        ("W/H/L byte->bits gx high", lambda plc: _byte_to_bits_case(plc, "GX0010H", rng, log_f)),
    ]

    with ToyopucHighLevelClient(
        args.host,
        args.port,
        protocol=args.protocol,
        local_port=args.local_port,
        timeout=args.timeout,
        retries=args.retries,
    ) as plc:
        for name, fn in cases:
            try:
                def _case(fn=fn, plc=plc) -> tuple[int, int]:
                    return fn(plc)

                ok, total = _run_case(name, _case, log_f)
            except (ToyopucError, ValueError) as exc:
                error_cases += 1
                _report_case_error(name, exc, log_f)
                if not args.skip_errors:
                    continue
                continue
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

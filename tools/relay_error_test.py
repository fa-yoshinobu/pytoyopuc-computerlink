from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Iterable, TextIO

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toyopuc import ToyopucHighLevelClient  # noqa: E402
from toyopuc.client import (  # noqa: E402
    ERROR_CODE_DESCRIPTIONS,
    _extract_relay_nak_error_code,
    _extract_response_error_code,
)
from toyopuc.protocol import build_pc10_block_read, build_word_read, parse_response  # noqa: E402
from toyopuc.relay import parse_relay_hops, unwrap_relay_response_chain  # noqa: E402


def parse_int_auto(text: str) -> int:
    return int(text, 0)


def _emit(line: str, log_f: TextIO | None) -> None:
    print(line)
    if log_f is not None:
        log_f.write(line + "\n")
        log_f.flush()


def _format_error_code(code: int | None) -> str:
    if code is None:
        return "none"
    return f"0x{code:02X} ({ERROR_CODE_DESCRIPTIONS.get(code, 'unknown')})"


def _format_hops(hops: Iterable[tuple[int, int]]) -> str:
    return ",".join(f"0x{link:02X}:0x{station:04X}" for link, station in hops)


def _auto_missing_hops(hops: str) -> str:
    parsed = parse_relay_hops(hops)
    link_no, station_no = parsed[-1]
    candidate = (station_no + 0x0064) & 0xFFFF
    if candidate == station_no:
        candidate = (candidate + 1) & 0xFFFF
    parsed[-1] = (link_no, candidate)
    return _format_hops(parsed)


def _auto_broken_hops(hops: str) -> str:
    parsed = parse_relay_hops(hops)
    link_no, station_no = parsed[-1]
    candidate = (station_no + 0x0064) & 0xFFFF
    if candidate == station_no:
        candidate = (candidate + 1) & 0xFFFF
    parsed.append((link_no, candidate))
    return _format_hops(parsed)


def _describe_last_result(plc: ToyopucHighLevelClient) -> str:
    if not plc.last_rx:
        return "last_rx=<none>"

    rx_hex = plc.last_rx.hex(" ").upper()
    relay_code = _extract_relay_nak_error_code(plc.last_rx)
    response_code = _extract_response_error_code(plc.last_rx)

    try:
        outer = parse_response(plc.last_rx)
    except Exception:
        return (
            f"last_rx={rx_hex} relay_error={_format_error_code(relay_code)} "
            f"response_error={_format_error_code(response_code)}"
        )

    if outer.cmd != 0x60:
        return (
            f"last_rx={rx_hex} relay_error={_format_error_code(relay_code)} "
            f"response_error={_format_error_code(response_code)}"
        )

    layers, final = unwrap_relay_response_chain(outer)
    if final is None:
        ack = layers[-1].ack if layers else None
        return (
            f"last_rx={rx_hex} relay_ack=0x{ack:02X} "
            f"relay_error={_format_error_code(relay_code)}"
        )

    if final.rc == 0x10:
        code = final.data[-1] if final.data else final.cmd
        return (
            f"last_rx={rx_hex} inner_rc=0x10 "
            f"response_error={_format_error_code(code)}"
        )

    return (
        f"last_rx={rx_hex} relay_error={_format_error_code(relay_code)} "
        f"response_error={_format_error_code(response_code)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Relay abnormal-case verification")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    parser.add_argument("--local-port", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--retries", type=int, default=0)
    parser.add_argument("--hops", required=True)
    parser.add_argument("--missing-hops", default="")
    parser.add_argument("--broken-hops", default="")
    parser.add_argument("--forbidden-write-device", default="")
    parser.add_argument("--forbidden-write-value", type=parse_int_auto, default=0x1234)
    parser.add_argument("--out-of-range-word-index", type=parse_int_auto, default=0x3000)
    parser.add_argument("--out-of-range-pc10-addr32", type=parse_int_auto, default=None)
    parser.add_argument("--log", default="")
    args = parser.parse_args()

    missing_hops = args.missing_hops or _auto_missing_hops(args.hops)
    broken_hops = args.broken_hops or _auto_broken_hops(args.hops)

    log_f = open(args.log, "w", encoding="utf-8") if args.log else None
    try:
        _emit(f"hops = {args.hops}", log_f)
        _emit(f"missing_hops = {missing_hops}", log_f)
        _emit(f"broken_hops = {broken_hops}", log_f)
        _emit(f"forbidden_write_device = {args.forbidden_write_device or '<skip>'}", log_f)
        _emit(f"out_of_range_word_index = 0x{args.out_of_range_word_index:04X}", log_f)
        if args.out_of_range_pc10_addr32 is not None:
            _emit(f"out_of_range_pc10_addr32 = 0x{args.out_of_range_pc10_addr32:08X}", log_f)

        with ToyopucHighLevelClient(
            args.host,
            args.port,
            protocol=args.protocol,
            local_port=args.local_port,
            timeout=args.timeout,
            retries=args.retries,
        ) as plc:
            total = 0
            ok = 0

            def run(name: str, fn) -> None:
                nonlocal total, ok
                total += 1
                try:
                    result = fn()
                except Exception as exc:
                    _emit(
                        f"{name}: expected error observed via exception {type(exc).__name__}: {exc}; "
                        + _describe_last_result(plc),
                        log_f,
                    )
                    ok += 1
                    return
                if hasattr(result, "rc") and getattr(result, "rc") == 0x10:
                    code = result.data[-1] if result.data else result.cmd
                    _emit(
                        f"{name}: expected error observed via inner response rc=0x10 "
                        f"error={_format_error_code(code)}; {_describe_last_result(plc)}",
                        log_f,
                    )
                    ok += 1
                    return
                _emit(f"{name}: FAIL unexpected success; {_describe_last_result(plc)}", log_f)

            run("missing-station cpu-status", lambda: plc.relay_read_cpu_status(missing_hops))
            run("broken-path clock-read", lambda: plc.relay_read_clock(broken_hops))
            run(
                "out-of-range basic-word read",
                lambda: plc.send_via_relay(args.hops, build_word_read(0x1000 + args.out_of_range_word_index, 1)),
            )

            if args.out_of_range_pc10_addr32 is not None:
                run(
                    "out-of-range pc10-word read",
                    lambda: plc.send_via_relay(args.hops, build_pc10_block_read(args.out_of_range_pc10_addr32, 2)),
                )

            if args.forbidden_write_device:
                run(
                    f"forbidden write {args.forbidden_write_device}",
                    lambda: plc.relay_write(args.hops, args.forbidden_write_device, args.forbidden_write_value),
                )
            else:
                _emit("forbidden-write: SKIP (use --forbidden-write-device to test a known protected address)", log_f)

            _emit(f"summary = {ok}/{total} expected-error cases observed", log_f)
            return 0 if ok == total else 1
    finally:
        if log_f is not None:
            log_f.close()


if __name__ == "__main__":
    raise SystemExit(main())

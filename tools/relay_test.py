#!/usr/bin/env python
import argparse
from datetime import datetime
from typing import Callable

from toyopuc import (
    ToyopucClient,
    ToyopucProtocolError,
    encode_word_address,
    parse_address,
)
from toyopuc.protocol import (
    build_clock_write,
    build_clock_read,
    build_cpu_status_read_a0,
    build_cpu_status_read,
    build_relay_nested,
    build_word_read,
    build_word_write,
    parse_clock_data,
    parse_cpu_status_data_a0,
    parse_cpu_status_data,
    unpack_u16_le,
)
from toyopuc.relay import (
    format_relay_hop as format_hop,
    parse_relay_hops as parse_hops,
    unwrap_relay_response_chain,
)


def parse_int_auto(text: str) -> int:
    return int(text, 0)


def parse_hex_bytes(text: str) -> bytes:
    cleaned = text.replace(" ", "").replace("-", "").replace(":", "")
    if cleaned.startswith("0x"):
        cleaned = cleaned[2:]
    if len(cleaned) % 2 != 0:
        raise argparse.ArgumentTypeError("hex byte string must contain an even number of hex digits")
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def parse_datetime_iso(text: str) -> datetime:
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO datetime: {text!r}") from exc


def format_frame(resp) -> bytes:
    length = len(resp.data) + 1
    ll = length & 0xFF
    lh = (length >> 8) & 0xFF
    return bytes([resp.ft, resp.rc, ll, lh, resp.cmd]) + resp.data


def build_inner_payload(args) -> bytes:
    if args.inner == "cpu-status":
        return build_cpu_status_read()
    if args.inner == "cpu-status-a0":
        return build_cpu_status_read_a0()
    if args.inner == "clock-read":
        return build_clock_read()
    if args.inner == "clock-write":
        if args.clock_value is None:
            raise SystemExit("--clock-value is required when --inner clock-write is used")
        weekday = (args.clock_value.weekday() + 1) % 7
        return build_clock_write(
            args.clock_value.second,
            args.clock_value.minute,
            args.clock_value.hour,
            args.clock_value.day,
            args.clock_value.month,
            args.clock_value.year % 100,
            weekday,
        )
    if args.inner == "word-read":
        addr = encode_word_address(parse_address(args.device, "word"))
        return build_word_read(addr, args.count)
    if args.inner == "word-write":
        addr = encode_word_address(parse_address(args.device, "word"))
        return build_word_write(addr, [args.value])
    return args.raw_inner

def print_decoded_inner(args, inner_resp, printer: Callable[[str], None]) -> None:
    if args.inner == "cpu-status":
        status = parse_cpu_status_data(inner_resp.data)
        printer(f"INNER CPU_STATUS raw = {status.raw_bytes_hex}")
        printer(f"INNER CPU_STATUS RUN = {status.run}")
        printer(f"INNER CPU_STATUS Alarm = {status.alarm}")
        printer(f"INNER CPU_STATUS PC10 mode = {status.pc10_mode}")
        printer(f"INNER CPU_STATUS Under writing flash register = {status.under_writing_flash_register}")
        printer(f"INNER CPU_STATUS Abnormal write flash register = {status.abnormal_write_flash_register}")
        return
    if args.inner == "cpu-status-a0":
        status = parse_cpu_status_data_a0(inner_resp.data)
        printer(f"INNER CPU_STATUS_A0 raw = {status.raw_bytes_hex}")
        printer(f"INNER CPU_STATUS_A0 RUN = {status.run}")
        printer(f"INNER CPU_STATUS_A0 Alarm = {status.alarm}")
        printer(f"INNER CPU_STATUS_A0 PC10 mode = {status.pc10_mode}")
        printer(f"INNER CPU_STATUS_A0 Under writing flash register = {status.under_writing_flash_register}")
        printer(f"INNER CPU_STATUS_A0 Abnormal write flash register = {status.abnormal_write_flash_register}")
        return
    if args.inner == "clock-read":
        clock = parse_clock_data(inner_resp.data)
        printer(f"INNER CLOCK raw = {clock}")
        try:
            printer(f"INNER CLOCK datetime = {clock.as_datetime().isoformat(sep=' ')}")
        except Exception as exc:
            printer(f"INNER CLOCK datetime = unavailable ({exc})")
        return
    if args.inner == "clock-write":
        printer(f"INNER CLOCK_WRITE target = {args.clock_value.isoformat(sep=' ')}")
        printer("INNER CLOCK_WRITE ack = success")
        return
    if args.inner == "word-read":
        words = unpack_u16_le(inner_resp.data)
        printer(f"INNER WORD_READ device = {args.device}")
        printer(f"INNER WORD_READ count = {args.count}")
        printer("INNER WORD_READ values = " + ", ".join(f"0x{value:04X}" for value in words))
        return
    if args.inner == "word-write":
        printer(f"INNER WORD_WRITE device = {args.device}")
        printer(f"INNER WORD_WRITE value = 0x{args.value & 0xFFFF:04X}")
        printer("INNER WORD_WRITE ack = success")

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Real-hardware relay command (`CMD=60`) test helper.")
    p.add_argument("--host", required=True)
    p.add_argument("--port", required=True, type=int)
    p.add_argument("--protocol", choices=("tcp", "udp"), default="tcp")
    p.add_argument("--local-port", type=int, default=0)
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument("--retries", type=int, default=0)
    p.add_argument(
        "--hops",
        required=True,
        type=parse_hops,
        help="comma-separated hop list, for example 0x12:0x0002 or P1-L2:N2",
    )
    p.add_argument(
        "--inner",
        choices=("cpu-status", "cpu-status-a0", "clock-read", "clock-write", "word-read", "word-write", "raw"),
        default="cpu-status",
        help="inner command to relay; default is safe read-only CPU status",
    )
    p.add_argument("--device", default="D0000", help="word device for --inner word-read")
    p.add_argument("--count", type=parse_int_auto, default=1, help="word count for --inner word-read")
    p.add_argument("--value", type=parse_int_auto, default=0x1234, help="word value for --inner word-write")
    p.add_argument("--clock-value", type=parse_datetime_iso, default=None, help="ISO datetime for --inner clock-write")
    p.add_argument("--raw-inner", type=parse_hex_bytes, default=b"", help="full inner frame bytes for --inner raw")
    p.add_argument("--log", default="", help="optional log file path")
    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.inner == "word-read" and args.count < 1:
        raise SystemExit("--count must be >= 1")
    if args.inner == "word-write" and args.count != 1:
        raise SystemExit("--inner word-write currently requires --count 1")
    if args.inner == "raw" and not args.raw_inner:
        raise SystemExit("--raw-inner is required when --inner raw is used")

    log_f = open(args.log, "w", encoding="utf-8") if args.log else None

    def log(line: str) -> None:
        print(line)
        if log_f:
            log_f.write(line + "\n")
            log_f.flush()

    inner_payload = build_inner_payload(args)

    plc = ToyopucClient(
        args.host,
        args.port,
        protocol=args.protocol,
        local_port=args.local_port,
        timeout=args.timeout,
        retries=args.retries,
    )
    try:
        resp = plc.send_payload(build_relay_nested(args.hops, inner_payload))
        outer_raw = format_frame(resp)
        log("HOPS = " + ", ".join(format_hop(link, station) for link, station in args.hops))
        log(f"INNER_MODE = {args.inner}")
        log("TX = " + (plc.last_tx.hex(" ").upper() if plc.last_tx else ""))
        log("RX = " + outer_raw.hex(" ").upper())
        if resp.cmd != 0x60:
            raise ToyopucProtocolError(f"Unexpected outer CMD in relay response: 0x{resp.cmd:02X}")

        layers, inner_resp = unwrap_relay_response_chain(resp)
        for i, layer in enumerate(layers, 1):
            prefix = "OUTER" if i == 1 else f"RELAY[{i}]"
            log(f"{prefix} link = 0x{layer.link_no:02X}")
            log(f"{prefix} station = 0x{layer.station_no:04X}")
            log(f"{prefix} ack = 0x{layer.ack:02X}")
            log(f"{prefix} INNER_RAW = {layer.inner_raw.hex(' ').upper()}")
            if layer.padding:
                log(f"{prefix} INNER_PADDING = {layer.padding.hex(' ').upper()}")

        if inner_resp is None:
            if layers:
                log(f"{'OUTER' if len(layers) == 1 else f'RELAY[{len(layers)}]'} INNER_PARSE = skipped because relay ACK is not 0x06")
            return 1

        log(f"INNER FT = 0x{inner_resp.ft:02X}")
        log(f"INNER RC = 0x{inner_resp.rc:02X}")
        log(f"INNER CMD = 0x{inner_resp.cmd:02X}")
        log("INNER DATA = " + inner_resp.data.hex(" ").upper())

        if inner_resp.rc != 0x00:
            return 1

        print_decoded_inner(args, inner_resp, log)
        return 0
    except Exception as e:
        log(f"ERR: {e}")
        if plc.last_tx is not None:
            log(f"LAST_TX {plc.last_tx.hex(' ').upper()}")
        if plc.last_rx is not None:
            log(f"LAST_RX {plc.last_rx.hex(' ').upper()}")
            if len(plc.last_rx) < 5:
                log(
                    "LAST_RX_NOTE short response: not a valid Computer Link frame "
                    "(expected at least 5 bytes: FT RC LL LH CMD)"
                )
        return 1
    finally:
        plc.close()
        if log_f:
            log_f.close()


if __name__ == "__main__":
    raise SystemExit(main())

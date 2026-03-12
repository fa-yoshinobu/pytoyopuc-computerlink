#!/usr/bin/env python
import argparse
import re
from dataclasses import dataclass
from typing import Callable, Optional, Sequence, Tuple, cast

from toyopuc import (
    ToyopucClient,
    ToyopucError,
    encode_bit_address,
    encode_exno_byte_u32,
    encode_fr_word_addr32,
    encode_ext_no_address,
    encode_program_bit_address,
    encode_program_word_address,
    encode_word_address,
    parse_address,
)


BASE_BIT_AREAS = {"P", "K", "V", "T", "C", "L", "X", "Y", "M"}
BASE_WORD_AREAS = {"S", "N", "R", "D", "B"}
EXT_BIT_AREAS = {"EP", "EK", "EV", "ET", "EC", "EL", "EX", "EY", "EM", "GX", "GY", "GM"}
EXT_WORD_AREAS = {"ES", "EN", "H", "U", "EB", "FR"}
PREFIX_TO_NO = {"P1": 0x01, "P2": 0x02, "P3": 0x03}
EXT_BIT_SPECS = {
    "EP": (0x00, 0x0000),
    "EK": (0x00, 0x0200),
    "EV": (0x00, 0x0400),
    "ET": (0x00, 0x0600),
    "EC": (0x00, 0x0600),
    "EL": (0x00, 0x0700),
    "EX": (0x00, 0x0B00),
    "EY": (0x00, 0x0B00),
    "EM": (0x00, 0x0C00),
    "GX": (0x07, 0x0000),
    "GY": (0x07, 0x0000),
    "GM": (0x07, 0x2000),
}


@dataclass
class Probe:
    label: str
    kind: str
    write: Callable[[ToyopucClient, int], None]


@dataclass
class ProbeRange:
    start_text: str
    stop_text: str


def _split_target(text: str) -> Tuple[Optional[str], str, int]:
    upper = text.upper()
    prefix = None
    if "-" in upper:
        prefix, upper = upper.split("-", 1)
        if prefix not in PREFIX_TO_NO:
            raise ValueError(f"Unsupported prefix: {prefix}")
    m = re.fullmatch(r"([A-Z]+)([0-9A-F]+)", upper)
    if not m:
        raise ValueError(f"Invalid target format: {text}")
    return prefix, m.group(1), int(m.group(2), 16)


def _pack_u16_le(value: int) -> bytes:
    return bytes([value & 0xFF, (value >> 8) & 0xFF])


def _pc10_u_word_addr32(index: int) -> int:
    block = index // 0x8000
    ex_no = 0x03 + block
    byte_addr = (index % 0x8000) * 2
    return encode_exno_byte_u32(ex_no, byte_addr)


def _pc10_eb_word_addr32(index: int) -> int:
    block = index // 0x8000
    ex_no = 0x10 + block
    byte_addr = (index % 0x8000) * 2
    return encode_exno_byte_u32(ex_no, byte_addr)


def build_probe(target_text: str) -> Tuple[Probe, int]:
    prefix, area, index = _split_target(target_text)

    if prefix is None:
        if area in BASE_BIT_AREAS:
            parsed = parse_address(f"{area}{index:04X}", "bit")
            addr = encode_bit_address(parsed)
            return (
                Probe(
                    label=f"{area}{index:04X}",
                    kind="bit",
                    write=cast(
                        Callable[[ToyopucClient, int], None],
                        lambda plc, value, addr=addr: plc.write_bit(addr, bool(value)),
                    ),
                ),
                1,
            )
        if area in BASE_WORD_AREAS:
            parsed = parse_address(f"{area}{index:04X}", "word")
            addr = encode_word_address(parsed)
            return (
                Probe(
                    label=f"{area}{index:04X}",
                    kind="word",
                    write=cast(
                        Callable[[ToyopucClient, int], None],
                        lambda plc, value, addr=addr: plc.write_words(addr, [value & 0xFFFF]),
                    ),
                ),
                0xFFFF,
            )
        if area in EXT_BIT_AREAS:
            no, byte_base = EXT_BIT_SPECS[area]
            bit_no = index & 0x07
            addr = byte_base + (index >> 3)
            return (
                Probe(
                    label=f"{area}{index:04X}",
                    kind="ext-bit",
                    write=cast(
                        Callable[[ToyopucClient, int], None],
                        lambda plc, value, no=no, bit_no=bit_no, addr=addr: plc.write_ext_multi(
                            [(no, bit_no, addr, value & 0x01)], [], []
                        ),
                    ),
                ),
                1,
            )
        if area in EXT_WORD_AREAS:
            width = max(4, len(f"{index:X}"))
            label = f"{area}{index:0{width}X}"
            if area == "U" and index >= 0x08000:
                addr32 = _pc10_u_word_addr32(index)
                return (
                    Probe(
                        label=label,
                        kind="pc10-word",
                        write=cast(
                            Callable[[ToyopucClient, int], None],
                            lambda plc, value, addr32=addr32: plc.pc10_block_write(
                                addr32, _pack_u16_le(value & 0xFFFF)
                            ),
                        ),
                    ),
                    0xFFFF,
                )
            if area == "EB" and index <= 0x3FFFF:
                addr32 = _pc10_eb_word_addr32(index)
                return (
                    Probe(
                        label=label,
                        kind="pc10-word",
                        write=cast(
                            Callable[[ToyopucClient, int], None],
                            lambda plc, value, addr32=addr32: plc.pc10_block_write(
                                addr32, _pack_u16_le(value & 0xFFFF)
                            ),
                        ),
                    ),
                    0xFFFF,
                )
            if area == "FR":
                addr32 = encode_fr_word_addr32(index)
                return (
                    Probe(
                        label=label,
                        kind="pc10-word",
                        write=cast(
                            Callable[[ToyopucClient, int], None],
                            lambda plc, value, addr32=addr32: plc.pc10_block_write(
                                addr32, _pack_u16_le(value & 0xFFFF)
                            ),
                        ),
                    ),
                    0xFFFF,
                )
            ext = encode_ext_no_address(area, index, "word")
            return (
                Probe(
                    label=label,
                    kind="ext-word",
                    write=cast(
                        Callable[[ToyopucClient, int], None],
                        lambda plc, value, no=ext.no, addr=ext.addr: plc.write_ext_words(
                            no, addr, [value & 0xFFFF]
                        ),
                    ),
                ),
                0xFFFF,
            )
    else:
        if area in BASE_BIT_AREAS:
            parsed = parse_address(f"{area}{index:04X}", "bit")
            bit_no, addr = encode_program_bit_address(parsed)
            no = PREFIX_TO_NO[prefix]
            return (
                Probe(
                    label=f"{prefix}-{area}{index:04X}",
                    kind="pref-bit",
                    write=cast(
                        Callable[[ToyopucClient, int], None],
                        lambda plc, value, no=no, bit_no=bit_no, addr=addr: plc.write_ext_multi(
                            [(no, bit_no, addr, value & 0x01)], [], []
                        ),
                    ),
                ),
                1,
            )
        if area in BASE_WORD_AREAS:
            parsed = parse_address(f"{area}{index:04X}", "word")
            no = PREFIX_TO_NO[prefix]
            addr = encode_program_word_address(parsed)
            return (
                Probe(
                    label=f"{prefix}-{area}{index:04X}",
                    kind="pref-word",
                    write=cast(
                        Callable[[ToyopucClient, int], None],
                        lambda plc, value, no=no, addr=addr: plc.write_ext_words(
                            no, addr, [value & 0xFFFF]
                        ),
                    ),
                ),
                0xFFFF,
            )

    raise ValueError(f"Unsupported target: {target_text}")


def _default_probe_ranges() -> Sequence[ProbeRange]:
    return [
        ProbeRange("D2FFF", "D2FF0"),
        ProbeRange("P1-D2FFF", "P1-D2FF0"),
        ProbeRange("P3-D2FFF", "P3-D2FF0"),
        ProbeRange("U1FFFF", "U1FFF0"),
    ]


def main() -> int:
    p = argparse.ArgumentParser(description="Probe downward to find the last writable address")
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    p.add_argument("--local-port", type=int, default=0)
    p.add_argument("--timeout", type=float, default=3.0)
    p.add_argument("--retries", type=int, default=0)
    p.add_argument("--start", default="", help="start from this address and move downward")
    p.add_argument("--stop", default="", help="optional lower bound")
    p.add_argument("--step", type=lambda s: int(s, 0), default=1)
    p.add_argument("--value", type=lambda s: int(s, 0), default=None)
    p.add_argument(
        "--auto-pending",
        action="store_true",
        help="probe known tail-end candidates automatically (D2FFF, P1-D2FFF, P3-D2FFF, U1FFFF)",
    )
    p.add_argument("--log", default="")
    args = p.parse_args()

    if not args.auto_pending and not args.start:
        raise SystemExit("use --start or --auto-pending")
    if args.step <= 0:
        raise SystemExit("--step must be > 0")

    log_f = open(args.log, "w", encoding="utf-8") if args.log else None
    results = []

    def log(line: str) -> None:
        print(line)
        if log_f:
            log_f.write(line + "\n")
            log_f.flush()

    ranges: Sequence[ProbeRange]
    if args.auto_pending:
        ranges = _default_probe_ranges()
    else:
        stop_text = args.stop
        if not stop_text:
            prefix0, area0, start_index0 = _split_target(args.start)
            width = max(4, len(f"{start_index0:X}"))
            stop_text = (
                f"{area0}{0:0{width}X}" if prefix0 is None else f"{prefix0}-{area0}{0:0{width}X}"
            )
        ranges = [ProbeRange(args.start, stop_text)]

    with ToyopucClient(
        args.host,
        args.port,
        protocol=args.protocol,
        local_port=args.local_port,
        timeout=args.timeout,
        retries=args.retries,
    ) as plc:
        for probe_range in ranges:
            prefix, area, start_index = _split_target(probe_range.start_text)
            stop_prefix, stop_area, stop_index = _split_target(probe_range.stop_text)
            if stop_prefix != prefix or stop_area != area:
                raise SystemExit("--start and --stop must use the same area")

            last_ok = None
            first_error = None
            log(f"=== probe {probe_range.start_text} -> {probe_range.stop_text} ===")

            index = start_index
            while index >= stop_index:
                target_text = f"{area}{index:X}" if prefix is None else f"{prefix}-{area}{index:X}"
                try:
                    probe, default_value = build_probe(target_text)
                    value = default_value if args.value is None else args.value
                    probe.write(plc, value)
                    last_ok = probe.label
                    log(f"OK    {probe.label}")
                except (ToyopucError, ValueError) as e:
                    if first_error is None:
                        first_error = f"{target_text} ({e})"
                    log(f"ERROR {target_text} {e}")
                index -= args.step

            results.append((probe_range.start_text, probe_range.stop_text, last_ok, first_error))

    print()
    print("Summary")
    for start_text, stop_text, last_ok, first_error in results:
        print(f"- {start_text} -> {stop_text}")
        print(f"  last_ok: {last_ok or 'none'}")
        print(f"  first_error: {first_error or 'none'}")
    if log_f:
        log_f.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

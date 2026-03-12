#!/usr/bin/env python
import argparse
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Tuple, cast

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


@dataclass
class Target:
    kind: str
    label: str
    value_text: str
    write: Callable[[ToyopucClient], None]


_EXT_BIT_AREA_SPECS = {
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

_PREFIX_TO_NO = {"P1": 0x01, "P2": 0x02, "P3": 0x03}


def _ext_bit_point(area: str, index: int) -> Tuple[int, int, int]:
    no, byte_base = _EXT_BIT_AREA_SPECS[area]
    return no, index & 0x07, byte_base + (index >> 3)


def _prefixed_bit_ext_addr(prefix: str, area: str, index: int) -> Tuple[int, int, int]:
    program_no = _PREFIX_TO_NO[prefix]
    parsed = parse_address(f"{area}{index:04X}", "bit")
    bit_no, addr = encode_program_bit_address(parsed)
    return program_no, bit_no, addr


def _prefixed_word_ext_addr(prefix: str, area: str, index: int) -> Tuple[int, int]:
    program_no = _PREFIX_TO_NO[prefix]
    parsed = parse_address(f"{area}{index:04X}", "word")
    addr = encode_program_word_address(parsed)
    return program_no, addr


def _pack_u16_le(value: int) -> bytes:
    return bytes([value & 0xFF, (value >> 8) & 0xFF])


def _pc10_u_word_addr32(index: int) -> int:
    if index < 0x08000 or index > 0x1FFFF:
        raise ValueError("U PC10 range is 0x08000-0x1FFFF")
    block = index // 0x8000
    ex_no = 0x03 + block
    byte_addr = (index % 0x8000) * 2
    return encode_exno_byte_u32(ex_no, byte_addr)


def _pc10_eb_word_addr32(index: int) -> int:
    if index < 0x00000 or index > 0x3FFFF:
        raise ValueError("EB PC10 range is 0x00000-0x3FFFF")
    block = index // 0x8000
    ex_no = 0x10 + block
    byte_addr = (index % 0x8000) * 2
    return encode_exno_byte_u32(ex_no, byte_addr)


def _base_targets() -> List[Target]:
    bit_ranges = {
        "P": [(0x000, 0x1FF), (0x1000, 0x17FF)],
        "K": [(0x000, 0x2FF)],
        "V": [(0x000, 0x0FF), (0x1000, 0x17FF)],
        "T": [(0x000, 0x1FF), (0x1000, 0x17FF)],
        "C": [(0x000, 0x1FF), (0x1000, 0x17FF)],
        "L": [(0x000, 0x7FF), (0x1000, 0x2FFF)],
        "X": [(0x000, 0x7FF)],
        "Y": [(0x000, 0x7FF)],
        "M": [(0x000, 0x7FF), (0x1000, 0x17FF)],
    }
    word_ranges = {
        "S": [(0x0000, 0x03FF), (0x1000, 0x13FF)],
        "N": [(0x0000, 0x01FF), (0x1000, 0x17FF)],
        "R": [(0x0000, 0x07FF)],
        "D": [(0x0000, 0x2FFF)],
    }

    targets: List[Target] = []
    for area, ranges in bit_ranges.items():
        for start, end in ranges:
            for idx in (start, end):
                parsed = parse_address(f"{area}{idx:04X}", "bit")
                addr = encode_bit_address(parsed)
                label = f"{area}{idx:04X}"
                targets.append(
                    Target(
                        kind="BIT",
                        label=label,
                        value_text="1",
                        write=cast(Callable[[ToyopucClient], None], lambda plc, addr=addr: plc.write_bit(addr, True)),
                    )
                )
    for area, ranges in word_ranges.items():
        for start, end in ranges:
            for idx in (start, end):
                parsed = parse_address(f"{area}{idx:04X}", "word")
                addr = encode_word_address(parsed)
                label = f"{area}{idx:04X}"
                targets.append(
                    Target(
                        kind="WORD",
                        label=label,
                        value_text="FFFF",
                        write=cast(
                            Callable[[ToyopucClient], None],
                            lambda plc, addr=addr: plc.write_words(addr, [0xFFFF]),
                        ),
                    )
                )
    return targets


def _prefixed_targets() -> List[Target]:
    bit_ranges = [
        ("P", [(0x000, 0x1FF), (0x1000, 0x17FF)]),
        ("K", [(0x000, 0x2FF)]),
        ("V", [(0x000, 0x0FF), (0x1000, 0x17FF)]),
        ("T", [(0x000, 0x1FF), (0x1000, 0x17FF)]),
        ("C", [(0x000, 0x1FF), (0x1000, 0x17FF)]),
        ("L", [(0x000, 0x7FF), (0x1000, 0x2FFF)]),
        ("X", [(0x000, 0x7FF)]),
        ("Y", [(0x000, 0x7FF)]),
        ("M", [(0x000, 0x7FF), (0x1000, 0x17FF)]),
    ]
    word_ranges = [
        ("S", [(0x0000, 0x03FF), (0x1000, 0x13FF)]),
        ("N", [(0x0000, 0x01FF), (0x1000, 0x17FF)]),
        ("R", [(0x0000, 0x07FF)]),
        ("D", [(0x0000, 0x2FFF)]),
    ]

    targets: List[Target] = []
    for prefix in ("P1", "P2", "P3"):
        for area, ranges in bit_ranges:
            for start, end in ranges:
                for idx in (start, end):
                    no, bit_no, addr = _prefixed_bit_ext_addr(prefix, area, idx)
                    label = f"{prefix}-{area}{idx:04X}"
                    targets.append(
                        Target(
                            kind="PREF BIT",
                            label=label,
                            value_text="1",
                            write=cast(
                                Callable[[ToyopucClient], None],
                                lambda plc, no=no, bit_no=bit_no, addr=addr: plc.write_ext_multi(
                                    [(no, bit_no, addr, 1)], [], []
                                ),
                            ),
                        )
                    )
        for area, ranges in word_ranges:
            for start, end in ranges:
                for idx in (start, end):
                    no, addr = _prefixed_word_ext_addr(prefix, area, idx)
                    label = f"{prefix}-{area}{idx:04X}"
                    targets.append(
                        Target(
                            kind="PREF WORD",
                            label=label,
                            value_text="FFFF",
                            write=cast(
                                Callable[[ToyopucClient], None],
                                lambda plc, no=no, addr=addr: plc.write_ext_words(no, addr, [0xFFFF]),
                            ),
                        )
                    )
    return targets


def _ext_targets(include_fr: bool) -> List[Target]:
    bit_ranges = {
        "EP": [(0x0000, 0x0FFF)],
        "EK": [(0x0000, 0x0FFF)],
        "EV": [(0x0000, 0x0FFF)],
        "ET": [(0x0000, 0x07FF)],
        "EC": [(0x0000, 0x07FF)],
        "EL": [(0x0000, 0x1FFF)],
        "EX": [(0x0000, 0x07FF)],
        "EY": [(0x0000, 0x07FF)],
        "EM": [(0x0000, 0x1FFF)],
        "GX": [(0x0000, 0xFFFF)],
        "GY": [(0x0000, 0xFFFF)],
        "GM": [(0x0000, 0xFFFF)],
    }
    word_ranges = {
        "ES": [(0x0000, 0x07FF)],
        "EN": [(0x0000, 0x07FF)],
        "H": [(0x0000, 0x07FF)],
        "U": [(0x00000, 0x1FFFF)],
        "EB": [(0x00000, 0x7FFFF)],
    }
    if include_fr:
        word_ranges["FR"] = [(0x000000, 0x1FFFFF)]

    targets: List[Target] = []
    for area, ranges in bit_ranges.items():
        for start, end in ranges:
            for idx in (start, end):
                no, bit_no, addr = _ext_bit_point(area, idx)
                label = f"{area}{idx:04X}"
                targets.append(
                    Target(
                        kind="EXT BIT",
                        label=label,
                        value_text="1",
                        write=cast(
                            Callable[[ToyopucClient], None],
                            lambda plc, no=no, bit_no=bit_no, addr=addr: plc.write_ext_multi(
                                [(no, bit_no, addr, 1)], [], []
                            ),
                        ),
                    )
                )
    for area, ranges in word_ranges.items():
        for start, end in ranges:
            for idx in (start, end):
                width = max(4, len(f"{idx:X}"))
                label = f"{area}{idx:0{width}X}"
                if area == "U" and idx >= 0x08000:
                    addr32 = _pc10_u_word_addr32(idx)
                    targets.append(
                        Target(
                            kind="PC10 WORD",
                            label=label,
                            value_text="FFFF",
                            write=cast(
                                Callable[[ToyopucClient], None],
                                lambda plc, addr32=addr32: plc.pc10_block_write(addr32, _pack_u16_le(0xFFFF)),
                            ),
                        )
                    )
                elif area == "EB" and idx <= 0x3FFFF:
                    addr32 = _pc10_eb_word_addr32(idx)
                    targets.append(
                        Target(
                            kind="PC10 WORD",
                            label=label,
                            value_text="FFFF",
                            write=cast(
                                Callable[[ToyopucClient], None],
                                lambda plc, addr32=addr32: plc.pc10_block_write(addr32, _pack_u16_le(0xFFFF)),
                            ),
                        )
                    )
                elif area == "FR":
                    addr32 = encode_fr_word_addr32(idx)
                    targets.append(
                        Target(
                            kind="PC10 WORD",
                            label=label,
                            value_text="FFFF",
                            write=cast(
                                Callable[[ToyopucClient], None],
                                lambda plc, addr32=addr32: plc.pc10_block_write(addr32, _pack_u16_le(0xFFFF)),
                            ),
                        )
                    )
                else:
                    ext = encode_ext_no_address(area, idx, "word")
                    targets.append(
                        Target(
                            kind="EXT WORD",
                            label=label,
                            value_text="FFFF",
                            write=cast(
                                Callable[[ToyopucClient], None],
                                lambda plc, no=ext.no, addr=ext.addr: plc.write_ext_words(no, addr, [0xFFFF]),
                            ),
                        )
                    )
    return targets


def build_targets(include_fr: bool) -> List[Target]:
    return _base_targets() + _prefixed_targets() + _ext_targets(include_fr)


def _prompt_step(index: int, total: int, target: Target) -> str:
    print()
    print(f"[{index}/{total}] next: [{target.kind}] {target.label} <= {target.value_text}")
    print("Enter=write, s=skip, q=quit")
    return input("> ").strip().lower()


def _prompt_result() -> str:
    print("Check the dedicated tool. Was the written value correct? (y/n/q)")
    return input("> ").strip().lower()


def _write_log(log_f, message: str) -> None:
    if log_f:
        log_f.write(message + "\n")
        log_f.flush()


def main() -> int:
    p = argparse.ArgumentParser(description="Manual write-and-check helper")
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    p.add_argument("--local-port", type=int, default=0)
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument("--retries", type=int, default=0)
    p.add_argument("--include-fr", action="store_true", help="include FR end points")
    p.add_argument("--log", default="", help="optional result log path")
    args = p.parse_args()

    targets = build_targets(args.include_fr)
    written = 0
    confirmed = 0
    failed = 0
    skipped = 0
    log_f = open(args.log, "w", encoding="utf-8") if args.log else None
    if log_f:
        _write_log(log_f, f"started: {datetime.now().isoformat(timespec='seconds')}")
        _write_log(log_f, f"host: {args.host}")
        _write_log(log_f, f"port: {args.port}")
        _write_log(log_f, f"protocol: {args.protocol}")
        _write_log(log_f, f"local_port: {args.local_port}")
        _write_log(log_f, f"targets: {len(targets)}")

    try:
        with ToyopucClient(
            args.host,
            args.port,
            protocol=args.protocol,
            local_port=args.local_port,
            timeout=args.timeout,
            retries=args.retries,
        ) as plc:
            for i, target in enumerate(targets, start=1):
                action = _prompt_step(i, len(targets), target)
                _write_log(log_f, f"[{i}/{len(targets)}] target=[{target.kind}] {target.label} value={target.value_text} action={action or 'write'}")
                if action == "q":
                    _write_log(log_f, "operator requested quit before write")
                    break
                if action == "s":
                    skipped += 1
                    _write_log(log_f, "result=skipped-before-write")
                    continue
                try:
                    target.write(plc)
                except ToyopucError as e:
                    print(f"WRITE ERROR: {e}")
                    failed += 1
                    _write_log(log_f, f"result=write-error detail={e}")
                    continue
                written += 1
                result = _prompt_result()
                _write_log(log_f, f"operator_result={result or 'skip'}")
                if result == "q":
                    _write_log(log_f, "operator requested quit after write")
                    break
                if result == "y":
                    confirmed += 1
                    _write_log(log_f, "result=confirmed")
                elif result == "n":
                    failed += 1
                    _write_log(log_f, "result=failed")
                else:
                    skipped += 1
                    _write_log(log_f, "result=skipped-after-write")
    finally:
        print()
        print("Summary")
        print(f"- targets: {len(targets)}")
        print(f"- written: {written}")
        print(f"- confirmed: {confirmed}")
        print(f"- failed: {failed}")
        print(f"- skipped: {skipped}")
        if log_f:
            _write_log(log_f, f"summary targets={len(targets)} written={written} confirmed={confirmed} failed={failed} skipped={skipped}")
            _write_log(log_f, f"finished: {datetime.now().isoformat(timespec='seconds')}")
            log_f.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

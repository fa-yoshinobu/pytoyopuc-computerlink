#!/usr/bin/env python
import argparse
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from toyopuc import (
    ToyopucClient,
    ToyopucError,
    encode_exno_byte_u32,
    encode_ext_no_address,
    encode_fr_word_addr32,
    encode_word_address,
    encode_program_word_address,
    parse_address,
)
from toyopuc.address import ParsedAddress

Range = Tuple[int, int]


@dataclass
class ReadTarget:
    name: str
    ranges: Sequence[Range]
    mode: str  # basic, ext, pc10, fr, bitword, pref_word, pref_bitword
    width: int  # hex width for display
    suffix: str = ""
    area: Optional[str] = None
    prefix: Optional[str] = None


TARGETS: Dict[str, ReadTarget] = {}


def _add_target(target: ReadTarget) -> None:
    TARGETS[target.name.upper()] = target


_BASIC_WORD_RANGES = {
    "S": [(0x0000, 0x13FF)],
    "N": [(0x0000, 0x17FF)],
    "R": [(0x0000, 0x07FF)],
    "D": [(0x0000, 0x2FFF)],
}

for area, ranges in _BASIC_WORD_RANGES.items():
    _add_target(ReadTarget(area, ranges, "basic", 4))

_BASIC_BIT_WORD_RANGES = {
    "P": [(0x0000, 0x17FF)],
    "K": [(0x0000, 0x002F)],
    "V": [(0x0000, 0x17FF)],
    "T": [(0x0000, 0x17FF)],
    "C": [(0x0000, 0x17FF)],
    "L": [(0x0000, 0x2FFF)],
    "X": [(0x0000, 0x07FF)],
    "Y": [(0x0000, 0x07FF)],
    "M": [(0x0000, 0x17FF)],
}

for area, ranges in _BASIC_BIT_WORD_RANGES.items():
    _add_target(ReadTarget(area, ranges, "bitword", 4, "W"))

_add_target(ReadTarget("U", [(0x00000, 0x1FFFF)], "pc10", 5))
_add_target(ReadTarget("EB", [(0x00000, 0x3FFFF)], "pc10", 5))
_add_target(ReadTarget("FR", [(0x000000, 0x1FFFFF)], "fr", 6))

for area in ("ES", "EN", "H"):
    _add_target(ReadTarget(area, [(0x0000, 0x07FF)], "ext", 4))

_EXT_BIT_RANGES = {
    "EP": [(0x0000, 0x0FFF)],
    "EK": [(0x0000, 0x0FFF)],
    "EV": [(0x0000, 0x0FFF)],
    "ET": [(0x0000, 0x07FF)],
    "EC": [(0x0000, 0x07FF)],
    "EL": [(0x0000, 0x1FFF)],
    "EX": [(0x0000, 0x07FF)],
    "EY": [(0x0000, 0x07FF)],
    "EM": [(0x0000, 0x1FFF)],
    "GX": [(0x0000, 0x1FFF)],
    "GY": [(0x0000, 0x1FFF)],
    "GM": [(0x0000, 0x1FFF)],
}

for area, ranges in _EXT_BIT_RANGES.items():
    _add_target(ReadTarget(area, ranges, "ext", 4 if ranges[0][1] <= 0x1FFF else 5, "W"))

_PREF_WORD_RANGES = {
    "S": [(0x0000, 0x13FF)],
    "N": [(0x0000, 0x17FF)],
    "R": [(0x0000, 0x07FF)],
    "D": [(0x0000, 0x2FFF)],
}

_PREF_BIT_WORD_RANGES = {
    "P": [(0x0000, 0x01FF), (0x1000, 0x17FF)],
    "K": [(0x0000, 0x002F)],
    "V": [(0x0000, 0x00FF), (0x1000, 0x17FF)],
    "T": [(0x0000, 0x01FF), (0x1000, 0x17FF)],
    "C": [(0x0000, 0x01FF), (0x1000, 0x17FF)],
    "L": [(0x0000, 0x07FF), (0x1000, 0x2FFF)],
    "X": [(0x0000, 0x07FF)],
    "Y": [(0x0000, 0x07FF)],
    "M": [(0x0000, 0x07FF), (0x1000, 0x17FF)],
}

_PREFIX_EX_NO = {"P1": 0x0D, "P2": 0x0E, "P3": 0x0F}

for prefix in _PREFIX_EX_NO:
    for area, ranges in _PREF_WORD_RANGES.items():
        name = f"{prefix}-{area}"
        _add_target(ReadTarget(name, ranges, "pref_word", 4, prefix=prefix, area=area))
    for area, ranges in _PREF_BIT_WORD_RANGES.items():
        name = f"{prefix}-{area}"
        _add_target(ReadTarget(name, ranges, "pref_bitword", 4, "W", prefix=prefix, area=area))


def _chunk_iter(start: int, end: int, chunk: int) -> Iterable[Tuple[int, int]]:
    current = start
    while current <= end:
        size = min(chunk, end - current + 1)
        yield current, size
        current += size


def _pc10_u_addr32(index: int) -> int:
    block = index // 0x8000
    ex_no = 0x03 + block
    byte_addr = (index % 0x8000) * 2
    return encode_exno_byte_u32(ex_no, byte_addr)


def _pc10_eb_addr32(index: int) -> int:
    block = index // 0x8000
    ex_no = 0x10 + block
    byte_addr = (index % 0x8000) * 2
    return encode_exno_byte_u32(ex_no, byte_addr)


def _pc10_block_read_words(plc: ToyopucClient, addr32: int, count: int) -> List[int]:
    data = plc.pc10_block_read(addr32, count * 2)
    return [int.from_bytes(data[i * 2 : (i + 1) * 2], "little") for i in range(count)]


def scan_basic(plc: ToyopucClient, area: str, start: int, count: int) -> None:
    parsed = parse_address(f"{area}{start:04X}", "word")
    addr = encode_word_address(parsed)
    plc.read_words(addr, count)


def scan_ext(plc: ToyopucClient, area: str, start: int, count: int) -> None:
    ext = encode_ext_no_address(area, start, "word")
    plc.read_ext_words(ext.no, ext.addr, count)


def scan_bitword(plc: ToyopucClient, area: str, start: int, count: int) -> None:
    parsed = ParsedAddress(area=area, index=start, unit="word", packed=True)
    addr = encode_word_address(parsed)
    plc.read_words(addr, count)


def scan_pref_word(
    plc: ToyopucClient,
    prefix: str,
    area: str,
    start: int,
    count: int,
    packed: bool = False,
) -> None:
    ex_no = _PREFIX_EX_NO[prefix]
    parsed = ParsedAddress(area=area, index=start, unit="word", packed=packed)
    addr = encode_program_word_address(parsed)
    plc.read_ext_words(ex_no, addr, count)


def _split_pc10_range(start: int, count: int, block_size: int) -> Iterable[Tuple[int, int]]:
    remaining = count
    current = start
    while remaining > 0:
        block_limit = ((current // block_size) + 1) * block_size
        chunk = min(remaining, block_limit - current)
        yield current, chunk
        current += chunk
        remaining -= chunk


def scan_pc10(plc: ToyopucClient, area: str, start: int, count: int) -> None:
    if area == "U" and start < 0x08000:
        prefix_count = min(count, max(0, 0x08000 - start))
        if prefix_count:
            scan_ext(plc, area, start, prefix_count)
        remaining = count - prefix_count
        if remaining <= 0:
            return
        start = start + prefix_count
        count = remaining
    if area == "EB":
        for chunk_start, chunk_len in _split_pc10_range(start, count, 0x8000):
            addr32 = _pc10_eb_addr32(chunk_start)
            _pc10_block_read_words(plc, addr32, chunk_len)
    elif area == "U":
        for chunk_start, chunk_len in _split_pc10_range(start, count, 0x8000):
            addr32 = _pc10_u_addr32(chunk_start)
            _pc10_block_read_words(plc, addr32, chunk_len)
    else:
        for chunk_start, chunk_len in _split_pc10_range(start, count, 0x8000):
            ext = encode_ext_no_address(area, chunk_start, "word")
            plc.read_ext_words(ext.no, ext.addr, chunk_len)


def scan_fr(plc: ToyopucClient, start: int, count: int) -> None:
    for chunk_start, chunk_len in _split_pc10_range(start, count, 0x8000):
        addr32 = encode_fr_word_addr32(chunk_start)
        _pc10_block_read_words(plc, addr32, chunk_len)


def scan_target(plc: ToyopucClient, target: ReadTarget, chunk_size: int) -> Tuple[int, int]:
    total = 0
    errors = 0

    def fmt(index: int) -> str:
        return f"{target.name}{index:0{target.width}X}{target.suffix}"

    area = target.area or target.name
    prefix = target.prefix

    for start, end in target.ranges:
        for chunk_start, chunk_len in _chunk_iter(start, end, chunk_size):
            chunk_end = chunk_start + chunk_len - 1
            print(f"{target.name}: {fmt(chunk_start)}-{fmt(chunk_end)} ({chunk_len} words)", flush=True)
            try:
                if target.mode == "basic":
                    scan_basic(plc, area, chunk_start, chunk_len)
                elif target.mode == "ext":
                    scan_ext(plc, area, chunk_start, chunk_len)
                elif target.mode == "pc10":
                    scan_pc10(plc, area, chunk_start, chunk_len)
                elif target.mode == "fr":
                    scan_fr(plc, chunk_start, chunk_len)
                elif target.mode == "bitword":
                    scan_bitword(plc, area, chunk_start, chunk_len)
                elif target.mode == "pref_word":
                    if prefix is None:
                        raise ValueError("Prefix required for pref_word target")
                    scan_pref_word(plc, prefix, area, chunk_start, chunk_len, packed=False)
                elif target.mode == "pref_bitword":
                    if prefix is None:
                        raise ValueError("Prefix required for pref_bitword target")
                    scan_pref_word(plc, prefix, area, chunk_start, chunk_len, packed=True)
                else:
                    raise ValueError(f"Unsupported mode: {target.mode}")
                total += chunk_len
            except ToyopucError:
                errors += chunk_len
    return total, errors


def main() -> int:
    p = argparse.ArgumentParser(description="Read-only range scan using word-oriented access")
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    p.add_argument("--local-port", type=int, default=0)
    p.add_argument("--timeout", type=float, default=3.0)
    p.add_argument("--retries", type=int, default=0)
    p.add_argument("--targets", default="S,N,R,D,U,EB")
    p.add_argument("--chunk", type=int, default=64)
    p.add_argument("--log", default="")
    args = p.parse_args()

    targets = [name.strip().upper() for name in args.targets.split(",") if name.strip()]
    specs: List[ReadTarget] = []
    for name in targets:
        spec = TARGETS.get(name)
        if spec is None:
            raise SystemExit(f"Unsupported target: {name}")
        specs.append(spec)

    log_f = open(args.log, "w", encoding="utf-8") if args.log else None

    try:
        with ToyopucClient(
            args.host,
            args.port,
            protocol=args.protocol,
            local_port=args.local_port,
            timeout=args.timeout,
            retries=args.retries,
        ) as plc:
            for spec in specs:
                total, errors = scan_target(plc, spec, args.chunk)
                line = f"{spec.name}: total={total} errors={errors}"
                print(line)
                if log_f:
                    log_f.write(line + "\n")
    finally:
        if log_f:
            log_f.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

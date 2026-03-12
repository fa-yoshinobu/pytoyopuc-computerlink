#!/usr/bin/env python
import argparse
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

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


Range = Tuple[int, int]


@dataclass(frozen=True)
class TargetSpec:
    name: str
    kind: str
    ranges: Sequence[Range]
    write_value: int
    writer: Callable[[ToyopucClient, int], None]


BASE_BIT_RANGES: Dict[str, Sequence[Range]] = {
    "P": [(0x0000, 0x01FF), (0x1000, 0x17FF)],
    "K": [(0x0000, 0x02FF)],
    "V": [(0x0000, 0x00FF), (0x1000, 0x17FF)],
    "T": [(0x0000, 0x01FF), (0x1000, 0x17FF)],
    "C": [(0x0000, 0x01FF), (0x1000, 0x17FF)],
    "L": [(0x0000, 0x07FF), (0x1000, 0x2FFF)],
    "X": [(0x0000, 0x07FF)],
    "Y": [(0x0000, 0x07FF)],
    "M": [(0x0000, 0x07FF), (0x1000, 0x17FF)],
}

BASE_WORD_RANGES: Dict[str, Sequence[Range]] = {
    "S": [(0x0000, 0x03FF), (0x1000, 0x13FF)],
    "N": [(0x0000, 0x01FF), (0x1000, 0x17FF)],
    "R": [(0x0000, 0x07FF)],
    "D": [(0x0000, 0x2FFF)],
    "B": [(0x0000, 0x1FFF)],
}

EXT_BIT_RANGES: Dict[str, Sequence[Range]] = {
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

EXT_WORD_RANGES: Dict[str, Sequence[Range]] = {
    "ES": [(0x0000, 0x07FF)],
    "EN": [(0x0000, 0x07FF)],
    "H": [(0x0000, 0x07FF)],
    "U": [(0x00000, 0x1FFFF)],
    "EB": [(0x00000, 0x7FFFF)],
    "FR": [(0x000000, 0x1FFFFF)],
}

PREFIXES = ("P1", "P2", "P3")
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


def _pack_u16_le(value: int) -> bytes:
    return bytes([value & 0xFF, (value >> 8) & 0xFF])


def _range_label(name: str, start: int, end: int) -> str:
    width = max(4, len(f"{end:X}"))
    return f"{name}{start:0{width}X}-{name}{end:0{width}X}"


def _write_log(log_f, line: str) -> None:
    if log_f:
        log_f.write(line + "\n")
        log_f.flush()


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


def _base_bit_writer(area: str) -> Callable[[ToyopucClient, int], None]:
    def writer(plc: ToyopucClient, index: int) -> None:
        parsed = parse_address(f"{area}{index:04X}", "bit")
        plc.write_bit(encode_bit_address(parsed), True)

    return writer


def _base_word_writer(area: str) -> Callable[[ToyopucClient, int], None]:
    def writer(plc: ToyopucClient, index: int) -> None:
        parsed = parse_address(f"{area}{index:04X}", "word")
        plc.write_words(encode_word_address(parsed), [0xFFFF])

    return writer


def _pref_bit_writer(prefix: str, area: str) -> Callable[[ToyopucClient, int], None]:
    no = PREFIX_TO_NO[prefix]

    def writer(plc: ToyopucClient, index: int) -> None:
        parsed = parse_address(f"{area}{index:04X}", "bit")
        bit_no, addr = encode_program_bit_address(parsed)
        plc.write_ext_multi([(no, bit_no, addr, 1)], [], [])

    return writer


def _pref_word_writer(prefix: str, area: str) -> Callable[[ToyopucClient, int], None]:
    no = PREFIX_TO_NO[prefix]

    def writer(plc: ToyopucClient, index: int) -> None:
        parsed = parse_address(f"{area}{index:04X}", "word")
        addr = encode_program_word_address(parsed)
        plc.write_ext_words(no, addr, [0xFFFF])

    return writer


def _ext_bit_writer(area: str) -> Callable[[ToyopucClient, int], None]:
    no, byte_base = EXT_BIT_SPECS[area]

    def writer(plc: ToyopucClient, index: int) -> None:
        bit_no = index & 0x07
        addr = byte_base + (index >> 3)
        plc.write_ext_multi([(no, bit_no, addr, 1)], [], [])

    return writer


def _ext_word_writer(area: str) -> Callable[[ToyopucClient, int], None]:
    def writer(plc: ToyopucClient, index: int) -> None:
        if area == "U" and index >= 0x08000:
            plc.pc10_block_write(_pc10_u_addr32(index), _pack_u16_le(0xFFFF))
            return
        if area == "EB" and index <= 0x3FFFF:
            plc.pc10_block_write(_pc10_eb_addr32(index), _pack_u16_le(0xFFFF))
            return
        if area == "FR":
            plc.pc10_block_write(encode_fr_word_addr32(index), _pack_u16_le(0xFFFF))
            return
        ext = encode_ext_no_address(area, index, "word")
        plc.write_ext_words(ext.no, ext.addr, [0xFFFF])

    return writer


def build_specs(include_fr: bool) -> Dict[str, TargetSpec]:
    specs: Dict[str, TargetSpec] = {}

    for area, ranges in BASE_BIT_RANGES.items():
        specs[area] = TargetSpec(area, "bit", ranges, 1, _base_bit_writer(area))
    for area, ranges in BASE_WORD_RANGES.items():
        specs[area] = TargetSpec(area, "word", ranges, 0xFFFF, _base_word_writer(area))
    for prefix in PREFIXES:
        for area, ranges in BASE_BIT_RANGES.items():
            name = f"{prefix}-{area}"
            specs[name] = TargetSpec(name, "pref-bit", ranges, 1, _pref_bit_writer(prefix, area))
        for area, ranges in BASE_WORD_RANGES.items():
            name = f"{prefix}-{area}"
            specs[name] = TargetSpec(name, "pref-word", ranges, 0xFFFF, _pref_word_writer(prefix, area))
    for area, ranges in EXT_BIT_RANGES.items():
        specs[area] = TargetSpec(area, "ext-bit", ranges, 1, _ext_bit_writer(area))
    for area, ranges in EXT_WORD_RANGES.items():
        if area == "FR" and not include_fr:
            continue
        specs[area] = TargetSpec(area, "ext-word", ranges, 0xFFFF, _ext_word_writer(area))
    return specs


def _compress_failures(values: Sequence[int]) -> List[Range]:
    if not values:
        return []
    out: List[Range] = []
    start = prev = values[0]
    for value in values[1:]:
        if value == prev + 1:
            prev = value
            continue
        out.append((start, prev))
        start = prev = value
    out.append((start, prev))
    return out


def _iter_indices(start: int, end: int, step: int, reverse: bool) -> Iterable[int]:
    if reverse:
        return range(end, start - 1, -step)
    return range(start, end + 1, step)


def _boundary_candidates(ok_values: Sequence[int], error_values: Sequence[int]) -> List[int]:
    ok_set = set(ok_values)
    candidates = set()
    for value in error_values:
        if value - 1 in ok_set:
            candidates.update((value - 1, value))
        if value + 1 in ok_set:
            candidates.update((value, value + 1))
    return sorted(candidates)


def _iter_targets(specs: Dict[str, TargetSpec], requested: Sequence[str]) -> List[TargetSpec]:
    if len(requested) == 1 and requested[0].lower() == "all":
        return list(specs.values())
    out: List[TargetSpec] = []
    for name in requested:
        key = name.upper()
        if key not in specs:
            raise SystemExit(f"Unknown target '{name}'. Use --targets all or explicit names like D,P1-D,U,GX.")
        out.append(specs[key])
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Exhaustive writable-range scan for every address in selected device families")
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    p.add_argument("--local-port", type=int, default=0)
    p.add_argument("--timeout", type=float, default=3.0)
    p.add_argument("--retries", type=int, default=0)
    p.add_argument("--targets", default="all", help="comma-separated target families, e.g. D,P1-D,U or all")
    p.add_argument("--include-fr", action="store_true")
    p.add_argument("--step", type=int, default=1, help="coarse scan step size (default: 1)")
    p.add_argument("--reverse", action="store_true", help="scan each range from high address to low address")
    p.add_argument(
        "--refine-boundary",
        action="store_true",
        help="after coarse scan, re-check boundary points around OK/NG transitions with step=1",
    )
    p.add_argument(
        "--stop-after-ng",
        type=int,
        default=0,
        help="stop a range after this many consecutive write errors (0=disabled)",
    )
    p.add_argument("--log", default="")
    args = p.parse_args()
    if args.step <= 0:
        raise SystemExit("--step must be >= 1")

    specs = build_specs(args.include_fr)
    requested = [part.strip() for part in args.targets.split(",") if part.strip()]
    targets = _iter_targets(specs, requested)
    log_f = open(args.log, "w", encoding="utf-8") if args.log else None

    with ToyopucClient(
        args.host,
        args.port,
        protocol=args.protocol,
        local_port=args.local_port,
        timeout=args.timeout,
        retries=args.retries,
    ) as plc:
        for spec in targets:
            header = f"=== {spec.name} ({spec.kind}) ==="
            print(header)
            _write_log(log_f, header)
            all_ok: List[int] = []
            all_error: List[int] = []
            last_ok: Optional[int] = None

            for start, end in spec.ranges:
                consecutive_ng = 0
                range_ok: List[int] = []
                range_error: List[int] = []
                stopped_early = False
                for index in _iter_indices(start, end, args.step, args.reverse):
                    try:
                        spec.writer(plc, index)
                        all_ok.append(index)
                        range_ok.append(index)
                        last_ok = index
                        consecutive_ng = 0
                    except (ToyopucError, ValueError):
                        all_error.append(index)
                        range_error.append(index)
                        consecutive_ng += 1
                        if args.stop_after_ng > 0 and consecutive_ng >= args.stop_after_ng:
                            line = f"stopped early after {consecutive_ng} consecutive errors in {_range_label(spec.name, start, end)}"
                            print(line)
                            _write_log(log_f, line)
                            stopped_early = True
                            break
                if args.refine_boundary and args.step > 1 and range_ok and range_error:
                    refined = _boundary_candidates(range_ok, range_error)
                    if refined:
                        line = f"refining {len(refined)} boundary point(s) in {_range_label(spec.name, start, end)}"
                        print(line)
                        _write_log(log_f, line)
                    coarse_known = set(range_ok) | set(range_error)
                    for index in refined:
                        if index in coarse_known:
                            continue
                        try:
                            spec.writer(plc, index)
                            all_ok.append(index)
                            range_ok.append(index)
                            last_ok = index
                        except (ToyopucError, ValueError):
                            all_error.append(index)
                            range_error.append(index)
                if stopped_early and args.refine_boundary and args.step > 1 and range_ok:
                    tail_index = last_ok if last_ok is not None else (end if args.reverse else start)
                    line = f"note: early stop may leave unchecked gap beyond {spec.name}{tail_index:X}"
                    _write_log(log_f, line)

            ok_count = len(all_ok)
            err_count = len(all_error)
            print(f"ok={ok_count} error={err_count}")
            _write_log(log_f, f"ok={ok_count} error={err_count}")

            if last_ok is None:
                print("last_ok=none")
                _write_log(log_f, "last_ok=none")
            else:
                width = max(4, len(f"{last_ok:X}"))
                print(f"last_ok={spec.name}{last_ok:0{width}X}")
                _write_log(log_f, f"last_ok={spec.name}{last_ok:0{width}X}")

            if all_ok:
                first_ok = all_ok[0]
                inner_errors = [idx for idx in all_error if first_ok <= idx <= last_ok]
                holes = _compress_failures(inner_errors)
                if holes:
                    print("holes:")
                    _write_log(log_f, "holes:")
                    for hole_start, hole_end in holes:
                        line = f"  {_range_label(spec.name, hole_start, hole_end)}"
                        print(line)
                        _write_log(log_f, line)
                else:
                    print("holes: none")
                    _write_log(log_f, "holes: none")
            else:
                print("holes: all unsupported")
                _write_log(log_f, "holes: all unsupported")

            print()
            _write_log(log_f, "")

    if log_f:
        log_f.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

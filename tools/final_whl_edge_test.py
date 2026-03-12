from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toyopuc import ToyopucError, ToyopucHighLevelClient


@dataclass(frozen=True)
class FamilyCase:
    area: str
    max_bit_index: int
    prefixed: bool


FAMILY_CASES: List[FamilyCase] = [
    # basic bit families (prefix required)
    FamilyCase("P", 0x17FF, True),
    FamilyCase("K", 0x02FF, True),
    FamilyCase("V", 0x17FF, True),
    FamilyCase("T", 0x17FF, True),
    FamilyCase("C", 0x17FF, True),
    FamilyCase("L", 0x2FFF, True),
    FamilyCase("X", 0x07FF, True),
    FamilyCase("Y", 0x07FF, True),
    FamilyCase("M", 0x17FF, True),
    # ext bit families
    FamilyCase("EP", 0x0FFF, False),
    FamilyCase("EK", 0x0FFF, False),
    FamilyCase("EV", 0x0FFF, False),
    FamilyCase("ET", 0x07FF, False),
    FamilyCase("EC", 0x07FF, False),
    FamilyCase("EL", 0x1FFF, False),
    FamilyCase("EX", 0x07FF, False),
    FamilyCase("EY", 0x07FF, False),
    FamilyCase("EM", 0x1FFF, False),
    FamilyCase("GM", 0xFFFF, False),
    FamilyCase("GX", 0xFFFF, False),
    FamilyCase("GY", 0xFFFF, False),
]


def _write_log(log_f, line: str) -> None:
    if log_f:
        log_f.write(line + "\n")
        log_f.flush()


def _format_case_name(case: FamilyCase, program_prefix: str) -> str:
    if case.prefixed:
        return f"{program_prefix}-{case.area}"
    return case.area


def _bit_width(max_bit_index: int) -> int:
    return max(1, len(f"{max_bit_index:X}"))


def _packed_width(max_bit_index: int) -> int:
    return max(1, _bit_width(max_bit_index) - 1)


def _word_to_bits(value: int) -> List[int]:
    return [1 if (value >> i) & 0x01 else 0 for i in range(16)]


def _read_device(plc: ToyopucHighLevelClient, hops: Optional[str], device: str):
    if hops:
        return plc.relay_read(hops, device)
    return plc.read(device)


def _write_device(plc: ToyopucHighLevelClient, hops: Optional[str], device: str, value: int) -> None:
    if hops:
        plc.relay_write(hops, device, value)
        return
    plc.write(device, value)


def _write_by_bits(
    plc: ToyopucHighLevelClient,
    hops: Optional[str],
    bit_devices: List[str],
    expected_bits: List[int],
) -> None:
    for bit_dev, bit_value in zip(bit_devices, expected_bits):
        _write_device(plc, hops, bit_dev, bit_value)


def _write_by_hl(
    plc: ToyopucHighLevelClient,
    hops: Optional[str],
    low_device: str,
    high_device: str,
    value: int,
) -> None:
    _write_device(plc, hops, low_device, value & 0xFF)
    _write_device(plc, hops, high_device, (value >> 8) & 0xFF)


def _build_addresses(case: FamilyCase, program_prefix: str) -> tuple[List[str], str, str, str]:
    base = _format_case_name(case, program_prefix)
    bit_start = (case.max_bit_index >> 4) << 4
    word_index = case.max_bit_index >> 4
    bit_digits = _bit_width(case.max_bit_index)
    packed_digits = _packed_width(case.max_bit_index)
    bits = [f"{base}{bit_start + i:0{bit_digits}X}" for i in range(16)]
    word = f"{base}{word_index:0{packed_digits}X}W"
    low = f"{base}{word_index:0{packed_digits}X}L"
    high = f"{base}{word_index:0{packed_digits}X}H"
    return bits, word, low, high


def _parse_areas(text: str) -> Optional[set[str]]:
    if not text.strip():
        return None
    return {part.strip().upper() for part in text.split(",") if part.strip()}


def _select_cases(areas: Optional[set[str]]) -> List[FamilyCase]:
    if areas is None:
        return FAMILY_CASES
    selected = [case for case in FAMILY_CASES if case.area in areas]
    missing = sorted(areas - {case.area for case in FAMILY_CASES})
    if missing:
        raise ValueError(f"Unknown area(s): {', '.join(missing)}")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Final-edge W/H/L consistency test for bit-device families (16-point contiguous write)"
    )
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    parser.add_argument("--local-port", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--retries", type=int, default=0)
    parser.add_argument("--hops", default="")
    parser.add_argument("--program-prefix", choices=["P1", "P2", "P3"], default="P1")
    parser.add_argument(
        "--areas",
        default="",
        help="comma-separated subset, e.g. M,EP,GM (default: all listed families)",
    )
    parser.add_argument("--word-pattern", default="", help="fixed 16-bit pattern, e.g. 0xA55A")
    parser.add_argument(
        "--write-mode",
        choices=["bits", "hl"],
        default="bits",
        help="bits: write 16 contiguous bits first (default), hl: write low/high bytes first",
    )
    parser.add_argument("--no-restore", action="store_true", help="do not restore original 16-point bit values")
    parser.add_argument("--skip-errors", action="store_true")
    parser.add_argument("--log", default="")
    args = parser.parse_args()

    hops = args.hops.strip() or None
    areas = _parse_areas(args.areas)
    cases = _select_cases(areas)
    fixed_pattern = int(args.word_pattern, 0) & 0xFFFF if args.word_pattern else None
    restore = not args.no_restore
    log_f = open(args.log, "w", encoding="utf-8") if args.log else None

    total_ok = 0
    total_all = 0
    error_cases = 0

    with ToyopucHighLevelClient(
        args.host,
        args.port,
        protocol=args.protocol,
        local_port=args.local_port,
        timeout=args.timeout,
        retries=args.retries,
    ) as plc:
        for idx, case in enumerate(cases):
            case_name = _format_case_name(case, args.program_prefix)
            bits, word, low, high = _build_addresses(case, args.program_prefix)
            word_value = fixed_pattern if fixed_pattern is not None else ((0xA55A ^ (idx * 0x1357)) & 0xFFFF)
            expected_bits = _word_to_bits(word_value)
            expected_low = word_value & 0xFF
            expected_high = (word_value >> 8) & 0xFF

            print(f"=== {case_name} ===")
            _write_log(log_f, f"=== {case_name} ===")
            _write_log(log_f, f"target bits: {bits[0]}..{bits[-1]}")
            _write_log(log_f, f"word/low/high: {word}, {low}, {high}")
            original_bits: Optional[List[int]] = None

            try:
                original_bits = [1 if bool(_read_device(plc, hops, bit_dev)) else 0 for bit_dev in bits]
                if args.write_mode == "bits":
                    _write_by_bits(plc, hops, bits, expected_bits)
                else:
                    _write_by_hl(plc, hops, low, high, word_value)

                read_word = int(_read_device(plc, hops, word))
                read_low = int(_read_device(plc, hops, low))
                read_high = int(_read_device(plc, hops, high))
                read_bits = [1 if bool(_read_device(plc, hops, bit_dev)) else 0 for bit_dev in bits]

                ok = (
                    read_word == word_value
                    and read_low == expected_low
                    and read_high == expected_high
                    and read_bits == expected_bits
                    and ((read_high << 8) | read_low) == read_word
                )

                line = (
                    f"{case_name}: "
                    f"mode={args.write_mode} "
                    f"target=0x{word_value:04X} read_word=0x{read_word:04X}, "
                    f"L=0x{read_low:02X}, H=0x{read_high:02X}, "
                    f"match={'OK' if ok else 'NG'}"
                )
                print(line)
                _write_log(log_f, line)

                total_all += 1
                if ok:
                    total_ok += 1
                else:
                    mismatch_line = (
                        f"{case_name}: expected bits={expected_bits}, "
                        f"read bits={read_bits}, "
                        f"expected word=0x{word_value:04X}, read word=0x{read_word:04X}"
                    )
                    print(mismatch_line)
                    _write_log(log_f, mismatch_line)
            except (ToyopucError, ValueError, RuntimeError) as exc:
                error_cases += 1
                line = f"{case_name}: ERROR {type(exc).__name__}: {exc}"
                print(line)
                _write_log(log_f, line)
                if not args.skip_errors:
                    if log_f:
                        log_f.close()
                    return 1
            finally:
                if restore and original_bits is not None:
                    try:
                        for bit_dev, bit_value in zip(bits, original_bits):
                            _write_device(plc, hops, bit_dev, bit_value)
                        restore_line = f"{case_name}: restore=OK"
                    except (ToyopucError, ValueError, RuntimeError) as restore_exc:
                        restore_line = f"{case_name}: restore=ERROR {type(restore_exc).__name__}: {restore_exc}"
                        error_cases += 1
                    print(restore_line)
                    _write_log(log_f, restore_line)

    summary = f"TOTAL: {total_ok}/{total_all}"
    errors = f"ERROR CASES: {error_cases}"
    print(summary)
    print(errors)
    _write_log(log_f, summary)
    _write_log(log_f, errors)
    if log_f:
        log_f.close()
    return 0 if total_ok == total_all and error_cases == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

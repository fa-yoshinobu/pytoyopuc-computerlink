from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable, Optional

from toyopuc import (
    ToyopucError,
    ToyopucHighLevelClient,
    encode_bit_address,
    encode_exno_byte_u32,
    parse_address,
)


def _write_log(log_f, line: str) -> None:
    if log_f:
        log_f.write(line + "\n")
        log_f.flush()


def _print_line(line: str, log_f) -> None:
    print(line)
    _write_log(log_f, line)


def _fmt_value(value: int, unit: str) -> str:
    if unit == "bit":
        return str(int(value) & 0x01)
    return f"0x{int(value) & 0xFFFF:04X}"


def _next_word_values(original: int) -> tuple[int, int]:
    phase1 = (original ^ 0xA55A) & 0xFFFF
    if phase1 == original:
        phase1 = (original + 1) & 0xFFFF
    phase2 = (original ^ 0x5AA5) & 0xFFFF
    if phase2 in (original, phase1):
        phase2 = (phase1 + 1) & 0xFFFF
    if phase2 in (original, phase1):
        phase2 = (phase1 + 0x1111) & 0xFFFF
    return phase1, phase2


def _pc10_multi_read_word(plc: ToyopucHighLevelClient, addr32: int) -> int:
    payload = bytearray([0x00, 0x00, 0x01, 0x00])
    payload.extend(addr32.to_bytes(4, "little"))
    data = plc.pc10_multi_read(bytes(payload))
    if len(data) < 6:
        raise ValueError("PC10 multi read response too short")
    body = data[4:]
    if len(body) < 2:
        raise ValueError("PC10 multi read word payload too short")
    return int.from_bytes(body[:2], "little")


def _pc10_multi_write_word(plc: ToyopucHighLevelClient, addr32: int, value: int) -> None:
    payload = bytearray([0x00, 0x00, 0x01, 0x00])
    payload.extend(addr32.to_bytes(4, "little"))
    payload.extend(int(value & 0xFFFF).to_bytes(2, "little"))
    plc.pc10_multi_write(bytes(payload))


def _u_addr32_all(index: int) -> int:
    if index < 0x00000 or index > 0x1FFFF:
        raise ValueError("U index out of range (0x00000-0x1FFFF)")
    ex_no = 0x03 + (index // 0x8000)
    byte_addr = (index % 0x8000) * 2
    return encode_exno_byte_u32(ex_no, byte_addr)


def _eb_addr32_pc10(index: int) -> int:
    if index < 0x00000 or index > 0x3FFFF:
        raise ValueError("EB PC10 candidate range is 0x00000-0x3FFFF")
    ex_no = 0x10 + (index // 0x8000)
    byte_addr = (index % 0x8000) * 2
    return encode_exno_byte_u32(ex_no, byte_addr)


@dataclass(frozen=True)
class BitCase:
    key: str
    device: str


@dataclass(frozen=True)
class WordCase:
    key: str
    device: str
    addr32_builder: Callable[[int], int]


BIT_CASES = {
    "l1000": BitCase("l1000", "L1000"),
    "l2fff": BitCase("l2fff", "L2FFF"),
    "m1000": BitCase("m1000", "M1000"),
    "m17ff": BitCase("m17ff", "M17FF"),
}

WORD_CASES = {
    "u00000": WordCase("u00000", "U00000", _u_addr32_all),
    "u07fff": WordCase("u07fff", "U07FFF", _u_addr32_all),
    "u08000": WordCase("u08000", "U08000", _u_addr32_all),
    "u1ffff": WordCase("u1ffff", "U1FFFF", _u_addr32_all),
    "eb00000": WordCase("eb00000", "EB00000", _eb_addr32_pc10),
    "eb3ffff": WordCase("eb3ffff", "EB3FFFF", _eb_addr32_pc10),
}


def _parse_case_keys(text: str) -> list[str]:
    keys = [item.strip().lower() for item in text.split(",") if item.strip()]
    if not keys:
        raise ValueError("at least one case key is required")
    return keys


def _run_bit_case(plc: ToyopucHighLevelClient, case: BitCase, log_f) -> bool:
    resolved = plc.resolve_device(case.device)
    basic_addr = encode_bit_address(parse_address(case.device, "bit"))
    _print_line(f"=== {case.key} ({case.device}) ===", log_f)
    _print_line(f"current scheme={resolved.scheme} alt=basic-bit CMD=20/21", log_f)
    _print_line("warning: this probe temporarily writes the selected point and restores it", log_f)

    original = 1 if bool(plc.read(case.device)) else 0
    phase1 = 1 - original
    restored = False
    alias_same_point: Optional[bool] = None

    try:
        plc.write(case.device, phase1)
        current1 = 1 if bool(plc.read(case.device)) else 0
        ok1 = current1 == phase1
        _print_line(f"phase1 current write={phase1} read={current1} ok={ok1}", log_f)
        if not ok1:
            return False

        try:
            basic_read = 1 if bool(plc.read_bit(basic_addr)) else 0
            basic_read_ok = basic_read == phase1
            _print_line(f"phase1 alt basic read={basic_read} match_current={basic_read_ok}", log_f)
        except ToyopucError as exc:
            _print_line(f"phase1 alt basic read ERR {exc}", log_f)
            return False

        try:
            plc.write_bit(basic_addr, bool(original))
            current2 = 1 if bool(plc.read(case.device)) else 0
            alias_same_point = current2 == original
            _print_line(
                f"phase2 alt basic write={original} current read={current2} alias_same_point={alias_same_point}",
                log_f,
            )
        except ToyopucError as exc:
            _print_line(f"phase2 alt basic write ERR {exc}", log_f)
            return False
    finally:
        try:
            plc.write(case.device, original)
            restored_read = 1 if bool(plc.read(case.device)) else 0
            restored = restored_read == original
            _print_line(f"restore expected={original} read={restored_read} ok={restored}", log_f)
        except ToyopucError as exc:
            _print_line(f"restore ERR {exc}", log_f)

    if not restored:
        return False
    if alias_same_point is None:
        return False
    if alias_same_point:
        _print_line("verdict: basic CMD=20/21 aliases the same point", log_f)
        return False
    _print_line("verdict: basic CMD=20/21 does not alias the same point; keep CMD=C4/C5", log_f)
    return True


def _run_word_case(plc: ToyopucHighLevelClient, case: WordCase, log_f) -> bool:
    resolved = plc.resolve_device(case.device)
    addr32 = case.addr32_builder(resolved.index)
    _print_line(f"=== {case.key} ({case.device}) ===", log_f)
    _print_line(f"current scheme={resolved.scheme} alt=pc10-word CMD=C4/C5", log_f)
    _print_line("warning: this probe temporarily writes the selected point and restores it", log_f)

    original = int(plc.read(case.device)) & 0xFFFF
    phase1, phase2 = _next_word_values(original)
    restored = False

    try:
        plc.write(case.device, phase1)
        current1 = int(plc.read(case.device)) & 0xFFFF
        ok1 = current1 == phase1
        _print_line(
            f"phase1 current write={_fmt_value(phase1, 'word')} read={_fmt_value(current1, 'word')} ok={ok1}",
            log_f,
        )
        if not ok1:
            return False

        try:
            alt_read = _pc10_multi_read_word(plc, addr32)
            alt_read_ok = alt_read == phase1
            _print_line(
                f"phase1 alt C4 read={_fmt_value(alt_read, 'word')} match_current={alt_read_ok}",
                log_f,
            )
            if not alt_read_ok:
                return False
        except (ToyopucError, ValueError) as exc:
            _print_line(f"phase1 alt C4 read ERR {exc}", log_f)
            return False

        try:
            _pc10_multi_write_word(plc, addr32, phase2)
            current2 = int(plc.read(case.device)) & 0xFFFF
            alias_ok = current2 == phase2
            _print_line(
                f"phase2 alt C5 write={_fmt_value(phase2, 'word')} current read={_fmt_value(current2, 'word')} alias_ok={alias_ok}",
                log_f,
            )
            if not alias_ok:
                return False
        except (ToyopucError, ValueError) as exc:
            _print_line(f"phase2 alt C5 write ERR {exc}", log_f)
            return False
    finally:
        try:
            plc.write(case.device, original)
            restored_read = int(plc.read(case.device)) & 0xFFFF
            restored = restored_read == original
            _print_line(
                f"restore expected={_fmt_value(original, 'word')} read={_fmt_value(restored_read, 'word')} ok={restored}",
                log_f,
            )
        except ToyopucError as exc:
            _print_line(f"restore ERR {exc}", log_f)

    if not restored:
        return False
    _print_line("verdict: CMD=C4/C5 aliases the same point", log_f)
    return True


def main() -> int:
    p = argparse.ArgumentParser(
        description="Probe whether selected ranges really need or can also use CMD=C4/C5"
    )
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    p.add_argument("--local-port", type=int, default=0)
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument("--retries", type=int, default=0)
    p.add_argument(
        "--cases",
        default="l1000,m1000,u00000,u08000,eb00000",
        help="comma-separated case keys",
    )
    p.add_argument("--log", default="")
    args = p.parse_args()

    selected_keys = _parse_case_keys(args.cases)
    selected_cases: list[BitCase | WordCase] = []
    for key in selected_keys:
        if key in BIT_CASES:
            selected_cases.append(BIT_CASES[key])
            continue
        if key in WORD_CASES:
            selected_cases.append(WORD_CASES[key])
            continue
        raise SystemExit(f"unknown case: {key}")

    log_f = open(args.log, "w", encoding="utf-8") if args.log else None
    ok_count = 0
    total = 0

    try:
        with ToyopucHighLevelClient(
            args.host,
            args.port,
            protocol=args.protocol,
            local_port=args.local_port,
            timeout=args.timeout,
            retries=args.retries,
        ) as plc:
            for case in selected_cases:
                total += 1
                try:
                    if isinstance(case, BitCase):
                        ok = _run_bit_case(plc, case, log_f)
                    else:
                        ok = _run_word_case(plc, case, log_f)
                except (ToyopucError, ValueError) as exc:
                    _print_line(f"case {case.key}: ERROR {type(exc).__name__}: {exc}", log_f)
                    ok = False
                if ok:
                    ok_count += 1
        _print_line(f"SUMMARY: {ok_count}/{total} cases passed", log_f)
    finally:
        if log_f:
            log_f.close()

    return 0 if ok_count == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

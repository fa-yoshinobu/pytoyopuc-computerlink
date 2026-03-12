from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Optional, Sequence

from toyopuc import ResolvedDevice, ToyopucClient, ToyopucError, resolve_device


def _decode_ext_multi_read_data(data: bytes, bit_count: int, byte_count: int, word_count: int):
    bit_bytes = (bit_count + 7) // 8
    need = bit_bytes + byte_count + word_count * 2
    if len(data) < need:
        raise ValueError("Response data too short for ext multi payload")
    offset = 0
    bits_raw = data[offset : offset + bit_bytes]
    offset += bit_bytes
    bytes_raw = data[offset : offset + byte_count]
    offset += byte_count
    words_raw = data[offset : offset + word_count * 2]

    bits = [((bits_raw[i // 8] >> (i % 8)) & 0x01) for i in range(bit_count)]
    bytes_out = list(bytes_raw)
    words_out = [words_raw[i] | (words_raw[i + 1] << 8) for i in range(0, len(words_raw), 2)]
    return bits, bytes_out, words_out


def _parse_no_list(text: str) -> list[int]:
    values: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        values.append(int(part, 0) & 0xFF)
    if not values:
        raise ValueError("candidate list must not be empty")
    return values


def _write_log(log_f, line: str) -> None:
    if log_f:
        log_f.write(line + "\n")
        log_f.flush()


def _print_line(line: str, log_f) -> None:
    print(line)
    _write_log(log_f, line)


def _fmt_optional_u8(value: Optional[int]) -> str:
    return "-" if value is None else f"0x{value:02X}"


def _fmt_optional_u16(value: Optional[int]) -> str:
    return "-" if value is None else f"0x{value:04X}"


def _fmt_snapshot(snapshot: "ProbeSnapshot") -> str:
    parts = []
    if snapshot.bit is not None:
        parts.append(f"bit={snapshot.bit}")
    if snapshot.byte is not None:
        parts.append(f"byte={_fmt_optional_u8(snapshot.byte)}")
    if snapshot.word is not None:
        parts.append(f"word={_fmt_optional_u16(snapshot.word)}")
    return " ".join(parts) if parts else "(empty)"


def _next_distinct_8(value: int, salt: int, *avoid: Optional[int]) -> int:
    candidate = (value ^ salt) & 0xFF
    if any(a is not None and candidate == a for a in avoid) or candidate == value:
        candidate = (value + 1) & 0xFF
    if any(a is not None and candidate == a for a in avoid) or candidate == value:
        candidate = (value + 0x53) & 0xFF
    return candidate


def _next_distinct_16(value: int, salt: int, *avoid: Optional[int]) -> int:
    candidate = (value ^ salt) & 0xFFFF
    if any(a is not None and candidate == a for a in avoid) or candidate == value:
        candidate = (value + 1) & 0xFFFF
    if any(a is not None and candidate == a for a in avoid) or candidate == value:
        candidate = (value + 0x5A53) & 0xFFFF
    return candidate


def _require_field(value: Optional[int], context: str) -> int:
    if value is None:
        raise ValueError(context)
    return value


@dataclass(frozen=True)
class ProbeSnapshot:
    bit: Optional[int] = None
    byte: Optional[int] = None
    word: Optional[int] = None


@dataclass(frozen=True)
class ProbeCase:
    key: str
    label: str
    expected_no: int
    bit: Optional[ResolvedDevice] = None
    byte: Optional[ResolvedDevice] = None
    word: Optional[ResolvedDevice] = None

    def counts(self) -> tuple[int, int, int]:
        return (1 if self.bit else 0, 1 if self.byte else 0, 1 if self.word else 0)

    def has_shared_bit_byte(self) -> bool:
        return (
            self.bit is not None
            and self.byte is not None
            and self.bit.addr is not None
            and self.byte.addr is not None
            and self.bit.addr == self.byte.addr
        )


def _make_case(
    key: str,
    label: str,
    *,
    bit_device: str | None = None,
    byte_device: str | None = None,
    word_device: str | None = None,
) -> ProbeCase:
    bit = resolve_device(bit_device) if bit_device else None
    byte = resolve_device(byte_device) if byte_device else None
    word = resolve_device(word_device) if word_device else None
    expected_values: list[int] = []
    for device in (bit, byte, word):
        if device is None:
            continue
        expected_values.append(_require_field(device.no, f"{key}: resolved device missing number"))
    if not expected_values:
        raise ValueError(f"{key}: case has no points")
    expected_no = expected_values[0]
    if any(item != expected_no for item in expected_values):
        raise ValueError(f"{key}: mixed expected no values are not supported")
    return ProbeCase(key=key, label=label, expected_no=expected_no, bit=bit, byte=byte, word=word)


def _build_cases() -> dict[str, ProbeCase]:
    return {
        "ext00": _make_case(
            "ext00",
            "EX/ES current no=0x00",
            bit_device="EX0000",
            byte_device="ES0000L",
            word_device="ES0000",
        ),
        "gx07": _make_case(
            "gx07",
            "GX shared-byte current no=0x07",
            bit_device="GX0000",
            byte_device="GX0000L",
        ),
        "p1": _make_case(
            "p1",
            "P1 current no=0x01",
            bit_device="P1-M0000",
            byte_device="P1-D0000L",
            word_device="P1-D0000",
        ),
        "p2": _make_case(
            "p2",
            "P2 current no=0x02",
            bit_device="P2-M0000",
            byte_device="P2-D0000L",
            word_device="P2-D0000",
        ),
        "p3": _make_case(
            "p3",
            "P3 current no=0x03",
            bit_device="P3-M0000",
            byte_device="P3-D0000L",
            word_device="P3-D0000",
        ),
    }


def _read_snapshot(plc: ToyopucClient, case: ProbeCase, no: int) -> ProbeSnapshot:
    bit_points = []
    byte_points = []
    word_points = []
    if case.bit is not None:
        bit_no = _require_field(case.bit.bit_no, f"{case.key}: bit case missing bit_no")
        addr = _require_field(case.bit.addr, f"{case.key}: bit case missing addr")
        bit_points.append((no, bit_no, addr))
    if case.byte is not None:
        addr = _require_field(case.byte.addr, f"{case.key}: byte case missing addr")
        byte_points.append((no, addr))
    if case.word is not None:
        addr = _require_field(case.word.addr, f"{case.key}: word case missing addr")
        word_points.append((no, addr))
    data = plc.read_ext_multi(bit_points, byte_points, word_points)
    bit_count, byte_count, word_count = case.counts()
    bits, bytes_out, words_out = _decode_ext_multi_read_data(data, bit_count, byte_count, word_count)
    return ProbeSnapshot(
        bit=bits[0] if bit_count else None,
        byte=bytes_out[0] if byte_count else None,
        word=words_out[0] if word_count else None,
    )


def _write_snapshot(plc: ToyopucClient, case: ProbeCase, no: int, snapshot: ProbeSnapshot) -> None:
    bit_points = []
    byte_points = []
    word_points = []
    if case.bit is not None and snapshot.bit is not None:
        bit_no = _require_field(case.bit.bit_no, f"{case.key}: bit case missing bit_no")
        addr = _require_field(case.bit.addr, f"{case.key}: bit case missing addr")
        bit_points.append((no, bit_no, addr, int(snapshot.bit) & 0x01))
    if case.byte is not None and snapshot.byte is not None:
        addr = _require_field(case.byte.addr, f"{case.key}: byte case missing addr")
        byte_points.append((no, addr, int(snapshot.byte) & 0xFF))
    if case.word is not None and snapshot.word is not None:
        addr = _require_field(case.word.addr, f"{case.key}: word case missing addr")
        word_points.append((no, addr, int(snapshot.word) & 0xFFFF))
    plc.write_ext_multi(bit_points, byte_points, word_points)


def _build_phase_snapshot(base: ProbeSnapshot, *, salt8: int, salt16: int, avoid: Optional[ProbeSnapshot] = None) -> ProbeSnapshot:
    return ProbeSnapshot(
        bit=None if base.bit is None else (1 - (base.bit & 0x01)),
        byte=None
        if base.byte is None
        else _next_distinct_8(base.byte, salt8, None if avoid is None else avoid.byte),
        word=None
        if base.word is None
        else _next_distinct_16(base.word, salt16, None if avoid is None else avoid.word),
    )


def _cohere_snapshot(case: ProbeCase, snapshot: ProbeSnapshot) -> ProbeSnapshot:
    if not case.has_shared_bit_byte():
        return snapshot
    if snapshot.bit is None or snapshot.byte is None or case.bit is None or case.bit.bit_no is None:
        return snapshot

    bit_pos = int(case.bit.bit_no) & 0x07
    byte_value = int(snapshot.byte) & 0xFF
    if int(snapshot.bit) & 0x01:
        byte_value |= 1 << bit_pos
    else:
        byte_value &= ~(1 << bit_pos)
    return ProbeSnapshot(
        bit=(byte_value >> bit_pos) & 0x01,
        byte=byte_value,
        word=snapshot.word,
    )


def _run_case(plc: ToyopucClient, case: ProbeCase, candidate_nos: Sequence[int], log_f) -> bool:
    _print_line(f"=== {case.key} ({case.label}) ===", log_f)
    _print_line(f"expected no=0x{case.expected_no:02X}", log_f)
    _print_line("warning: this probe temporarily writes the selected scratch points and restores them", log_f)

    original = _read_snapshot(plc, case, case.expected_no)
    original = _cohere_snapshot(case, original)
    _print_line(f"original expected={_fmt_snapshot(original)}", log_f)

    phase1 = _cohere_snapshot(case, _build_phase_snapshot(original, salt8=0xA5, salt16=0xA55A))
    phase2 = _cohere_snapshot(case, _build_phase_snapshot(phase1, salt8=0x5A, salt16=0x5AA5, avoid=original))
    suspicious: list[int] = []
    restored = False

    try:
        for phase_name, expected in (("phase1", phase1), ("phase2", phase2)):
            _write_snapshot(plc, case, case.expected_no, expected)
            read_back = _read_snapshot(plc, case, case.expected_no)
            ok = read_back == expected
            _print_line(
                f"{phase_name} expected write={_fmt_snapshot(expected)} read={_fmt_snapshot(read_back)} ok={ok}",
                log_f,
            )
            if not ok:
                return False

            for candidate in candidate_nos:
                if candidate == case.expected_no:
                    continue
                try:
                    candidate_read = _read_snapshot(plc, case, candidate)
                except ToyopucError as exc:
                    _print_line(f"{phase_name} candidate no=0x{candidate:02X} ERR {exc}", log_f)
                    continue
                match = candidate_read == expected
                _print_line(
                    f"{phase_name} candidate no=0x{candidate:02X} read={_fmt_snapshot(candidate_read)} match_expected={match}",
                    log_f,
                )
                if match and candidate not in suspicious:
                    suspicious.append(candidate)
    finally:
        try:
            _write_snapshot(plc, case, case.expected_no, original)
            restored_read = _read_snapshot(plc, case, case.expected_no)
            restored = restored_read == original
            _print_line(
                f"restore expected={_fmt_snapshot(original)} read={_fmt_snapshot(restored_read)} ok={restored}",
                log_f,
            )
        except ToyopucError as exc:
            _print_line(f"restore ERR {exc}", log_f)

    if not restored:
        return False
    if suspicious:
        _print_line(
            "verdict: SUSPICIOUS alias/match on candidate no="
            + ",".join(f"0x{value:02X}" for value in suspicious),
            log_f,
        )
        return False
    _print_line("verdict: OK current mapping is distinct from tested candidates", log_f)
    return True


def main() -> int:
    cases = _build_cases()

    p = argparse.ArgumentParser(
        description="Probe CMD=98/99 program-number interpretation by comparing current mapping against candidate no values"
    )
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    p.add_argument("--local-port", type=int, default=0)
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument("--retries", type=int, default=0)
    p.add_argument(
        "--cases",
        default="ext00,gx07,p1",
        help="comma-separated case keys: ext00,gx07,p1,p2,p3",
    )
    p.add_argument(
        "--candidate-nos",
        default="0x00,0x01,0x02,0x03,0x07",
        help="comma-separated candidate no values to compare",
    )
    p.add_argument("--log", default="")
    args = p.parse_args()

    selected_keys = [item.strip().lower() for item in args.cases.split(",") if item.strip()]
    if not selected_keys:
        raise SystemExit("no cases selected")
    selected_cases: list[ProbeCase] = []
    for key in selected_keys:
        if key not in cases:
            raise SystemExit(f"unknown case: {key}")
        selected_cases.append(cases[key])
    candidate_nos = _parse_no_list(args.candidate_nos)

    log_f = open(args.log, "w", encoding="utf-8") if args.log else None
    ok_count = 0
    total = 0

    try:
        with ToyopucClient(
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
                    ok = _run_case(plc, case, candidate_nos, log_f)
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

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import TextIO, TypeVar, cast

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toyopuc import ToyopucDeviceClient, resolve_device  # noqa: E402
from toyopuc.high_level import ResolvedDevice  # noqa: E402
from toyopuc.protocol import (  # noqa: E402
    build_ext_word_read,
    build_ext_word_write,
    build_pc10_block_read,
    build_pc10_block_write,
    build_word_read,
    build_word_write,
    unpack_u16_le,
)

T = TypeVar("T")


def _require(value: T | None, label: str) -> T:
    if value is None:
        raise ValueError(f"resolved device missing {label}")
    return value


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        return value
    raise TypeError(f"unsupported readback type: {type(value)!r}")


def parse_int_auto(text: str) -> int:
    return int(text, 0)


def parse_csv_list(text: str) -> list[str]:
    parts = [part.strip() for part in text.replace(" ", "").split(",")]
    return [part for part in parts if part]


def parse_csv_ints(text: str) -> list[int]:
    return [parse_int_auto(part) for part in parse_csv_list(text)]


def parse_datetime_iso(text: str) -> datetime:
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO datetime: {text!r}") from exc


def _emit(line: str, log_f: TextIO | None) -> None:
    print(line)
    if log_f is not None:
        log_f.write(line + "\n")
        log_f.flush()


def _pattern(
    count: int, base: int, step: int, loop_index: int, loop_step: int
) -> list[int]:
    start = (base + loop_index * loop_step) & 0xFFFF
    return [((start + i * step) & 0xFFFF) for i in range(count)]


def _format_words(values: Iterable[int]) -> str:
    return "[" + ", ".join(f"0x{int(value) & 0xFFFF:04X}" for value in values) + "]"


def _relay_block_read(
    plc: ToyopucDeviceClient, hops: str, device: str, count: int
) -> list[int]:
    resolved = resolve_device(device)
    if resolved.unit != "word":
        raise ValueError(f"{device} is not a word device")
    if resolved.scheme == "basic-word":
        resp = plc.send_via_relay(
            hops, build_word_read(_require(resolved.basic_addr, "basic_addr"), count)
        )
        if resp.cmd != 0x1C:
            raise ValueError(
                f"Unexpected CMD in relay basic word-read response: 0x{resp.cmd:02X}"
            )
        return unpack_u16_le(resp.data)
    if resolved.scheme in ("program-word", "ext-word"):
        resp = plc.send_via_relay(
            hops,
            build_ext_word_read(
                _require(resolved.no, "no"), _require(resolved.addr, "addr"), count
            ),
        )
        if resp.cmd != 0x94:
            raise ValueError(
                f"Unexpected CMD in relay ext word-read response: 0x{resp.cmd:02X}"
            )
        return unpack_u16_le(resp.data)
    if resolved.scheme == "pc10-word":
        resp = plc.send_via_relay(
            hops, build_pc10_block_read(_require(resolved.addr32, "addr32"), count * 2)
        )
        if resp.cmd != 0xC2:
            raise ValueError(
                f"Unexpected CMD in relay PC10 word-read response: 0x{resp.cmd:02X}"
            )
        return unpack_u16_le(resp.data)
    raise ValueError(f"{device} uses unsupported block scheme: {resolved.scheme}")


def _relay_block_write(
    plc: ToyopucDeviceClient, hops: str, device: str, values: list[int]
) -> None:
    resolved = resolve_device(device)
    if resolved.unit != "word":
        raise ValueError(f"{device} is not a word device")
    masked = [int(value) & 0xFFFF for value in values]
    if resolved.scheme == "basic-word":
        resp = plc.send_via_relay(
            hops, build_word_write(_require(resolved.basic_addr, "basic_addr"), masked)
        )
        if resp.cmd != 0x1D:
            raise ValueError(
                f"Unexpected CMD in relay basic word-write response: 0x{resp.cmd:02X}"
            )
        return
    if resolved.scheme in ("program-word", "ext-word"):
        resp = plc.send_via_relay(
            hops,
            build_ext_word_write(
                _require(resolved.no, "no"), _require(resolved.addr, "addr"), masked
            ),
        )
        if resp.cmd != 0x95:
            raise ValueError(
                f"Unexpected CMD in relay ext word-write response: 0x{resp.cmd:02X}"
            )
        return
    if resolved.scheme == "pc10-word":
        payload = b"".join(value.to_bytes(2, "little") for value in masked)
        resp = plc.send_via_relay(
            hops, build_pc10_block_write(_require(resolved.addr32, "addr32"), payload)
        )
        if resp.cmd != 0xC3:
            raise ValueError(
                f"Unexpected CMD in relay PC10 word-write response: 0x{resp.cmd:02X}"
            )
        return
    raise ValueError(f"{device} uses unsupported block scheme: {resolved.scheme}")


def _run_case(log_f: TextIO | None, name: str, fn) -> bool:
    try:
        detail = fn()
        _emit(f"{name}: {detail}", log_f)
        return True
    except Exception as exc:
        _emit(f"{name}: ERROR {type(exc).__name__}: {exc}", log_f)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Relay matrix verification for larger block counts and mixed writes"
    )
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    parser.add_argument("--local-port", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--retries", type=int, default=0)
    parser.add_argument("--hops", required=True)
    parser.add_argument("--targets", default="P1-D0000,P1-R0000,P1-S0000,U08000")
    parser.add_argument("--counts", default="8,16,32")
    parser.add_argument("--loops", type=int, default=3)
    parser.add_argument("--value", type=parse_int_auto, default=0x1000)
    parser.add_argument("--step", type=parse_int_auto, default=1)
    parser.add_argument("--loop-step", type=parse_int_auto, default=0x0100)
    parser.add_argument("--skip-write-many", action="store_true")
    parser.add_argument("--skip-mixed", action="store_true")
    parser.add_argument("--clock-loops", type=int, default=0)
    parser.add_argument("--clock-start", type=parse_datetime_iso, default=None)
    parser.add_argument("--clock-step-seconds", type=int, default=5)
    parser.add_argument("--log", default="")
    args = parser.parse_args()

    targets = parse_csv_list(args.targets)
    counts = parse_csv_ints(args.counts)
    if not targets:
        raise SystemExit("--targets must not be empty")
    if not counts or any(count < 1 for count in counts):
        raise SystemExit("--counts must contain positive integers")
    if args.loops < 1:
        raise SystemExit("--loops must be >= 1")
    if args.clock_loops < 0:
        raise SystemExit("--clock-loops must be >= 0")

    log_f = open(args.log, "w", encoding="utf-8") if args.log else None
    try:
        _emit(f"hops = {args.hops}", log_f)
        _emit(f"targets = {','.join(targets)}", log_f)
        _emit(f"counts = {','.join(str(count) for count in counts)}", log_f)
        _emit(f"loops = {args.loops}", log_f)
        _emit(f"value = 0x{args.value & 0xFFFF:04X}", log_f)
        _emit(f"step = 0x{args.step & 0xFFFF:04X}", log_f)
        _emit(f"loop_step = 0x{args.loop_step & 0xFFFF:04X}", log_f)
        _emit(f"clock_loops = {args.clock_loops}", log_f)

        with ToyopucDeviceClient(
            args.host,
            args.port,
            protocol=args.protocol,
            local_port=args.local_port,
            timeout=args.timeout,
            retries=args.retries,
        ) as plc:
            total = 0
            ok = 0

            for target in targets:
                for count in counts:

                    def _block_case(target=target, count=count) -> str:
                        passed = 0
                        for loop_index in range(args.loops):
                            expected = _pattern(
                                count, args.value, args.step, loop_index, args.loop_step
                            )
                            _relay_block_write(plc, args.hops, target, expected)
                            actual = _relay_block_read(plc, args.hops, target, count)
                            matched = actual == expected
                            if matched:
                                passed += 1
                            _emit(
                                f"block {target} count={count} loop={loop_index + 1}: "
                                f"write={_format_words(expected)} read={_format_words(actual)} ok={matched}",
                                log_f,
                            )
                        if passed != args.loops:
                            raise ValueError(f"{passed}/{args.loops} loops matched")
                        return f"{passed}/{args.loops} loops passed"

                    total += 1
                    if _run_case(log_f, f"block {target} x{count}", _block_case):
                        ok += 1

            if not args.skip_write_many:

                def _write_many_case() -> str:
                    items: dict[str, object] = {}
                    for i, target in enumerate(targets):
                        items[target] = (args.value + 0x2000 + i) & 0xFFFF
                    plc.relay_write_many(
                        args.hops, cast(Mapping[str | ResolvedDevice, object], items)
                    )
                    actual = plc.relay_read_many(args.hops, list(items.keys()))
                    normalized = [_as_int(value) for value in actual]
                    expected = [_as_int(items[target]) for target in items]
                    if normalized != expected:
                        raise ValueError(
                            f"expected={_format_words(expected)} got={_format_words(normalized)}"
                        )
                    return f"targets={','.join(items.keys())} values={_format_words(expected)}"

                total += 1
                if _run_case(log_f, "write_many words", _write_many_case):
                    ok += 1

            if not args.skip_mixed:

                def _mixed_case() -> str:
                    items: dict[str, object] = {
                        "P1-M0000": 1,
                        "P1-D0000L": 0x79,
                        "P1-D0000": 0x2468,
                        "ES0000": 0x9ABC,
                        "U08000": 0xDEF0,
                    }
                    plc.relay_write_many(
                        args.hops, cast(Mapping[str | ResolvedDevice, object], items)
                    )
                    actual = plc.relay_read_many(args.hops, list(items.keys()))
                    normalized = [_as_int(value) for value in actual]
                    expected = [_as_int(items[key]) for key in items]
                    if normalized != expected:
                        raise ValueError(f"expected={expected} got={normalized}")
                    return "items=" + ", ".join(
                        f"{key}=0x{_as_int(items[key]):X}" for key in items
                    )

                total += 1
                if _run_case(log_f, "mixed write_many", _mixed_case):
                    ok += 1

            if args.clock_loops:

                def _clock_case() -> str:
                    original = plc.relay_read_clock(args.hops).as_datetime()
                    base = args.clock_start or original
                    passed = 0
                    for loop_index in range(args.clock_loops):
                        target = base + timedelta(
                            seconds=loop_index * args.clock_step_seconds
                        )
                        plc.relay_write_clock(args.hops, target)
                        readback = plc.relay_read_clock(args.hops).as_datetime()
                        matched = abs((readback - target).total_seconds()) <= 2
                        if matched:
                            passed += 1
                        _emit(
                            f"clock loop={loop_index + 1}: target={target.isoformat(sep=' ')} "
                            f"readback={readback.isoformat(sep=' ')} ok={matched}",
                            log_f,
                        )
                    plc.relay_write_clock(args.hops, original)
                    restored = plc.relay_read_clock(args.hops).as_datetime()
                    restored_ok = abs((restored - original).total_seconds()) <= 2
                    if not restored_ok:
                        raise ValueError(
                            f"restore mismatch: original={original.isoformat(sep=' ')} restored={restored.isoformat(sep=' ')}"  # noqa: E501
                        )
                    if passed != args.clock_loops:
                        raise ValueError(
                            f"{passed}/{args.clock_loops} clock loops matched"
                        )
                    return (
                        f"{passed}/{args.clock_loops} loops passed "
                        f"restored={restored.isoformat(sep=' ')}"
                    )

                total += 1
                if _run_case(log_f, "clock long-run", _clock_case):
                    ok += 1

            _emit(f"summary = {ok}/{total} cases passed", log_f)
            return 0 if ok == total else 1
    finally:
        if log_f is not None:
            log_f.close()


if __name__ == "__main__":
    raise SystemExit(main())

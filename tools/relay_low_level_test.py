from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys
from typing import Callable, TextIO

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toyopuc import (  # noqa: E402
    ToyopucClient,
    encode_bit_address,
    encode_byte_address,
    encode_word_address,
    parse_address,
    resolve_device,
)
from toyopuc.protocol import (  # noqa: E402
    build_bit_read,
    build_bit_write,
    build_byte_read,
    build_byte_write,
    build_ext_byte_read,
    build_ext_byte_write,
    build_ext_multi_read,
    build_ext_multi_write,
    build_ext_word_read,
    build_ext_word_write,
    build_multi_byte_read,
    build_multi_byte_write,
    build_multi_word_read,
    build_multi_word_write,
    build_pc10_block_read,
    build_pc10_block_write,
    unpack_u16_le,
)


def parse_int_auto(text: str) -> int:
    return int(text, 0)


def parse_datetime_iso(text: str) -> datetime:
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO datetime: {text!r}") from exc


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


def _log_factory(log_f: TextIO | None):
    def _log(line: str) -> None:
        print(line)
        if log_f:
            log_f.write(line + "\n")
            log_f.flush()

    return _log


def _format_u16_list(values: list[int]) -> str:
    return "[" + ", ".join(f"0x{value:04X}" for value in values) + "]"


def _run_case(log: Callable[[str], None], name: str, fn: Callable[[], str]) -> bool:
    try:
        line = fn()
        log(f"{name}: {line}")
        return True
    except Exception as exc:
        log(f"{name}: ERROR {type(exc).__name__}: {exc}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Relay low-level command sweep")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    parser.add_argument("--local-port", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--retries", type=int, default=0)
    parser.add_argument("--hops", required=True)
    parser.add_argument(
        "--clock-value",
        type=parse_datetime_iso,
        default=None,
        help="optional target time for relay clock-write; original clock is restored afterward",
    )
    parser.add_argument("--log", default="")
    args = parser.parse_args()

    log_f = open(args.log, "w", encoding="utf-8") if args.log else None
    log = _log_factory(log_f)

    try:
        with ToyopucClient(
            args.host,
            args.port,
            protocol=args.protocol,
            local_port=args.local_port,
            timeout=args.timeout,
            retries=args.retries,
        ) as plc:
            log(f"hops = {args.hops}")
            log(f"protocol = {args.protocol}")

            total = 0
            ok = 0

            def run(name: str, fn: Callable[[], str]) -> None:
                nonlocal total, ok
                total += 1
                if _run_case(log, name, fn):
                    ok += 1

            def basic_bit_case() -> str:
                addr = encode_bit_address(parse_address("M0000", "bit"))
                original = plc.send_via_relay(args.hops, build_bit_read(addr)).data[0] != 0
                target = not original
                plc.send_via_relay(args.hops, build_bit_write(addr, 1 if target else 0))
                readback = plc.send_via_relay(args.hops, build_bit_read(addr)).data[0] != 0
                plc.send_via_relay(args.hops, build_bit_write(addr, 1 if original else 0))
                if readback != target:
                    raise ValueError(f"expected {int(target)} got {int(readback)}")
                return f"M0000 write={int(target)} read={int(readback)}"

            def basic_word_case() -> str:
                addr = encode_word_address(parse_address("D0000", "word"))
                original = plc.relay_read_words(args.hops, addr, 1)[0]
                target = original ^ 0xFFFF
                plc.relay_write_words(args.hops, addr, [target])
                readback = plc.relay_read_words(args.hops, addr, 1)[0]
                plc.relay_write_words(args.hops, addr, [original])
                if readback != target:
                    raise ValueError(f"expected 0x{target:04X} got 0x{readback:04X}")
                return f"D0000 write=0x{target:04X} read=0x{readback:04X}"

            def basic_byte_case() -> str:
                addr = encode_byte_address(parse_address("D0000L", "byte"))
                original = plc.send_via_relay(args.hops, build_byte_read(addr, 1)).data[0]
                target = original ^ 0xFF
                plc.send_via_relay(args.hops, build_byte_write(addr, [target]))
                readback = plc.send_via_relay(args.hops, build_byte_read(addr, 1)).data[0]
                plc.send_via_relay(args.hops, build_byte_write(addr, [original]))
                if readback != target:
                    raise ValueError(f"expected 0x{target:02X} got 0x{readback:02X}")
                return f"D0000L write=0x{target:02X} read=0x{readback:02X}"

            def multi_word_case() -> str:
                addrs = [
                    encode_word_address(parse_address("D0000", "word")),
                    encode_word_address(parse_address("D0001", "word")),
                ]
                original = unpack_u16_le(plc.send_via_relay(args.hops, build_multi_word_read(addrs)).data)
                target = [original[0] ^ 0xAAAA, original[1] ^ 0x5555]
                plc.send_via_relay(args.hops, build_multi_word_write(list(zip(addrs, target))))
                readback = unpack_u16_le(plc.send_via_relay(args.hops, build_multi_word_read(addrs)).data)
                plc.send_via_relay(args.hops, build_multi_word_write(list(zip(addrs, original))))
                if readback != target:
                    raise ValueError(f"expected={_format_u16_list(target)} got={_format_u16_list(readback)}")
                return f"D0000,D0001 values={_format_u16_list(readback)}"

            def multi_byte_case() -> str:
                addrs = [
                    encode_byte_address(parse_address("D0000L", "byte")),
                    encode_byte_address(parse_address("D0001L", "byte")),
                ]
                original = list(plc.send_via_relay(args.hops, build_multi_byte_read(addrs)).data)
                target = [original[0] ^ 0xFF, original[1] ^ 0xFF]
                plc.send_via_relay(args.hops, build_multi_byte_write(list(zip(addrs, target))))
                readback = list(plc.send_via_relay(args.hops, build_multi_byte_read(addrs)).data)
                plc.send_via_relay(args.hops, build_multi_byte_write(list(zip(addrs, original))))
                if readback != target:
                    raise ValueError(f"expected={target} got={readback}")
                return f"D0000L,D0001L values={readback}"

            def ext_word_case() -> str:
                dev = resolve_device("ES0000")
                original = unpack_u16_le(plc.send_via_relay(args.hops, build_ext_word_read(dev.no, dev.addr, 1)).data)[0]
                target = original ^ 0xFFFF
                plc.send_via_relay(args.hops, build_ext_word_write(dev.no, dev.addr, [target]))
                readback = unpack_u16_le(plc.send_via_relay(args.hops, build_ext_word_read(dev.no, dev.addr, 1)).data)[0]
                plc.send_via_relay(args.hops, build_ext_word_write(dev.no, dev.addr, [original]))
                if readback != target:
                    raise ValueError(f"expected 0x{target:04X} got 0x{readback:04X}")
                return f"ES0000 write=0x{target:04X} read=0x{readback:04X}"

            def ext_byte_case() -> str:
                dev = resolve_device("EX0000L")
                original = plc.send_via_relay(args.hops, build_ext_byte_read(dev.no, dev.addr, 1)).data[0]
                target = original ^ 0xFF
                plc.send_via_relay(args.hops, build_ext_byte_write(dev.no, dev.addr, [target]))
                readback = plc.send_via_relay(args.hops, build_ext_byte_read(dev.no, dev.addr, 1)).data[0]
                plc.send_via_relay(args.hops, build_ext_byte_write(dev.no, dev.addr, [original]))
                if readback != target:
                    raise ValueError(f"expected 0x{target:02X} got 0x{readback:02X}")
                return f"EX0000L write=0x{target:02X} read=0x{readback:02X}"

            def ext_multi_case() -> str:
                bit_dev = resolve_device("EX0000")
                byte_dev = resolve_device("EX0008L")
                word_dev = resolve_device("ES0000")
                bit_original = plc.send_via_relay(
                    args.hops,
                    build_ext_multi_read([(bit_dev.no, bit_dev.bit_no, bit_dev.addr)], [], []),
                ).data[0] & 0x01
                byte_original = plc.send_via_relay(args.hops, build_ext_byte_read(byte_dev.no, byte_dev.addr, 1)).data[0]
                word_original = unpack_u16_le(plc.send_via_relay(args.hops, build_ext_word_read(word_dev.no, word_dev.addr, 1)).data)[0]
                bit_target = 0 if bit_original else 1
                byte_target = byte_original ^ 0xFF
                word_target = word_original ^ 0xFFFF
                plc.send_via_relay(
                    args.hops,
                    build_ext_multi_write(
                        [(bit_dev.no, bit_dev.bit_no, bit_dev.addr, bit_target)],
                        [(byte_dev.no, byte_dev.addr, byte_target)],
                        [(word_dev.no, word_dev.addr, word_target)],
                    ),
                )
                data = plc.send_via_relay(
                    args.hops,
                    build_ext_multi_read(
                        [(bit_dev.no, bit_dev.bit_no, bit_dev.addr)],
                        [(byte_dev.no, byte_dev.addr)],
                        [(word_dev.no, word_dev.addr)],
                    ),
                ).data
                bits, bytes_out, words_out = _decode_ext_multi_read_data(data, 1, 1, 1)
                plc.send_via_relay(
                    args.hops,
                    build_ext_multi_write(
                        [(bit_dev.no, bit_dev.bit_no, bit_dev.addr, bit_original)],
                        [(byte_dev.no, byte_dev.addr, byte_original)],
                        [(word_dev.no, word_dev.addr, word_original)],
                    ),
                )
                if bits != [bit_target] or bytes_out != [byte_target] or words_out != [word_target]:
                    raise ValueError(
                        f"expected bit={bit_target} byte={byte_target} word=0x{word_target:04X} "
                        f"got bit={bits} byte={bytes_out} word={words_out}"
                    )
                return f"bit={bit_target} byte=0x{byte_target:02X} word=0x{word_target:04X}"

            def pc10_word_case() -> str:
                dev = resolve_device("U08000")
                original = unpack_u16_le(plc.send_via_relay(args.hops, build_pc10_block_read(dev.addr32, 2)).data)[0]
                target = original ^ 0xFFFF
                plc.send_via_relay(args.hops, build_pc10_block_write(dev.addr32, target.to_bytes(2, "little")))
                readback = unpack_u16_le(plc.send_via_relay(args.hops, build_pc10_block_read(dev.addr32, 2)).data)[0]
                plc.send_via_relay(args.hops, build_pc10_block_write(dev.addr32, original.to_bytes(2, "little")))
                if readback != target:
                    raise ValueError(f"expected 0x{target:04X} got 0x{readback:04X}")
                return f"U08000 write=0x{target:04X} read=0x{readback:04X}"

            def clock_write_case() -> str:
                if args.clock_value is None:
                    raise ValueError("--clock-value is required for clock-write")
                original = plc.relay_read_clock(args.hops)
                original_dt = original.as_datetime()
                plc.relay_write_clock(args.hops, args.clock_value)
                readback = plc.relay_read_clock(args.hops)
                readback_dt = readback.as_datetime()
                try:
                    plc.relay_write_clock(args.hops, original_dt)
                    restored_dt = plc.relay_read_clock(args.hops).as_datetime()
                except Exception:
                    restored_dt = original_dt
                delta = abs((readback_dt - args.clock_value).total_seconds())
                if delta > 2:
                    raise ValueError(f"clock readback drift too large: {delta:.1f}s")
                return (
                    f"target={args.clock_value.isoformat(sep=' ')} "
                    f"readback={readback_dt.isoformat(sep=' ')} "
                    f"restored={restored_dt.isoformat(sep=' ')}"
                )

            run(
                "cpu-status",
                lambda: (
                    lambda status: f"raw={status.raw_bytes_hex} run={status.run} alarm={status.alarm} pc10={status.pc10_mode}"
                )(plc.relay_read_cpu_status(args.hops)),
            )
            run(
                "cpu-status-a0",
                lambda: (
                    lambda status: f"raw={status.raw_bytes_hex} run={status.run} alarm={status.alarm} pc10={status.pc10_mode}"
                )(plc.relay_read_cpu_status_a0(args.hops)),
            )
            run(
                "clock-read",
                lambda: (
                    lambda clock: f"datetime={clock.as_datetime().isoformat(sep=' ')}"
                )(plc.relay_read_clock(args.hops)),
            )
            if args.clock_value is not None:
                run("clock-write", clock_write_case)

            run("basic-bit cmd20/21", basic_bit_case)
            run("basic-word cmd1c/1d", basic_word_case)
            run("basic-byte cmd1e/1f", basic_byte_case)
            run("multi-word cmd22/23", multi_word_case)
            run("multi-byte cmd24/25", multi_byte_case)
            run("ext-word cmd94/95", ext_word_case)
            run("ext-byte cmd96/97", ext_byte_case)
            run("ext-multi cmd98/99", ext_multi_case)
            run("pc10-word cmdc2/c3", pc10_word_case)

            log(f"summary = {ok}/{total} cases passed")
            return 0 if ok == total else 1
    finally:
        if log_f:
            log_f.close()


if __name__ == "__main__":
    raise SystemExit(main())

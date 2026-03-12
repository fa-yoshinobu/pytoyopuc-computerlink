#!/usr/bin/env python
import argparse
import random
from typing import Dict, List, Optional, Tuple

from toyopuc import (
    ToyopucClient,
    ToyopucError,
    encode_bit_address,
    encode_byte_address,
    encode_exno_bit_u32,
    encode_exno_byte_u32,
    encode_fr_word_addr32,
    encode_ext_no_address,
    encode_program_bit_address,
    encode_program_byte_address,
    encode_program_word_address,
    encode_word_address,
    parse_address,
    parse_prefixed_address,
)

TOLERATED_MISMATCH_COUNTS: Dict[str, int] = {}


def _hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def _pack_u32_le(value: int) -> bytes:
    return bytes(
        [
            value & 0xFF,
            (value >> 8) & 0xFF,
            (value >> 16) & 0xFF,
            (value >> 24) & 0xFF,
        ]
    )


def _range_label(area: str, start: int, end: int, width: int) -> str:
    return f"{area}{start:0{width}X}-{area}{end:0{width}X}"


def _ranges_label(area: str, ranges: List[Tuple[int, int]]) -> str:
    max_end = max(end for _, end in ranges)
    width = max(4, len(f"{max_end:X}"))
    return ", ".join(_range_label(area, start, end, width) for start, end in ranges)


def _log_frames(log_f, plc: ToyopucClient, prefix: str) -> None:
    if not log_f:
        return
    if plc.last_tx:
        log_f.write(f"{prefix} TX {_hex(plc.last_tx)}\n")
    if plc.last_rx:
        log_f.write(f"{prefix} RX {_hex(plc.last_rx)}\n")


def _record_tolerated(label: str) -> None:
    TOLERATED_MISMATCH_COUNTS[label] = TOLERATED_MISMATCH_COUNTS.get(label, 0) + 1


def _print_result(prefix: str, label: str, ok: int, total: int, log_f=None) -> None:
    if total == 0:
        line = f"{prefix} {label}: SKIP (unsupported)"
    else:
        line = f"{prefix} {label}: {ok}/{total}"
    print(line)
    if log_f:
        log_f.write(line + "\n")


def _is_tolerated_area(kind: str, area: str) -> bool:
    return (kind == "bit" and area == "V") or (kind == "word" and area == "S")


def pick_indices(rng: random.Random, start: int, end: int, count: int) -> List[int]:
    span = end - start + 1
    if count >= span:
        return list(range(start, end + 1))
    return rng.sample(range(start, end + 1), count)


def pick_indices_min_max(
    rng: random.Random, start: int, end: int, count: int
) -> List[int]:
    span = end - start + 1
    if span <= 0:
        return []
    if span == 1:
        return [start]
    if count >= span:
        return list(range(start, end + 1))
    indices = {start, end}
    target = max(count, 2)
    if target > 2:
        sample = rng.sample(range(start + 1, end), min(target - 2, span - 2))
        indices.update(sample)
    return sorted(indices)


def _pc10_multi_read_bits(plc: ToyopucClient, addrs32: List[int]) -> List[int]:
    bit_cnt = len(addrs32)
    payload = bytearray([bit_cnt & 0xFF, 0x00, 0x00, 0x00])
    for addr in addrs32:
        payload.extend(_pack_u32_le(addr))
    data = plc.pc10_multi_read(bytes(payload))
    if len(data) < 4:
        raise ValueError("PC10 multi read response too short")
    data = data[4:]
    out: List[int] = []
    if bit_cnt == 0:
        return out
    for i in range(bit_cnt):
        byte_index = i // 8
        bit_index = i % 8
        val = (data[byte_index] >> bit_index) & 0x01
        out.append(val)
    return out


def _pc10_multi_write_bits(plc: ToyopucClient, addrs32: List[int], values: List[int]) -> None:
    bit_cnt = len(addrs32)
    payload = bytearray([bit_cnt & 0xFF, 0x00, 0x00, 0x00])
    for addr in addrs32:
        payload.extend(_pack_u32_le(addr))
    # data: bits packed
    data_len = (bit_cnt + 7) // 8
    data = bytearray([0x00] * data_len)
    for i, v in enumerate(values):
        if v & 0x01:
            data[i // 8] |= 1 << (i % 8)
    payload.extend(data)
    plc.pc10_multi_write(bytes(payload))


def _pc10_multi_read_words(plc: ToyopucClient, addrs32: List[int]) -> List[int]:
    word_cnt = len(addrs32)
    payload = bytearray([0x00, 0x00, word_cnt & 0xFF, 0x00])
    for addr in addrs32:
        payload.extend(_pack_u32_le(addr))
    data = plc.pc10_multi_read(bytes(payload))
    if len(data) < 4:
        raise ValueError("PC10 multi read response too short")
    data = data[4:]
    out = []
    for i in range(word_cnt):
        base = i * 2
        out.append(data[base] | (data[base + 1] << 8))
    return out


def _pc10_multi_write_words(plc: ToyopucClient, addrs32: List[int], values: List[int]) -> None:
    word_cnt = len(addrs32)
    payload = bytearray([0x00, 0x00, word_cnt & 0xFF, 0x00])
    for addr in addrs32:
        payload.extend(_pack_u32_le(addr))
    for value in values:
        payload.extend(_pack_u16_le(value))
    plc.pc10_multi_write(bytes(payload))


def _verify_bit_sequence(
    write_fn,
    read_fn,
    log_fn,
    mismatch_prefix: str,
    log_f,
    tolerated_label: str | None = None,
) -> Tuple[int, int]:
    ok = 0
    total = 0
    for value in (0, 1):
        write_fn(value)
        log_fn(f"write {value}")
        read_back = 1 if read_fn() else 0
        log_fn(f"read {value}")
        total += 1
        if read_back == value:
            ok += 1
        elif tolerated_label is not None:
            _record_tolerated(tolerated_label)
            ok += 1
            if log_f:
                log_f.write(f"{mismatch_prefix} exp={value} got={read_back} (tolerated)\n")
        elif log_f:
            log_f.write(f"{mismatch_prefix} exp={value} got={read_back}\n")
    return ok, total


def _verify_word_sequence(
    write_fn,
    read_fn,
    log_fn,
    mismatch_prefix: str,
    rng: random.Random,
    log_f,
    tolerated_label: str | None = None,
) -> Tuple[int, int]:
    ok = 0
    total = 0
    first_value = rng.randint(0, 0xFFFF)
    for label, value in (("write1", first_value), ("write2", first_value ^ 0xFFFF)):
        write_fn(value)
        log_fn(f"{label}")
        read_back = read_fn()
        log_fn(f"{label} read")
        total += 1
        if read_back == value:
            ok += 1
        elif tolerated_label is not None:
            _record_tolerated(tolerated_label)
            ok += 1
            if log_f:
                log_f.write(
                    f"{mismatch_prefix} exp=0x{value:04X} got=0x{read_back:04X} (tolerated)\n"
                )
        elif log_f:
            log_f.write(f"{mismatch_prefix} exp=0x{value:04X} got=0x{read_back:04X}\n")
    return ok, total


def _verify_word_block_sequence(
    write_fn,
    read_fn,
    log_fn,
    mismatch_prefix: str,
    count: int,
    rng: random.Random,
    log_f,
) -> Tuple[int, int]:
    values1 = [rng.randint(0, 0xFFFF) for _ in range(count)]
    write_fn(values1)
    log_fn("write1")
    read_back1 = list(read_fn())
    log_fn("write1 read")
    if read_back1 != values1:
        if log_f:
            log_f.write(f"{mismatch_prefix} write1 mismatch\n")
        return 0, 1

    values2 = [value ^ 0xFFFF for value in values1]
    write_fn(values2)
    log_fn("write2")
    read_back2 = list(read_fn())
    log_fn("write2 read")
    if read_back2 != values2:
        if log_f:
            log_f.write(f"{mismatch_prefix} write2 mismatch\n")
        return 0, 1
    return 1, 1


def _verify_byte_block_sequence(
    write_fn,
    read_fn,
    log_fn,
    mismatch_prefix: str,
    count: int,
    rng: random.Random,
    log_f,
) -> Tuple[int, int]:
    values1 = bytes(rng.getrandbits(8) for _ in range(count))
    write_fn(values1)
    log_fn("write1")
    read_back1 = bytes(read_fn())
    log_fn("write1 read")
    if read_back1 != values1:
        if log_f:
            log_f.write(f"{mismatch_prefix} write1 mismatch\n")
        return 0, 1

    values2 = bytes(value ^ 0xFF for value in values1)
    write_fn(values2)
    log_fn("write2")
    read_back2 = bytes(read_fn())
    log_fn("write2 read")
    if read_back2 != values2:
        if log_f:
            log_f.write(f"{mismatch_prefix} write2 mismatch\n")
        return 0, 1
    return 1, 1


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


def _pack_u16_le(value: int) -> bytes:
    return bytes([value & 0xFF, (value >> 8) & 0xFF])


def _unpack_u16_le(data: bytes) -> int:
    if len(data) != 2:
        raise ValueError("word data must be 2 bytes")
    return data[0] | (data[1] << 8)


def _unpack_words_block(data: bytes) -> List[int]:
    if len(data) % 2 != 0:
        raise ValueError("word block data must be even length")
    return [data[i] | (data[i + 1] << 8) for i in range(0, len(data), 2)]


def _test_bit_indices(
    plc: ToyopucClient,
    area: str,
    indices: List[int],
    rng: random.Random,
    log_f=None,
    skip_errors: bool = False,
) -> Tuple[int, int]:
    ok = 0
    total = 0
    for idx in indices:
        try:
            addr = encode_bit_address(parse_address(f"{area}{idx:04X}", "bit"))
            o, t = _verify_bit_sequence(
                lambda value: plc.write_bit(addr, bool(value)),
                lambda: plc.read_bit(addr),
                lambda suffix: _log_frames(log_f, plc, f"[BIT] {area}{idx:04X} {suffix}"),
                f"[BIT] MISMATCH {area}{idx:04X}",
                log_f,
                tolerated_label=f"BIT:{area}" if _is_tolerated_area("bit", area) else None,
            )
            ok += o
            total += t
        except ToyopucError as e:
            if not skip_errors:
                raise
            if log_f:
                log_f.write(f"[BIT] ERROR {area}{idx:04X} {e}\n")
    return ok, total


def _test_word_indices(
    plc: ToyopucClient,
    area: str,
    indices: List[int],
    rng: random.Random,
    log_f=None,
    skip_errors: bool = False,
) -> Tuple[int, int]:
    ok = 0
    total = 0
    for idx in indices:
        try:
            addr = encode_word_address(parse_address(f"{area}{idx:04X}", "word"))
            o, t = _verify_word_sequence(
                lambda value: plc.write_words(addr, [value]),
                lambda: plc.read_words(addr, 1)[0],
                lambda suffix: _log_frames(log_f, plc, f"[WORD] {area}{idx:04X} {suffix}"),
                f"[WORD] MISMATCH {area}{idx:04X}",
                rng,
                log_f,
                tolerated_label=f"WORD:{area}" if _is_tolerated_area("word", area) else None,
            )
            ok += o
            total += t
        except ToyopucError as e:
            if not skip_errors:
                raise
            if log_f:
                log_f.write(f"[WORD] ERROR {area}{idx:04X} {e}\n")
    return ok, total


def _test_ext_word_indices(
    plc: ToyopucClient,
    area: str,
    indices: List[int],
    rng: random.Random,
    log_f=None,
    skip_errors: bool = False,
    encoder=None,
) -> Tuple[int, int]:
    ok = 0
    total = 0
    if encoder is None:
        def encoder(a: str, i: int) -> Tuple[int, int]:
            ext = encode_ext_no_address(a, i, "word")
            return ext.no, ext.addr
    for idx in indices:
        try:
            no, addr = encoder(area, idx)
            o, t = _verify_word_sequence(
                lambda value: plc.write_ext_words(no, addr, [value]),
                lambda: plc.read_ext_words(no, addr, 1)[0],
                lambda suffix: _log_frames(log_f, plc, f"[EXT WORD] {area} {idx:06X} {suffix}"),
                f"[EXT WORD] MISMATCH {area} {idx:06X}",
                rng,
                log_f,
                tolerated_label=f"WORD:{area}" if _is_tolerated_area("word", area) else None,
            )
            ok += o
            total += t
        except (ToyopucError, ValueError) as e:
            if not skip_errors:
                raise
            if log_f:
                log_f.write(f"[EXT WORD] ERROR {area} {idx:06X} {e}\n")
    return ok, total


def run_bit_area_ranges(
    plc: ToyopucClient,
    area: str,
    ranges: List[Tuple[int, int]],
    count: int,
    rng: random.Random,
    log_f=None,
    skip_errors: bool = False,
) -> Tuple[int, int]:
    ok = 0
    total = 0
    for start, end in ranges:
        indices = pick_indices_min_max(rng, start, end, count)
        o, t = _test_bit_indices(plc, area, indices, rng, log_f, skip_errors=skip_errors)
        ok += o
        total += t
    return ok, total


def run_word_area_ranges(
    plc: ToyopucClient,
    area: str,
    ranges: List[Tuple[int, int]],
    count: int,
    rng: random.Random,
    log_f=None,
    skip_errors: bool = False,
) -> Tuple[int, int]:
    ok = 0
    total = 0
    for start, end in ranges:
        indices = pick_indices_min_max(rng, start, end, count)
        o, t = _test_word_indices(plc, area, indices, rng, log_f, skip_errors=skip_errors)
        ok += o
        total += t
    return ok, total


def run_ext_word_area_ranges(
    plc: ToyopucClient,
    area: str,
    ranges: List[Tuple[int, int]],
    count: int,
    rng: random.Random,
    log_f=None,
    skip_errors: bool = False,
    encoder=None,
) -> Tuple[int, int]:
    ok = 0
    total = 0
    for start, end in ranges:
        indices = pick_indices_min_max(rng, start, end, count)
        o, t = _test_ext_word_indices(
            plc, area, indices, rng, log_f, skip_errors=skip_errors, encoder=encoder
        )
        ok += o
        total += t
    return ok, total


def run_word_area(
    plc: ToyopucClient,
    area: str,
    start: int,
    end: int,
    count: int,
    rng: random.Random,
    log_f=None,
    skip_errors: bool = False,
) -> Tuple[int, int]:
    return _test_word_indices(
        plc,
        area,
        pick_indices(rng, start, end, count),
        rng,
        log_f,
        skip_errors=skip_errors,
    )


def run_byte_area(
    plc: ToyopucClient,
    area: str,
    start: int,
    end: int,
    count: int,
    rng: random.Random,
    log_f=None,
    skip_errors: bool = False,
) -> Tuple[int, int]:
    ok = 0
    total = 0
    for idx in pick_indices(rng, start, end, count):
        try:
            addr = encode_byte_address(parse_address(f"{area}{idx:04X}L", "byte"))
            value = rng.randint(0, 0xFF)
            plc.write_bytes(addr, [value])
            _log_frames(log_f, plc, f"[BYTE] {area}{idx:04X}L write")
            read_back = plc.read_bytes(addr, 1)[0]
            _log_frames(log_f, plc, f"[BYTE] {area}{idx:04X}L read")
            total += 1
            if read_back == value:
                ok += 1
            elif log_f:
                log_f.write(
                    f"[BYTE] MISMATCH {area}{idx:04X}L exp=0x{value:02X} got=0x{read_back:02X}\n"
                )
        except ToyopucError as e:
            if not skip_errors:
                raise
            if log_f:
                log_f.write(f"[BYTE] ERROR {area}{idx:04X}L {e}\n")
    return ok, total


def run_bit_area(
    plc: ToyopucClient,
    area: str,
    start: int,
    end: int,
    count: int,
    rng: random.Random,
    log_f=None,
    skip_errors: bool = False,
) -> Tuple[int, int]:
    return _test_bit_indices(
        plc,
        area,
        pick_indices(rng, start, end, count),
        rng,
        log_f,
        skip_errors=skip_errors,
    )


def run_ext_word_area(
    plc: ToyopucClient,
    area: str,
    start: int,
    end: int,
    count: int,
    rng: random.Random,
    log_f=None,
    skip_errors: bool = False,
) -> Tuple[int, int]:
    return _test_ext_word_indices(
        plc,
        area,
        pick_indices(rng, start, end, count),
        rng,
        log_f,
        skip_errors=skip_errors,
    )


def run_ext_byte_area(
    plc: ToyopucClient,
    area: str,
    start: int,
    end: int,
    count: int,
    rng: random.Random,
    log_f=None,
    skip_errors: bool = False,
) -> Tuple[int, int]:
    ok = 0
    total = 0
    for idx in pick_indices(rng, start, end, count):
        try:
            ext = encode_ext_no_address(area, idx, "byte")
            value = rng.randint(0, 0xFF)
            plc.write_ext_bytes(ext.no, ext.addr, [value])
            _log_frames(log_f, plc, f"[EXT BYTE] {area} {idx:06X} write")
            read_back = plc.read_ext_bytes(ext.no, ext.addr, 1)[0]
            _log_frames(log_f, plc, f"[EXT BYTE] {area} {idx:06X} read")
            total += 1
            if read_back == value:
                ok += 1
            elif log_f:
                log_f.write(
                    f"[EXT BYTE] MISMATCH {area} {idx:06X} exp=0x{value:02X} got=0x{read_back:02X}\n"
                )
        except (ToyopucError, ValueError) as e:
            if not skip_errors:
                raise
            if log_f:
                log_f.write(f"[EXT BYTE] ERROR {area} {idx:06X} {e}\n")
    return ok, total


def run_max_block_lengths(
    plc: ToyopucClient,
    rng: random.Random,
    log_f=None,
    skip_errors: bool = False,
    pc10_word_count: int = 0x200,
) -> List[Tuple[str, int, int]]:
    results: List[Tuple[str, int, int]] = []

    def run(label: str, fn) -> None:
        try:
            ok, total = fn()
        except (ToyopucError, ValueError) as e:
            if not skip_errors:
                raise
            if log_f:
                log_f.write(f"[BLOCK] ERROR {label} {e}\n")
            results.append((f"{label} SKIP", 0, 0))
            return
        results.append((label, ok, total))

    run(
        "D0000-D01FF words(x0200)",
        lambda: _verify_word_block_sequence(
            lambda values: plc.write_words(encode_word_address(parse_address("D0000", "word")), values),
            lambda: plc.read_words(encode_word_address(parse_address("D0000", "word")), 0x200),
            lambda suffix: _log_frames(log_f, plc, f"[BLOCK WORD] D0000 x0200 {suffix}"),
            "[BLOCK WORD] MISMATCH D0000 x0200",
            0x200,
            rng,
            log_f,
        ),
    )
    run(
        "D0000L-D01FFH bytes(x0400)",
        lambda: _verify_byte_block_sequence(
            lambda values: plc.write_bytes(encode_byte_address(parse_address("D0000L", "byte")), values),
            lambda: plc.read_bytes(encode_byte_address(parse_address("D0000L", "byte")), 0x400),
            lambda suffix: _log_frames(log_f, plc, f"[BLOCK BYTE] D0000L x0400 {suffix}"),
            "[BLOCK BYTE] MISMATCH D0000L x0400",
            0x400,
            rng,
            log_f,
        ),
    )
    run(
        "U00000-U001FF words(x0200)",
        lambda: _verify_word_block_sequence(
            lambda values: plc.write_ext_words(0x08, 0x0000, values),
            lambda: plc.read_ext_words(0x08, 0x0000, 0x200),
            lambda suffix: _log_frames(log_f, plc, f"[BLOCK EXT WORD] U00000 x0200 {suffix}"),
            "[BLOCK EXT WORD] MISMATCH U00000 x0200",
            0x200,
            rng,
            log_f,
        ),
    )
    run(
        "U00000-U001FF bytes(x0400)",
        lambda: _verify_byte_block_sequence(
            lambda values: plc.write_ext_bytes(0x08, 0x0000, values),
            lambda: plc.read_ext_bytes(0x08, 0x0000, 0x400),
            lambda suffix: _log_frames(log_f, plc, f"[BLOCK EXT BYTE] U00000 x0400 {suffix}"),
            "[BLOCK EXT BYTE] MISMATCH U00000 x0400",
            0x400,
            rng,
            log_f,
        ),
    )
    run(
        f"U08000-U{0x08000 + pc10_word_count - 1:05X} words(x{pc10_word_count:04X}) via PC10",
        lambda: _verify_word_block_sequence(
            lambda values: plc.pc10_block_write(_pc10_u_word_addr32(0x08000), b"".join(_pack_u16_le(v) for v in values)),
            lambda: _unpack_words_block(plc.pc10_block_read(_pc10_u_word_addr32(0x08000), pc10_word_count * 2)),
            lambda suffix: _log_frames(log_f, plc, f"[BLOCK PC10 WORD] U08000 x{pc10_word_count:04X} {suffix}"),
            f"[BLOCK PC10 WORD] MISMATCH U08000 x{pc10_word_count:04X}",
            pc10_word_count,
            rng,
            log_f,
        ),
    )
    run(
        f"EB00000-EB{pc10_word_count - 1:05X} words(x{pc10_word_count:04X}) via PC10",
        lambda: _verify_word_block_sequence(
            lambda values: plc.pc10_block_write(_pc10_eb_word_addr32(0x00000), b"".join(_pack_u16_le(v) for v in values)),
            lambda: _unpack_words_block(plc.pc10_block_read(_pc10_eb_word_addr32(0x00000), pc10_word_count * 2)),
            lambda suffix: _log_frames(log_f, plc, f"[BLOCK PC10 WORD] EB00000 x{pc10_word_count:04X} {suffix}"),
            f"[BLOCK PC10 WORD] MISMATCH EB00000 x{pc10_word_count:04X}",
            pc10_word_count,
            rng,
            log_f,
        ),
    )
    return results


def _verify_ext_multi_case(
    plc: ToyopucClient,
    label: str,
    bit_point: Tuple[int, int, int],
    byte_point: Tuple[int, int],
    word_point: Tuple[int, int],
    rng: random.Random,
    log_f=None,
) -> Tuple[int, int]:
    bit_no, bit_pos, bit_addr = bit_point
    byte_no, byte_addr = byte_point
    word_no, word_addr = word_point

    byte_value1 = rng.randint(0, 0xFF)
    word_value1 = rng.randint(0, 0xFFFF)
    plc.write_ext_multi(
        [(bit_no, bit_pos, bit_addr, 0)],
        [(byte_no, byte_addr, byte_value1)],
        [(word_no, word_addr, word_value1)],
    )
    _log_frames(log_f, plc, f"[EXT MULTI] {label} write1")
    data1 = plc.read_ext_multi(
        [(bit_no, bit_pos, bit_addr)],
        [(byte_no, byte_addr)],
        [(word_no, word_addr)],
    )
    _log_frames(log_f, plc, f"[EXT MULTI] {label} read1")
    bits1, bytes1, words1 = _decode_ext_multi_read_data(data1, 1, 1, 1)
    if bits1 != [0] or bytes1 != [byte_value1] or words1 != [word_value1]:
        if log_f:
            log_f.write(
                f"[EXT MULTI] MISMATCH {label} write1 bit={bits1} byte={bytes1} word={words1}\n"
            )
        return 0, 1

    byte_value2 = byte_value1 ^ 0xFF
    word_value2 = word_value1 ^ 0xFFFF
    plc.write_ext_multi(
        [(bit_no, bit_pos, bit_addr, 1)],
        [(byte_no, byte_addr, byte_value2)],
        [(word_no, word_addr, word_value2)],
    )
    _log_frames(log_f, plc, f"[EXT MULTI] {label} write2")
    data2 = plc.read_ext_multi(
        [(bit_no, bit_pos, bit_addr)],
        [(byte_no, byte_addr)],
        [(word_no, word_addr)],
    )
    _log_frames(log_f, plc, f"[EXT MULTI] {label} read2")
    bits2, bytes2, words2 = _decode_ext_multi_read_data(data2, 1, 1, 1)
    if bits2 != [1] or bytes2 != [byte_value2] or words2 != [word_value2]:
        if log_f:
            log_f.write(
                f"[EXT MULTI] MISMATCH {label} write2 bit={bits2} byte={bytes2} word={words2}\n"
            )
        return 0, 1
    return 1, 1


def _verify_ext_multi_pair_case(
    plc: ToyopucClient,
    label: str,
    bit_point: Tuple[int, int, int] | None,
    byte_point: Tuple[int, int] | None,
    word_point: Tuple[int, int] | None,
    rng: random.Random,
    log_f=None,
) -> Tuple[int, int]:
    bit_points_w = []
    bit_points_r = []
    byte_points_w = []
    byte_points_r = []
    word_points_w = []
    word_points_r = []
    expected1_bits = []
    expected1_bytes = []
    expected1_words = []
    expected2_bits = []
    expected2_bytes = []
    expected2_words = []

    if bit_point is not None:
        bit_no, bit_pos, bit_addr = bit_point
        bit_points_w.append((bit_no, bit_pos, bit_addr, 0))
        bit_points_r.append((bit_no, bit_pos, bit_addr))
        expected1_bits.append(0)
        expected2_bits.append(1)
    if byte_point is not None:
        byte_no, byte_addr = byte_point
        byte_value1 = rng.randint(0, 0xFF)
        byte_points_w.append((byte_no, byte_addr, byte_value1))
        byte_points_r.append((byte_no, byte_addr))
        expected1_bytes.append(byte_value1)
        expected2_bytes.append(byte_value1 ^ 0xFF)
    if word_point is not None:
        word_no, word_addr = word_point
        word_value1 = rng.randint(0, 0xFFFF)
        word_points_w.append((word_no, word_addr, word_value1))
        word_points_r.append((word_no, word_addr))
        expected1_words.append(word_value1)
        expected2_words.append(word_value1 ^ 0xFFFF)

    plc.write_ext_multi(bit_points_w, byte_points_w, word_points_w)
    _log_frames(log_f, plc, f"[EXT MULTI] {label} write1")
    data1 = plc.read_ext_multi(bit_points_r, byte_points_r, word_points_r)
    _log_frames(log_f, plc, f"[EXT MULTI] {label} read1")
    bits1, bytes1, words1 = _decode_ext_multi_read_data(
        data1, len(bit_points_r), len(byte_points_r), len(word_points_r)
    )
    if bits1 != expected1_bits or bytes1 != expected1_bytes or words1 != expected1_words:
        if log_f:
            log_f.write(
                f"[EXT MULTI] MISMATCH {label} write1 bit={bits1} byte={bytes1} word={words1}\n"
            )
        return 0, 1

    if bit_point is not None:
        bit_no, bit_pos, bit_addr = bit_point
        bit_points_w = [(bit_no, bit_pos, bit_addr, 1)]
    if byte_point is not None:
        byte_no, byte_addr = byte_point
        byte_points_w = [(byte_no, byte_addr, expected2_bytes[0])]
    if word_point is not None:
        word_no, word_addr = word_point
        word_points_w = [(word_no, word_addr, expected2_words[0])]

    plc.write_ext_multi(bit_points_w, byte_points_w, word_points_w)
    _log_frames(log_f, plc, f"[EXT MULTI] {label} write2")
    data2 = plc.read_ext_multi(bit_points_r, byte_points_r, word_points_r)
    _log_frames(log_f, plc, f"[EXT MULTI] {label} read2")
    bits2, bytes2, words2 = _decode_ext_multi_read_data(
        data2, len(bit_points_r), len(byte_points_r), len(word_points_r)
    )
    if bits2 != expected2_bits or bytes2 != expected2_bytes or words2 != expected2_words:
        if log_f:
            log_f.write(
                f"[EXT MULTI] MISMATCH {label} write2 bit={bits2} byte={bytes2} word={words2}\n"
            )
        return 0, 1
    return 1, 1


def run_ext_multi_mixed(
    plc: ToyopucClient,
    rng: random.Random,
    log_f=None,
    skip_errors: bool = False,
) -> List[Tuple[str, int, int]]:
    results: List[Tuple[str, int, int]] = []

    cases: List[Tuple[str, Tuple[int, int, int], Tuple[int, int], Tuple[int, int]]] = []
    cases.append(
        (
            "EX0000 + U0000(byte) + EN0000(word)",
            _ext_bit_point("EX", 0x0000),
            (encode_ext_no_address("U", 0x0000, "byte").no, encode_ext_no_address("U", 0x0000, "byte").addr),
            (encode_ext_no_address("EN", 0x0000, "word").no, encode_ext_no_address("EN", 0x0000, "word").addr),
        )
    )
    cases.append(
        (
            "GX0000 + GX/GY byte(0001) + ES0000(word)",
            _ext_bit_point("GX", 0x0000),
            (encode_ext_no_address("GXY", 0x0001, "byte").no, encode_ext_no_address("GXY", 0x0001, "byte").addr),
            (encode_ext_no_address("ES", 0x0000, "word").no, encode_ext_no_address("ES", 0x0000, "word").addr),
        )
    )
    ex_no, parsed_byte = parse_prefixed_address("P1-D0000L", "byte")
    _, parsed_word = parse_prefixed_address("P1-D0000", "word")
    cases.append(
        (
            "P1-M0000 + P1-D0000(byte) + P1-D0000(word)",
            _prefixed_bit_ext_addr("P1", "M", 0x0000),
            (0x01, encode_program_byte_address(parsed_byte)),
            (0x01, encode_program_word_address(parsed_word)),
        )
    )

    for label, bit_point, byte_point, word_point in cases:
        try:
            ok, total = _verify_ext_multi_case(
                plc, label, bit_point, byte_point, word_point, rng, log_f
            )
        except (ToyopucError, ValueError) as e:
            if not skip_errors:
                raise
            if log_f:
                log_f.write(f"[EXT MULTI] ERROR {label} {e}\n")
            results.append((f"{label} SKIP", 0, 0))
            continue
        results.append((label, ok, total))

    split_cases: List[
        Tuple[
            str,
            Optional[Tuple[int, int, int]],
            Optional[Tuple[int, int]],
            Optional[Tuple[int, int]],
        ]
    ] = [
        (
            "GX0000 + GX/GY byte(0000)",
            _ext_bit_point("GX", 0x0000),
            (encode_ext_no_address("GXY", 0x0000, "byte").no, encode_ext_no_address("GXY", 0x0000, "byte").addr),
            None,
        ),
        (
            "GX/GY byte(0000) + ES0000(word)",
            None,
            (encode_ext_no_address("GXY", 0x0000, "byte").no, encode_ext_no_address("GXY", 0x0000, "byte").addr),
            (encode_ext_no_address("ES", 0x0000, "word").no, encode_ext_no_address("ES", 0x0000, "word").addr),
        ),
        (
            "GX0000 + ES0000(word)",
            _ext_bit_point("GX", 0x0000),
            None,
            (encode_ext_no_address("ES", 0x0000, "word").no, encode_ext_no_address("ES", 0x0000, "word").addr),
        ),
    ]
    for label_split, bit_point_opt, byte_point_opt, word_point_opt in split_cases:
        try:
            ok, total = _verify_ext_multi_pair_case(
                plc, label_split, bit_point_opt, byte_point_opt, word_point_opt, rng, log_f
            )
        except (ToyopucError, ValueError) as e:
            if not skip_errors:
                raise
            if log_f:
                log_f.write(f"[EXT MULTI] ERROR {label_split} {e}\n")
            results.append((f"{label_split} SKIP", 0, 0))
            continue
        results.append((label_split, ok, total))
    return results


def run_boundary_values(
    plc: ToyopucClient,
    rng: random.Random,
    log_f=None,
    skip_errors: bool = False,
) -> List[Tuple[str, int, int]]:
    results: List[Tuple[str, int, int]] = []

    def run(label: str, fn) -> None:
        try:
            ok, total = fn()
        except (ToyopucError, ValueError) as e:
            if not skip_errors:
                raise
            if log_f:
                log_f.write(f"[BOUNDARY] ERROR {label} {e}\n")
            results.append((f"{label} SKIP", 0, 0))
            return
        results.append((label, ok, total))

    run(
        "U07FFE-U08001 transition",
        lambda: run_ext_word_area_ranges(
            plc,
            "U",
            [(0x07FFE, 0x08001)],
            4,
            rng,
            log_f,
            skip_errors=skip_errors,
            encoder=_encode_pc10g_u,
        ),
    )
    run(
        "EB3FFFE-EB40001 transition",
        lambda: run_ext_word_area_ranges(
            plc,
            "EB",
            [(0x3FFFE, 0x40001)],
            4,
            rng,
            log_f,
            skip_errors=skip_errors,
        ),
    )
    run(
        "L07FE-L1001 transition",
        lambda: (
            lambda a, b: (a[0] + b[0], a[1] + b[1])
        )(
            _test_bit_indices(plc, "L", [0x07FE, 0x07FF], rng, log_f, skip_errors=skip_errors),
            _test_pc10_bit_area_ranges_with_builder(
                plc,
                "L",
                [(0x1000, 0x1001)],
                2,
                rng,
                lambda idx: _pc10_base_bit_addr32("L", idx),
                log_f,
                skip_errors=skip_errors,
            ),
        ),
    )
    run(
        "M07FE-M1001 transition",
        lambda: (
            lambda a, b: (a[0] + b[0], a[1] + b[1])
        )(
            _test_bit_indices(plc, "M", [0x07FE, 0x07FF], rng, log_f, skip_errors=skip_errors),
            _test_pc10_bit_area_ranges_with_builder(
                plc,
                "M",
                [(0x1000, 0x1001)],
                2,
                rng,
                lambda idx: _pc10_base_bit_addr32("M", idx),
                log_f,
                skip_errors=skip_errors,
            ),
        ),
    )
    return results


def _encode_pc10g_u(area: str, index: int) -> Tuple[int, int]:
    if area != "U":
        raise ValueError("pc10g encoder only supports U")
    if index < 0x00000 or index > 0x1FFFF:
        raise ValueError("U index out of range (0x00000-0x1FFFF)")
    block = index // 0x8000
    no = 0x03 + block
    addr = index % 0x8000
    return no, addr


def _test_pc10_bit_area_ranges(
    plc: ToyopucClient,
    area: str,
    ex_no: int,
    ranges: List[Tuple[int, int]],
    count: int,
    rng: random.Random,
    log_f=None,
    skip_errors: bool = False,
) -> Tuple[int, int]:
    ok = 0
    total = 0
    for start, end in ranges:
        indices = pick_indices_min_max(rng, start, end, count)
        for idx in indices:
            try:
                addr32 = encode_exno_bit_u32(ex_no, idx)
                o, t = _verify_bit_sequence(
                    lambda value: _pc10_multi_write_bits(plc, [addr32], [value]),
                    lambda: bool(_pc10_multi_read_bits(plc, [addr32])[0]),
                    lambda suffix: _log_frames(log_f, plc, f"[PC10 BIT] {area}{idx:04X} {suffix}"),
                    f"[PC10 BIT] MISMATCH {area}{idx:04X}",
                    log_f,
                    tolerated_label=f"BIT:{area}" if _is_tolerated_area("bit", area) else None,
                )
                ok += o
                total += t
            except ToyopucError as e:
                if not skip_errors:
                    raise
                if log_f:
                    log_f.write(f"[PC10 BIT] ERROR {area}{idx:04X} {e}\n")
    return ok, total


def _test_pc10_bit_area_ranges_with_builder(
    plc: ToyopucClient,
    label: str,
    ranges: List[Tuple[int, int]],
    count: int,
    rng: random.Random,
    addr_builder,
    log_f=None,
    skip_errors: bool = False,
) -> Tuple[int, int]:
    ok = 0
    total = 0
    for start, end in ranges:
        indices = pick_indices_min_max(rng, start, end, count)
        for idx in indices:
            try:
                addr32 = addr_builder(idx)
                o, t = _verify_bit_sequence(
                    lambda value: _pc10_multi_write_bits(plc, [addr32], [value]),
                    lambda: bool(_pc10_multi_read_bits(plc, [addr32])[0]),
                    lambda suffix: _log_frames(log_f, plc, f"[PC10 BIT] {label}{idx:04X} {suffix}"),
                    f"[PC10 BIT] MISMATCH {label}{idx:04X}",
                    log_f,
                    tolerated_label=f"BIT:{label}" if _is_tolerated_area("bit", label) else None,
                )
                ok += o
                total += t
            except (ToyopucError, ValueError) as e:
                if not skip_errors:
                    raise
                if log_f:
                    log_f.write(f"[PC10 BIT] ERROR {label}{idx:04X} {e}\n")
    return ok, total


def _test_ext_bit_area_ranges(
    plc: ToyopucClient,
    area: str,
    ranges: List[Tuple[int, int]],
    count: int,
    rng: random.Random,
    log_f=None,
    skip_errors: bool = False,
) -> Tuple[int, int]:
    ok = 0
    total = 0
    for start, end in ranges:
        indices = pick_indices_min_max(rng, start, end, count)
        for idx in indices:
            try:
                no, bit_no, addr = _ext_bit_point(area, idx)
                o, t = _verify_bit_sequence(
                    lambda value: _ext_multi_write_bit(plc, no, bit_no, addr, value),
                    lambda: bool(_ext_multi_read_bit(plc, no, bit_no, addr)),
                    lambda suffix: _log_frames(log_f, plc, f"[EXT BIT] {area}{idx:04X} {suffix}"),
                    f"[EXT BIT] MISMATCH {area}{idx:04X}",
                    log_f,
                    tolerated_label=f"BIT:{area}" if _is_tolerated_area("bit", area) else None,
                )
                ok += o
                total += t
            except (ToyopucError, ValueError) as e:
                if not skip_errors:
                    raise
                if log_f:
                    log_f.write(f"[EXT BIT] ERROR {area}{idx:04X} {e}\n")
    return ok, total


def _test_pc10_word_area_ranges_with_builder(
    plc: ToyopucClient,
    label: str,
    ranges: List[Tuple[int, int]],
    count: int,
    rng: random.Random,
    addr_builder,
    log_f=None,
    skip_errors: bool = False,
) -> Tuple[int, int]:
    ok = 0
    total = 0
    for start, end in ranges:
        indices = pick_indices_min_max(rng, start, end, count)
        for idx in indices:
            try:
                addr32 = addr_builder(idx)
                o, t = _verify_word_sequence(
                    lambda value: _pc10_multi_write_words(plc, [addr32], [value]),
                    lambda: _pc10_multi_read_words(plc, [addr32])[0],
                    lambda suffix: _log_frames(log_f, plc, f"[PC10 WORD] {label}{idx:05X} {suffix}"),
                    f"[PC10 WORD] MISMATCH {label}{idx:05X}",
                    rng,
                    log_f,
                    tolerated_label=f"WORD:{label}" if _is_tolerated_area("word", label) else None,
                )
                ok += o
                total += t
            except (ToyopucError, ValueError) as e:
                if not skip_errors:
                    raise
                if log_f:
                    log_f.write(f"[PC10 WORD] ERROR {label}{idx:05X} {e}\n")
    return ok, total


def _pc10_word_addr32(prefix: str, area: str, index: int) -> int:
    ex_no, parsed = parse_prefixed_address(f"{prefix}-{area}{index:04X}L", "byte")
    return encode_exno_byte_u32(ex_no, encode_byte_address(parsed))


def _pc10_bit_addr32(prefix: str, area: str, index: int) -> int:
    ex_no, parsed = parse_prefixed_address(f"{prefix}-{area}{index:04X}", "bit")
    return encode_exno_bit_u32(ex_no, encode_bit_address(parsed))


def _pc10_write_word(plc: ToyopucClient, addr32: int, value: int) -> None:
    plc.pc10_block_write(addr32, _pack_u16_le(value))


def _pc10_read_word(plc: ToyopucClient, addr32: int) -> int:
    return _unpack_u16_le(plc.pc10_block_read(addr32, 2))


def _pc10_base_bit_addr32(area: str, index: int) -> int:
    parsed = parse_address(f"{area}{index:04X}", "bit")
    return encode_bit_address(parsed)


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


def _program_no(prefix: str) -> int:
    mapping = {"P1": 0x01, "P2": 0x02, "P3": 0x03}
    try:
        return mapping[prefix.upper()]
    except KeyError as exc:
        raise ValueError(f"Unsupported prefix: {prefix}") from exc


def _prefixed_word_ext_addr(prefix: str, area: str, index: int) -> Tuple[int, int]:
    program_no = _program_no(prefix)
    parsed = parse_address(f"{area}{index:04X}", "word")
    return program_no, encode_program_word_address(parsed)


def _prefixed_bit_ext_addr(prefix: str, area: str, index: int) -> Tuple[int, int, int]:
    program_no = _program_no(prefix)
    parsed = parse_address(f"{area}{index:04X}", "bit")
    bit_no, addr = encode_program_bit_address(parsed)
    return program_no, bit_no, addr


def _ext_multi_read_bit(plc: ToyopucClient, no: int, bit_no: int, addr: int) -> int:
    data = plc.read_ext_multi([(no, bit_no, addr)], [], [])
    return data[0] & 0x01


def _ext_multi_write_bit(plc: ToyopucClient, no: int, bit_no: int, addr: int, value: int) -> None:
    plc.write_ext_multi([(no, bit_no, addr, value & 0x01)], [], [])


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


def _ext_bit_point(area: str, index: int) -> Tuple[int, int, int]:
    try:
        no, byte_base = _EXT_BIT_AREA_SPECS[area]
    except KeyError as exc:
        raise ValueError(f"Unsupported extended bit area: {area}") from exc
    bit_no = index & 0x07
    addr = byte_base + (index >> 3)
    if addr > 0xFFFF:
        raise ValueError(f"Extended bit address out of range: {area}{index:04X}")
    return no, bit_no, addr


def _test_prefixed_bit_area_ranges(
    plc: ToyopucClient,
    prefix: str,
    area: str,
    ranges: List[Tuple[int, int]],
    count: int,
    rng: random.Random,
    log_f=None,
    skip_errors: bool = False,
) -> Tuple[int, int]:
    ok = 0
    total = 0
    for start, end in ranges:
        indices = pick_indices_min_max(rng, start, end, count)
        for idx in indices:
            try:
                no, bit_no, addr = _prefixed_bit_ext_addr(prefix, area, idx)
                o, t = _verify_bit_sequence(
                    lambda value: _ext_multi_write_bit(plc, no, bit_no, addr, value),
                    lambda: bool(_ext_multi_read_bit(plc, no, bit_no, addr)),
                    lambda suffix: _log_frames(
                        log_f, plc, f"[PREF BIT] {prefix}-{area}{idx:04X} {suffix}"
                    ),
                    f"[PREF BIT] MISMATCH {prefix}-{area}{idx:04X}",
                    log_f,
                    tolerated_label=f"BIT:{area}" if _is_tolerated_area("bit", area) else None,
                )
                ok += o
                total += t
            except (ToyopucError, ValueError) as e:
                if not skip_errors:
                    raise
                if log_f:
                    log_f.write(f"[PREF BIT] ERROR {prefix}-{area}{idx:04X} {e}\n")
    return ok, total


def _test_prefixed_word_area_ranges(
    plc: ToyopucClient,
    prefix: str,
    area: str,
    ranges: List[Tuple[int, int]],
    count: int,
    rng: random.Random,
    log_f=None,
    skip_errors: bool = False,
) -> Tuple[int, int]:
    ok = 0
    total = 0
    for start, end in ranges:
        indices = pick_indices_min_max(rng, start, end, count)
        for idx in indices:
            try:
                no, addr = _prefixed_word_ext_addr(prefix, area, idx)
                o, t = _verify_word_sequence(
                    lambda value: plc.write_ext_words(no, addr, [value]),
                    lambda: plc.read_ext_words(no, addr, 1)[0],
                    lambda suffix: _log_frames(
                        log_f, plc, f"[PREF WORD] {prefix}-{area}{idx:04X} {suffix}"
                    ),
                    f"[PREF WORD] MISMATCH {prefix}-{area}{idx:04X}",
                    rng,
                    log_f,
                    tolerated_label=f"WORD:{area}" if _is_tolerated_area("word", area) else None,
                )
                ok += o
                total += t
            except (ToyopucError, ValueError) as e:
                if not skip_errors:
                    raise
                if log_f:
                    log_f.write(f"[PREF WORD] ERROR {prefix}-{area}{idx:04X} {e}\n")
    return ok, total


def main() -> int:
    p = argparse.ArgumentParser(description="Auto read/write verification")
    p.add_argument("--host", default="192.168.0.10")
    p.add_argument("--port", type=int, default=15000)
    p.add_argument("--local-port", type=int, default=0, help="local UDP source port (default: auto)")
    p.add_argument("--protocol", default="tcp", choices=["tcp", "udp"])
    p.add_argument("--timeout", type=float, default=3.0)
    p.add_argument("--retries", type=int, default=0)
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--count", type=int, default=16, help="samples per area")
    p.add_argument("--include-io", action="store_true", help="include X/Y/L (can affect hardware)")
    p.add_argument("--include-special", action="store_true", help="include S/N/R (may be read-only)")
    p.add_argument("--include-extended", action="store_true", help="include U/EB extended areas")
    p.add_argument("--include-fr", action="store_true", help="include FR extended area")
    p.add_argument(
        "--include-all",
        action="store_true",
        help="include IO + special + extended",
    )
    p.add_argument(
        "--pc10g-full",
        action="store_true",
        help="PC10G device list: test all device types (min/max always checked)",
    )
    p.add_argument(
        "--include-p123",
        action="store_true",
        help="include P1/P2/P3 prefixed device tests via PC10 access",
    )
    p.add_argument(
        "--skip-errors",
        action="store_true",
        help="skip areas/points that return protocol errors and continue",
    )
    p.add_argument(
        "--max-block-test",
        action="store_true",
        help="run contiguous block-length tests for D/U/EB representative ranges",
    )
    p.add_argument(
        "--pc10-block-words",
        type=lambda s: int(s, 0),
        default=0x200,
        help="PC10 block-test word count (default: 0x200)",
    )
    p.add_argument(
        "--ext-multi-test",
        action="store_true",
        help="run a mixed CMD=98/99 test using bit+byte+word points together",
    )
    p.add_argument(
        "--boundary-test",
        action="store_true",
        help="run focused boundary tests around protocol and address split points",
    )
    p.add_argument("--log", default="", help="log file path (optional)")
    args = p.parse_args()
    TOLERATED_MISMATCH_COUNTS.clear()

    if args.pc10_block_words <= 0:
        raise SystemExit("--pc10-block-words must be > 0")
    if args.pc10_block_words > 0x200:
        print(
            f"WARNING: --pc10-block-words={args.pc10_block_words:#x} exceeds the verified safe default 0x200."
        )

    rng = random.Random(args.seed)

    bit_areas: Dict[str, Tuple[int, int]] = {}
    word_areas: Dict[str, Tuple[int, int]] = {}
    byte_areas: Dict[str, Tuple[int, int]] = {}
    ext_word_areas: Dict[str, Tuple[int, int]] = {}
    ext_byte_areas: Dict[str, Tuple[int, int]] = {}

    # Define test ranges by area index (hex)
    if args.pc10g_full:
        bit_area_ranges = {
            "P": [(0x000, 0x1FF)],
            "K": [(0x000, 0x2FF)],
            "V": [(0x000, 0x0FF)],
            "T": [(0x000, 0x1FF)],
            "C": [(0x000, 0x1FF)],
            "L": [(0x000, 0x7FF), (0x1000, 0x2FFF)],
            "X": [(0x000, 0x7FF)],
            "Y": [(0x000, 0x7FF)],
            "M": [(0x000, 0x7FF), (0x1000, 0x17FF)],
        }
        ext_bit_area_ranges = {
            "EP": [(0x000, 0x0FFF)],
            "EK": [(0x000, 0x0FFF)],
            "EV": [(0x000, 0x0FFF)],
            "ET": [(0x000, 0x07FF)],
            "EC": [(0x000, 0x07FF)],
            "EL": [(0x000, 0x1FFF)],
            "EX": [(0x000, 0x07FF)],
            "EY": [(0x000, 0x07FF)],
            "EM": [(0x000, 0x1FFF)],
        }
        gx_bit_area_ranges = {
            "GX": [(0x0000, 0xFFFF)],
            "GY": [(0x0000, 0xFFFF)],
            "GM": [(0x0000, 0xFFFF)],
        }
        word_area_ranges = {
            "S": [(0x0000, 0x03FF), (0x1000, 0x13FF)],
            "N": [(0x0000, 0x01FF), (0x1000, 0x17FF)],
            "R": [(0x0000, 0x07FF)],
            "D": [(0x0000, 0x2FFF)],
        }
        ext_word_area_ranges = {
            "ES": [(0x0000, 0x07FF)],
            "EN": [(0x0000, 0x07FF)],
            "H": [(0x0000, 0x07FF)],
            "U": [(0x00000, 0x1FFFF)],
            "EB": [(0x00000, 0x7FFFF)],
        }
        prefixed_bit_area_ranges = [
            ("P000-P1FF", "P", [(0x000, 0x1FF)]),
            ("P1000-P17FF", "P", [(0x1000, 0x17FF)]),
            ("K000-K2FF", "K", [(0x000, 0x2FF)]),
            ("V000-V0FF", "V", [(0x000, 0x0FF)]),
            ("V1000-V17FF", "V", [(0x1000, 0x17FF)]),
            ("T000-T1FF", "T", [(0x000, 0x1FF)]),
            ("T1000-T17FF", "T", [(0x1000, 0x17FF)]),
            ("C000-C1FF", "C", [(0x000, 0x1FF)]),
            ("C1000-C17FF", "C", [(0x1000, 0x17FF)]),
            ("L000-L7FF", "L", [(0x000, 0x7FF)]),
            ("L1000-L2FFF", "L", [(0x1000, 0x2FFF)]),
            ("X000-X7FF", "X", [(0x000, 0x7FF)]),
            ("Y000-Y7FF", "Y", [(0x000, 0x7FF)]),
            ("M000-M7FF", "M", [(0x000, 0x7FF)]),
            ("M1000-M17FF", "M", [(0x1000, 0x17FF)]),
        ]
        prefixed_word_area_ranges = [
            ("S0000-S03FF", "S", [(0x0000, 0x03FF)]),
            ("S1000-S13FF", "S", [(0x1000, 0x13FF)]),
            ("N0000-N01FF", "N", [(0x0000, 0x01FF)]),
            ("N1000-N17FF", "N", [(0x1000, 0x17FF)]),
            ("R0000-R07FF", "R", [(0x0000, 0x07FF)]),
            ("D0000-D2FFF", "D", [(0x0000, 0x2FFF)]),
        ]
        if args.include_fr:
            ext_word_area_ranges["FR"] = [(0x000000, 0x1FFFFF)]
    else:
        bit_areas = {
            "K": (0x000, 0x2FF),
            "V": (0x000, 0x0FF),
            "M": (0x000, 0x7FF),
        }
        if args.include_all or args.include_io:
            bit_areas.update({"L": (0x000, 0x7FF), "X": (0x000, 0x7FF), "Y": (0x000, 0x7FF)})

        word_areas = {
            "D": (0x0000, 0x2FFF),
            "B": (0x0000, 0x1FFF),
        }
        if args.include_all or args.include_special:
            word_areas.update({"S": (0x0000, 0x03FF), "N": (0x0000, 0x01FF), "R": (0x0000, 0x07FF)})

        byte_areas = {
            "D": (0x0000, 0x2FFF),
            "B": (0x0000, 0x1FFF),
        }

        ext_word_areas = {}
        ext_byte_areas = {}
        if args.include_all or args.include_extended:
            ext_word_areas["U"] = (0x0000, 0x7FFF)
            ext_byte_areas["U"] = (0x0000, 0xFFFF)
            ext_word_areas["EB"] = (0x00000, 0x1FFFF)
            ext_byte_areas["EB"] = (0x00000, 0x1FFFF)
        if args.include_fr:
            ext_word_areas["FR"] = (0x000000, 0x1FFFFF)
    total_ok = 0
    total = 0

    log_f = open(args.log, "a", encoding="utf-8") if args.log else None

    with ToyopucClient(
        args.host,
        args.port,
        local_port=args.local_port,
        protocol=args.protocol,
        timeout=args.timeout,
        retries=args.retries,
    ) as plc:
        if args.ext_multi_test:
            for label, ok, t in run_ext_multi_mixed(
                plc, rng, log_f, skip_errors=args.skip_errors
            ):
                _print_result("[EXT MULTI]", label, ok, t, log_f)
                total_ok += ok
                total += t
        if args.boundary_test:
            for label, ok, t in run_boundary_values(
                plc, rng, log_f, skip_errors=args.skip_errors
            ):
                _print_result("[BOUNDARY]", label, ok, t, log_f)
                total_ok += ok
                total += t
        if args.max_block_test:
            for label, ok, t in run_max_block_lengths(
                plc, rng, log_f, skip_errors=args.skip_errors, pc10_word_count=args.pc10_block_words
            ):
                _print_result("[BLOCK]", label, ok, t, log_f)
                total_ok += ok
                total += t
        if args.pc10g_full:
            for area, ranges in bit_area_ranges.items():
                try:
                    _ = encode_bit_address(parse_address(f"{area}0000", "bit"))
                except Exception:
                    print(f"[BIT] {area}: SKIP (unsupported)")
                    if log_f:
                        log_f.write(f"[BIT] {area}: SKIP (unsupported)\n")
                    continue
                if area == "L":
                    ok1, t1 = run_bit_area_ranges(
                        plc,
                        area,
                        [(0x000, 0x7FF)],
                        args.count,
                        rng,
                        log_f,
                        skip_errors=args.skip_errors,
                    )
                    ok2, t2 = _test_pc10_bit_area_ranges_with_builder(
                        plc,
                        "L",
                        [(0x1000, 0x2FFF)],
                        args.count,
                        rng,
                        lambda idx: _pc10_base_bit_addr32("L", idx),
                        log_f,
                        skip_errors=args.skip_errors,
                    )
                    label = _ranges_label(area, [(0x000, 0x7FF), (0x1000, 0x2FFF)])
                    _print_result("[BIT]", label, ok1 + ok2, t1 + t2, log_f)
                    total_ok += ok1 + ok2
                    total += t1 + t2
                    continue

                if area == "M":
                    ok1, t1 = run_bit_area_ranges(
                        plc,
                        area,
                        [(0x000, 0x7FF)],
                        args.count,
                        rng,
                        log_f,
                        skip_errors=args.skip_errors,
                    )
                    ok2, t2 = _test_pc10_bit_area_ranges_with_builder(
                        plc,
                        "M",
                        [(0x1000, 0x17FF)],
                        args.count,
                        rng,
                        lambda idx: _pc10_base_bit_addr32("M", idx),
                        log_f,
                        skip_errors=args.skip_errors,
                    )
                    label = _ranges_label(area, [(0x000, 0x7FF), (0x1000, 0x17FF)])
                    _print_result("[BIT]", label, ok1 + ok2, t1 + t2, log_f)
                    total_ok += ok1 + ok2
                    total += t1 + t2
                    continue

                ok, t = run_bit_area_ranges(
                    plc, area, ranges, args.count, rng, log_f, skip_errors=args.skip_errors
                )
                label = _ranges_label(area, ranges)
                _print_result("[BIT]", label, ok, t, log_f)
                total_ok += ok
                total += t

            for area, ranges in word_area_ranges.items():
                try:
                    _ = encode_word_address(parse_address(f"{area}0000", "word"))
                except Exception:
                    print(f"[WORD] {area}: SKIP (unsupported)")
                    if log_f:
                        log_f.write(f"[WORD] {area}: SKIP (unsupported)\n")
                    continue
                ok, t = run_word_area_ranges(
                    plc, area, ranges, args.count, rng, log_f, skip_errors=args.skip_errors
                )
                label = _ranges_label(area, ranges)
                _print_result("[WORD]", label, ok, t, log_f)
                total_ok += ok
                total += t

            if args.include_p123:
                for prefix in ("P1", "P2", "P3"):
                    for label, area, ranges in prefixed_bit_area_ranges:
                        ok, t = _test_prefixed_bit_area_ranges(
                            plc,
                            prefix,
                            area,
                            ranges,
                            args.count,
                            rng,
                            log_f,
                            skip_errors=args.skip_errors,
                        )
                        _print_result("[PREF BIT]", f"{prefix}-{label}", ok, t, log_f)
                        total_ok += ok
                        total += t

                    for label, area, ranges in prefixed_word_area_ranges:
                        ok, t = _test_prefixed_word_area_ranges(
                            plc,
                            prefix,
                            area,
                            ranges,
                            args.count,
                            rng,
                            log_f,
                            skip_errors=args.skip_errors,
                        )
                        _print_result("[PREF WORD]", f"{prefix}-{label}", ok, t, log_f)
                        total_ok += ok
                        total += t

            # Extended bit areas via CMD=98/99
            for area, ranges in ext_bit_area_ranges.items():
                ok, t = _test_ext_bit_area_ranges(
                    plc, area, ranges, args.count, rng, log_f, skip_errors=args.skip_errors
                )
                label = _ranges_label(area, ranges)
                _print_result("[EXT BIT]", label, ok, t, log_f)
                total_ok += ok
                total += t

            # GX series bit areas via CMD=98/99
            for area, ranges in gx_bit_area_ranges.items():
                ok, t = _test_ext_bit_area_ranges(
                    plc, area, ranges, args.count, rng, log_f, skip_errors=args.skip_errors
                )
                label = _ranges_label(area, ranges)
                _print_result("[EXT BIT]", label, ok, t, log_f)
                total_ok += ok
                total += t

            for area, ranges in ext_word_area_ranges.items():
                try:
                    if area == "U":
                        _ = _encode_pc10g_u(area, ranges[0][0])
                    else:
                        _ = encode_ext_no_address(area, ranges[0][0], "word")
                except Exception:
                    print(f"[EXT WORD] {area}: SKIP (unsupported)")
                    if log_f:
                        log_f.write(f"[EXT WORD] {area}: SKIP (unsupported)\n")
                    continue

                if area == "U":
                    ok1, t1 = run_ext_word_area_ranges(
                        plc,
                        area,
                        [(0x00000, 0x07FFF)],
                        args.count,
                        rng,
                        log_f,
                        skip_errors=args.skip_errors,
                        encoder=None,
                    )
                    ok2, t2 = _test_pc10_word_area_ranges_with_builder(
                        plc,
                        "U",
                        [(0x08000, 0x1FFFF)],
                        args.count,
                        rng,
                        _pc10_u_word_addr32,
                        log_f,
                        skip_errors=args.skip_errors,
                    )
                    label = _ranges_label("U", [(0x00000, 0x07FFF), (0x08000, 0x1FFFF)])
                    _print_result("[EXT WORD]", label, ok1 + ok2, t1 + t2, log_f)
                    total_ok += ok1 + ok2
                    total += t1 + t2
                    continue

                if area == "EB":
                    ok1, t1 = _test_pc10_word_area_ranges_with_builder(
                        plc,
                        "EB",
                        [(0x00000, 0x3FFFF)],
                        args.count,
                        rng,
                        _pc10_eb_word_addr32,
                        log_f,
                        skip_errors=args.skip_errors,
                    )
                    ok2, t2 = run_ext_word_area_ranges(
                        plc,
                        area,
                        [(0x40000, 0x7FFFF)],
                        args.count,
                        rng,
                        log_f,
                        skip_errors=args.skip_errors,
                        encoder=None,
                    )
                    label = _ranges_label("EB", [(0x00000, 0x3FFFF), (0x40000, 0x7FFFF)])
                    _print_result("[EXT WORD]", label, ok1 + ok2, t1 + t2, log_f)
                    total_ok += ok1 + ok2
                    total += t1 + t2
                    continue

                if area == "FR":
                    ok, t = _test_pc10_word_area_ranges_with_builder(
                        plc,
                        "FR",
                        ranges,
                        args.count,
                        rng,
                        encode_fr_word_addr32,
                        log_f,
                        skip_errors=args.skip_errors,
                    )
                    label = _ranges_label("FR", ranges)
                    _print_result("[EXT WORD]", label, ok, t, log_f)
                    total_ok += ok
                    total += t
                    continue

                encoder = _encode_pc10g_u if area == "U" else None
                ok, t = run_ext_word_area_ranges(
                    plc,
                    area,
                    ranges,
                    args.count,
                    rng,
                    log_f,
                    skip_errors=args.skip_errors,
                    encoder=encoder,
                )
                label = _ranges_label(area, ranges)
                _print_result("[EXT WORD]", label, ok, t, log_f)
                total_ok += ok
                total += t
        else:
            for area, (s, e) in bit_areas.items():
                ok, t = run_bit_area(
                    plc, area, s, e, args.count, rng, log_f, skip_errors=args.skip_errors
                )
                label = _range_label(area, s, e, max(4, len(f"{e:X}")))
                _print_result("[BIT]", label, ok, t, log_f)
                total_ok += ok
                total += t

            for area, (s, e) in word_areas.items():
                ok, t = run_word_area(
                    plc, area, s, e, args.count, rng, log_f, skip_errors=args.skip_errors
                )
                label = _range_label(area, s, e, max(4, len(f"{e:X}")))
                _print_result("[WORD]", label, ok, t, log_f)
                total_ok += ok
                total += t

            for area, (s, e) in byte_areas.items():
                ok, t = run_byte_area(
                    plc, area, s, e, args.count, rng, log_f, skip_errors=args.skip_errors
                )
                label = _range_label(area, s, e, max(4, len(f"{e:X}")))
                _print_result("[BYTE]", label, ok, t, log_f)
                total_ok += ok
                total += t

            for area, (s, e) in ext_word_areas.items():
                ok, t = run_ext_word_area(
                    plc,
                    area,
                    s,
                    e,
                    args.count,
                    rng,
                    log_f,
                    skip_errors=args.skip_errors,
                )
                label = _range_label(area, s, e, max(4, len(f"{e:X}")))
                _print_result("[EXT WORD]", label, ok, t, log_f)
                total_ok += ok
                total += t

            for area, (s, e) in ext_byte_areas.items():
                ok, t = run_ext_byte_area(
                    plc, area, s, e, args.count, rng, log_f, skip_errors=args.skip_errors
                )
                label = _range_label(area, s, e, max(4, len(f"{e:X}")))
                _print_result("[EXT BYTE]", label, ok, t, log_f)
                total_ok += ok
                total += t

    print(f"TOTAL: {total_ok}/{total}")
    tolerated_total = sum(TOLERATED_MISMATCH_COUNTS.values())
    if tolerated_total:
        print(f"TOLERATED: {tolerated_total}")
        for label in sorted(TOLERATED_MISMATCH_COUNTS):
            print(f"  {label}: {TOLERATED_MISMATCH_COUNTS[label]}")
    if log_f:
        log_f.write(f"TOTAL: {total_ok}/{total}\n")
        if tolerated_total:
            log_f.write(f"TOLERATED: {tolerated_total}\n")
            for label in sorted(TOLERATED_MISMATCH_COUNTS):
                log_f.write(f"{label}: {TOLERATED_MISMATCH_COUNTS[label]}\n")
        log_f.close()
    return 0 if total_ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

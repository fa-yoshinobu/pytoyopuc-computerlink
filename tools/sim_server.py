#!/usr/bin/env python
import argparse
import socket
import threading
from datetime import datetime
from typing import Dict, Mapping, MutableMapping, Tuple, TypeVar

from toyopuc.protocol import FT_COMMAND, FT_RESPONSE


_BASIC_PACKED = {
    'P': {'word_base': 0x0000, 'byte_base': 0x0000, 'bit_base': 0x0000, 'bit_count': 0x0200},
    'K': {'word_base': 0x0020, 'byte_base': 0x0040, 'bit_base': 0x0200, 'bit_count': 0x0300},
    'V': {'word_base': 0x0050, 'byte_base': 0x00A0, 'bit_base': 0x0500, 'bit_count': 0x0100},
    'T': {'word_base': 0x0060, 'byte_base': 0x00C0, 'bit_base': 0x0600, 'bit_count': 0x0200},
    'C': {'word_base': 0x0060, 'byte_base': 0x00C0, 'bit_base': 0x0600, 'bit_count': 0x0200},
    'L': {'word_base': 0x0080, 'byte_base': 0x0100, 'bit_base': 0x0800, 'bit_count': 0x0800},
    'X': {'word_base': 0x0100, 'byte_base': 0x0200, 'bit_base': 0x1000, 'bit_count': 0x0800},
    'Y': {'word_base': 0x0100, 'byte_base': 0x0200, 'bit_base': 0x1000, 'bit_count': 0x0800},
    'M': {'word_base': 0x0180, 'byte_base': 0x0300, 'bit_base': 0x1800, 'bit_count': 0x0800},
}

_PROGRAM_BIT_SEGMENTS = {
    'P': [(0x000, 0x1FF, 0x0000), (0x1000, 0x17FF, 0xC000)],
    'K': [(0x000, 0x2FF, 0x0040)],
    'V': [(0x000, 0x0FF, 0x00A0), (0x1000, 0x17FF, 0xC100)],
    'T': [(0x000, 0x1FF, 0x00C0), (0x1000, 0x17FF, 0xC200)],
    'C': [(0x000, 0x1FF, 0x00C0), (0x1000, 0x17FF, 0xC200)],
    'L': [(0x000, 0x7FF, 0x0100), (0x1000, 0x2FFF, 0xC400)],
    'X': [(0x000, 0x7FF, 0x0200)],
    'Y': [(0x000, 0x7FF, 0x0200)],
    'M': [(0x000, 0x7FF, 0x0300), (0x1000, 0x17FF, 0xC300)],
}

_EXT_BIT_AREAS = {
    'EP': {'no': 0x00, 'word_base': 0x0000, 'byte_base': 0x0000, 'bit_count': 0x1000},
    'EK': {'no': 0x00, 'word_base': 0x0100, 'byte_base': 0x0200, 'bit_count': 0x1000},
    'EV': {'no': 0x00, 'word_base': 0x0200, 'byte_base': 0x0400, 'bit_count': 0x1000},
    'ET': {'no': 0x00, 'word_base': 0x0300, 'byte_base': 0x0600, 'bit_count': 0x0800},
    'EC': {'no': 0x00, 'word_base': 0x0300, 'byte_base': 0x0600, 'bit_count': 0x0800},
    'EL': {'no': 0x00, 'word_base': 0x0380, 'byte_base': 0x0700, 'bit_count': 0x2000},
    'EX': {'no': 0x00, 'word_base': 0x0580, 'byte_base': 0x0B00, 'bit_count': 0x0800},
    'EY': {'no': 0x00, 'word_base': 0x0580, 'byte_base': 0x0B00, 'bit_count': 0x0800},
    'EM': {'no': 0x00, 'word_base': 0x0600, 'byte_base': 0x0C00, 'bit_count': 0x2000},
    'GX': {'no': 0x07, 'word_base': 0x0000, 'byte_base': 0x0000, 'bit_count': 0x10000},
    'GY': {'no': 0x07, 'word_base': 0x0000, 'byte_base': 0x0000, 'bit_count': 0x10000},
    'GM': {'no': 0x07, 'word_base': 0x0000, 'byte_base': 0x2000, 'bit_count': 0x10000},
}


def _basic_word_byte_addr(addr: int) -> int | None:
    for spec in _BASIC_PACKED.values():
        word_count = spec['bit_count'] // 16
        if spec['word_base'] <= addr < spec['word_base'] + word_count:
            return spec['byte_base'] + (addr - spec['word_base']) * 2
    return None


def _basic_byte_key(addr: int) -> int | None:
    for spec in _BASIC_PACKED.values():
        byte_count = spec['bit_count'] // 8
        if spec['byte_base'] <= addr < spec['byte_base'] + byte_count:
            return addr
    return None


def _basic_bit_key(addr: int) -> tuple[int, int] | None:
    for spec in _BASIC_PACKED.values():
        if spec['bit_base'] <= addr < spec['bit_base'] + spec['bit_count']:
            rel = addr - spec['bit_base']
            return spec['byte_base'] + (rel >> 3), rel & 0x07
    return None


def _program_word_byte_addr(addr: int) -> int | None:
    for segments in _PROGRAM_BIT_SEGMENTS.values():
        for start, end, byte_base in segments:
            word_base = byte_base >> 1
            word_count = (end - start + 1) // 16
            if word_base <= addr < word_base + word_count:
                return byte_base + (addr - word_base) * 2
    return None


def _program_byte_key(addr: int) -> int | None:
    for segments in _PROGRAM_BIT_SEGMENTS.values():
        for start, end, byte_base in segments:
            byte_count = (end - start + 1) // 8
            if byte_base <= addr < byte_base + byte_count:
                return addr
    return None


def _ext_word_byte_addr(no: int, addr: int) -> int | None:
    for spec in _EXT_BIT_AREAS.values():
        if spec['no'] != no:
            continue
        word_count = spec['bit_count'] // 16
        if spec['word_base'] <= addr < spec['word_base'] + word_count:
            return spec['byte_base'] + (addr - spec['word_base']) * 2
    return None


def _ext_byte_key(no: int, addr: int) -> int | None:
    for spec in _EXT_BIT_AREAS.values():
        if spec['no'] != no:
            continue
        byte_count = spec['bit_count'] // 8
        if spec['byte_base'] <= addr < spec['byte_base'] + byte_count:
            return addr
    return None


K = TypeVar("K")


def _read_u16_from_map(store: Mapping[K, int], low_key: K, high_key: K) -> int:
    return (store.get(low_key, 0) & 0xFF) | ((store.get(high_key, 0) & 0xFF) << 8)


def _write_u16_to_map(store: MutableMapping[K, int], low_key: K, high_key: K, value: int) -> None:
    store[low_key] = value & 0xFF
    store[high_key] = (value >> 8) & 0xFF


def parse_command(frame: bytes) -> Tuple[int, bytes]:
    if len(frame) < 5:
        raise ValueError("frame too short")
    ft, rc, ll, lh, cmd = frame[:5]
    if ft != FT_COMMAND:
        raise ValueError("not a command frame")
    length = ll | (lh << 8)
    expected = 4 + length
    if len(frame) != expected:
        raise ValueError("invalid length")
    return cmd, frame[5:]


def build_response(cmd: int, data: bytes, rc: int = 0x00) -> bytes:
    length = 1 + len(data)
    ll = length & 0xFF
    lh = (length >> 8) & 0xFF
    return bytes([FT_RESPONSE, rc, ll, lh, cmd]) + data


class Memory:
    def __init__(self) -> None:
        self.word: Dict[int, int] = {}
        self.byte: Dict[int, int] = {}
        self.bit: Dict[int, int] = {}
        self.ext_word: Dict[Tuple[int, int], int] = {}
        self.ext_byte: Dict[Tuple[int, int], int] = {}
        self.ext_bit: Dict[Tuple[int, int, int], int] = {}
        self.pc10: Dict[int, int] = {}
        self.basic_packed_byte: Dict[int, int] = {}
        self.program_packed_byte: Dict[Tuple[int, int], int] = {}
        self.ext_packed_byte: Dict[Tuple[int, int], int] = {}
        self.clock = datetime(2026, 3, 8, 12, 34, 56)
        # Example: RUN + PC10 mode, programs 1/2/3 running.
        self.cpu_status = bytes([0x81, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0E])


def pack_bcd(value: int) -> int:
    if not (0 <= value <= 99):
        raise ValueError("BCD value out of range")
    return ((value // 10) << 4) | (value % 10)


def unpack_bcd(value: int) -> int:
    return ((value >> 4) & 0x0F) * 10 + (value & 0x0F)


def handle_command(mem: Memory, frame: bytes) -> bytes:
    cmd, data = parse_command(frame)

    if cmd == 0x32:
        if len(data) < 2:
            return build_response(cmd, b"", rc=0x01)

        sub0, sub1 = data[0], data[1]

        if sub0 == 0x11 and sub1 == 0x00:  # CPU status read
            return build_response(cmd, bytes([0x11, 0x00]) + mem.cpu_status)

        if sub0 == 0x70 and sub1 == 0x00:  # clock read
            dt = mem.clock
            clock_data = bytes(
                [
                    0x70,
                    0x00,
                    pack_bcd(dt.second),
                    pack_bcd(dt.minute),
                    pack_bcd(dt.hour),
                    pack_bcd(dt.day),
                    pack_bcd(dt.month),
                    pack_bcd(dt.year % 100),
                    (dt.weekday() + 1) % 7,  # Sunday=0
                ]
            )
            return build_response(cmd, clock_data)

        if sub0 == 0x71 and sub1 == 0x00:  # clock write
            if len(data) < 9:
                return build_response(cmd, b"", rc=0x01)
            second = unpack_bcd(data[2])
            minute = unpack_bcd(data[3])
            hour = unpack_bcd(data[4])
            day = unpack_bcd(data[5])
            month = unpack_bcd(data[6])
            year_2digit = unpack_bcd(data[7])
            try:
                mem.clock = datetime(2000 + year_2digit, month, day, hour, minute, second)
            except ValueError:
                return build_response(cmd, b"", rc=0x01)
            return build_response(cmd, bytes([0x71, 0x00]))

        return build_response(cmd, b"", rc=0x01)

    if cmd == 0x1C:  # word read
        addr = data[0] | (data[1] << 8)
        count = data[2] | (data[3] << 8)
        out = bytearray()
        for i in range(count):
            byte_addr = _basic_word_byte_addr(addr + i)
            if byte_addr is not None:
                v = _read_u16_from_map(mem.basic_packed_byte, byte_addr, byte_addr + 1)
            else:
                v = mem.word.get(addr + i, 0) & 0xFFFF
            out.extend([v & 0xFF, (v >> 8) & 0xFF])
        return build_response(cmd, bytes(out))

    if cmd == 0x1D:  # word write
        addr = data[0] | (data[1] << 8)
        payload = data[2:]
        for i in range(0, len(payload), 2):
            v = payload[i] | (payload[i + 1] << 8)
            word_addr = addr + (i // 2)
            byte_addr = _basic_word_byte_addr(word_addr)
            if byte_addr is not None:
                _write_u16_to_map(mem.basic_packed_byte, byte_addr, byte_addr + 1, v)
            else:
                mem.word[word_addr] = v
        return build_response(cmd, b"")

    if cmd == 0x1E:  # byte read
        addr = data[0] | (data[1] << 8)
        count = data[2] | (data[3] << 8)
        out = bytearray()
        for i in range(count):
            byte_addr = addr + i
            key = _basic_byte_key(byte_addr)
            if key is not None:
                out.append(mem.basic_packed_byte.get(key, 0) & 0xFF)
            else:
                out.append(mem.byte.get(byte_addr, 0) & 0xFF)
        return build_response(cmd, bytes(out))

    if cmd == 0x1F:  # byte write
        addr = data[0] | (data[1] << 8)
        payload = data[2:]
        for i, b in enumerate(payload):
            byte_addr = addr + i
            key = _basic_byte_key(byte_addr)
            if key is not None:
                mem.basic_packed_byte[key] = b & 0xFF
            else:
                mem.byte[byte_addr] = b & 0xFF
        return build_response(cmd, b"")

    if cmd == 0x20:  # bit read
        addr = data[0] | (data[1] << 8)
        bit_key = _basic_bit_key(addr)
        if bit_key is not None:
            byte_addr, bit = bit_key
            v = (mem.basic_packed_byte.get(byte_addr, 0) >> bit) & 0x01
        else:
            v = mem.bit.get(addr, 0) & 0x01
        return build_response(cmd, bytes([v]))

    if cmd == 0x21:  # bit write
        addr = data[0] | (data[1] << 8)
        bit_key = _basic_bit_key(addr)
        if bit_key is not None:
            byte_addr, bit = bit_key
            current = mem.basic_packed_byte.get(byte_addr, 0) & 0xFF
            if data[2] & 0x01:
                current |= (1 << bit)
            else:
                current &= ~(1 << bit)
            mem.basic_packed_byte[byte_addr] = current
        else:
            mem.bit[addr] = data[2] & 0x01
        return build_response(cmd, b"")

    if cmd == 0x22:  # multi word read
        out = bytearray()
        for i in range(0, len(data), 2):
            addr = data[i] | (data[i + 1] << 8)
            v = mem.word.get(addr, 0) & 0xFFFF
            out.extend([v & 0xFF, (v >> 8) & 0xFF])
        return build_response(cmd, bytes(out))

    if cmd == 0x23:  # multi word write
        for i in range(0, len(data), 4):
            addr = data[i] | (data[i + 1] << 8)
            v = data[i + 2] | (data[i + 3] << 8)
            mem.word[addr] = v
        return build_response(cmd, b"")

    if cmd == 0x24:  # multi byte read
        out = bytearray()
        for i in range(0, len(data), 2):
            addr = data[i] | (data[i + 1] << 8)
            out.append(mem.byte.get(addr, 0) & 0xFF)
        return build_response(cmd, bytes(out))

    if cmd == 0x25:  # multi byte write
        for i in range(0, len(data), 3):
            addr = data[i] | (data[i + 1] << 8)
            v = data[i + 2]
            mem.byte[addr] = v & 0xFF
        return build_response(cmd, b"")

    if cmd == 0x94:  # ext word read
        no = data[0]
        addr = data[1] | (data[2] << 8)
        count = data[3] | (data[4] << 8)
        out = bytearray()
        for i in range(count):
            word_addr = addr + i
            byte_addr = _program_word_byte_addr(word_addr) if no in (0x01, 0x02, 0x03) else _ext_word_byte_addr(no, word_addr)
            if byte_addr is not None:
                store = mem.program_packed_byte if no in (0x01, 0x02, 0x03) else mem.ext_packed_byte
                low_key = (no, byte_addr)
                high_key = (no, byte_addr + 1)
                v = _read_u16_from_map(store, low_key, high_key)
            else:
                v = mem.ext_word.get((no, word_addr), 0) & 0xFFFF
            out.extend([v & 0xFF, (v >> 8) & 0xFF])
        return build_response(cmd, bytes(out))

    if cmd == 0x95:  # ext word write
        no = data[0]
        addr = data[1] | (data[2] << 8)
        payload = data[3:]
        for i in range(0, len(payload), 2):
            v = payload[i] | (payload[i + 1] << 8)
            word_addr = addr + (i // 2)
            byte_addr = _program_word_byte_addr(word_addr) if no in (0x01, 0x02, 0x03) else _ext_word_byte_addr(no, word_addr)
            if byte_addr is not None:
                store = mem.program_packed_byte if no in (0x01, 0x02, 0x03) else mem.ext_packed_byte
                _write_u16_to_map(store, (no, byte_addr), (no, byte_addr + 1), v)
            else:
                mem.ext_word[(no, word_addr)] = v
        return build_response(cmd, b"")

    if cmd == 0x96:  # ext byte read
        no = data[0]
        addr = data[1] | (data[2] << 8)
        count = data[3] | (data[4] << 8)
        out = bytearray()
        for i in range(count):
            byte_addr = addr + i
            key_addr = _program_byte_key(byte_addr) if no in (0x01, 0x02, 0x03) else _ext_byte_key(no, byte_addr)
            if key_addr is not None:
                store = mem.program_packed_byte if no in (0x01, 0x02, 0x03) else mem.ext_packed_byte
                out.append(store.get((no, key_addr), 0) & 0xFF)
            else:
                out.append(mem.ext_byte.get((no, byte_addr), 0) & 0xFF)
        return build_response(cmd, bytes(out))

    if cmd == 0x97:  # ext byte write
        no = data[0]
        addr = data[1] | (data[2] << 8)
        payload = data[3:]
        for i, b in enumerate(payload):
            byte_addr = addr + i
            key_addr = _program_byte_key(byte_addr) if no in (0x01, 0x02, 0x03) else _ext_byte_key(no, byte_addr)
            if key_addr is not None:
                store = mem.program_packed_byte if no in (0x01, 0x02, 0x03) else mem.ext_packed_byte
                store[(no, key_addr)] = b & 0xFF
            else:
                mem.ext_byte[(no, byte_addr)] = b & 0xFF
        return build_response(cmd, b"")

    if cmd == 0xC2:  # PC10 block read
        addr32 = data[0] | (data[1] << 8) | (data[2] << 16) | (data[3] << 24)
        count = data[4] | (data[5] << 8)
        out = bytearray()
        for i in range(count):
            out.append(mem.pc10.get(addr32 + i, 0) & 0xFF)
        return build_response(cmd, bytes(out))

    if cmd == 0xC3:  # PC10 block write
        addr32 = data[0] | (data[1] << 8) | (data[2] << 16) | (data[3] << 24)
        payload = data[4:]
        for i, b in enumerate(payload):
            mem.pc10[addr32 + i] = b & 0xFF
        return build_response(cmd, b"")

    if cmd == 0x60:  # relay command (simple unwrap)
        if len(data) < 3:
            return build_response(cmd, b"", rc=0x01)
        link_no, station_no, enq = data[0], data[1], data[2]
        if enq != 0x05:
            return build_response(cmd, bytes([link_no, station_no, 0x15]), rc=0x01)
        inner = data[3:]
        inner_resp = handle_command(mem, inner)
        # ACK=0x06
        return build_response(cmd, bytes([link_no, station_no, 0x06]) + inner_resp)

    if cmd == 0x98:  # ext multi read
        if len(data) < 3:
            return build_response(cmd, b"", rc=0x01)
        bit_cnt, byte_cnt, word_cnt = data[0], data[1], data[2]
        idx = 3
        bits = []
        for _ in range(bit_cnt):
            spec = data[idx]
            no = spec & 0x0F
            bit = (spec >> 4) & 0x0F
            addr = data[idx + 1] | (data[idx + 2] << 8)
            idx += 3
            bits.append((no, addr, bit))
        bytespec = []
        for _ in range(byte_cnt):
            no = data[idx]
            addr = data[idx + 1] | (data[idx + 2] << 8)
            idx += 3
            bytespec.append((no, addr))
        wordspec = []
        for _ in range(word_cnt):
            no = data[idx]
            addr = data[idx + 1] | (data[idx + 2] << 8)
            idx += 3
            wordspec.append((no, addr))

        out = bytearray()
        # bits packed into bytes, bit0 is first
        if bits:
            acc = 0
            bit_pos = 0
            for no, addr, bit in bits:
                if no in (0x01, 0x02, 0x03):
                    val = (mem.program_packed_byte.get((no, addr), 0) >> bit) & 0x01
                else:
                    key_addr = _ext_byte_key(no, addr)
                    if key_addr is not None:
                        val = (mem.ext_packed_byte.get((no, key_addr), 0) >> bit) & 0x01
                    else:
                        val = mem.ext_bit.get((no, addr, bit), 0) & 0x01
                if val:
                    acc |= (1 << bit_pos)
                bit_pos += 1
                if bit_pos == 8:
                    out.append(acc & 0xFF)
                    acc = 0
                    bit_pos = 0
            if bit_pos:
                out.append(acc & 0xFF)
        for no, addr in bytespec:
            out.append(mem.ext_byte.get((no, addr), 0) & 0xFF)
        for no, addr in wordspec:
            v = mem.ext_word.get((no, addr), 0) & 0xFFFF
            out.extend([v & 0xFF, (v >> 8) & 0xFF])
        return build_response(cmd, bytes(out))

    if cmd == 0x99:  # ext multi write
        if len(data) < 3:
            return build_response(cmd, b"", rc=0x01)
        bit_cnt, byte_cnt, word_cnt = data[0], data[1], data[2]
        idx = 3
        for _ in range(bit_cnt):
            spec = data[idx]
            no = spec & 0x0F
            bit = (spec >> 4) & 0x0F
            addr = data[idx + 1] | (data[idx + 2] << 8)
            value = data[idx + 3] & 0x01
            idx += 4
            if no in (0x01, 0x02, 0x03):
                current = mem.program_packed_byte.get((no, addr), 0) & 0xFF
                if value:
                    current |= (1 << bit)
                else:
                    current &= ~(1 << bit)
                mem.program_packed_byte[(no, addr)] = current
            else:
                key_addr = _ext_byte_key(no, addr)
                if key_addr is not None:
                    current = mem.ext_packed_byte.get((no, key_addr), 0) & 0xFF
                    if value:
                        current |= (1 << bit)
                    else:
                        current &= ~(1 << bit)
                    mem.ext_packed_byte[(no, key_addr)] = current
                else:
                    mem.ext_bit[(no, addr, bit)] = value
        for _ in range(byte_cnt):
            no = data[idx]
            addr = data[idx + 1] | (data[idx + 2] << 8)
            value = data[idx + 3] & 0xFF
            idx += 4
            mem.ext_byte[(no, addr)] = value
        for _ in range(word_cnt):
            no = data[idx]
            addr = data[idx + 1] | (data[idx + 2] << 8)
            value = data[idx + 3] | (data[idx + 4] << 8)
            idx += 5
            mem.ext_word[(no, addr)] = value
        return build_response(cmd, b"")

    if cmd == 0xC4:  # PC10 multi read (sim format)
        if len(data) < 4:
            return build_response(cmd, b"", rc=0x01)
        bit_cnt, byte_cnt, word_cnt, long_cnt = data[0], data[1], data[2], data[3]
        idx = 4
        addrs = []
        for _ in range(bit_cnt + byte_cnt + word_cnt + long_cnt):
            addr32 = data[idx] | (data[idx + 1] << 8) | (data[idx + 2] << 16) | (data[idx + 3] << 24)
            idx += 4
            addrs.append(addr32)
        out = bytearray()
        # bits packed
        if bit_cnt:
            acc = 0
            bit_pos = 0
            for i in range(bit_cnt):
                v = mem.pc10.get(addrs[i], 0) & 0x01
                if v:
                    acc |= (1 << bit_pos)
                bit_pos += 1
                if bit_pos == 8:
                    out.append(acc & 0xFF)
                    acc = 0
                    bit_pos = 0
            if bit_pos:
                out.append(acc & 0xFF)
        offset = bit_cnt
        for i in range(byte_cnt):
            out.append(mem.pc10.get(addrs[offset + i], 0) & 0xFF)
        offset += byte_cnt
        for i in range(word_cnt):
            v = mem.pc10.get(addrs[offset + i], 0) & 0xFFFF
            out.extend([v & 0xFF, (v >> 8) & 0xFF])
        offset += word_cnt
        for i in range(long_cnt):
            v = mem.pc10.get(addrs[offset + i], 0) & 0xFFFFFFFF
            out.extend([v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF])
        return build_response(cmd, bytes(out))

    if cmd == 0xC5:  # PC10 multi write (sim format)
        if len(data) < 4:
            return build_response(cmd, b"", rc=0x01)
        bit_cnt, byte_cnt, word_cnt, long_cnt = data[0], data[1], data[2], data[3]
        idx = 4
        addrs = []
        for _ in range(bit_cnt + byte_cnt + word_cnt + long_cnt):
            addr32 = data[idx] | (data[idx + 1] << 8) | (data[idx + 2] << 16) | (data[idx + 3] << 24)
            idx += 4
            addrs.append(addr32)
        # data section
        # bits packed
        for i in range(bit_cnt):
            byte_index = i // 8
            bit_index = i % 8
            val = (data[idx + byte_index] >> bit_index) & 0x01
            mem.pc10[addrs[i]] = val
        idx += (bit_cnt + 7) // 8
        offset = bit_cnt
        for i in range(byte_cnt):
            mem.pc10[addrs[offset + i]] = data[idx]
            idx += 1
        offset += byte_cnt
        for i in range(word_cnt):
            v = data[idx] | (data[idx + 1] << 8)
            mem.pc10[addrs[offset + i]] = v
            idx += 2
        offset += word_cnt
        for i in range(long_cnt):
            v = data[idx] | (data[idx + 1] << 8) | (data[idx + 2] << 16) | (data[idx + 3] << 24)
            mem.pc10[addrs[offset + i]] = v
            idx += 4
        return build_response(cmd, b"")

    if cmd in (0xC6, 0xCA, 0xA0):
        return build_response(cmd, b"")

    return build_response(cmd, b"", rc=0x01)


def handle_tcp_client(conn: socket.socket, mem: Memory) -> None:
    with conn:
        while True:
            header = conn.recv(4)
            if not header:
                return
            if len(header) < 4:
                return
            ll, lh = header[2], header[3]
            length = ll | (lh << 8)
            body = b""
            while len(body) < length:
                chunk = conn.recv(length - len(body))
                if not chunk:
                    return
                body += chunk
            frame = header + body
            try:
                resp = handle_command(mem, frame)
            except Exception:
                resp = build_response(0x00, b"", rc=0x01)
            conn.sendall(resp)


def run_tcp(host: str, port: int) -> None:
    mem = Memory()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen()
        print(f"TCP simulator listening on {host}:{port}")
        while True:
            conn, _ = s.accept()
            t = threading.Thread(target=handle_tcp_client, args=(conn, mem), daemon=True)
            t.start()


def run_udp(host: str, port: int) -> None:
    mem = Memory()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind((host, port))
        print(f"UDP simulator listening on {host}:{port}")
        while True:
            data, addr = s.recvfrom(8192)
            try:
                resp = handle_command(mem, data)
            except Exception:
                resp = build_response(0x00, b"", rc=0x01)
            s.sendto(resp, addr)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=15000)
    p.add_argument("--udp", action="store_true")
    args = p.parse_args()

    if args.udp:
        run_udp(args.host, args.port)
    else:
        run_tcp(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

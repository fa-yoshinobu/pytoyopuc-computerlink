
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional, Sequence, Tuple

from .exceptions import ToyopucProtocolError


FT_COMMAND = 0x00
FT_RESPONSE = 0x80


@dataclass(frozen=True)
class ResponseFrame:
    """Parsed response frame header and body."""

    ft: int
    rc: int
    cmd: int
    data: bytes


@dataclass(frozen=True)
class ClockData:
    """Raw PLC clock fields returned by ``CMD=32 / 70 00``.

    Attributes:
        second: BCD-decoded seconds field.
        minute: BCD-decoded minutes field.
        hour: BCD-decoded hour field in 24-hour format.
        day: BCD-decoded day-of-month field.
        month: BCD-decoded month field. Some models can report ``0`` when the
            calendar part is unset.
        year_2digit: Lower two digits of the year.
        weekday: PLC weekday value where ``0`` means Sunday.
    """

    second: int
    minute: int
    hour: int
    day: int
    month: int
    year_2digit: int
    weekday: int

    def as_datetime(self, *, year_base: int = 2000) -> datetime:
        year = year_base + self.year_2digit
        return datetime(year, self.month, self.day, self.hour, self.minute, self.second)


@dataclass(frozen=True)
class CpuStatusData:
    """Decoded container for the 8 CPU-status bytes from ``CMD=32 / 11 00``.

    The ``data1``-``data8`` fields store the raw status bytes. The boolean
    properties expose the manual-defined flag meanings such as ``run``,
    ``alarm``, and ``program1_running``.
    """

    data1: int
    data2: int
    data3: int
    data4: int
    data5: int
    data6: int
    data7: int
    data8: int

    @property
    def raw_bytes(self) -> bytes:
        return bytes(
            [
                self.data1,
                self.data2,
                self.data3,
                self.data4,
                self.data5,
                self.data6,
                self.data7,
                self.data8,
            ]
        )

    @property
    def raw_bytes_hex(self) -> str:
        return " ".join(f"{b:02X}" for b in self.raw_bytes)

    def raw_hex(self) -> str:
        return self.raw_bytes_hex

    @property
    def run(self) -> bool:
        return bool(self.data1 & 0x80)

    @property
    def under_stop(self) -> bool:
        return bool(self.data1 & 0x40)

    @property
    def under_stop_request_continuity(self) -> bool:
        return bool(self.data1 & 0x20)

    @property
    def under_pseudo_stop(self) -> bool:
        return bool(self.data1 & 0x10)

    @property
    def debug_mode(self) -> bool:
        return bool(self.data1 & 0x08)

    @property
    def io_monitor_user_mode(self) -> bool:
        return bool(self.data1 & 0x04)

    @property
    def pc3_mode(self) -> bool:
        return bool(self.data1 & 0x02)

    @property
    def pc10_mode(self) -> bool:
        return bool(self.data1 & 0x01)

    @property
    def fatal_failure(self) -> bool:
        return bool(self.data2 & 0x80)

    @property
    def faint_failure(self) -> bool:
        return bool(self.data2 & 0x40)

    @property
    def alarm(self) -> bool:
        return bool(self.data2 & 0x20)

    @property
    def io_allocation_parameter_altered(self) -> bool:
        return bool(self.data2 & 0x08)

    @property
    def with_memory_card(self) -> bool:
        return bool(self.data2 & 0x04)

    @property
    def memory_card_operation(self) -> bool:
        return bool(self.data3 & 0x80)

    @property
    def write_protected_program_info(self) -> bool:
        return bool(self.data3 & 0x40)

    @property
    def read_protected_system_memory(self) -> bool:
        return bool(self.data4 & 0x80)

    @property
    def write_protected_system_memory(self) -> bool:
        return bool(self.data4 & 0x40)

    @property
    def read_protected_system_io(self) -> bool:
        return bool(self.data4 & 0x20)

    @property
    def write_protected_system_io(self) -> bool:
        return bool(self.data4 & 0x10)

    @property
    def trace(self) -> bool:
        return bool(self.data5 & 0x80)

    @property
    def scan_sampling_trace(self) -> bool:
        return bool(self.data5 & 0x40)

    @property
    def periodic_sampling_trace(self) -> bool:
        return bool(self.data5 & 0x20)

    @property
    def enable_detected(self) -> bool:
        return bool(self.data5 & 0x10)

    @property
    def trigger_detected(self) -> bool:
        return bool(self.data5 & 0x08)

    @property
    def one_scan_step(self) -> bool:
        return bool(self.data5 & 0x04)

    @property
    def one_block_step(self) -> bool:
        return bool(self.data5 & 0x02)

    @property
    def one_instruction_step(self) -> bool:
        return bool(self.data5 & 0x01)

    @property
    def io_offline(self) -> bool:
        return bool(self.data6 & 0x80)

    @property
    def remote_run_setting(self) -> bool:
        return bool(self.data6 & 0x40)

    @property
    def status_latch_setting(self) -> bool:
        return bool(self.data6 & 0x20)

    @property
    def write_priority_limited_program_info(self) -> bool:
        return bool(self.data7 & 0x40)

    @property
    def abnormal_write_flash_register(self) -> bool:
        return bool(self.data7 & 0x20)

    @property
    def under_writing_flash_register(self) -> bool:
        return bool(self.data7 & 0x10)

    @property
    def abnormal_write_equipment_info(self) -> bool:
        return bool(self.data7 & 0x08)

    @property
    def abnormal_writing_equipment_info(self) -> bool:
        return bool(self.data7 & 0x04)

    @property
    def abnormal_write_during_run(self) -> bool:
        return bool(self.data7 & 0x02)

    @property
    def under_writing_during_run(self) -> bool:
        return bool(self.data7 & 0x01)

    @property
    def program3_running(self) -> bool:
        return bool(self.data8 & 0x08)

    @property
    def program2_running(self) -> bool:
        return bool(self.data8 & 0x04)

    @property
    def program1_running(self) -> bool:
        return bool(self.data8 & 0x02)


def build_command(cmd: int, data: bytes) -> bytes:
    """Build a generic TOYOPUC command frame."""
    length = 1 + len(data)  # CMD + data
    ll = length & 0xFF
    lh = (length >> 8) & 0xFF
    return bytes([FT_COMMAND, 0x00, ll, lh, cmd]) + data


def parse_response(frame: bytes) -> ResponseFrame:
    """Parse a raw response frame into a `ResponseFrame`."""
    if len(frame) < 5:
        raise ToyopucProtocolError('Response too short')
    ft, rc, ll, lh, cmd = frame[:5]
    length = ll | (lh << 8)
    expected = 4 + length
    if len(frame) != expected:
        raise ToyopucProtocolError(
            f'Invalid length: expected {expected} bytes, got {len(frame)} bytes'
        )
    data = frame[5:]
    return ResponseFrame(ft=ft, rc=rc, cmd=cmd, data=data)


def pack_u16_le(value: int) -> bytes:
    return bytes([value & 0xFF, (value >> 8) & 0xFF])


def unpack_u16_le(data: bytes) -> List[int]:
    if len(data) % 2 != 0:
        raise ToyopucProtocolError('Word data length must be even')
    return [data[i] | (data[i + 1] << 8) for i in range(0, len(data), 2)]


def pack_ext_bit_spec(no: int, bit: int) -> int:
    if not 0 <= no <= 0x0F:
        raise ToyopucProtocolError('Extended bit No must fit in 4 bits')
    if not 0 <= bit <= 0x0F:
        raise ToyopucProtocolError('Extended bit position must fit in 4 bits')
    return ((bit & 0x0F) << 4) | (no & 0x0F)


def pack_bcd(value: int) -> int:
    if value < 0 or value > 99:
        raise ToyopucProtocolError('BCD value out of range')
    return ((value // 10) << 4) | (value % 10)


def unpack_bcd(value: int) -> int:
    hi = (value >> 4) & 0x0F
    lo = value & 0x0F
    if hi > 9 or lo > 9:
        raise ToyopucProtocolError(f'Invalid BCD byte: 0x{value:02X}')
    return hi * 10 + lo


def build_clock_read() -> bytes:
    """Build `CMD=32 / 70 00` clock-read command."""
    return build_command(0x32, bytes([0x70, 0x00]))


def build_cpu_status_read() -> bytes:
    """Build `CMD=32 / 11 00` CPU-status-read command."""
    return build_command(0x32, bytes([0x11, 0x00]))


def build_cpu_status_read_a0() -> bytes:
    """Build `CMD=A0 / 01 10` CPU-status-read command.

    This path is documented separately from `CMD=32 / 11 00` and is used by
    the FR/flash write completion flow. The current implementation exposes the
    payload as raw 8 status bytes until bit-level interpretation is confirmed.
    """
    return build_command(0xA0, bytes([0x01, 0x10]))


def build_clock_write(
    second: int,
    minute: int,
    hour: int,
    day: int,
    month: int,
    year_2digit: int,
    weekday: int,
) -> bytes:
    """Build `CMD=32 / 71 00` clock-write command from raw clock fields."""
    if not 0 <= weekday <= 6:
        raise ToyopucProtocolError('Weekday must be in range 0-6')
    data = bytes(
        [
            0x71,
            0x00,
            pack_bcd(second),
            pack_bcd(minute),
            pack_bcd(hour),
            pack_bcd(day),
            pack_bcd(month),
            pack_bcd(year_2digit),
            pack_bcd(weekday),
        ]
    )
    return build_command(0x32, data)


def parse_clock_data(data: bytes) -> ClockData:
    """Parse a clock-read payload into `ClockData`."""
    if len(data) != 9 or data[0] != 0x70 or data[1] != 0x00:
        raise ToyopucProtocolError('Clock read response must be 9 bytes starting with 70 00')
    return ClockData(
        second=unpack_bcd(data[2]),
        minute=unpack_bcd(data[3]),
        hour=unpack_bcd(data[4]),
        day=unpack_bcd(data[5]),
        month=unpack_bcd(data[6]),
        year_2digit=unpack_bcd(data[7]),
        weekday=unpack_bcd(data[8]),
    )


def parse_cpu_status_data(data: bytes) -> CpuStatusData:
    """Parse a CPU-status payload into `CpuStatusData`."""
    if len(data) != 10 or data[0] != 0x11 or data[1] != 0x00:
        raise ToyopucProtocolError('CPU status response must be 10 bytes starting with 11 00')
    return CpuStatusData(
        data1=data[2],
        data2=data[3],
        data3=data[4],
        data4=data[5],
        data5=data[6],
        data6=data[7],
        data7=data[8],
        data8=data[9],
    )


def parse_cpu_status_data_a0(data: bytes) -> CpuStatusData:
    """Parse a `CMD=A0 / 01 10` CPU-status payload into `CpuStatusData`."""
    if len(data) != 10 or data[0] != 0x01 or data[1] != 0x10:
        raise ToyopucProtocolError('A0 CPU status response must be 10 bytes starting with 01 10')
    return CpuStatusData(
        data1=data[2],
        data2=data[3],
        data3=data[4],
        data4=data[5],
        data5=data[6],
        data6=data[7],
        data7=data[8],
        data8=data[9],
    )


def parse_cpu_status_data_a0_raw(data: bytes) -> bytes:
    """Parse `CMD=A0 / 01 10` CPU-status payload and return raw status bytes."""
    return parse_cpu_status_data_a0(data).raw_bytes


def build_word_read(addr: int, count: int) -> bytes:
    return build_command(0x1C, pack_u16_le(addr) + pack_u16_le(count))


def build_word_write(addr: int, values: Iterable[int]) -> bytes:
    vals = list(values)
    data = pack_u16_le(addr) + b''.join(pack_u16_le(v) for v in vals)
    return build_command(0x1D, data)


def build_byte_read(addr: int, count: int) -> bytes:
    return build_command(0x1E, pack_u16_le(addr) + pack_u16_le(count))


def build_byte_write(addr: int, values: Iterable[int]) -> bytes:
    vals = bytes(values)
    return build_command(0x1F, pack_u16_le(addr) + vals)


def build_bit_read(addr: int) -> bytes:
    return build_command(0x20, pack_u16_le(addr))


def build_bit_write(addr: int, value: int) -> bytes:
    return build_command(0x21, pack_u16_le(addr) + bytes([1 if value else 0]))


def build_multi_word_read(addrs: Iterable[int]) -> bytes:
    data = b''.join(pack_u16_le(a) for a in addrs)
    return build_command(0x22, data)


def build_multi_word_write(pairs: Iterable[tuple[int, int]]) -> bytes:
    data = b''.join(pack_u16_le(a) + pack_u16_le(v) for a, v in pairs)
    return build_command(0x23, data)


def build_multi_byte_read(addrs: Iterable[int]) -> bytes:
    data = b''.join(pack_u16_le(a) for a in addrs)
    return build_command(0x24, data)


def build_multi_byte_write(pairs: Iterable[tuple[int, int]]) -> bytes:
    data = b''.join(pack_u16_le(a) + bytes([v & 0xFF]) for a, v in pairs)
    return build_command(0x25, data)


def build_ext_word_read(no: int, addr: int, count: int) -> bytes:
    return build_command(0x94, bytes([no & 0xFF]) + pack_u16_le(addr) + pack_u16_le(count))


def build_ext_word_write(no: int, addr: int, values: Iterable[int]) -> bytes:
    vals = list(values)
    data = bytes([no & 0xFF]) + pack_u16_le(addr) + b''.join(pack_u16_le(v) for v in vals)
    return build_command(0x95, data)


def build_ext_byte_read(no: int, addr: int, count: int) -> bytes:
    return build_command(0x96, bytes([no & 0xFF]) + pack_u16_le(addr) + pack_u16_le(count))


def build_ext_byte_write(no: int, addr: int, values: Iterable[int]) -> bytes:
    vals = bytes(values)
    data = bytes([no & 0xFF]) + pack_u16_le(addr) + vals
    return build_command(0x97, data)


def build_ext_multi_read(
    bit_points: Sequence[Tuple[int, int, int]],
    byte_points: Sequence[Tuple[int, int]],
    word_points: Sequence[Tuple[int, int]],
) -> bytes:
    data = bytearray()
    data.extend([len(bit_points) & 0xFF, len(byte_points) & 0xFF, len(word_points) & 0xFF])
    for no, bit, addr in bit_points:
        data.extend([pack_ext_bit_spec(no, bit)])
        data.extend(pack_u16_le(addr))
    for no, addr in byte_points:
        data.extend([no & 0xFF])
        data.extend(pack_u16_le(addr))
    for no, addr in word_points:
        data.extend([no & 0xFF])
        data.extend(pack_u16_le(addr))
    return build_command(0x98, bytes(data))


def build_ext_multi_write(
    bit_points: Sequence[Tuple[int, int, int, int]],
    byte_points: Sequence[Tuple[int, int, int]],
    word_points: Sequence[Tuple[int, int, int]],
) -> bytes:
    data = bytearray()
    data.extend([len(bit_points) & 0xFF, len(byte_points) & 0xFF, len(word_points) & 0xFF])
    for no, bit, addr, value in bit_points:
        data.extend([pack_ext_bit_spec(no, bit)])
        data.extend(pack_u16_le(addr))
        data.extend([value & 0x01])
    for no, addr, value in byte_points:
        data.extend([no & 0xFF])
        data.extend(pack_u16_le(addr))
        data.extend([value & 0xFF])
    for no, addr, value in word_points:
        data.extend([no & 0xFF])
        data.extend(pack_u16_le(addr))
        data.extend(pack_u16_le(value))
    return build_command(0x99, bytes(data))


# PC10 commands (C2-C6)
def build_pc10_block_read(addr32: int, count: int) -> bytes:
    # Address is 32-bit (low word, high word)
    return build_command(
        0xC2, pack_u16_le(addr32 & 0xFFFF) + pack_u16_le((addr32 >> 16) & 0xFFFF) + pack_u16_le(count)
    )


def build_pc10_block_write(addr32: int, data_bytes: bytes) -> bytes:
    return build_command(
        0xC3, pack_u16_le(addr32 & 0xFFFF) + pack_u16_le((addr32 >> 16) & 0xFFFF) + data_bytes
    )


def build_pc10_multi_read(payload: bytes) -> bytes:
    # Payload is already formatted per manual (CMD=C4)
    return build_command(0xC4, payload)


def build_pc10_multi_write(payload: bytes) -> bytes:
    # Payload is already formatted per manual (CMD=C5)
    return build_command(0xC5, payload)


def build_fr_register(ex_no: int) -> bytes:
    return build_command(0xCA, bytes([ex_no & 0xFF]))


# Relay command (CMD=60) helpers
def _normalize_inner_payload(inner_payload: bytes) -> bytes:
    """Ensure the payload is in `[LL, LH, CMD, ...]` form for relay wrapping."""
    if len(inner_payload) < 3:
        raise ValueError("inner payload must contain at least LL, LH, and CMD bytes")
    if inner_payload[0] == FT_COMMAND:
        if len(inner_payload) < 5:
            raise ValueError("inner command frame too short")
        if inner_payload[1] != 0x00:
            raise ValueError("relay inner frame must be a command request (RC=0x00)")
        trimmed = inner_payload[2:]
    else:
        trimmed = inner_payload

    if len(trimmed) < 3:
        raise ValueError("inner payload must contain LL, LH, and CMD bytes")
    inner_length = trimmed[0] | (trimmed[1] << 8)
    if inner_length + 2 != len(trimmed):
        raise ValueError(
            f"inner payload length mismatch: len={len(trimmed)} vs expected {inner_length + 2}"
        )
    return trimmed


def _frame_to_inner_payload(frame: bytes) -> bytes:
    if len(frame) < 5 or frame[0] != FT_COMMAND or frame[1] != 0x00:
        raise ValueError("relay frame must be a normal command request")
    return frame[2:]


def build_relay_command(link_no: int, station_no: int, inner_payload: bytes, *, enq: int = 0x05) -> bytes:
    """Build a single-hop relay command (`CMD=60`)."""
    inner = _normalize_inner_payload(inner_payload)
    data = bytes(
        [
            link_no & 0xFF,
            station_no & 0xFF,
            (station_no >> 8) & 0xFF,
            enq & 0xFF,
        ]
    ) + inner + b"\x00"
    return build_command(0x60, data)


def build_relay_nested(hops: Sequence[Tuple[int, int]], inner_payload: bytes) -> bytes:
    hops = list(hops)
    if not hops:
        raise ValueError("at least one relay hop is required")
    inner = _normalize_inner_payload(inner_payload)
    frame: Optional[bytes] = None
    for link_no, station_no in reversed(hops):
        frame = build_relay_command(link_no, station_no, inner)
        inner = _frame_to_inner_payload(frame)
    assert frame is not None
    return frame

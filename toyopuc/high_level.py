from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from .address import (
    ParsedAddress,
    encode_bit_address,
    encode_byte_address,
    encode_exno_byte_u32,
    encode_ext_no_address,
    encode_fr_word_addr32,
    encode_program_bit_address,
    encode_program_byte_address,
    encode_program_word_address,
    encode_word_address,
    parse_address,
    parse_prefixed_address,
)
from .client import (
    ToyopucClient,
    _pack_float32_low_word_first_words,
    _pack_uint32_low_word_first_words,
    _unpack_float32_low_word_first_words,
    _unpack_uint32_low_word_first_words,
)
from .errors import ToyopucProtocolError
from .profiles import ToyopucAddressingOptions, ToyopucDeviceProfiles
from .protocol import (
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
    build_pc10_multi_read,
    build_pc10_multi_write,
    build_word_read,
    build_word_write,
    unpack_u16_le,
)

_BASIC_BIT_AREAS = {"P", "K", "V", "T", "C", "L", "X", "Y", "M"}
_BASIC_WORD_AREAS = {"S", "N", "R", "D", "B"}
_EXT_BIT_AREAS = {
    "EP",
    "EK",
    "EV",
    "ET",
    "EC",
    "EL",
    "EX",
    "EY",
    "EM",
    "GX",
    "GY",
    "GM",
}
_EXT_WORD_AREAS = {"ES", "EN", "H", "U", "EB", "FR"}
_PREFIX_REQUIRED_AREAS = {
    "P",
    "K",
    "V",
    "T",
    "C",
    "L",
    "X",
    "Y",
    "M",
    "S",
    "N",
    "R",
    "D",
}
_PREFIX_PROGRAM_NO = {"P1": 0x01, "P2": 0x02, "P3": 0x03}
_EXT_BIT_SPECS = {
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

T = TypeVar("T")
_DEVICE_CACHE_MAX = 512
_RUN_PLAN_CACHE_MAX = 256


def _require(value: T | None, label: str) -> T:
    if value is None:
        raise ValueError(f"Resolved device missing {label}")
    return value


@dataclass(frozen=True)
class ResolvedDevice:
    """Resolved high-level device description."""

    text: str
    scheme: str
    unit: str
    area: str
    index: int
    digits: int = 0
    prefix: str | None = None
    high: bool = False
    packed: bool = False
    basic_addr: int | None = None
    no: int | None = None
    addr: int | None = None
    bit_no: int | None = None
    addr32: int | None = None


def _infer_unit_and_area(device: str) -> tuple[str | None, str, str]:
    text = device.strip().upper()
    prefix = None
    body = text
    if text.startswith(("P1-", "P2-", "P3-")):
        prefix, body = text.split("-", 1)

    if body.endswith("W"):
        parsed_packed_word = body[:-1]
        for area in sorted(_BASIC_BIT_AREAS | _EXT_BIT_AREAS, key=len, reverse=True):
            if parsed_packed_word.startswith(area):
                return prefix, area, "word"
        raise ValueError(f"Unknown packed word area: {device}")

    if body.endswith(("L", "H")):
        parsed_byte = body[:-1]
        for area in sorted(
            _BASIC_BIT_AREAS | _BASIC_WORD_AREAS | _EXT_BIT_AREAS | _EXT_WORD_AREAS,
            key=len,
            reverse=True,
        ):
            if parsed_byte.startswith(area):
                return prefix, area, "byte"
        raise ValueError(f"Unknown address area: {device}")

    for area in sorted(
        _EXT_BIT_AREAS | _EXT_WORD_AREAS | _BASIC_BIT_AREAS | _BASIC_WORD_AREAS,
        key=len,
        reverse=True,
    ):
        if body.startswith(area):
            if area in _EXT_BIT_AREAS or area in _BASIC_BIT_AREAS:
                return prefix, area, "bit"
            return prefix, area, "word"
    raise ValueError(f"Unknown address area: {device}")


def _pc10_u_addr32(index: int, *, byte: bool = False, high: bool = False) -> int:
    if index < 0x08000 or index > 0x1FFFF:
        raise ValueError("U PC10 range is 0x08000-0x1FFFF")
    block = index // 0x8000
    ex_no = 0x03 + block
    byte_addr = (index % 0x8000) * 2 + (1 if byte and high else 0)
    if byte and not high:
        byte_addr = (index % 0x8000) * 2
    return encode_exno_byte_u32(ex_no, byte_addr)


def _pc10_eb_addr32(index: int, *, byte: bool = False, high: bool = False) -> int:
    if index < 0x00000 or index > 0x3FFFF:
        raise ValueError("EB PC10 range is 0x00000-0x3FFFF")
    block = index // 0x8000
    ex_no = 0x10 + block
    byte_addr = (index % 0x8000) * 2 + (1 if byte and high else 0)
    if byte and not high:
        byte_addr = (index % 0x8000) * 2
    return encode_exno_byte_u32(ex_no, byte_addr)


def _resolve_ext_bit(parsed: ParsedAddress, text: str) -> ResolvedDevice:
    no, byte_base = _EXT_BIT_SPECS[parsed.area]
    return ResolvedDevice(
        text=text,
        scheme="ext-bit",
        unit="bit",
        area=parsed.area,
        index=parsed.index,
        digits=parsed.digits,
        no=no,
        bit_no=parsed.index & 0x07,
        addr=byte_base + (parsed.index >> 3),
    )


def _try_resolve_direct_pc10_bit(
    parsed: ParsedAddress,
    text: str,
    options: ToyopucAddressingOptions,
) -> ResolvedDevice | None:
    """Return a pc10-bit ResolvedDevice if the address falls in the PC10 upper bit range."""
    area = parsed.area
    if area in {"P", "V", "T", "C"}:
        if not (options.use_upper_bit_pc10 and 0x1000 <= parsed.index <= 0x17FF):
            return None
    elif area == "L":
        if not (options.use_upper_bit_pc10 and 0x1000 <= parsed.index <= 0x2FFF):
            return None
    elif area == "M":
        if not (options.use_upper_m_bit_pc10 and 0x1000 <= parsed.index <= 0x17FF):
            return None
    else:
        return None
    return ResolvedDevice(
        text=text,
        scheme="pc10-bit",
        unit="bit",
        area=parsed.area,
        index=parsed.index,
        digits=parsed.digits,
        packed=parsed.packed,
        addr32=encode_bit_address(parsed),
    )


def _try_resolve_direct_pc10_derived(
    parsed: ParsedAddress,
    text: str,
    options: ToyopucAddressingOptions,
) -> ResolvedDevice | None:
    """Return a pc10-word/byte device if the address is a derived bit-area PC10 access."""
    area = parsed.area
    if area in {"P", "V", "T", "C", "L"}:
        if not (options.use_upper_bit_pc10 and parsed.index >= 0x100):
            return None
    elif area == "M":
        if not (options.use_upper_m_bit_pc10 and parsed.index >= 0x100):
            return None
    else:
        return None

    if parsed.unit == "word":
        byte_addr = encode_word_address(parsed) * 2
        return ResolvedDevice(
            text=text,
            scheme="pc10-word",
            unit="word",
            area=parsed.area,
            index=parsed.index,
            digits=parsed.digits,
            packed=parsed.packed,
            addr32=encode_exno_byte_u32(0x00, byte_addr),
        )
    # byte
    byte_addr = encode_byte_address(parsed)
    return ResolvedDevice(
        text=text,
        scheme="pc10-byte",
        unit="byte",
        area=parsed.area,
        index=parsed.index,
        digits=parsed.digits,
        high=parsed.high,
        packed=parsed.packed,
        addr32=encode_exno_byte_u32(0x00, byte_addr),
    )


def _validate_profile_access(
    parsed: ParsedAddress,
    prefix: str | None,
    profile: str,
    device: str,
) -> None:
    """Validate that *parsed* is within the allowed ranges for *profile*.

    Raises ValueError with a descriptive message on violation.
    """
    descriptor = ToyopucDeviceProfiles.get_area_descriptor(parsed.area, profile)
    if parsed.packed and not descriptor.supports_packed_word:
        raise ValueError(f"W suffix is not available for area {parsed.area!r} in profile {profile!r}: {device}")
    expected_width = descriptor.get_address_width(parsed.unit, parsed.packed)
    if parsed.digits and parsed.digits > expected_width:
        raise ValueError(
            f"Address width out of range for profile {profile!r}: {device} (max {expected_width} hex digits)"
        )
    prefixed = prefix is not None
    ranges = descriptor.get_ranges_for_unit(prefixed, parsed.unit, parsed.packed)
    if not ranges:
        access_mode = "prefixed" if prefixed else "direct"
        raise ValueError(
            f"Area {parsed.area!r} is not available for {access_mode} access in profile {profile!r}: {device}"
        )
    if not any(r.contains(parsed.index) for r in ranges):
        raise ValueError(f"Address out of range for profile {profile!r}: {device}")


def resolve_device(
    device: str,
    options: ToyopucAddressingOptions | None = None,
    profile: str | None = None,
) -> ResolvedDevice:
    """Resolve a string device address into a normalized access descriptor.

    Args:
        device: Device address string (e.g. ``"P1-D0100"``, ``"P1-M1000"``).
        options: Addressing option flags that control PC10 routing.  When
            *None* and *profile* is given the profile's options are used;
            otherwise the Generic (all-True) defaults apply.
        profile: Optional device profile name (e.g.
            ``"TOYOPUC-Plus:Plus Standard mode"``).  When given, the address
            index is validated against the profile's supported ranges.
    """
    if options is None:
        if profile:
            options = ToyopucDeviceProfiles.from_name(profile).addressing_options
        else:
            options = ToyopucAddressingOptions()

    normalized_profile: str | None = ToyopucDeviceProfiles.from_name(profile).name if profile else None

    prefix, area, unit = _infer_unit_and_area(device)
    text = device.strip().upper()
    if prefix is None and area in _PREFIX_REQUIRED_AREAS:
        raise ValueError(f"{area} area requires P1-/P2-/P3- prefix: {text}")

    if prefix:
        ex_no, parsed = parse_prefixed_address(text, unit)
        if normalized_profile:
            _validate_profile_access(parsed, prefix, normalized_profile, device)
        if unit == "bit":
            bit_no, addr = encode_program_bit_address(parsed)
            addr32: int | None = None
            try:
                addr32 = encode_bit_address(parsed) | (ex_no << 19)
            except ValueError:
                addr32 = None
            return ResolvedDevice(
                text=text,
                scheme="program-bit",
                unit="bit",
                area=parsed.area,
                index=parsed.index,
                digits=parsed.digits,
                prefix=prefix,
                packed=parsed.packed,
                no=_PREFIX_PROGRAM_NO[prefix],
                bit_no=bit_no,
                addr=addr,
                addr32=addr32,
            )
        if unit == "word":
            if parsed.packed and parsed.area not in _BASIC_BIT_AREAS:
                raise ValueError(f"W suffix is only valid for bit-device families: {text}")
            return ResolvedDevice(
                text=text,
                scheme="program-word",
                unit="word",
                area=parsed.area,
                index=parsed.index,
                digits=parsed.digits,
                prefix=prefix,
                packed=parsed.packed,
                no=_PREFIX_PROGRAM_NO[prefix],
                addr=encode_program_word_address(parsed),
            )
        return ResolvedDevice(
            text=text,
            scheme="program-byte",
            unit="byte",
            area=parsed.area,
            index=parsed.index,
            digits=parsed.digits,
            prefix=prefix,
            high=parsed.high,
            packed=parsed.packed,
            no=_PREFIX_PROGRAM_NO[prefix],
            addr=encode_program_byte_address(parsed),
        )

    parsed = parse_address(text, unit)
    if normalized_profile:
        _validate_profile_access(parsed, prefix=None, profile=normalized_profile, device=device)

    if unit == "bit":
        pc10_bit = _try_resolve_direct_pc10_bit(parsed, text, options)
        if pc10_bit is not None:
            return pc10_bit
        if parsed.area in _BASIC_BIT_AREAS:
            return ResolvedDevice(
                text=text,
                scheme="basic-bit",
                unit="bit",
                area=parsed.area,
                index=parsed.index,
                digits=parsed.digits,
                packed=parsed.packed,
                basic_addr=encode_bit_address(parsed),
            )
        return _resolve_ext_bit(parsed, text)

    if unit == "word":
        if parsed.packed and parsed.area in _BASIC_WORD_AREAS | _EXT_WORD_AREAS:
            raise ValueError(f"W suffix is only valid for bit-device families: {text}")
        pc10_derived = _try_resolve_direct_pc10_derived(parsed, text, options)
        if pc10_derived is not None:
            return pc10_derived
        if parsed.area in _BASIC_WORD_AREAS | _BASIC_BIT_AREAS:
            return ResolvedDevice(
                text=text,
                scheme="basic-word",
                unit="word",
                area=parsed.area,
                index=parsed.index,
                digits=parsed.digits,
                packed=parsed.packed,
                basic_addr=encode_word_address(parsed),
            )
        if parsed.area == "U" and parsed.index >= 0x08000 and options.use_upper_u_pc10:
            return ResolvedDevice(
                text=text,
                scheme="pc10-word",
                unit="word",
                area=parsed.area,
                index=parsed.index,
                digits=parsed.digits,
                packed=parsed.packed,
                addr32=_pc10_u_addr32(parsed.index),
            )
        if parsed.area == "EB" and parsed.index <= 0x3FFFF and options.use_eb_pc10:
            return ResolvedDevice(
                text=text,
                scheme="pc10-word",
                unit="word",
                area=parsed.area,
                index=parsed.index,
                digits=parsed.digits,
                packed=parsed.packed,
                addr32=_pc10_eb_addr32(parsed.index),
            )
        if parsed.area == "FR" and options.use_fr_pc10:
            return ResolvedDevice(
                text=text,
                scheme="pc10-word",
                unit="word",
                area=parsed.area,
                index=parsed.index,
                digits=parsed.digits,
                packed=parsed.packed,
                addr32=encode_fr_word_addr32(parsed.index),
            )
        ext = encode_ext_no_address(parsed.area, parsed.index, "word")
        return ResolvedDevice(
            text=text,
            scheme="ext-word",
            unit="word",
            area=parsed.area,
            index=parsed.index,
            digits=parsed.digits,
            packed=parsed.packed,
            no=ext.no,
            addr=ext.addr,
        )

    # byte unit
    pc10_derived_byte = _try_resolve_direct_pc10_derived(parsed, text, options)
    if pc10_derived_byte is not None:
        return pc10_derived_byte
    if parsed.area in _BASIC_WORD_AREAS | _BASIC_BIT_AREAS:
        return ResolvedDevice(
            text=text,
            scheme="basic-byte",
            unit="byte",
            area=parsed.area,
            index=parsed.index,
            digits=parsed.digits,
            high=parsed.high,
            packed=parsed.packed,
            basic_addr=encode_byte_address(parsed),
        )
    if parsed.area == "U" and parsed.index >= 0x08000 and options.use_upper_u_pc10:
        return ResolvedDevice(
            text=text,
            scheme="pc10-byte",
            unit="byte",
            area=parsed.area,
            index=parsed.index,
            digits=parsed.digits,
            high=parsed.high,
            packed=parsed.packed,
            addr32=_pc10_u_addr32(parsed.index, byte=True, high=parsed.high),
        )
    if parsed.area == "EB" and parsed.index <= 0x3FFFF and options.use_eb_pc10:
        return ResolvedDevice(
            text=text,
            scheme="pc10-byte",
            unit="byte",
            area=parsed.area,
            index=parsed.index,
            digits=parsed.digits,
            high=parsed.high,
            packed=parsed.packed,
            addr32=_pc10_eb_addr32(parsed.index, byte=True, high=parsed.high),
        )
    if parsed.area == "FR":
        raise ValueError("FR does not support byte access; use word access via PC10 block commands")

    ext = encode_ext_no_address(parsed.area, parsed.index * 2 + (1 if parsed.high else 0), "byte")
    return ResolvedDevice(
        text=text,
        scheme="ext-byte",
        unit="byte",
        area=parsed.area,
        index=parsed.index,
        digits=parsed.digits,
        high=parsed.high,
        packed=parsed.packed,
        no=ext.no,
        addr=ext.addr,
    )


def _read_pc10_multi_bits(client: ToyopucClient, addrs32: Sequence[int]) -> list[int]:
    payload = bytearray([len(addrs32) & 0xFF, 0x00, 0x00, 0x00])
    for addr32 in addrs32:
        payload.extend(addr32.to_bytes(4, "little"))
    data = client.pc10_multi_read(bytes(payload))[4:]
    return [(data[i // 8] >> (i % 8)) & 0x01 for i in range(len(addrs32))]


def _parse_ext_multi_bit_data(data: bytes, count: int) -> list[int]:
    need = (count + 7) // 8
    if len(data) < need:
        raise ToyopucProtocolError("Extended multi-bit response too short")
    return [(data[i // 8] >> (i % 8)) & 0x01 for i in range(count)]


def _build_pc10_multi_word_read_payload(addrs32: Sequence[int]) -> bytes:
    payload = bytearray(4 + len(addrs32) * 4)
    payload[2] = len(addrs32) & 0xFF
    for i, addr32 in enumerate(addrs32):
        payload[4 + i * 4 : 8 + i * 4] = addr32.to_bytes(4, "little")
    return bytes(payload)


def _parse_pc10_multi_word_data(data: bytes, count: int) -> list[int]:
    need = 4 + count * 2
    if len(data) < need:
        raise ToyopucProtocolError("PC10 multi-word response too short")
    return [int.from_bytes(data[4 + i * 2 : 6 + i * 2], "little") for i in range(count)]


def _read_pc10_multi_words(client: ToyopucClient, addrs32: Sequence[int]) -> list[int]:
    data = client.pc10_multi_read(_build_pc10_multi_word_read_payload(addrs32))
    return _parse_pc10_multi_word_data(data, len(addrs32))


def _read_pc10_block_word(client: ToyopucClient, addr32: int) -> int:
    data = client.pc10_block_read(addr32, 2)
    return int.from_bytes(data[:2], "little")


def _write_pc10_block_word(client: ToyopucClient, addr32: int, value: int) -> None:
    client.pc10_block_write(addr32, int(value & 0xFFFF).to_bytes(2, "little"))


def _pack_pc10_multi_bit_payload(addr32_values: Sequence[tuple[int, int]]) -> bytes:
    payload = bytearray([len(addr32_values) & 0xFF, 0x00, 0x00, 0x00])
    for addr32, _ in addr32_values:
        payload.extend(addr32.to_bytes(4, "little"))
    bit_bytes = bytearray((len(addr32_values) + 7) // 8)
    for i, (_, value) in enumerate(addr32_values):
        if int(value) & 0x01:
            bit_bytes[i // 8] |= 1 << (i % 8)
    payload.extend(bit_bytes)
    return bytes(payload)


def _pack_pc10_multi_word_payload(addr32_values: Sequence[tuple[int, int]]) -> bytes:
    payload = bytearray(4 + len(addr32_values) * 4 + len(addr32_values) * 2)
    payload[2] = len(addr32_values) & 0xFF
    for i, (addr32, _) in enumerate(addr32_values):
        payload[4 + i * 4 : 8 + i * 4] = addr32.to_bytes(4, "little")
    values_offset = 4 + len(addr32_values) * 4
    for i, (_, value) in enumerate(addr32_values):
        payload[values_offset + i * 2 : values_offset + i * 2 + 2] = int(value & 0xFFFF).to_bytes(2, "little")
    return bytes(payload)


def _raise_generic_fr_write_error() -> None:
    raise ValueError("Generic FR writes are disabled; use write_fr(..., commit=False|True) or commit_fr() explicitly")


# ---------------------------------------------------------------------------
# Batch-read helpers (module-level, scheme-based grouping)
# ---------------------------------------------------------------------------

_SCHEME_BATCH_KEY: dict[str, str] = {
    "basic-word": "basic-word",
    "basic-byte": "basic-byte",
    "ext-word": "ext-word",
    "program-word": "ext-word",
    "ext-byte": "ext-byte",
    "program-byte": "ext-byte",
    "ext-bit": "ext-bit",
    "program-bit": "ext-bit",
    "pc10-bit": "pc10-bit",
    "pc10-word": "pc10-word",
    "pc10-byte": "pc10-byte",
}


def _batch_key(resolved: ResolvedDevice) -> str | None:
    return _SCHEME_BATCH_KEY.get(resolved.scheme)


def _pc10_block(resolved: ResolvedDevice) -> int | None:
    if resolved.addr32 is not None and resolved.scheme in (
        "pc10-bit",
        "pc10-word",
        "pc10-byte",
    ):
        return resolved.addr32 >> 16
    return None


def _batch_run_length(devices: list[ResolvedDevice], start: int, split_pc10: bool) -> int:
    key = _batch_key(devices[start])
    if key is None:
        return 1
    pc10_blk = _pc10_block(devices[start]) if split_pc10 else None
    idx = start + 1
    while idx < len(devices):
        if _batch_key(devices[idx]) != key:
            break
        if split_pc10 and _pc10_block(devices[idx]) != pc10_blk:
            break
        idx += 1
    return idx - start


def _is_consecutive_basic(devices: list[ResolvedDevice], step: int = 1) -> bool:
    if not devices:
        return True
    start = devices[0].basic_addr
    if start is None:
        return False
    return all(d.basic_addr == start + i * step for i, d in enumerate(devices))


def _is_consecutive_ext_word(devices: list[ResolvedDevice]) -> bool:
    if not devices:
        return True
    no0 = devices[0].no
    addr0 = devices[0].addr
    if no0 is None or addr0 is None:
        return False
    return all(d.no == no0 and d.addr == addr0 + i for i, d in enumerate(devices))


def _is_consecutive_pc10_word(devices: list[ResolvedDevice]) -> bool:
    if not devices:
        return True
    a0 = devices[0].addr32
    if a0 is None:
        return False
    return all(d.addr32 == a0 + i * 2 for i, d in enumerate(devices))


def _contains_packed_pc10_word_device(devices: list[ResolvedDevice]) -> bool:
    return any(d.scheme == "pc10-word" and d.unit == "word" and d.packed for d in devices)


def _pc10_word_segment_length(devices: list[ResolvedDevice], start: int) -> int:
    a0 = _require(devices[start].addr32, "pc10 addr32")
    run = 1
    while start + run < len(devices):
        if _require(devices[start + run].addr32, "pc10 addr32") != a0 + run * 2:
            break
        run += 1
    return run


class ToyopucDeviceClient(ToyopucClient):
    """High-level client that accepts string device addresses."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._resolved_device_cache: dict[str, ResolvedDevice] = {}
        self._run_plan_cache: dict[tuple[bool, tuple[ResolvedDevice, ...]], tuple[int, ...]] = {}

    def _get_run_plan(self, devices: list[ResolvedDevice], split_pc10: bool) -> tuple[int, ...]:
        key = (split_pc10, tuple(devices))
        plan = self._run_plan_cache.get(key)
        if plan is None:
            lengths: list[int] = []
            idx = 0
            while idx < len(devices):
                run = _batch_run_length(devices, idx, split_pc10)
                lengths.append(run)
                idx += run
            plan = tuple(lengths)
            if len(self._run_plan_cache) >= _RUN_PLAN_CACHE_MAX:
                self._run_plan_cache.clear()
            self._run_plan_cache[key] = plan
        return plan

    def resolve_device(self, device: str) -> ResolvedDevice:
        """Resolve a string address into a `ResolvedDevice`."""
        key = device.strip().upper()
        resolved = self._resolved_device_cache.get(key)
        if resolved is None:
            resolved = resolve_device(key)
            if len(self._resolved_device_cache) >= _DEVICE_CACHE_MAX:
                self._resolved_device_cache.clear()
            self._resolved_device_cache[key] = resolved
        return resolved

    def relay_read(
        self,
        hops: str | Iterable[tuple[int, int]],
        device: str | ResolvedDevice,
        count: int = 1,
    ) -> object:
        """Read one item or a contiguous sequence through relay hops."""
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        if count < 1:
            raise ValueError("count must be >= 1")
        if count == 1:
            return self._relay_read_resolved_device(hops, resolved)
        return self._relay_read_runs(hops, self._seq_devices(resolved, count), split_pc10=True)

    def relay_write(
        self,
        hops: str | Iterable[tuple[int, int]],
        device: str | ResolvedDevice,
        value: Any,
    ) -> None:
        """Write one item or a contiguous sequence through relay hops."""
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        if resolved.unit == "bit":
            if isinstance(value, (list, tuple)):
                for i, item in enumerate(value):
                    self._relay_write_resolved_device(hops, self._offset_resolved_device(resolved, i), item)
                return
            self._relay_write_resolved_device(hops, resolved, value)
            return

        if isinstance(value, (bytes, bytearray)):
            for i, item in enumerate(value):
                self._relay_write_resolved_device(hops, self._offset_resolved_device(resolved, i), item)
            return
        if isinstance(value, (list, tuple)):
            for i, item in enumerate(value):
                self._relay_write_resolved_device(hops, self._offset_resolved_device(resolved, i), item)
            return
        self._relay_write_resolved_device(hops, resolved, value)

    def relay_read_words(
        self,
        hops: str | Iterable[tuple[int, int]],
        device: int | str | ResolvedDevice,
        count: int = 1,
    ) -> list[int]:
        """Read one or more word devices through relay hops."""
        if isinstance(device, int):
            return super().relay_read_words(hops, device, count)
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        if resolved.unit != "word":
            raise ValueError("relay_read_words() requires a word device")
        values = self.relay_read(hops, resolved, count)
        if isinstance(values, list):
            return [int(item) for item in values]
        return [int(values)]  # type: ignore

    def relay_write_words(
        self,
        hops: str | Iterable[tuple[int, int]],
        device: int | str | ResolvedDevice,
        value: Iterable[int] | int,
    ) -> None:
        """Write one or more word devices through relay hops."""
        if isinstance(device, int):
            if isinstance(value, int):
                super().relay_write_words(hops, device, [value])
            else:
                super().relay_write_words(hops, device, value)
            return
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        if resolved.unit != "word":
            raise ValueError("relay_write_words() requires a word device")
        self.relay_write(hops, resolved, value)

    def relay_read_many(
        self,
        hops: str | Iterable[tuple[int, int]],
        devices: Sequence[str | ResolvedDevice],
    ) -> list[object]:
        """Read multiple devices through relay hops with batching when possible."""
        resolved = [self.resolve_device(d) if isinstance(d, str) else d for d in devices]
        return self._relay_read_runs(hops, resolved, split_pc10=False)

    def relay_write_many(
        self,
        hops: str | Iterable[tuple[int, int]],
        items: Mapping[str | ResolvedDevice, object],
    ) -> None:
        """Write multiple devices through relay hops with batching when possible."""
        resolved_items = []
        for device, value in items.items():
            resolved = self.resolve_device(device) if isinstance(device, str) else device
            resolved_items.append((resolved, value))
        if not resolved_items:
            return
        self._relay_write_runs(
            hops,
            [resolved for resolved, _ in resolved_items],
            [value for _, value in resolved_items],
            split_pc10=True,
        )

    def read_fr(self, device: str | ResolvedDevice, count: int = 1) -> Any:
        """Read one or more FR words using the dedicated FR path."""
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        if resolved.area != "FR" or resolved.unit != "word":
            raise ValueError("read_fr() requires an FR word device such as FR000000")
        values = self.read_fr_words(resolved.index, count)
        return values[0] if count == 1 else values

    def relay_read_fr(
        self,
        hops: str | Iterable[tuple[int, int]],
        device: str | ResolvedDevice,
        count: int = 1,
    ) -> Any:
        """Read one or more FR words through relay hops."""
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        if resolved.area != "FR" or resolved.unit != "word":
            raise ValueError("relay_read_fr() requires an FR word device such as FR000000")
        return self.relay_read(hops, resolved, count)

    def write_fr(
        self,
        device: str | ResolvedDevice,
        value: Any,
        *,
        commit: bool = False,
        wait: bool | None = None,
        timeout: float = 30.0,
        poll_interval: float = 0.2,
    ) -> None:
        """Write one or more FR words, optionally committing and waiting."""
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        if resolved.area != "FR" or resolved.unit != "word":
            raise ValueError("write_fr() requires an FR word device such as FR000000")
        if isinstance(value, (list, tuple)):
            values = [int(item) for item in value]
        else:
            values = [int(value)]
        should_wait = bool(commit) if wait is None else bool(wait)
        self.write_fr_words_ex(
            resolved.index,
            values,
            commit=commit,
            wait=should_wait,
            timeout=timeout,
            poll_interval=poll_interval,
        )

    def relay_write_fr(
        self,
        hops: str | Iterable[tuple[int, int]],
        device: str | ResolvedDevice,
        value: Any,
        *,
        commit: bool = False,
        wait: bool | None = None,
        timeout: float = 30.0,
        poll_interval: float = 0.2,
    ) -> None:
        """Write one or more FR words through relay hops, optionally committing."""
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        if resolved.area != "FR" or resolved.unit != "word":
            raise ValueError("relay_write_fr() requires an FR word device such as FR000000")
        if isinstance(value, (list, tuple)):
            values = [int(item) for item in value]
        else:
            values = [int(value)]
        should_wait = bool(commit) if wait is None else bool(wait)
        self.relay_write_fr_words_ex(
            hops,
            resolved.index,
            values,
            commit=commit,
            wait=should_wait,
            timeout=timeout,
            poll_interval=poll_interval,
        )

    def commit_fr(
        self,
        device: str | ResolvedDevice,
        count: int = 1,
        *,
        wait: bool = False,
        timeout: float = 30.0,
        poll_interval: float = 0.2,
    ) -> None:
        """Commit every FR block touched by the given FR word range."""
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        if resolved.area != "FR" or resolved.unit != "word":
            raise ValueError("commit_fr() requires an FR word device such as FR000000")
        self.commit_fr_range(
            resolved.index,
            count,
            wait=wait,
            timeout=timeout,
            poll_interval=poll_interval,
        )

    def relay_commit_fr(
        self,
        hops: str | Iterable[tuple[int, int]],
        device: str | ResolvedDevice,
        count: int = 1,
        *,
        wait: bool = False,
        timeout: float = 30.0,
        poll_interval: float = 0.2,
    ) -> None:
        """Commit every FR block touched by the given FR word range through relay hops."""
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        if resolved.area != "FR" or resolved.unit != "word":
            raise ValueError("relay_commit_fr() requires an FR word device such as FR000000")
        self.relay_commit_fr_range(
            hops,
            resolved.index,
            count,
            wait=wait,
            timeout=timeout,
            poll_interval=poll_interval,
        )

    def read(self, device: str | ResolvedDevice, count: int = 1) -> Any:
        """Read one item or a contiguous sequence from a device address."""
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        if count < 1:
            raise ValueError("count must be >= 1")
        if count == 1:
            return self._read_resolved_device(resolved)
        return self._read_runs(self._seq_devices(resolved, count), split_pc10=True)

    def write(self, device: str | ResolvedDevice, value: Any) -> None:
        """Write one item or a contiguous sequence to a device address."""
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        if resolved.area == "FR":
            _raise_generic_fr_write_error()
        if resolved.unit == "bit":
            if isinstance(value, (list, tuple)):
                for i, item in enumerate(value):
                    self._write_resolved_device(self._offset_resolved_device(resolved, i), item)
                return
            self._write_resolved_device(resolved, value)
            return

        if isinstance(value, (bytes, bytearray)):
            for i, item in enumerate(value):
                self._write_resolved_device(self._offset_resolved_device(resolved, i), item)
            return
        if isinstance(value, (list, tuple)):
            for i, item in enumerate(value):
                self._write_resolved_device(self._offset_resolved_device(resolved, i), item)
            return
        self._write_resolved_device(resolved, value)

    def read_many(self, devices: Sequence[str | ResolvedDevice]) -> list[object]:
        """Read multiple devices with batching when possible and preserve input order."""
        resolved = [self.resolve_device(d) if isinstance(d, str) else d for d in devices]
        return self._read_runs(resolved, split_pc10=False)

    def write_many(self, items: Mapping[str | ResolvedDevice, object]) -> None:
        """Write multiple devices with batching when possible in mapping iteration order."""
        resolved_items = []
        for device, value in items.items():
            resolved = self.resolve_device(device) if isinstance(device, str) else device
            if resolved.area == "FR":
                _raise_generic_fr_write_error()
            resolved_items.append((resolved, value))
        if not resolved_items:
            return
        self._write_runs(
            [resolved for resolved, _ in resolved_items],
            [value for _, value in resolved_items],
            split_pc10=True,
        )

    def read_dword(self, device: int | str | ResolvedDevice) -> int:
        """Read one 32-bit value from two consecutive word devices."""
        return self.read_dwords(device, 1)[0]

    def write_dword(self, device: int | str | ResolvedDevice, value: int) -> None:
        """Write one 32-bit value to two consecutive word devices."""
        self.write_dwords(device, [value])

    def read_dwords(
        self, device: int | str | ResolvedDevice, count: int, *, atomic_transfer: bool = False
    ) -> list[int]:
        """Read one or more 32-bit values from consecutive word devices."""
        if isinstance(device, int):
            return super().read_dwords(device, count)
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        self._ensure_word_device(resolved, "read_dwords()")
        if count < 1:
            raise ValueError("count must be >= 1")
        words = self._read_resolved_word_values(resolved, count * 2, split_pc10=not atomic_transfer)
        return _unpack_uint32_low_word_first_words(words)

    def write_dwords(
        self, device: int | str | ResolvedDevice, values: Iterable[int], *, atomic_transfer: bool = False
    ) -> None:
        """Write one or more 32-bit values to consecutive word devices."""
        if isinstance(device, int):
            return super().write_dwords(device, values)
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        self._ensure_word_device(resolved, "write_dwords()")
        self._write_resolved_word_values(
            resolved, _pack_uint32_low_word_first_words(values), split_pc10=not atomic_transfer
        )

    def read_float32(self, device: int | str | ResolvedDevice) -> float:
        """Read one IEEE-754 float32 from two consecutive word devices."""
        return self.read_float32s(device, 1)[0]

    def write_float32(self, device: int | str | ResolvedDevice, value: float) -> None:
        """Write one IEEE-754 float32 to two consecutive word devices."""
        self.write_float32s(device, [value])

    def read_float32s(
        self, device: int | str | ResolvedDevice, count: int, *, atomic_transfer: bool = False
    ) -> list[float]:
        """Read one or more IEEE-754 float32 values from consecutive word devices."""
        if isinstance(device, int):
            return super().read_float32s(device, count)
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        self._ensure_word_device(resolved, "read_float32s()")
        if count < 1:
            raise ValueError("count must be >= 1")
        words = self._read_resolved_word_values(resolved, count * 2, split_pc10=not atomic_transfer)
        return _unpack_float32_low_word_first_words(words)

    def write_float32s(
        self, device: int | str | ResolvedDevice, values: Iterable[float], *, atomic_transfer: bool = False
    ) -> None:
        """Write one or more IEEE-754 float32 values to consecutive word devices."""
        if isinstance(device, int):
            return super().write_float32s(device, values)
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        self._ensure_word_device(resolved, "write_float32s()")
        self._write_resolved_word_values(
            resolved, _pack_float32_low_word_first_words(values), split_pc10=not atomic_transfer
        )

    def relay_read_dword(
        self,
        hops: str | Iterable[tuple[int, int]],
        device: str | ResolvedDevice,
    ) -> int:
        """Read one 32-bit value through relay hops."""
        return self.relay_read_dwords(hops, device, 1)[0]

    def relay_write_dword(
        self,
        hops: str | Iterable[tuple[int, int]],
        device: str | ResolvedDevice,
        value: int,
    ) -> None:
        """Write one 32-bit value through relay hops."""
        self.relay_write_dwords(hops, device, [value])

    def relay_read_dwords(
        self,
        hops: str | Iterable[tuple[int, int]],
        device: str | ResolvedDevice,
        count: int,
        *,
        atomic_transfer: bool = False,
    ) -> list[int]:
        """Read one or more 32-bit values through relay hops."""
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        self._ensure_word_device(resolved, "relay_read_dwords()")
        if count < 1:
            raise ValueError("count must be >= 1")
        words = self._relay_read_resolved_word_values(hops, resolved, count * 2, split_pc10=not atomic_transfer)
        return _unpack_uint32_low_word_first_words(words)

    def relay_write_dwords(
        self,
        hops: str | Iterable[tuple[int, int]],
        device: str | ResolvedDevice,
        values: Iterable[int],
        *,
        atomic_transfer: bool = False,
    ) -> None:
        """Write one or more 32-bit values through relay hops."""
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        self._ensure_word_device(resolved, "relay_write_dwords()")
        self._relay_write_resolved_word_values(
            hops, resolved, _pack_uint32_low_word_first_words(values), split_pc10=not atomic_transfer
        )

    def relay_read_float32(
        self,
        hops: str | Iterable[tuple[int, int]],
        device: str | ResolvedDevice,
    ) -> float:
        """Read one IEEE-754 float32 through relay hops."""
        return self.relay_read_float32s(hops, device, 1)[0]

    def relay_write_float32(
        self,
        hops: str | Iterable[tuple[int, int]],
        device: str | ResolvedDevice,
        value: float,
    ) -> None:
        """Write one IEEE-754 float32 through relay hops."""
        self.relay_write_float32s(hops, device, [value])

    def relay_read_float32s(
        self,
        hops: str | Iterable[tuple[int, int]],
        device: str | ResolvedDevice,
        count: int,
        *,
        atomic_transfer: bool = False,
    ) -> list[float]:
        """Read one or more IEEE-754 float32 values through relay hops."""
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        self._ensure_word_device(resolved, "relay_read_float32s()")
        if count < 1:
            raise ValueError("count must be >= 1")
        words = self._relay_read_resolved_word_values(hops, resolved, count * 2, split_pc10=not atomic_transfer)
        return _unpack_float32_low_word_first_words(words)

    def relay_write_float32s(
        self,
        hops: str | Iterable[tuple[int, int]],
        device: str | ResolvedDevice,
        values: Iterable[float],
        *,
        atomic_transfer: bool = False,
    ) -> None:
        """Write one or more IEEE-754 float32 values through relay hops."""
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        self._ensure_word_device(resolved, "relay_write_float32s()")
        self._relay_write_resolved_word_values(
            hops, resolved, _pack_float32_low_word_first_words(values), split_pc10=not atomic_transfer
        )

    def _ensure_word_device(self, resolved: ResolvedDevice, method_name: str) -> None:
        if resolved.unit != "word":
            raise ValueError(f"{method_name} requires a word device")

    def _read_resolved_word_values(
        self, resolved: ResolvedDevice, word_count: int, split_pc10: bool = True
    ) -> list[int]:
        if word_count < 1:
            raise ValueError("word_count must be >= 1")
        if word_count == 1:
            return [int(self._read_resolved_device(resolved)) & 0xFFFF]
        return [int(v) & 0xFFFF for v in self._read_runs(self._seq_devices(resolved, word_count), split_pc10)]

    def _relay_read_resolved_word_values(
        self,
        hops: str | Iterable[tuple[int, int]],
        resolved: ResolvedDevice,
        word_count: int,
        split_pc10: bool = True,
    ) -> list[int]:
        if word_count < 1:
            raise ValueError("word_count must be >= 1")
        if word_count == 1:
            return [int(self._relay_read_resolved_device(hops, resolved)) & 0xFFFF]
        runs = self._relay_read_runs(hops, self._seq_devices(resolved, word_count), split_pc10)
        return [int(v) & 0xFFFF for v in runs]

    def _write_resolved_word_values(
        self, resolved: ResolvedDevice, word_values: Iterable[int], split_pc10: bool = True
    ) -> None:
        values = [int(value) & 0xFFFF for value in word_values]
        if not values:
            raise ValueError("values must not be empty")
        if resolved.area == "FR":
            self.write_fr(resolved, values)
            return
        self._write_runs(self._seq_devices(resolved, len(values)), values, split_pc10)

    def _relay_write_resolved_word_values(
        self,
        hops: str | Iterable[tuple[int, int]],
        resolved: ResolvedDevice,
        word_values: Iterable[int],
        split_pc10: bool = True,
    ) -> None:
        values = [int(value) & 0xFFFF for value in word_values]
        if not values:
            raise ValueError("values must not be empty")
        if resolved.area == "FR":
            self.relay_write_fr(hops, resolved, values)
            return
        self._relay_write_runs(hops, self._seq_devices(resolved, len(values)), values, split_pc10)

    def _read_resolved_device(self, resolved: ResolvedDevice) -> Any:
        if resolved.scheme == "basic-bit":
            addr = _require(resolved.basic_addr, "basic_addr")
            return self.read_bit(addr)
        if resolved.scheme == "basic-word":
            addr = _require(resolved.basic_addr, "basic_addr")
            return self.read_words(addr, 1)[0]
        if resolved.scheme == "basic-byte":
            addr = _require(resolved.basic_addr, "basic_addr")
            return self.read_bytes(addr, 1)[0]
        if resolved.scheme == "program-bit":
            no = _require(resolved.no, "program number")
            bit_no = _require(resolved.bit_no, "program bit")
            addr = _require(resolved.addr, "program addr")
            return bool(self.read_ext_multi([(no, bit_no, addr)], [], [])[0] & 0x01)
        if resolved.scheme == "program-word":
            no = _require(resolved.no, "program number")
            addr = _require(resolved.addr, "program addr")
            return self.read_ext_words(no, addr, 1)[0]
        if resolved.scheme == "program-byte":
            no = _require(resolved.no, "program number")
            addr = _require(resolved.addr, "program addr")
            return self.read_ext_bytes(no, addr, 1)[0]
        if resolved.scheme == "ext-bit":
            no = _require(resolved.no, "extended number")
            bit_no = _require(resolved.bit_no, "extended bit")
            addr = _require(resolved.addr, "extended addr")
            return bool(self.read_ext_multi([(no, bit_no, addr)], [], [])[0] & 0x01)
        if resolved.scheme == "ext-word":
            no = _require(resolved.no, "extended number")
            addr = _require(resolved.addr, "extended addr")
            return self.read_ext_words(no, addr, 1)[0]
        if resolved.scheme == "ext-byte":
            no = _require(resolved.no, "extended number")
            addr = _require(resolved.addr, "extended addr")
            return self.read_ext_bytes(no, addr, 1)[0]
        if resolved.scheme == "pc10-bit":
            addr32 = _require(resolved.addr32, "pc10 addr32")
            return bool(_read_pc10_multi_bits(self, [addr32])[0])
        if resolved.scheme == "pc10-word":
            addr32 = _require(resolved.addr32, "pc10 addr32")
            return _read_pc10_block_word(self, addr32)
        if resolved.scheme == "pc10-byte":
            addr32 = _require(resolved.addr32, "pc10 addr32")
            return self.pc10_block_read(addr32, 1)[0]
        raise ValueError(f"Unsupported resolved scheme: {resolved.scheme}")

    def _relay_read_resolved_device(self, hops: str | Iterable[tuple[int, int]], resolved: ResolvedDevice) -> Any:
        if resolved.scheme == "basic-bit":
            resp = self.send_via_relay(hops, build_bit_read(_require(resolved.basic_addr, "basic_addr")))
            if resp.cmd != 0x20:
                raise ToyopucProtocolError("Unexpected CMD in relay bit-read response")
            if len(resp.data) != 1:
                raise ToyopucProtocolError("Relay bit-read response must be 1 byte")
            return bool(resp.data[0] & 0x01)
        if resolved.scheme == "basic-word":
            resp = self.send_via_relay(hops, build_word_read(_require(resolved.basic_addr, "basic_addr"), 1))
            if resp.cmd != 0x1C:
                raise ToyopucProtocolError("Unexpected CMD in relay word-read response")
            return unpack_u16_le(resp.data)[0]
        if resolved.scheme == "basic-byte":
            resp = self.send_via_relay(hops, build_byte_read(_require(resolved.basic_addr, "basic_addr"), 1))
            if resp.cmd != 0x1E:
                raise ToyopucProtocolError("Unexpected CMD in relay byte-read response")
            if len(resp.data) != 1:
                raise ToyopucProtocolError("Relay byte-read response must be 1 byte")
            return resp.data[0]
        if resolved.scheme == "program-bit":
            resp = self.send_via_relay(
                hops,
                build_ext_multi_read(
                    [
                        (
                            _require(resolved.no, "program number"),
                            _require(resolved.bit_no, "program bit"),
                            _require(resolved.addr, "program addr"),
                        )
                    ],
                    [],
                    [],
                ),
            )
            if resp.cmd != 0x98:
                raise ToyopucProtocolError("Unexpected CMD in relay multi-read response")
            if not resp.data:
                raise ToyopucProtocolError("Relay multi-read response missing bit payload")
            return bool(resp.data[0] & 0x01)
        if resolved.scheme == "program-word":
            resp = self.send_via_relay(
                hops,
                build_ext_word_read(
                    _require(resolved.no, "program number"),
                    _require(resolved.addr, "program addr"),
                    1,
                ),
            )
            if resp.cmd != 0x94:
                raise ToyopucProtocolError("Unexpected CMD in relay ext word-read response")
            return unpack_u16_le(resp.data)[0]
        if resolved.scheme == "program-byte":
            resp = self.send_via_relay(
                hops,
                build_ext_byte_read(
                    _require(resolved.no, "program number"),
                    _require(resolved.addr, "program addr"),
                    1,
                ),
            )
            if resp.cmd != 0x96:
                raise ToyopucProtocolError("Unexpected CMD in relay ext byte-read response")
            if len(resp.data) != 1:
                raise ToyopucProtocolError("Relay ext byte-read response must be 1 byte")
            return resp.data[0]
        if resolved.scheme == "ext-bit":
            resp = self.send_via_relay(
                hops,
                build_ext_multi_read(
                    [
                        (
                            _require(resolved.no, "extended number"),
                            _require(resolved.bit_no, "extended bit"),
                            _require(resolved.addr, "extended addr"),
                        )
                    ],
                    [],
                    [],
                ),
            )
            if resp.cmd != 0x98:
                raise ToyopucProtocolError("Unexpected CMD in relay multi-read response")
            if not resp.data:
                raise ToyopucProtocolError("Relay multi-read response missing bit payload")
            return bool(resp.data[0] & 0x01)
        if resolved.scheme == "ext-word":
            resp = self.send_via_relay(
                hops,
                build_ext_word_read(
                    _require(resolved.no, "extended number"),
                    _require(resolved.addr, "extended addr"),
                    1,
                ),
            )
            if resp.cmd != 0x94:
                raise ToyopucProtocolError("Unexpected CMD in relay ext word-read response")
            return unpack_u16_le(resp.data)[0]
        if resolved.scheme == "ext-byte":
            resp = self.send_via_relay(
                hops,
                build_ext_byte_read(
                    _require(resolved.no, "extended number"),
                    _require(resolved.addr, "extended addr"),
                    1,
                ),
            )
            if resp.cmd != 0x96:
                raise ToyopucProtocolError("Unexpected CMD in relay ext byte-read response")
            if len(resp.data) != 1:
                raise ToyopucProtocolError("Relay ext byte-read response must be 1 byte")
            return resp.data[0]
        if resolved.scheme == "pc10-bit":
            addr32 = _require(resolved.addr32, "pc10 addr32")
            payload = bytearray([0x01, 0x00, 0x00, 0x00])
            payload.extend(addr32.to_bytes(4, "little"))
            resp = self.send_via_relay(hops, build_pc10_multi_read(bytes(payload)))
            if resp.cmd != 0xC4:
                raise ToyopucProtocolError("Unexpected CMD in relay PC10 multi-read response")
            if len(resp.data) < 5:
                raise ToyopucProtocolError("Relay PC10 bit-read response too short")
            return bool(resp.data[4] & 0x01)
        if resolved.scheme == "pc10-word":
            resp = self.send_via_relay(hops, build_pc10_block_read(_require(resolved.addr32, "pc10 addr32"), 2))
            if resp.cmd != 0xC2:
                raise ToyopucProtocolError("Unexpected CMD in relay PC10 block-read response")
            if len(resp.data) < 2:
                raise ToyopucProtocolError("Relay PC10 word-read response too short")
            return int.from_bytes(resp.data[:2], "little")
        if resolved.scheme == "pc10-byte":
            resp = self.send_via_relay(hops, build_pc10_block_read(_require(resolved.addr32, "pc10 addr32"), 1))
            if resp.cmd != 0xC2:
                raise ToyopucProtocolError("Unexpected CMD in relay PC10 block-read response")
            if len(resp.data) < 1:
                raise ToyopucProtocolError("Relay PC10 byte-read response too short")
            return resp.data[0]
        raise ValueError(f"Unsupported resolved scheme: {resolved.scheme}")

    def _write_resolved_device(self, resolved: ResolvedDevice, value: Any) -> None:
        if resolved.area == "FR":
            _raise_generic_fr_write_error()
        if resolved.scheme == "basic-bit":
            addr = _require(resolved.basic_addr, "basic_addr")
            self.write_bit(addr, bool(value))
            return
        if resolved.scheme == "basic-word":
            addr = _require(resolved.basic_addr, "basic_addr")
            self.write_words(addr, [int(value)])
            return
        if resolved.scheme == "basic-byte":
            addr = _require(resolved.basic_addr, "basic_addr")
            self.write_bytes(addr, [int(value)])
            return
        if resolved.scheme == "program-bit":
            no = _require(resolved.no, "program number")
            bit_no = _require(resolved.bit_no, "program bit")
            addr = _require(resolved.addr, "program addr")
            self.write_ext_multi([(no, bit_no, addr, int(value) & 0x01)], [], [])
            return
        if resolved.scheme == "program-word":
            no = _require(resolved.no, "program number")
            addr = _require(resolved.addr, "program addr")
            self.write_ext_words(no, addr, [int(value)])
            return
        if resolved.scheme == "program-byte":
            no = _require(resolved.no, "program number")
            addr = _require(resolved.addr, "program addr")
            self.write_ext_bytes(no, addr, [int(value)])
            return
        if resolved.scheme == "ext-bit":
            no = _require(resolved.no, "extended number")
            bit_no = _require(resolved.bit_no, "extended bit")
            addr = _require(resolved.addr, "extended addr")
            self.write_ext_multi([(no, bit_no, addr, int(value) & 0x01)], [], [])
            return
        if resolved.scheme == "ext-word":
            no = _require(resolved.no, "extended number")
            addr = _require(resolved.addr, "extended addr")
            self.write_ext_words(no, addr, [int(value)])
            return
        if resolved.scheme == "ext-byte":
            no = _require(resolved.no, "extended number")
            addr = _require(resolved.addr, "extended addr")
            self.write_ext_bytes(no, addr, [int(value)])
            return
        if resolved.scheme == "pc10-bit":
            addr32 = _require(resolved.addr32, "pc10 addr32")
            self.pc10_multi_write(_pack_pc10_multi_bit_payload([(addr32, int(value) & 0x01)]))
            return
        if resolved.scheme == "pc10-word":
            addr32 = _require(resolved.addr32, "pc10 addr32")
            _write_pc10_block_word(self, addr32, int(value))
            return
        if resolved.scheme == "pc10-byte":
            addr32 = _require(resolved.addr32, "pc10 addr32")
            self.pc10_block_write(addr32, bytes([int(value) & 0xFF]))
            return
        raise ValueError(f"Unsupported resolved scheme: {resolved.scheme}")

    def _relay_write_resolved_device(
        self,
        hops: str | Iterable[tuple[int, int]],
        resolved: ResolvedDevice,
        value: Any,
    ) -> None:
        if resolved.scheme == "basic-bit":
            resp = self.send_via_relay(
                hops,
                build_bit_write(_require(resolved.basic_addr, "basic_addr"), int(value) & 0x01),
            )
            if resp.cmd != 0x21:
                raise ToyopucProtocolError("Unexpected CMD in relay bit-write response")
            return
        if resolved.scheme == "basic-word":
            resp = self.send_via_relay(
                hops,
                build_word_write(_require(resolved.basic_addr, "basic_addr"), [int(value)]),
            )
            if resp.cmd != 0x1D:
                raise ToyopucProtocolError("Unexpected CMD in relay word-write response")
            return
        if resolved.scheme == "basic-byte":
            resp = self.send_via_relay(
                hops,
                build_byte_write(_require(resolved.basic_addr, "basic_addr"), [int(value)]),
            )
            if resp.cmd != 0x1F:
                raise ToyopucProtocolError("Unexpected CMD in relay byte-write response")
            return
        if resolved.scheme == "program-bit":
            resp = self.send_via_relay(
                hops,
                build_ext_multi_write(
                    [
                        (
                            _require(resolved.no, "program number"),
                            _require(resolved.bit_no, "program bit"),
                            _require(resolved.addr, "program addr"),
                            int(value) & 0x01,
                        )
                    ],
                    [],
                    [],
                ),
            )
            if resp.cmd != 0x99:
                raise ToyopucProtocolError("Unexpected CMD in relay multi-write response")
            return
        if resolved.scheme == "program-word":
            resp = self.send_via_relay(
                hops,
                build_ext_word_write(
                    _require(resolved.no, "program number"),
                    _require(resolved.addr, "program addr"),
                    [int(value)],
                ),
            )
            if resp.cmd != 0x95:
                raise ToyopucProtocolError("Unexpected CMD in relay ext word-write response")
            return
        if resolved.scheme == "program-byte":
            resp = self.send_via_relay(
                hops,
                build_ext_byte_write(
                    _require(resolved.no, "program number"),
                    _require(resolved.addr, "program addr"),
                    [int(value)],
                ),
            )
            if resp.cmd != 0x97:
                raise ToyopucProtocolError("Unexpected CMD in relay ext byte-write response")
            return
        if resolved.scheme == "ext-bit":
            resp = self.send_via_relay(
                hops,
                build_ext_multi_write(
                    [
                        (
                            _require(resolved.no, "extended number"),
                            _require(resolved.bit_no, "extended bit"),
                            _require(resolved.addr, "extended addr"),
                            int(value) & 0x01,
                        )
                    ],
                    [],
                    [],
                ),
            )
            if resp.cmd != 0x99:
                raise ToyopucProtocolError("Unexpected CMD in relay multi-write response")
            return
        if resolved.scheme == "ext-word":
            resp = self.send_via_relay(
                hops,
                build_ext_word_write(
                    _require(resolved.no, "extended number"),
                    _require(resolved.addr, "extended addr"),
                    [int(value)],
                ),
            )
            if resp.cmd != 0x95:
                raise ToyopucProtocolError("Unexpected CMD in relay ext word-read response")
            return
        if resolved.scheme == "ext-byte":
            resp = self.send_via_relay(
                hops,
                build_ext_byte_write(
                    _require(resolved.no, "extended number"),
                    _require(resolved.addr, "extended addr"),
                    [int(value)],
                ),
            )
            if resp.cmd != 0x97:
                raise ToyopucProtocolError("Unexpected CMD in relay ext byte-write response")
            return
        if resolved.scheme == "pc10-bit":
            resp = self.send_via_relay(
                hops,
                build_pc10_multi_write(
                    _pack_pc10_multi_bit_payload([(_require(resolved.addr32, "pc10 addr32"), int(value) & 0x01)])
                ),
            )
            if resp.cmd != 0xC5:
                raise ToyopucProtocolError("Unexpected CMD in relay PC10 multi-write response")
            return
        if resolved.scheme == "pc10-word":
            resp = self.send_via_relay(
                hops,
                build_pc10_block_write(
                    _require(resolved.addr32, "pc10 addr32"),
                    (int(value) & 0xFFFF).to_bytes(2, "little"),
                ),
            )
            if resp.cmd != 0xC3:
                raise ToyopucProtocolError("Unexpected CMD in relay PC10 block-write response")
            return
        if resolved.scheme == "pc10-byte":
            resp = self.send_via_relay(
                hops,
                build_pc10_block_write(_require(resolved.addr32, "pc10 addr32"), bytes([int(value) & 0xFF])),
            )
            if resp.cmd != 0xC3:
                raise ToyopucProtocolError("Unexpected CMD in relay PC10 block-write response")
            return
        raise ValueError(f"Unsupported resolved scheme: {resolved.scheme}")

    def _offset_resolved_device(self, resolved: ResolvedDevice, delta: int) -> ResolvedDevice:
        if delta == 0:
            return resolved
        width = resolved.digits if resolved.digits > 0 else max(4, len(f"{resolved.index:X}"))
        if resolved.unit == "byte":
            suffix = "H" if resolved.high else "L"
            index = resolved.index + delta
            if resolved.prefix:
                return resolve_device(f"{resolved.prefix}-{resolved.area}{index:0{width}X}{suffix}")
            return resolve_device(f"{resolved.area}{index:0{width}X}{suffix}")
        index = resolved.index + delta
        suffix = "W" if resolved.packed and resolved.unit == "word" else ""
        if resolved.prefix:
            return resolve_device(f"{resolved.prefix}-{resolved.area}{index:0{width}X}{suffix}")
        return resolve_device(f"{resolved.area}{index:0{width}X}{suffix}")

    def _seq_devices(self, resolved: ResolvedDevice, count: int) -> list[ResolvedDevice]:
        """Build a list of *count* sequentially-offset ResolvedDevices."""
        devs: list[ResolvedDevice] = [resolved]
        for i in range(1, count):
            devs.append(self._offset_resolved_device(resolved, i))
        return devs

    # ------------------------------------------------------------------
    # Batch-read helpers
    # ------------------------------------------------------------------

    def _read_basic_word_batch(self, devices: list[ResolvedDevice]) -> list[int]:
        addrs = [_require(d.basic_addr, "basic_addr") for d in devices]
        if _is_consecutive_basic(devices):
            return self.read_words(addrs[0], len(devices))
        return list(self.read_words_multi(addrs))

    def _read_ext_word_batch(self, devices: list[ResolvedDevice]) -> list[int]:
        if _is_consecutive_ext_word(devices):
            no = _require(devices[0].no, "no")
            addr = _require(devices[0].addr, "addr")
            return self.read_ext_words(no, addr, len(devices))
        return unpack_u16_le(
            self.read_ext_multi(
                [],
                [],
                [(_require(d.no, "no"), _require(d.addr, "addr")) for d in devices],
            )
        )[: len(devices)]

    def _read_ext_byte_batch(self, devices: list[ResolvedDevice]) -> list[int]:
        no0 = devices[0].no
        if no0 is not None and all(d.no == no0 for d in devices):
            addrs = [_require(d.addr, "addr") for d in devices]
            if all(a == addrs[0] + i for i, a in enumerate(addrs)):
                return list(self.read_ext_bytes(no0, addrs[0], len(devices)))
        return list(
            self.read_ext_multi(
                [],
                [(_require(d.no, "no"), _require(d.addr, "addr")) for d in devices],
                [],
            )[: len(devices)]
        )

    def _read_ext_bit_batch(self, devices: list[ResolvedDevice]) -> list[bool]:
        bits = [(_require(d.no, "no"), _require(d.bit_no, "bit_no"), _require(d.addr, "addr")) for d in devices]
        data = self.read_ext_multi(bits, [], [])
        return [bool(v) for v in _parse_ext_multi_bit_data(data, len(devices))]

    def _read_pc10_word_batch_by_segments(self, devices: list[ResolvedDevice]) -> list[int]:
        values: list[int] = []
        segment_start = 0
        while segment_start < len(devices):
            segment_len = _pc10_word_segment_length(devices, segment_start)
            start_addr = _require(devices[segment_start].addr32, "pc10 addr32")
            words = unpack_u16_le(self.pc10_block_read(start_addr, segment_len * 2))
            if len(words) < segment_len:
                raise ToyopucProtocolError("PC10 block-read response too short")
            values.extend(words[:segment_len])
            segment_start += segment_len
        return values

    def _read_pc10_word_batch(self, devices: list[ResolvedDevice]) -> list[int]:
        if _is_consecutive_pc10_word(devices):
            addr32 = _require(devices[0].addr32, "pc10 addr32")
            raw = self.pc10_block_read(addr32, len(devices) * 2)
            return [int.from_bytes(raw[i * 2 : i * 2 + 2], "little") for i in range(len(devices))]
        if _contains_packed_pc10_word_device(devices):
            return self._read_pc10_word_batch_by_segments(devices)
        return _read_pc10_multi_words(self, [_require(d.addr32, "pc10 addr32") for d in devices])

    def _read_pc10_byte_batch(self, devices: list[ResolvedDevice]) -> list[int]:
        addrs32 = [_require(d.addr32, "pc10 addr32") for d in devices]
        if all(a == addrs32[0] + i for i, a in enumerate(addrs32)):
            raw = self.pc10_block_read(addrs32[0], len(devices))
            return list(raw)
        return [self.pc10_block_read(a, 1)[0] for a in addrs32]

    def _read_batch(self, devices: list[ResolvedDevice]) -> list[Any]:
        if not devices:
            return []
        key = _batch_key(devices[0])
        if key == "basic-word":
            return self._read_basic_word_batch(devices)
        if key == "basic-byte":
            return list(self.read_bytes_multi([_require(d.basic_addr, "basic_addr") for d in devices]))
        if key == "ext-word":
            return self._read_ext_word_batch(devices)
        if key == "ext-byte":
            return self._read_ext_byte_batch(devices)
        if key == "ext-bit":
            return self._read_ext_bit_batch(devices)
        if key == "pc10-word":
            return self._read_pc10_word_batch(devices)
        if key == "pc10-bit":
            return [bool(b) for b in _read_pc10_multi_bits(self, [_require(d.addr32, "pc10 addr32") for d in devices])]
        if key == "pc10-byte":
            return self._read_pc10_byte_batch(devices)
        return [self._read_resolved_device(d) for d in devices]

    def _read_runs(self, devices: list[ResolvedDevice], split_pc10: bool) -> list[Any]:
        results: list[Any] = [None] * len(devices)
        idx = 0
        for run in self._get_run_plan(devices, split_pc10):
            batch = self._read_batch(devices[idx : idx + run])
            for j, v in enumerate(batch):
                results[idx + j] = v
            idx += run
        return results

    # ------------------------------------------------------------------
    # Batch-read helpers (relay)
    # ------------------------------------------------------------------

    def _relay_read_basic_word_batch(self, hops: Any, devices: list[ResolvedDevice]) -> list[int]:
        if _is_consecutive_basic(devices):
            start = _require(devices[0].basic_addr, "basic_addr")
            resp = self.send_via_relay(hops, build_word_read(start, len(devices)))
            if resp.cmd != 0x1C:
                raise ToyopucProtocolError("Unexpected CMD in relay word-read response")
            return unpack_u16_le(resp.data)[: len(devices)]
        resp = self.send_via_relay(hops, build_multi_word_read([_require(d.basic_addr, "basic_addr") for d in devices]))
        if resp.cmd != 0x22:
            raise ToyopucProtocolError("Unexpected CMD in relay multi-word-read response")
        return unpack_u16_le(resp.data)[: len(devices)]

    def _relay_read_basic_byte_batch(self, hops: Any, devices: list[ResolvedDevice]) -> list[int]:
        addrs = [_require(d.basic_addr, "basic_addr") for d in devices]
        if _is_consecutive_basic(devices):
            resp = self.send_via_relay(hops, build_byte_read(addrs[0], len(devices)))
            if resp.cmd != 0x1E:
                raise ToyopucProtocolError("Unexpected CMD in relay byte-read response")
            return list(resp.data[: len(devices)])
        resp = self.send_via_relay(hops, build_multi_byte_read(addrs))
        if resp.cmd != 0x24:
            raise ToyopucProtocolError("Unexpected CMD in relay multi-byte-read response")
        return list(resp.data[: len(devices)])

    def _relay_read_ext_word_batch(self, hops: Any, devices: list[ResolvedDevice]) -> list[int]:
        if _is_consecutive_ext_word(devices):
            no = _require(devices[0].no, "no")
            addr = _require(devices[0].addr, "addr")
            resp = self.send_via_relay(hops, build_ext_word_read(no, addr, len(devices)))
            if resp.cmd != 0x94:
                raise ToyopucProtocolError("Unexpected CMD in relay ext-word-read response")
            return unpack_u16_le(resp.data)[: len(devices)]
        resp = self.send_via_relay(
            hops,
            build_ext_multi_read(
                [],
                [],
                [(_require(d.no, "no"), _require(d.addr, "addr")) for d in devices],
            ),
        )
        if resp.cmd != 0x98:
            raise ToyopucProtocolError("Unexpected CMD in relay ext multi-read response")
        return unpack_u16_le(resp.data)[: len(devices)]

    def _relay_read_ext_byte_batch(self, hops: Any, devices: list[ResolvedDevice]) -> list[int]:
        no0 = devices[0].no
        if no0 is not None and all(d.no == no0 for d in devices):
            addrs = [_require(d.addr, "addr") for d in devices]
            if all(a == addrs[0] + i for i, a in enumerate(addrs)):
                resp = self.send_via_relay(hops, build_ext_byte_read(no0, addrs[0], len(devices)))
                if resp.cmd != 0x96:
                    raise ToyopucProtocolError("Unexpected CMD in relay ext byte-read response")
                return list(resp.data[: len(devices)])
        resp = self.send_via_relay(
            hops,
            build_ext_multi_read(
                [],
                [(_require(d.no, "no"), _require(d.addr, "addr")) for d in devices],
                [],
            ),
        )
        if resp.cmd != 0x98:
            raise ToyopucProtocolError("Unexpected CMD in relay ext multi-read response")
        return list(resp.data[: len(devices)])

    def _relay_read_ext_bit_batch(self, hops: Any, devices: list[ResolvedDevice]) -> list[bool]:
        bits = [(_require(d.no, "no"), _require(d.bit_no, "bit_no"), _require(d.addr, "addr")) for d in devices]
        resp = self.send_via_relay(hops, build_ext_multi_read(bits, [], []))
        if resp.cmd != 0x98:
            raise ToyopucProtocolError("Unexpected CMD in relay ext-multi-read response")
        return [bool(v) for v in _parse_ext_multi_bit_data(resp.data, len(devices))]

    def _relay_read_pc10_word_batch_by_segments(self, hops: Any, devices: list[ResolvedDevice]) -> list[int]:
        values: list[int] = []
        segment_start = 0
        while segment_start < len(devices):
            segment_len = _pc10_word_segment_length(devices, segment_start)
            start_addr = _require(devices[segment_start].addr32, "pc10 addr32")
            resp = self.send_via_relay(hops, build_pc10_block_read(start_addr, segment_len * 2))
            if resp.cmd != 0xC2:
                raise ToyopucProtocolError("Unexpected CMD in relay PC10 block-read response")
            words = unpack_u16_le(resp.data)
            if len(words) < segment_len:
                raise ToyopucProtocolError("PC10 block-read response too short")
            values.extend(words[:segment_len])
            segment_start += segment_len
        return values

    def _relay_read_pc10_word_batch(self, hops: Any, devices: list[ResolvedDevice]) -> list[int]:
        if _is_consecutive_pc10_word(devices):
            addr32 = _require(devices[0].addr32, "pc10 addr32")
            resp = self.send_via_relay(hops, build_pc10_block_read(addr32, len(devices) * 2))
            if resp.cmd != 0xC2:
                raise ToyopucProtocolError("Unexpected CMD in relay PC10 block-read response")
            return [int.from_bytes(resp.data[i * 2 : i * 2 + 2], "little") for i in range(len(devices))]
        if _contains_packed_pc10_word_device(devices):
            return self._relay_read_pc10_word_batch_by_segments(hops, devices)
        payload = _build_pc10_multi_word_read_payload([_require(d.addr32, "pc10 addr32") for d in devices])
        resp = self.send_via_relay(
            hops,
            build_pc10_multi_read(payload),
        )
        if resp.cmd != 0xC4:
            raise ToyopucProtocolError("Unexpected CMD in relay PC10 multi-read response")
        return _parse_pc10_multi_word_data(resp.data, len(devices))

    def _relay_read_pc10_bit_batch(self, hops: Any, devices: list[ResolvedDevice]) -> list[bool]:
        addrs32 = [_require(d.addr32, "pc10 addr32") for d in devices]
        payload = bytearray([len(addrs32) & 0xFF, 0x00, 0x00, 0x00])
        for a in addrs32:
            payload.extend(a.to_bytes(4, "little"))
        resp = self.send_via_relay(hops, build_pc10_multi_read(bytes(payload)))
        if resp.cmd != 0xC4:
            raise ToyopucProtocolError("Unexpected CMD in relay PC10 multi-read response")
        bit_data = resp.data[4:]
        return [bool((bit_data[i // 8] >> (i % 8)) & 0x01) for i in range(len(devices))]

    def _relay_read_pc10_byte_batch(self, hops: Any, devices: list[ResolvedDevice]) -> list[int]:
        addrs32 = [_require(d.addr32, "pc10 addr32") for d in devices]
        if all(a == addrs32[0] + i for i, a in enumerate(addrs32)):
            resp = self.send_via_relay(hops, build_pc10_block_read(addrs32[0], len(devices)))
            if resp.cmd != 0xC2:
                raise ToyopucProtocolError("Unexpected CMD in relay PC10 block-read response")
            return list(resp.data[: len(devices)])
        return [int(self._relay_read_resolved_device(hops, d)) for d in devices]

    def _relay_read_batch(self, hops: Any, devices: list[ResolvedDevice]) -> list[Any]:
        if not devices:
            return []
        key = _batch_key(devices[0])
        if key == "basic-word":
            return self._relay_read_basic_word_batch(hops, devices)
        if key == "basic-byte":
            return self._relay_read_basic_byte_batch(hops, devices)
        if key == "ext-word":
            return self._relay_read_ext_word_batch(hops, devices)
        if key == "ext-byte":
            return self._relay_read_ext_byte_batch(hops, devices)
        if key == "ext-bit":
            return self._relay_read_ext_bit_batch(hops, devices)
        if key == "pc10-word":
            return self._relay_read_pc10_word_batch(hops, devices)
        if key == "pc10-bit":
            return self._relay_read_pc10_bit_batch(hops, devices)
        if key == "pc10-byte":
            return self._relay_read_pc10_byte_batch(hops, devices)
        return [self._relay_read_resolved_device(hops, d) for d in devices]

    def _relay_read_runs(self, hops: Any, devices: list[ResolvedDevice], split_pc10: bool) -> list[Any]:
        results: list[Any] = [None] * len(devices)
        idx = 0
        for run in self._get_run_plan(devices, split_pc10):
            batch = self._relay_read_batch(hops, devices[idx : idx + run])
            for j, v in enumerate(batch):
                results[idx + j] = v
            idx += run
        return results

    # ------------------------------------------------------------------
    # Batch-write helpers
    # ------------------------------------------------------------------

    def _write_basic_word_batch(self, devices: list[ResolvedDevice], values: list[int]) -> None:
        addrs = [_require(d.basic_addr, "basic_addr") for d in devices]
        if _is_consecutive_basic(devices):
            self.write_words(addrs[0], values)
        else:
            self.write_words_multi(list(zip(addrs, values, strict=False)))

    def _write_basic_byte_batch(self, devices: list[ResolvedDevice], values: list[int]) -> None:
        self.write_bytes_multi(
            [(_require(d.basic_addr, "basic_addr"), v & 0xFF) for d, v in zip(devices, values, strict=False)]
        )

    def _write_ext_word_batch(self, devices: list[ResolvedDevice], values: list[int]) -> None:
        if _is_consecutive_ext_word(devices):
            no = _require(devices[0].no, "no")
            addr = _require(devices[0].addr, "addr")
            self.write_ext_words(no, addr, values)
        else:
            self.write_ext_multi(
                [],
                [],
                [(_require(d.no, "no"), _require(d.addr, "addr"), v) for d, v in zip(devices, values, strict=False)],
            )

    def _write_ext_byte_batch(self, devices: list[ResolvedDevice], values: list[int]) -> None:
        no0 = devices[0].no
        if no0 is not None and all(d.no == no0 for d in devices):
            addrs = [_require(d.addr, "addr") for d in devices]
            if all(a == addrs[0] + i for i, a in enumerate(addrs)):
                self.write_ext_bytes(no0, addrs[0], values)
                return
        self.write_ext_multi(
            [],
            [(_require(d.no, "no"), _require(d.addr, "addr"), v) for d, v in zip(devices, values, strict=False)],
            [],
        )

    def _write_ext_bit_batch(self, devices: list[ResolvedDevice], values: list[int]) -> None:
        self.write_ext_multi(
            [
                (_require(d.no, "no"), _require(d.bit_no, "bit_no"), _require(d.addr, "addr"), v & 0x01)
                for d, v in zip(devices, values, strict=False)
            ],
            [],
            [],
        )

    def _write_pc10_word_batch(self, devices: list[ResolvedDevice], values: list[int]) -> None:
        if _is_consecutive_pc10_word(devices):
            addr32 = _require(devices[0].addr32, "pc10 addr32")
            data = b"".join((int(v) & 0xFFFF).to_bytes(2, "little") for v in values)
            self.pc10_block_write(addr32, data)
            return
        self.pc10_multi_write(
            _pack_pc10_multi_word_payload(
                [(_require(d.addr32, "pc10 addr32"), v) for d, v in zip(devices, values, strict=False)]
            )
        )

    def _write_pc10_bit_batch(self, devices: list[ResolvedDevice], values: list[int]) -> None:
        self.pc10_multi_write(
            _pack_pc10_multi_bit_payload(
                [(_require(d.addr32, "pc10 addr32"), v & 0x01) for d, v in zip(devices, values, strict=False)]
            )
        )

    def _write_pc10_byte_batch(self, devices: list[ResolvedDevice], values: list[int]) -> None:
        addrs32 = [_require(d.addr32, "pc10 addr32") for d in devices]
        if all(a == addrs32[0] + i for i, a in enumerate(addrs32)):
            self.pc10_block_write(addrs32[0], bytes(v & 0xFF for v in values))
            return
        for d, v in zip(devices, values, strict=False):
            self._write_resolved_device(d, v)

    def _write_batch(self, devices: list[ResolvedDevice], values: list[Any]) -> None:
        if not devices:
            return
        key = _batch_key(devices[0])
        if key == "basic-word":
            self._write_basic_word_batch(devices, [int(v) & 0xFFFF for v in values])
            return
        if key == "basic-byte":
            self._write_basic_byte_batch(devices, [int(v) & 0xFF for v in values])
            return
        if key == "ext-word":
            self._write_ext_word_batch(devices, [int(v) & 0xFFFF for v in values])
            return
        if key == "ext-byte":
            self._write_ext_byte_batch(devices, [int(v) & 0xFF for v in values])
            return
        if key == "ext-bit":
            self._write_ext_bit_batch(devices, [int(v) & 0x01 for v in values])
            return
        if key == "pc10-word":
            self._write_pc10_word_batch(devices, [int(v) & 0xFFFF for v in values])
            return
        if key == "pc10-bit":
            self._write_pc10_bit_batch(devices, [int(v) & 0x01 for v in values])
            return
        if key == "pc10-byte":
            self._write_pc10_byte_batch(devices, [int(v) & 0xFF for v in values])
            return
        for d, v in zip(devices, values, strict=False):
            self._write_resolved_device(d, v)

    def _write_runs(self, devices: list[ResolvedDevice], values: list[Any], split_pc10: bool) -> None:
        idx = 0
        for run in self._get_run_plan(devices, split_pc10):
            self._write_batch(devices[idx : idx + run], values[idx : idx + run])
            idx += run

    def _relay_write_basic_word_batch(self, hops: Any, devices: list[ResolvedDevice], values: list[int]) -> None:
        if _is_consecutive_basic(devices):
            start = _require(devices[0].basic_addr, "basic_addr")
            resp = self.send_via_relay(hops, build_word_write(start, values))
            if resp.cmd != 0x1D:
                raise ToyopucProtocolError("Unexpected CMD in relay word-write response")
            return
        resp = self.send_via_relay(
            hops,
            build_multi_word_write(
                [(_require(d.basic_addr, "basic_addr"), v) for d, v in zip(devices, values, strict=False)]
            ),
        )
        if resp.cmd != 0x23:
            raise ToyopucProtocolError("Unexpected CMD in relay multi-word-write response")

    def _relay_write_basic_byte_batch(self, hops: Any, devices: list[ResolvedDevice], values: list[int]) -> None:
        addrs = [_require(d.basic_addr, "basic_addr") for d in devices]
        if _is_consecutive_basic(devices):
            resp = self.send_via_relay(hops, build_byte_write(addrs[0], values))
            if resp.cmd != 0x1F:
                raise ToyopucProtocolError("Unexpected CMD in relay byte-write response")
            return
        resp = self.send_via_relay(
            hops,
            build_multi_byte_write(list(zip(addrs, values, strict=False))),
        )
        if resp.cmd != 0x25:
            raise ToyopucProtocolError("Unexpected CMD in relay multi-byte-write response")

    def _relay_write_ext_word_batch(self, hops: Any, devices: list[ResolvedDevice], values: list[int]) -> None:
        if _is_consecutive_ext_word(devices):
            no = _require(devices[0].no, "no")
            addr = _require(devices[0].addr, "addr")
            resp = self.send_via_relay(hops, build_ext_word_write(no, addr, values))
            if resp.cmd != 0x95:
                raise ToyopucProtocolError("Unexpected CMD in relay ext word-write response")
            return
        resp = self.send_via_relay(
            hops,
            build_ext_multi_write(
                [],
                [],
                [(_require(d.no, "no"), _require(d.addr, "addr"), v) for d, v in zip(devices, values, strict=False)],
            ),
        )
        if resp.cmd != 0x99:
            raise ToyopucProtocolError("Unexpected CMD in relay ext multi-write response")

    def _relay_write_ext_byte_batch(self, hops: Any, devices: list[ResolvedDevice], values: list[int]) -> None:
        no0 = devices[0].no
        if no0 is not None and all(d.no == no0 for d in devices):
            addrs = [_require(d.addr, "addr") for d in devices]
            if all(a == addrs[0] + i for i, a in enumerate(addrs)):
                resp = self.send_via_relay(hops, build_ext_byte_write(no0, addrs[0], values))
                if resp.cmd != 0x97:
                    raise ToyopucProtocolError("Unexpected CMD in relay ext byte-write response")
                return
        resp = self.send_via_relay(
            hops,
            build_ext_multi_write(
                [],
                [(_require(d.no, "no"), _require(d.addr, "addr"), v) for d, v in zip(devices, values, strict=False)],
                [],
            ),
        )
        if resp.cmd != 0x99:
            raise ToyopucProtocolError("Unexpected CMD in relay ext multi-write response")

    def _relay_write_ext_bit_batch(self, hops: Any, devices: list[ResolvedDevice], values: list[int]) -> None:
        resp = self.send_via_relay(
            hops,
            build_ext_multi_write(
                [
                    (_require(d.no, "no"), _require(d.bit_no, "bit_no"), _require(d.addr, "addr"), v & 0x01)
                    for d, v in zip(devices, values, strict=False)
                ],
                [],
                [],
            ),
        )
        if resp.cmd != 0x99:
            raise ToyopucProtocolError("Unexpected CMD in relay ext multi-write response")

    def _relay_write_pc10_word_batch(self, hops: Any, devices: list[ResolvedDevice], values: list[int]) -> None:
        if _is_consecutive_pc10_word(devices):
            addr32 = _require(devices[0].addr32, "pc10 addr32")
            data = b"".join((int(v) & 0xFFFF).to_bytes(2, "little") for v in values)
            resp = self.send_via_relay(hops, build_pc10_block_write(addr32, data))
            if resp.cmd != 0xC3:
                raise ToyopucProtocolError("Unexpected CMD in relay PC10 block-write response")
            return
        resp = self.send_via_relay(
            hops,
            build_pc10_multi_write(
                _pack_pc10_multi_word_payload(
                    [(_require(d.addr32, "pc10 addr32"), v) for d, v in zip(devices, values, strict=False)]
                )
            ),
        )
        if resp.cmd != 0xC5:
            raise ToyopucProtocolError("Unexpected CMD in relay PC10 multi-write response")

    def _relay_write_pc10_bit_batch(self, hops: Any, devices: list[ResolvedDevice], values: list[int]) -> None:
        resp = self.send_via_relay(
            hops,
            build_pc10_multi_write(
                _pack_pc10_multi_bit_payload(
                    [(_require(d.addr32, "pc10 addr32"), v & 0x01) for d, v in zip(devices, values, strict=False)]
                )
            ),
        )
        if resp.cmd != 0xC5:
            raise ToyopucProtocolError("Unexpected CMD in relay PC10 multi-write response")

    def _relay_write_pc10_byte_batch(self, hops: Any, devices: list[ResolvedDevice], values: list[int]) -> None:
        addrs32 = [_require(d.addr32, "pc10 addr32") for d in devices]
        if all(a == addrs32[0] + i for i, a in enumerate(addrs32)):
            resp = self.send_via_relay(hops, build_pc10_block_write(addrs32[0], bytes(v & 0xFF for v in values)))
            if resp.cmd != 0xC3:
                raise ToyopucProtocolError("Unexpected CMD in relay PC10 block-write response")
            return
        for d, v in zip(devices, values, strict=False):
            self._relay_write_resolved_device(hops, d, v)

    def _relay_write_batch(self, hops: Any, devices: list[ResolvedDevice], values: list[Any]) -> None:
        if not devices:
            return
        key = _batch_key(devices[0])
        if key == "basic-word":
            self._relay_write_basic_word_batch(hops, devices, [int(v) & 0xFFFF for v in values])
            return
        if key == "basic-byte":
            self._relay_write_basic_byte_batch(hops, devices, [int(v) & 0xFF for v in values])
            return
        if key == "ext-word":
            self._relay_write_ext_word_batch(hops, devices, [int(v) & 0xFFFF for v in values])
            return
        if key == "ext-byte":
            self._relay_write_ext_byte_batch(hops, devices, [int(v) & 0xFF for v in values])
            return
        if key == "ext-bit":
            self._relay_write_ext_bit_batch(hops, devices, [int(v) & 0x01 for v in values])
            return
        if key == "pc10-word":
            self._relay_write_pc10_word_batch(hops, devices, [int(v) & 0xFFFF for v in values])
            return
        if key == "pc10-bit":
            self._relay_write_pc10_bit_batch(hops, devices, [int(v) & 0x01 for v in values])
            return
        if key == "pc10-byte":
            self._relay_write_pc10_byte_batch(hops, devices, [int(v) & 0xFF for v in values])
            return
        for d, v in zip(devices, values, strict=False):
            self._relay_write_resolved_device(hops, d, v)

    def _relay_write_runs(self, hops: Any, devices: list[ResolvedDevice], values: list[Any], split_pc10: bool) -> None:
        idx = 0
        for run in self._get_run_plan(devices, split_pc10):
            self._relay_write_batch(hops, devices[idx : idx + run], values[idx : idx + run])
            idx += run

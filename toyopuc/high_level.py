from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Mapping, Optional, Sequence, TypeVar, Union

from .address import (
    ParsedAddress,
    encode_bit_address,
    encode_byte_address,
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
from .client import ToyopucClient
from .exceptions import ToyopucProtocolError
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
_EXT_BIT_AREAS = {"EP", "EK", "EV", "ET", "EC", "EL", "EX", "EY", "EM", "GX", "GY", "GM"}
_EXT_WORD_AREAS = {"ES", "EN", "H", "U", "EB", "FR"}
_PREFIX_REQUIRED_AREAS = {"P", "K", "V", "T", "C", "L", "X", "Y", "M", "S", "N", "R", "D"}
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


def _require(value: Optional[T], label: str) -> T:
    if value is None:
        raise ValueError(f"Resolved device missing {label}")
    return value


@dataclass(frozen=True)
class ResolvedDevice:
    """Resolved high-level device description.

    This is the normalized result of `resolve_device()`. It records which
    command family should be used and the encoded address fields needed for it.

    Attributes:
        text: Original normalized device string.
        scheme: Selected access path such as ``basic-word``, ``program-bit``,
            ``ext-byte``, or ``pc10-word``.
        unit: Resolved access unit: ``bit``, ``byte``, or ``word``.
        area: Device family such as ``D``, ``M``, ``EX``, or ``GX``.
        index: Numeric address value interpreted as hexadecimal.
        prefix: Optional ``P1``/``P2``/``P3`` program prefix.
        high: ``True`` when the resolved byte address uses the upper-byte
            designator ``H``.
        packed: ``True`` when the address used ``W/H/L`` notation for a
            bit-device family.
        basic_addr: Encoded basic-area address used by ``CMD=1C``-``25``.
        no: Extended/program number used by ``CMD=94``-``99``.
        addr: 16-bit address field used with ``no``.
        bit_no: Bit position used by extended/program bit access.
        addr32: 32-bit PC10 address used by ``CMD=C2``-``C5``.
    """

    text: str
    scheme: str
    unit: str
    area: str
    index: int
    digits: int = 0
    prefix: Optional[str] = None
    high: bool = False
    packed: bool = False
    basic_addr: Optional[int] = None
    no: Optional[int] = None
    addr: Optional[int] = None
    bit_no: Optional[int] = None
    addr32: Optional[int] = None


def _infer_unit_and_area(device: str) -> tuple[Optional[str], str, str]:
    text = device.strip().upper()
    prefix = None
    body = text
    if text.startswith(("P1-", "P2-", "P3-")):
        prefix, body = text.split("-", 1)

    parsed_packed_word = None
    if body.endswith("W"):
        parsed_packed_word = body[:-1]
        for area in sorted(_BASIC_BIT_AREAS | _EXT_BIT_AREAS, key=len, reverse=True):
            if parsed_packed_word.startswith(area):
                return prefix, area, "word"
        raise ValueError(f"Unknown packed word area: {device}")

    parsed_byte = None
    if body.endswith(("L", "H")):
        parsed_byte = body[:-1]
        for area in sorted(_BASIC_BIT_AREAS | _BASIC_WORD_AREAS | _EXT_BIT_AREAS | _EXT_WORD_AREAS, key=len, reverse=True):
            if parsed_byte.startswith(area):
                return prefix, area, "byte"
        raise ValueError(f"Unknown address area: {device}")

    for area in sorted(_EXT_BIT_AREAS | _EXT_WORD_AREAS | _BASIC_BIT_AREAS | _BASIC_WORD_AREAS, key=len, reverse=True):
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


def resolve_device(device: str) -> ResolvedDevice:
    """Resolve a string device address into a normalized access descriptor."""
    prefix, area, unit = _infer_unit_and_area(device)
    text = device.strip().upper()
    if prefix is None and area in _PREFIX_REQUIRED_AREAS:
        raise ValueError(f"{area} area requires P1-/P2-/P3- prefix: {text}")

    if prefix:
        ex_no, parsed = parse_prefixed_address(text, unit)
        if unit == "bit":
            bit_no, addr = encode_program_bit_address(parsed)
            addr32: Optional[int] = None
            try:
                # Keep PC10 addr32 when the basic bit encoder can represent it.
                # Upper prefixed ranges are still valid for program-bit access
                # even if they are outside basic direct bit ranges.
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

    if unit == "bit":
        if parsed.area in {"L", "M"} and parsed.index >= 0x1000:
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
        if parsed.area == "U" and parsed.index >= 0x08000:
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
        if parsed.area == "EB" and parsed.index <= 0x3FFFF:
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
        if parsed.area == "FR":
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
    if parsed.area == "U" and parsed.index >= 0x08000:
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
    if parsed.area == "EB" and parsed.index <= 0x3FFFF:
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


def _pack_pc10_multi_word_payload(addr32_values: Sequence[tuple[int, int]]) -> bytes:
    payload = bytearray([0x00, 0x00, len(addr32_values) & 0xFF, 0x00])
    for addr32, _ in addr32_values:
        payload.extend(addr32.to_bytes(4, "little"))
    for _, value in addr32_values:
        payload.extend(int(value).to_bytes(2, "little"))
    return bytes(payload)


def _read_pc10_multi_words(client: ToyopucClient, addrs32: Sequence[int]) -> List[int]:
    payload = bytearray([0x00, 0x00, len(addrs32) & 0xFF, 0x00])
    for addr32 in addrs32:
        payload.extend(addr32.to_bytes(4, "little"))
    data = client.pc10_multi_read(bytes(payload))
    data = data[4:]
    return [int.from_bytes(data[i * 2 : i * 2 + 2], "little") for i in range(len(addrs32))]


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


def _read_pc10_multi_bits(client: ToyopucClient, addrs32: Sequence[int]) -> List[int]:
    payload = bytearray([len(addrs32) & 0xFF, 0x00, 0x00, 0x00])
    for addr32 in addrs32:
        payload.extend(addr32.to_bytes(4, "little"))
    data = client.pc10_multi_read(bytes(payload))[4:]
    return [(data[i // 8] >> (i % 8)) & 0x01 for i in range(len(addrs32))]


def _raise_generic_fr_write_error() -> None:
    raise ValueError(
        "Generic FR writes are disabled; use write_fr(..., commit=False|True) or commit_fr() explicitly"
    )


class ToyopucHighLevelClient(ToyopucClient):
    """High-level client that accepts string device addresses.

    This wrapper hides branching between basic, prefixed, extended, and PC10
    access paths. It is the default client for application code.

    Use this class when you want the library to choose the correct low-level
    command family from a string such as ``D0000``, ``P1-M0000``, ``EX0010W``,
    or ``GX0010H``.
    """

    def read_cpu_status(self):
        return super().read_cpu_status()

    def relay_read_cpu_status(self, hops):
        return super().relay_read_cpu_status(hops)

    def read_cpu_status_a0(self):
        return super().read_cpu_status_a0()

    def relay_read_cpu_status_a0(self, hops):
        return super().relay_read_cpu_status_a0(hops)

    def read_cpu_status_a0_raw(self):
        return super().read_cpu_status_a0_raw()

    def relay_read_cpu_status_a0_raw(self, hops):
        return super().relay_read_cpu_status_a0_raw(hops)

    def read_clock(self):
        return super().read_clock()

    def relay_read_clock(self, hops):
        return super().relay_read_clock(hops)

    def relay_write_clock(self, hops, value: datetime) -> None:
        super().relay_write_clock(hops, value)

    def write_clock(self, value: datetime) -> None:
        super().write_clock(value)

    def resolve_device(self, device: str) -> ResolvedDevice:
        """Resolve a string address into a `ResolvedDevice`."""
        return resolve_device(device)

    def relay_read(self, hops, device: Union[str, ResolvedDevice], count: int = 1):
        """Read one item or a contiguous sequence through relay hops."""
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        if count < 1:
            raise ValueError("count must be >= 1")
        if count == 1:
            return self._relay_read_one(hops, resolved)
        return [self._relay_read_one(hops, self._offset(resolved, i)) for i in range(count)]

    def relay_write(self, hops, device: Union[str, ResolvedDevice], value) -> None:
        """Write one item or a contiguous sequence through relay hops."""
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        if resolved.unit == "bit":
            if isinstance(value, (list, tuple)):
                for i, item in enumerate(value):
                    self._relay_write_one(hops, self._offset(resolved, i), item)
                return
            self._relay_write_one(hops, resolved, value)
            return

        if isinstance(value, (bytes, bytearray)):
            for i, item in enumerate(value):
                self._relay_write_one(hops, self._offset(resolved, i), item)
            return
        if isinstance(value, (list, tuple)):
            for i, item in enumerate(value):
                self._relay_write_one(hops, self._offset(resolved, i), item)
            return
        self._relay_write_one(hops, resolved, value)

    def relay_read_words(
        self,
        hops: str | Iterable[tuple[int, int]],
        device: Union[int, str, ResolvedDevice],
        count: int = 1,
    ) -> List[int]:
        """Read one or more word devices through relay hops."""
        if isinstance(device, int):
            return super().relay_read_words(hops, device, count)
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        if resolved.unit != "word":
            raise ValueError("relay_read_words() requires a word device")
        values = self.relay_read(hops, resolved, count)
        if isinstance(values, list):
            return [int(item) for item in values]
        return [int(values)]

    def relay_write_words(
        self,
        hops: str | Iterable[tuple[int, int]],
        device: Union[int, str, ResolvedDevice],
        value: Union[Iterable[int], int],
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

    def relay_read_many(self, hops, devices: Sequence[Union[str, ResolvedDevice]]) -> List[object]:
        """Read multiple devices through relay hops and preserve input order."""
        return [self.relay_read(hops, device) for device in devices]

    def relay_write_many(self, hops, items: Mapping[Union[str, ResolvedDevice], object]) -> None:
        """Write multiple devices through relay hops in input order."""
        for device, value in items.items():
            self.relay_write(hops, device, value)

    def read_fr(self, device: Union[str, ResolvedDevice], count: int = 1):
        """Read one or more FR words using the dedicated FR path."""
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        if resolved.area != "FR" or resolved.unit != "word":
            raise ValueError("read_fr() requires an FR word device such as FR000000")
        values = self.read_fr_words(resolved.index, count)
        return values[0] if count == 1 else values

    def relay_read_fr(self, hops, device: Union[str, ResolvedDevice], count: int = 1):
        """Read one or more FR words through relay hops."""
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        if resolved.area != "FR" or resolved.unit != "word":
            raise ValueError("relay_read_fr() requires an FR word device such as FR000000")
        return self.relay_read(hops, resolved, count)

    def write_fr(
        self,
        device: Union[str, ResolvedDevice],
        value,
        *,
        commit: bool = False,
        wait: Optional[bool] = None,
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
        hops,
        device: Union[str, ResolvedDevice],
        value,
        *,
        commit: bool = False,
        wait: Optional[bool] = None,
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
        device: Union[str, ResolvedDevice],
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
        hops,
        device: Union[str, ResolvedDevice],
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

    def read(self, device: Union[str, ResolvedDevice], count: int = 1):
        """Read one item or a contiguous sequence from a device address.

        Args:
            device: String address or previously resolved device descriptor.
            count: Number of contiguous items to read.

        Returns:
            A scalar when ``count == 1``. Otherwise a list of values in device
            order.
        """
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        if count < 1:
            raise ValueError("count must be >= 1")
        if count == 1:
            return self._read_one(resolved)
        return [self._read_one(self._offset(resolved, i)) for i in range(count)]

    def write(self, device: Union[str, ResolvedDevice], value) -> None:
        """Write one item or a contiguous sequence to a device address.

        Args:
            device: String address or previously resolved device descriptor.
            value: Scalar, sequence, or bytes-like object depending on the
                target unit.
        """
        resolved = self.resolve_device(device) if isinstance(device, str) else device
        if resolved.area == "FR":
            _raise_generic_fr_write_error()
        if resolved.unit == "bit":
            if isinstance(value, (list, tuple)):
                for i, item in enumerate(value):
                    self._write_one(self._offset(resolved, i), item)
                return
            self._write_one(resolved, value)
            return

        if isinstance(value, (bytes, bytearray)):
            for i, item in enumerate(value):
                self._write_one(self._offset(resolved, i), item)
            return
        if isinstance(value, (list, tuple)):
            for i, item in enumerate(value):
                self._write_one(self._offset(resolved, i), item)
            return
        self._write_one(resolved, value)

    def read_many(self, devices: Sequence[Union[str, ResolvedDevice]]) -> List[object]:
        """Read multiple devices and preserve input order.

        Args:
            devices: Sequence of string addresses or resolved device objects.

        Returns:
            List of values in the same order as ``devices``.

        Notes:
            This method currently favors simple, predictable dispatch over
            grouped transport optimization.
        """
        resolved = [self.resolve_device(d) if isinstance(d, str) else d for d in devices]
        return [self._read_one(item) for item in resolved]

    def write_many(self, items: Mapping[Union[str, ResolvedDevice], object]) -> None:
        """Write multiple devices in mapping iteration order.

        Args:
            items: Mapping of device -> value pairs.

        Notes:
            This method currently dispatches each item independently.
        """
        resolved_items = []
        for device, value in items.items():
            resolved = self.resolve_device(device) if isinstance(device, str) else device
            if resolved.area == "FR":
                _raise_generic_fr_write_error()
            resolved_items.append((resolved, value))
        for resolved, value in resolved_items:
            self._write_one(resolved, value)

    def _read_one(self, resolved: ResolvedDevice):
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

    def _relay_read_one(self, hops, resolved: ResolvedDevice):
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
                    [(_require(resolved.no, "program number"), _require(resolved.bit_no, "program bit"), _require(resolved.addr, "program addr"))],
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
                build_ext_word_read(_require(resolved.no, "program number"), _require(resolved.addr, "program addr"), 1),
            )
            if resp.cmd != 0x94:
                raise ToyopucProtocolError("Unexpected CMD in relay ext word-read response")
            return unpack_u16_le(resp.data)[0]
        if resolved.scheme == "program-byte":
            resp = self.send_via_relay(
                hops,
                build_ext_byte_read(_require(resolved.no, "program number"), _require(resolved.addr, "program addr"), 1),
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
                    [(_require(resolved.no, "extended number"), _require(resolved.bit_no, "extended bit"), _require(resolved.addr, "extended addr"))],
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
                build_ext_word_read(_require(resolved.no, "extended number"), _require(resolved.addr, "extended addr"), 1),
            )
            if resp.cmd != 0x94:
                raise ToyopucProtocolError("Unexpected CMD in relay ext word-read response")
            return unpack_u16_le(resp.data)[0]
        if resolved.scheme == "ext-byte":
            resp = self.send_via_relay(
                hops,
                build_ext_byte_read(_require(resolved.no, "extended number"), _require(resolved.addr, "extended addr"), 1),
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

    def _write_one(self, resolved: ResolvedDevice, value) -> None:
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

    def _relay_write_one(self, hops, resolved: ResolvedDevice, value) -> None:
        if resolved.scheme == "basic-bit":
            resp = self.send_via_relay(hops, build_bit_write(_require(resolved.basic_addr, "basic_addr"), int(value) & 0x01))
            if resp.cmd != 0x21:
                raise ToyopucProtocolError("Unexpected CMD in relay bit-write response")
            return
        if resolved.scheme == "basic-word":
            resp = self.send_via_relay(hops, build_word_write(_require(resolved.basic_addr, "basic_addr"), [int(value)]))
            if resp.cmd != 0x1D:
                raise ToyopucProtocolError("Unexpected CMD in relay word-write response")
            return
        if resolved.scheme == "basic-byte":
            resp = self.send_via_relay(hops, build_byte_write(_require(resolved.basic_addr, "basic_addr"), [int(value)]))
            if resp.cmd != 0x1F:
                raise ToyopucProtocolError("Unexpected CMD in relay byte-write response")
            return
        if resolved.scheme == "program-bit":
            resp = self.send_via_relay(
                hops,
                build_ext_multi_write(
                    [(_require(resolved.no, "program number"), _require(resolved.bit_no, "program bit"), _require(resolved.addr, "program addr"), int(value) & 0x01)],
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
                build_ext_word_write(_require(resolved.no, "program number"), _require(resolved.addr, "program addr"), [int(value)]),
            )
            if resp.cmd != 0x95:
                raise ToyopucProtocolError("Unexpected CMD in relay ext word-write response")
            return
        if resolved.scheme == "program-byte":
            resp = self.send_via_relay(
                hops,
                build_ext_byte_write(_require(resolved.no, "program number"), _require(resolved.addr, "program addr"), [int(value)]),
            )
            if resp.cmd != 0x97:
                raise ToyopucProtocolError("Unexpected CMD in relay ext byte-write response")
            return
        if resolved.scheme == "ext-bit":
            resp = self.send_via_relay(
                hops,
                build_ext_multi_write(
                    [(_require(resolved.no, "extended number"), _require(resolved.bit_no, "extended bit"), _require(resolved.addr, "extended addr"), int(value) & 0x01)],
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
                build_ext_word_write(_require(resolved.no, "extended number"), _require(resolved.addr, "extended addr"), [int(value)]),
            )
            if resp.cmd != 0x95:
                raise ToyopucProtocolError("Unexpected CMD in relay ext word-write response")
            return
        if resolved.scheme == "ext-byte":
            resp = self.send_via_relay(
                hops,
                build_ext_byte_write(_require(resolved.no, "extended number"), _require(resolved.addr, "extended addr"), [int(value)]),
            )
            if resp.cmd != 0x97:
                raise ToyopucProtocolError("Unexpected CMD in relay ext byte-write response")
            return
        if resolved.scheme == "pc10-bit":
            resp = self.send_via_relay(
                hops,
                build_pc10_multi_write(_pack_pc10_multi_bit_payload([(_require(resolved.addr32, "pc10 addr32"), int(value) & 0x01)])),
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

    def _offset(self, resolved: ResolvedDevice, delta: int) -> ResolvedDevice:
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

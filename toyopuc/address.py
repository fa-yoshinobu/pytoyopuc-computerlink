
import re
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class ParsedAddress:
    """Normalized parsed device address.

    Attributes:
        area: Device family such as ``D``, ``M``, ``EX`` or ``GX``.
        index: Numeric address value interpreted as hexadecimal.
        unit: Requested access unit: ``"word"``, ``"byte"``, or ``"bit"``.
        high: ``True`` when the parsed byte designator is the upper byte
            suffix ``H``.
        packed: ``True`` when a bit-device family is addressed through
            ``W/H/L`` notation instead of plain bit notation.
    """
    area: str
    index: int
    unit: str  # 'word', 'byte', 'bit'
    high: bool = False
    packed: bool = False
    digits: int = 0


@dataclass(frozen=True)
class ExNoAddress32:
    """32-bit PC10 address components.

    Attributes:
        ex_no: Extended-area number used to build the packed 32-bit PC10
            address.
        addr: 16-bit byte or bit offset inside the extended area.
        unit: Access family used for the encoded value: ``"byte"`` or
            ``"bit"``.
    """
    ex_no: int
    addr: int
    unit: str  # 'byte' or 'bit'


@dataclass(frozen=True)
class ExtNoAddress:
    """Extended-area address for ``CMD=94``-``99``.

    Attributes:
        no: Extended/program number carried in the command payload.
        addr: 16-bit address field used with that number.
        unit: Requested access unit: ``"word"``, ``"byte"``, or ``"bit"``.
    """
    no: int
    addr: int
    unit: str  # 'word', 'byte', 'bit'


# Base addresses from manual section 3.4.2
_WORD_BASE = {
    'P': 0x0000,
    'K': 0x0020,
    'V': 0x0050,
    'T': 0x0060,
    'C': 0x0060,
    'L': 0x0080,
    'X': 0x0100,
    'Y': 0x0100,
    'M': 0x0180,
    'S': 0x0200,
    'N': 0x0600,
    'R': 0x0800,
    'D': 0x1000,
    'B': 0x6000,
}

_BYTE_BASE = {
    'P': 0x0000,
    'K': 0x0040,
    'V': 0x00A0,
    'T': 0x00C0,
    'C': 0x00C0,
    'L': 0x0100,
    'X': 0x0200,
    'Y': 0x0200,
    'M': 0x0300,
    'S': 0x0400,
    'N': 0x0C00,
    'R': 0x1000,
    'D': 0x2000,
    'B': 0xC000,
}

_BIT_BASE = {
    'P': 0x0000,
    'K': 0x0200,
    'V': 0x0500,
    'T': 0x0600,
    'C': 0x0600,
    'L': 0x0800,
    'X': 0x1000,
    'Y': 0x1000,
    'M': 0x1800,
}

_BASIC_BIT_SEGMENTS = {
    'P': [(0x000, 0x1FF)],
    'K': [(0x000, 0x2FF)],
    'V': [(0x000, 0x0FF)],
    'T': [(0x000, 0x1FF)],
    'C': [(0x000, 0x1FF)],
    'L': [(0x000, 0x7FF), (0x1000, 0x2FFF)],
    'X': [(0x000, 0x7FF)],
    'Y': [(0x000, 0x7FF)],
    'M': [(0x000, 0x7FF), (0x1000, 0x17FF)],
}

_EXT_BIT_SEGMENTS = {
    'EP': [(0x0000, 0x0FFF)],
    'EK': [(0x0000, 0x0FFF)],
    'EV': [(0x0000, 0x0FFF)],
    'ET': [(0x0000, 0x07FF)],
    'EC': [(0x0000, 0x07FF)],
    'EL': [(0x0000, 0x1FFF)],
    'EX': [(0x0000, 0x07FF)],
    'EY': [(0x0000, 0x07FF)],
    'EM': [(0x0000, 0x1FFF)],
    'GX': [(0x0000, 0xFFFF)],
    'GY': [(0x0000, 0xFFFF)],
    'GM': [(0x0000, 0xFFFF)],
}


_ADDR_RE = re.compile(r'^(?P<area>[A-Z]{1,2})(?P<num>[0-9A-Fa-f]+)(?P<suffix>[LHW])?$')
_PREF_RE = re.compile(
    r'^(?P<prefix>P[123])-(?P<area>[A-Z]{1,2})(?P<num>[0-9A-Fa-f]+)(?P<suffix>[LHW])?$'
)

_P_EXNO = {
    'P1': 0x0D,
    'P2': 0x0E,
    'P3': 0x0F,
}

# Extended area mapping for CMD=94-99.
# The address field is not a simple linear index for all areas; it depends on
# the access unit and the manual's extended-area base table.
_EXT_AREA_MAP = {
    'EP': {'no': 0x00, 'word_base': 0x0000, 'byte_base': 0x0000},
    'EK': {'no': 0x00, 'word_base': 0x0100, 'byte_base': 0x0200},
    'EV': {'no': 0x00, 'word_base': 0x0200, 'byte_base': 0x0400},
    'ET': {'no': 0x00, 'word_base': 0x0300, 'byte_base': 0x0600},
    'EC': {'no': 0x00, 'word_base': 0x0300, 'byte_base': 0x0600},
    'EL': {'no': 0x00, 'word_base': 0x0380, 'byte_base': 0x0700},
    'EX': {'no': 0x00, 'word_base': 0x0580, 'byte_base': 0x0B00},
    'EY': {'no': 0x00, 'word_base': 0x0580, 'byte_base': 0x0B00},
    'EM': {'no': 0x00, 'word_base': 0x0600, 'byte_base': 0x0C00},
    'ES': {'no': 0x00, 'word_base': 0x0800, 'byte_base': 0x1000},
    'EN': {'no': 0x00, 'word_base': 0x1000, 'byte_base': 0x2000},
    'H': {'no': 0x00, 'word_base': 0x1800, 'byte_base': 0x3000},
    'U': {'no': 0x08, 'word_base': 0x0000, 'byte_base': 0x0000},
    'GX': {'no': 0x07, 'word_base': 0x0000, 'byte_base': 0x0000},
    'GY': {'no': 0x07, 'word_base': 0x0000, 'byte_base': 0x0000},
    'GM': {'no': 0x07, 'word_base': 0x1000, 'byte_base': 0x2000},
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

_PROGRAM_WORD_SEGMENTS = {
    'S': [(0x0000, 0x03FF, 0x0200), (0x1000, 0x13FF, 0x6400)],
    'N': [(0x0000, 0x01FF, 0x0600), (0x1000, 0x17FF, 0x6800)],
    'R': [(0x0000, 0x07FF, 0x0800)],
    'D': [(0x0000, 0x0FFF, 0x1000), (0x1000, 0x2FFF, 0x2000)],
}

_PROGRAM_BYTE_SEGMENTS = {
    'S': [(0x0000, 0x03FF, 0x0400), (0x1000, 0x13FF, 0xC800)],
    'N': [(0x0000, 0x01FF, 0x0C00), (0x1000, 0x17FF, 0xD000)],
    'R': [(0x0000, 0x07FF, 0x1000)],
    'D': [(0x0000, 0x0FFF, 0x2000), (0x1000, 0x2FFF, 0x4000)],
}


def _derive_packed_segments(bit_segments: dict[str, list[tuple[int, int]]]) -> dict[str, list[tuple[int, int]]]:
    packed_segments: dict[str, list[tuple[int, int]]] = {}
    for area, segments in bit_segments.items():
        packed_segments[area] = []
        for start, end in segments:
            packed_segments[area].append((start >> 4, end >> 4))
    return packed_segments


_BASIC_PACKED_SEGMENTS = _derive_packed_segments(_BASIC_BIT_SEGMENTS)
_EXT_PACKED_SEGMENTS = _derive_packed_segments(_EXT_BIT_SEGMENTS)


def _derive_program_segments_from_bit_segments() -> tuple[dict[str, list[tuple[int, int, int]]], dict[str, list[tuple[int, int, int]]]]:
    word_segments: dict[str, list[tuple[int, int, int]]] = {}
    byte_segments: dict[str, list[tuple[int, int, int]]] = {}
    for area, segments in _PROGRAM_BIT_SEGMENTS.items():
        word_segments[area] = []
        byte_segments[area] = []
        for start, end, byte_base in segments:
            packed_start = start >> 4
            packed_end = end >> 4
            word_segments[area].append((packed_start, packed_end, byte_base >> 1))
            byte_segments[area].append((packed_start, packed_end, byte_base))
    return word_segments, byte_segments


_PROGRAM_BIT_WORD_SEGMENTS, _PROGRAM_BIT_BYTE_SEGMENTS = _derive_program_segments_from_bit_segments()

_PROGRAM_PACKED_SEGMENTS = {
    area: [(start, end) for start, end, _ in segments]
    for area, segments in _PROGRAM_BIT_WORD_SEGMENTS.items()
}

_PACKED_MAX_DIGITS = {
    'M': 3,
    'EP': 3,
    'GM': 3,
}


def _in_segments(index: int, segments: list[tuple[int, int]]) -> bool:
    return any(start <= index <= end for start, end in segments)


def _validate_bit_index(area: str, index: int) -> None:
    if area in _BASIC_BIT_SEGMENTS:
        if not _in_segments(index, _BASIC_BIT_SEGMENTS[area]):
            raise ValueError(f'Bit address out of range for {area}: {area}{index:04X}')
        return
    if area in _EXT_BIT_SEGMENTS:
        if not _in_segments(index, _EXT_BIT_SEGMENTS[area]):
            raise ValueError(f'Bit address out of range for {area}: {area}{index:04X}')


def _validate_packed_digits(area: str, text: str, digits: int) -> None:
    max_digits = _PACKED_MAX_DIGITS.get(area)
    if max_digits is not None and digits > max_digits:
        raise ValueError(f'Packed W/H/L notation must use <= {max_digits} hex digits for {area}: {text!r}')


def _validate_packed_index(area: str, index: int, *, prefixed: bool, text: str) -> None:
    if prefixed:
        segments = _PROGRAM_PACKED_SEGMENTS.get(area)
    elif area in _BASIC_PACKED_SEGMENTS:
        segments = _BASIC_PACKED_SEGMENTS[area]
    else:
        segments = _EXT_PACKED_SEGMENTS.get(area)
    if segments is None:
        raise ValueError(f'W/H/L suffix is only valid for bit-device families: {text!r}')
    if not _in_segments(index, segments):
        raise ValueError(f'Packed W/H/L address out of range: {text!r}')


def parse_address(text: str, unit: str, *, radix: int = 16) -> ParsedAddress:
    """Parse address strings like 'D0100', 'D0100L', 'M0201'.

    Notes:
    - The manual examples use hexadecimal numeric fields (e.g. D0100 -> 0x0100).
    - Use radix=10 if your PLC uses decimal notation.
    """
    m = _ADDR_RE.match(text.strip().upper())
    if not m:
        raise ValueError(f'Invalid address format: {text!r}')

    area = m.group('area')
    num_text = m.group('num')
    num = int(num_text, radix)
    suffix = m.group('suffix')

    if unit == 'byte' and suffix is None:
        # Default to low byte when omitted for byte access.
        suffix = 'L'
    if unit == 'byte':
        if suffix not in ('L', 'H'):
            raise ValueError(f'L/H suffix required for byte unit: {text!r}')
    elif unit == 'word':
        if suffix not in (None, 'W'):
            raise ValueError(f'W suffix only valid for packed word notation: {text!r}')
    else:
        if suffix is not None:
            raise ValueError(f'Suffix only valid for byte/packed-word notation: {text!r}')

    if unit == 'bit':
        _validate_bit_index(area, num)
    elif suffix == 'W' or (unit == 'byte' and (area in _BASIC_BIT_SEGMENTS or area in _EXT_BIT_SEGMENTS)):
        _validate_packed_digits(area, text, len(num_text))
        _validate_packed_index(area, num, prefixed=False, text=text)

    return ParsedAddress(
        area=area,
        index=num,
        unit=unit,
        high=(suffix == 'H'),
        packed=(suffix == 'W'),
        digits=len(num_text),
    )


def parse_prefixed_address(text: str, unit: str, *, radix: int = 16) -> Tuple[int, ParsedAddress]:
    """Parse a prefixed address and return `(program_ex_no, parsed_address)`.

    Examples:
    - `P1-M1000`
    - `P2-D2000L`
    - `P3-X0010H`

    The returned `ex_no` is the prefix-side program exchange number used by
    prefixed access paths. The second value is a normal `ParsedAddress`.
    """
    m = _PREF_RE.match(text.strip().upper())
    if not m:
        raise ValueError(f'Invalid prefixed address format: {text!r}')

    prefix = m.group('prefix')
    area = m.group('area')
    num_text = m.group('num')
    num = int(num_text, radix)
    suffix = m.group('suffix')

    if unit == 'byte' and suffix is None:
        suffix = 'L'
    if unit == 'byte':
        if suffix not in ('L', 'H'):
            raise ValueError(f'L/H suffix required for byte unit: {text!r}')
    elif unit == 'word':
        if suffix not in (None, 'W'):
            raise ValueError(f'W suffix only valid for packed word notation: {text!r}')
    else:
        if suffix is not None:
            raise ValueError(f'Suffix only valid for byte/packed-word notation: {text!r}')

    if unit == 'bit':
        if area not in _PROGRAM_BIT_SEGMENTS:
            raise ValueError(f'Unsupported program bit area: {area}')
        if not _in_segments(num, [(start, end) for start, end, _ in _PROGRAM_BIT_SEGMENTS[area]]):
            raise ValueError(f'Program bit address out of range: {area}{num:04X}')
    elif suffix == 'W' or (unit == 'byte' and area in _PROGRAM_BIT_SEGMENTS):
        _validate_packed_digits(area, text, len(num_text))
        _validate_packed_index(area, num, prefixed=True, text=text)

    ex_no = _P_EXNO[prefix]
    return ex_no, ParsedAddress(
        area=area,
        index=num,
        unit=unit,
        high=(suffix == 'H'),
        packed=(suffix == 'W'),
        digits=len(num_text),
    )


def encode_word_address(addr: ParsedAddress) -> int:
    """Encode a basic-area word address into the numeric protocol address.

    This is used for normal word commands such as `CMD=1C/1D`.
    For bit-device families, `...W` notation is accepted and mapped to the
    corresponding word address.
    """
    if addr.unit != 'word':
        raise ValueError('Expected word address')
    if addr.packed and addr.area not in _BIT_BASE:
        raise ValueError(f'W suffix is only valid for bit-device families: {addr.area}{addr.index:X}W')
    if addr.packed and not _in_segments(addr.index, _BASIC_PACKED_SEGMENTS[addr.area]):
        raise ValueError(f'Packed W address out of range: {addr.area}{addr.index:03X}W')
    base = _WORD_BASE.get(addr.area)
    if base is None:
        raise ValueError(f'Unsupported word area: {addr.area}')
    return base + addr.index


def encode_byte_address(addr: ParsedAddress) -> int:
    """Encode a basic-area byte address into the numeric protocol address.

    This is used for normal byte commands such as `CMD=1E/1F`.
    For bit-device families, `...L` and `...H` are treated as W/H/L addressing.
    """
    if addr.unit != 'byte':
        raise ValueError('Expected byte address')
    if addr.area in _BASIC_PACKED_SEGMENTS and not _in_segments(addr.index, _BASIC_PACKED_SEGMENTS[addr.area]):
        suffix = 'H' if addr.high else 'L'
        raise ValueError(f'Packed byte address out of range: {addr.area}{addr.index:03X}{suffix}')
    base = _BYTE_BASE.get(addr.area)
    if base is None:
        raise ValueError(f'Unsupported byte area: {addr.area}')
    return base + addr.index * 2 + (1 if addr.high else 0)


def encode_bit_address(addr: ParsedAddress) -> int:
    """Encode a basic-area bit address into the numeric protocol address.

    This is used for normal bit commands such as `CMD=20/21`.
    """
    if addr.unit != 'bit':
        raise ValueError('Expected bit address')
    base = _BIT_BASE.get(addr.area)
    if base is None:
        raise ValueError(f'Unsupported bit area: {addr.area}')
    if not _in_segments(addr.index, _BASIC_BIT_SEGMENTS[addr.area]):
        raise ValueError(f'Bit address out of range for {addr.area}: {addr.area}{addr.index:04X}')
    return base + addr.index


def encode_program_word_address(addr: ParsedAddress) -> int:
    """Encode a prefixed (`P1/P2/P3`) word address for `CMD=94/95`.

    This also supports `...W` addressing on prefixed bit-device families.
    """
    if addr.unit != 'word':
        raise ValueError('Expected word address')
    if addr.packed and addr.area not in _PROGRAM_BIT_SEGMENTS:
        raise ValueError(f'W suffix is only valid for prefixed bit-device families: {addr.area}{addr.index:X}W')
    segments = _PROGRAM_WORD_SEGMENTS.get(addr.area)
    if segments is None:
        segments = _PROGRAM_BIT_WORD_SEGMENTS.get(addr.area)
    if segments is None:
        raise ValueError(f'Unsupported program word area: {addr.area}')
    for start, end, base in segments:
        if start <= addr.index <= end:
            return base + (addr.index - start)
    raise ValueError(f'Program word address out of range: {addr.area}{addr.index:04X}')


def encode_program_byte_address(addr: ParsedAddress) -> int:
    """Encode a prefixed (`P1/P2/P3`) byte address for `CMD=96/97`.

    This also supports `...L` / `...H` addressing on prefixed bit-device
    families.
    """
    if addr.unit != 'byte':
        raise ValueError('Expected byte address')
    segments = _PROGRAM_BYTE_SEGMENTS.get(addr.area)
    if segments is None:
        segments = _PROGRAM_BIT_BYTE_SEGMENTS.get(addr.area)
    if segments is None:
        raise ValueError(f'Unsupported program byte area: {addr.area}')
    for start, end, base in segments:
        if start <= addr.index <= end:
            return base + (addr.index - start) * 2 + (1 if addr.high else 0)
    suffix = 'H' if addr.high else 'L'
    raise ValueError(f'Program byte address out of range: {addr.area}{addr.index:04X}{suffix}')


def encode_program_bit_address(addr: ParsedAddress) -> Tuple[int, int]:
    """Encode a prefixed (`P1/P2/P3`) bit address for `CMD=98/99`.

    Returns `(bit_no, addr)` where `bit_no` is the bit position inside the
    addressed byte/word group and `addr` is the 16-bit monitor address field.
    """
    if addr.unit != 'bit':
        raise ValueError('Expected bit address')
    segments = _PROGRAM_BIT_SEGMENTS.get(addr.area)
    if segments is None:
        raise ValueError(f'Unsupported program bit area: {addr.area}')
    for start, end, byte_base in segments:
        if start <= addr.index <= end:
            rel = addr.index - start
            return rel & 0x07, byte_base + (rel >> 3)
    raise ValueError(f'Program bit address out of range: {addr.area}{addr.index:04X}')


def encode_exno_bit_u32(ex_no: int, bit_addr: int) -> int:
    """Encode a PC10 32-bit bit address from exchange number and bit address."""
    return ((ex_no & 0xFF) << 19) | (bit_addr & 0x7FFFF)


def encode_exno_byte_u32(ex_no: int, byte_addr: int) -> int:
    """Encode a PC10 32-bit byte address from exchange number and byte address."""
    return ((ex_no & 0xFF) << 16) | (byte_addr & 0xFFFF)


def split_u32_words(value: int) -> Tuple[int, int]:
    """Split a 32-bit value into `(low_word, high_word)`."""
    low = value & 0xFFFF
    high = (value >> 16) & 0xFFFF
    return low, high


def fr_block_ex_no(index: int) -> int:
    """Return the FR block ``Ex No.`` for a word index.

    FR is organized in 0x8000-word blocks. The manual's FR registration
    command (`CMD=CA`) uses the block `Ex No.` in the range ``0x40-0x7F``.
    """
    if index < 0x000000 or index > 0x1FFFFF:
        raise ValueError('FR index out of range (0x000000-0x1FFFFF)')
    return 0x40 + (index // 0x8000)


def encode_fr_word_addr32(index: int) -> int:
    """Encode an FR word index for PC10 block access (`CMD=C2/C3`).

    Real hardware FR access uses PC10 block read/write with:
    - high word: FR block `Ex No.` (`0x40-0x7F`)
    - low word: byte offset inside the 0x8000-word block
    """
    ex_no = fr_block_ex_no(index)
    byte_addr = (index % 0x8000) * 2
    return encode_exno_byte_u32(ex_no, byte_addr)


def encode_ext_no_address(area: str, index: int, unit: str) -> ExtNoAddress:
    """Encode an extended-area address into `(No., 16-bit address)`.

    This is the main helper for `CMD=94-99` on areas such as:
    - `ES`, `EN`, `H`
    - `U`, `EB`
    - extended bit-device families when they are addressed by word/byte form

    Note:
    - real-hardware `FR` word access uses `encode_fr_word_addr32()` with
      `CMD=C2/C3`, not `CMD=94-99`
    """
    area_u = area.upper()
    no: Optional[int] = None
    addr = index

    if area_u in _EXT_AREA_MAP:
        area_map = _EXT_AREA_MAP[area_u]
        no = area_map['no']
        if unit == 'word':
            addr = area_map['word_base'] + index
        elif unit == 'byte':
            addr = area_map['byte_base'] + index
        else:
            raise ValueError(f'Unsupported unit for extended No mapping: {unit}')
    elif area_u == 'EB':
        # EB blocks are 0x8000 each
        if index < 0x00000 or index > 0x3FFFF:
            raise ValueError('EB index out of range (0x00000-0x3FFFF)')
        block = index // 0x8000
        no = 0x09 + block
        addr = index % 0x8000
    elif area_u == 'FR':
        # FR blocks are 0x8000 each, Ex No 0x40-0x7F
        if index < 0x000000 or index > 0x1FFFFF:
            raise ValueError('FR index out of range (0x000000-0x1FFFFF)')
        block = index // 0x8000
        no = 0x40 + block
        addr = index % 0x8000
    else:
        raise ValueError(f'Unsupported extended area for No mapping: {area}')

    if addr < 0 or addr > 0xFFFF:
        raise ValueError('Address out of 16-bit range')

    return ExtNoAddress(no=no, addr=addr, unit=unit)

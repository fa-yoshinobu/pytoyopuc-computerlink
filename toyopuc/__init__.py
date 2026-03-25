"""Public package entry points for `toyopuc`.

Use:
- `ToyopucClient` for low-level protocol-oriented access
- `ToyopucDeviceClient` for string-address based access
- `resolve_device()` when you want address-family resolution without I/O
"""

__version__ = "0.1.2"

from .address import (
    encode_bit_address,
    encode_byte_address,
    encode_exno_bit_u32,
    encode_exno_byte_u32,
    encode_ext_no_address,
    encode_fr_word_addr32,
    encode_program_bit_address,
    encode_program_byte_address,
    encode_program_word_address,
    encode_word_address,
    fr_block_ex_no,
    parse_address,
    parse_prefixed_address,
    split_u32_words,
)
from .async_client import AsyncToyopucClient, AsyncToyopucDeviceClient
from .client import ToyopucClient, ToyopucTraceDirection, ToyopucTraceFrame
from .errors import ToyopucError, ToyopucProtocolError, ToyopucTimeoutError
from .high_level import ResolvedDevice, ToyopucDeviceClient, resolve_device
from .profiles import (
    ToyopucAddressingOptions,
    ToyopucAddressRange,
    ToyopucAreaDescriptor,
    ToyopucDeviceProfile,
    ToyopucDeviceProfiles,
)
from .protocol import ClockData, CpuStatusData
from .relay import RelayLayer, format_relay_hop, normalize_relay_hops, parse_relay_hops
from .utils import (
    open_and_connect,
    poll,
    read_dwords,
    read_named,
    read_typed,
    read_words,
    write_bit_in_word,
    write_typed,
)

__all__ = [
    "ToyopucClient",
    "AsyncToyopucClient",
    "AsyncToyopucDeviceClient",
    "ToyopucDeviceClient",
    "ResolvedDevice",
    "ClockData",
    "CpuStatusData",
    "RelayLayer",
    "ToyopucError",
    "ToyopucProtocolError",
    "ToyopucTimeoutError",
    "ToyopucTraceDirection",
    "ToyopucTraceFrame",
    "open_and_connect",
    "poll",
    "read_dwords",
    "read_named",
    "read_typed",
    "read_words",
    "write_bit_in_word",
    "write_typed",
    "parse_address",
    "parse_prefixed_address",
    "encode_word_address",
    "encode_byte_address",
    "encode_bit_address",
    "encode_program_word_address",
    "encode_program_byte_address",
    "encode_program_bit_address",
    "encode_exno_bit_u32",
    "encode_exno_byte_u32",
    "split_u32_words",
    "encode_ext_no_address",
    "fr_block_ex_no",
    "encode_fr_word_addr32",
    "parse_relay_hops",
    "normalize_relay_hops",
    "format_relay_hop",
    "resolve_device",
    "ToyopucAddressRange",
    "ToyopucAddressingOptions",
    "ToyopucAreaDescriptor",
    "ToyopucDeviceProfile",
    "ToyopucDeviceProfiles",
]

"""Cross-language spec compliance: TOYOPUC Computer Link protocol vectors.

Each vector in computerlink_frame_vectors.json defines the expected binary
output of a frame-builder function or the expected parsed fields of a response
frame. The same JSON is consumed by the .NET test suite, ensuring Python and
.NET produce identical bytes on the wire.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from toyopuc.protocol import (
    build_bit_read,
    build_bit_write,
    build_byte_read,
    build_clock_read,
    build_cpu_status_read,
    build_word_read,
    pack_bcd,
    parse_response,
)

_VECTORS_PATH = Path(__file__).parent / "vectors" / "computerlink_frame_vectors.json"
_DATA = json.loads(_VECTORS_PATH.read_text())

_FRAME_VECTORS = _DATA["frame_vectors"]
_RESPONSE_VECTORS = _DATA["response_vectors"]
_BCD_VECTORS = _DATA["bcd_vectors"]


def _build_frame(vec: dict[str, Any]) -> bytes:
    fn = vec["function"]
    if fn == "build_clock_read":
        return build_clock_read()
    if fn == "build_cpu_status_read":
        return build_cpu_status_read()
    if fn == "build_word_read":
        return build_word_read(vec["addr"], vec["count"])
    if fn == "build_byte_read":
        return build_byte_read(vec["addr"], vec["count"])
    if fn == "build_bit_read":
        return build_bit_read(vec["addr"])
    if fn == "build_bit_write":
        return build_bit_write(vec["addr"], vec["value"])
    raise ValueError(f"Unknown function: {fn}")


@pytest.mark.parametrize("vec", _FRAME_VECTORS, ids=lambda v: v["id"])
def test_frame_build(vec: dict[str, Any]) -> None:
    result = _build_frame(vec)
    expected = bytes.fromhex(vec["hex"])
    assert result == expected, (
        f"[{vec['id']}] got {result.hex()}, expected {vec['hex']}"
    )


@pytest.mark.parametrize("vec", _RESPONSE_VECTORS, ids=lambda v: v["id"])
def test_response_parse(vec: dict[str, Any]) -> None:
    raw = bytes.fromhex(vec["hex"])
    frame = parse_response(raw)
    assert frame.ft == vec["ft"], f"[{vec['id']}] ft mismatch"
    assert frame.rc == vec["rc"], f"[{vec['id']}] rc mismatch"
    assert frame.cmd == vec["cmd"], f"[{vec['id']}] cmd mismatch"
    assert frame.data == bytes.fromhex(vec["data_hex"]), f"[{vec['id']}] data mismatch"


@pytest.mark.parametrize("vec", _BCD_VECTORS, ids=lambda v: f"bcd_{v['value']}")
def test_pack_bcd(vec: dict[str, Any]) -> None:
    result = pack_bcd(vec["value"])
    assert result == vec["bcd_decimal"], (
        f"pack_bcd({vec['value']}) = {result}, expected {vec['bcd_decimal']}"
    )

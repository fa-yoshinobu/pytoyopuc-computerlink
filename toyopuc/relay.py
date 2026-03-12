from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Tuple

from .exceptions import ToyopucProtocolError
from .protocol import ResponseFrame, parse_response


@dataclass(frozen=True)
class RelayLayer:
    """One decoded relay wrapper layer from a `CMD=60` response."""

    link_no: int
    station_no: int
    ack: int
    inner_raw: bytes
    padding: bytes = b""


def parse_relay_hops(text: str) -> List[Tuple[int, int]]:
    """Parse relay hops from `P1-L2:N2` or `0x12:0x0002` style text."""
    hops: List[Tuple[int, int]] = []
    for part in text.split(","):
        item = part.strip()
        if not item:
            continue
        m = re.fullmatch(r"P([0-9A-Fa-f])[-:]L([0-9A-Fa-f])\s*:\s*N([0-9A-Fa-fx]+)", item, re.IGNORECASE)
        if m:
            link = (int(m.group(1), 16) << 4) | int(m.group(2), 16)
            station = int(m.group(3), 0)
            if station < 1:
                raise ValueError("N number must be >= 1")
            hops.append((link, station))
            continue
        m = re.fullmatch(r"([0-9A-Fa-f])[-:]([0-9A-Fa-f]):([0-9A-Fa-fx]+)", item)
        if m:
            link = (int(m.group(1), 16) << 4) | int(m.group(2), 16)
            station = int(m.group(3), 0)
            hops.append((link, station))
            continue
        if ":" not in item:
            raise ValueError("each hop must be LINK:STATION or P1-L2:N2")
        link_text, station_text = item.split(":", 1)
        hops.append((int(link_text, 0), int(station_text, 0)))
    if not hops:
        raise ValueError("at least one hop is required")
    return hops


def normalize_relay_hops(hops: str | Iterable[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Normalize relay hops from text or `(link, station)` pairs."""
    if isinstance(hops, str):
        return parse_relay_hops(hops)
    normalized = [(int(link) & 0xFF, int(station) & 0xFFFF) for link, station in hops]
    if not normalized:
        raise ValueError("at least one hop is required")
    return normalized


def format_relay_hop(link: int, station: int) -> str:
    """Format one relay hop in the preferred `P1-L2:N2` style."""
    return f"P{(link >> 4) & 0x0F:X}-L{link & 0x0F:X}:N{station} (0x{link:02X}:0x{station:04X})"


def parse_relay_inner_response(inner_raw: bytes) -> tuple[ResponseFrame, bytes]:
    """Parse one inner relay payload (`LL LH CMD ...`) into a response frame."""
    if len(inner_raw) < 3:
        raise ToyopucProtocolError("Inner relay response too short")
    inner_length = inner_raw[0] | (inner_raw[1] << 8)
    expected = 2 + inner_length
    if len(inner_raw) < expected:
        raise ToyopucProtocolError(
            f"Inner relay response truncated: expected {expected} bytes, got {len(inner_raw)} bytes"
        )
    inner_frame = bytes([0x80, 0x00]) + inner_raw[:expected]
    padding = inner_raw[expected:]
    return parse_response(inner_frame), padding


def unwrap_relay_response_chain(resp: ResponseFrame) -> tuple[List[RelayLayer], ResponseFrame | None]:
    """Unwrap nested relay responses until a non-relay inner response is reached.

    Returns `(layers, final_response)`. When a relay layer returns NAK
    (`ack != 0x06`), `final_response` is `None` and the last layer contains the
    raw relay NAK payload.
    """
    layers: List[RelayLayer] = []
    current = resp
    while current.cmd == 0x60:
        if len(current.data) < 4:
            raise ToyopucProtocolError("Relay response data too short")
        link_no = current.data[0]
        station_no = current.data[1] | (current.data[2] << 8)
        ack = current.data[3]
        inner_raw = current.data[4:]
        if ack != 0x06:
            layers.append(RelayLayer(link_no, station_no, ack, inner_raw))
            return layers, None
        current, padding = parse_relay_inner_response(inner_raw)
        layers.append(RelayLayer(link_no, station_no, ack, inner_raw, padding))
    return layers, current

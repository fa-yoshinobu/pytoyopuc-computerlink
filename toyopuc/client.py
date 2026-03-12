
from __future__ import annotations

import socket
import time
from datetime import datetime
from typing import Iterable, List, Optional, Tuple, Self

from .address import encode_fr_word_addr32, fr_block_ex_no
from .exceptions import ToyopucError, ToyopucProtocolError, ToyopucTimeoutError
from .protocol import (
    CpuStatusData,
    FT_RESPONSE,
    ClockData,
    ResponseFrame,
    build_bit_read,
    build_bit_write,
    build_byte_read,
    build_byte_write,
    build_command,
    build_cpu_status_read,
    build_cpu_status_read_a0,
    build_clock_read,
    build_clock_write,
    build_ext_byte_read,
    build_ext_byte_write,
    build_ext_multi_read,
    build_ext_multi_write,
    build_ext_word_read,
    build_ext_word_write,
    build_fr_register,
    build_multi_byte_read,
    build_multi_byte_write,
    build_multi_word_read,
    build_multi_word_write,
    build_pc10_block_read,
    build_pc10_block_write,
    build_pc10_multi_read,
    build_pc10_multi_write,
    build_relay_command,
    build_relay_nested,
    build_word_read,
    build_word_write,
    parse_clock_data,
    parse_cpu_status_data,
    parse_cpu_status_data_a0,
    parse_cpu_status_data_a0_raw,
    parse_response,
    unpack_u16_le,
)
from .relay import normalize_relay_hops, parse_relay_inner_response, unwrap_relay_response_chain


ERROR_CODE_DESCRIPTIONS = {
    0x11: 'CPU module hardware failure',
    0x20: 'Relay command ENQ fixed data is not 0x05',
    0x21: 'Invalid transfer number in relay command',
    0x23: 'Invalid command code',
    0x24: 'Invalid subcommand code',
    0x25: 'Invalid command-format data byte',
    0x26: 'Invalid function-call operand count',
    0x31: 'Write or function call prohibited during sequence operation',
    0x32: 'Command not executable during stop continuity',
    0x33: 'Debug function called while not in debug mode',
    0x34: 'Access prohibited by configuration',
    0x35: 'Execution-priority limiting configuration prohibits execution',
    0x36: 'Execution-priority limiting by another device prohibits execution',
    0x39: 'Reset required after writing I/O parameters before scan start',
    0x3C: 'Command not executable during fatal failure',
    0x3D: 'Competing process prevents execution',
    0x3E: 'Command not executable because reset exists',
    0x3F: 'Command not executable because of stop duration',
    0x40: 'Address or address+count is out of range',
    0x41: 'Word/byte count is out of range',
    0x42: 'Undesignated data was sent',
    0x43: 'Invalid function-call operand',
    0x52: 'Timer/counter set or current value access command mismatch',
    0x66: 'No reply from relay link module',
    0x70: 'Relay link module not executable',
    0x72: 'No reply from relay link module',
    0x73: 'Relay command collision on same link module; retry required',
}


_FR_BLOCK_WORDS = 0x8000
_FR_MAX_INDEX = 0x1FFFFF
_FR_IO_CHUNK_WORDS = 0x0200


def _validate_fr_index(index: int) -> int:
    idx = int(index)
    if idx < 0 or idx > _FR_MAX_INDEX:
        raise ValueError('FR index out of range (0x000000-0x1FFFFF)')
    return idx


def _iter_fr_segments(start_index: int, word_count: int):
    index = _validate_fr_index(start_index)
    remaining = int(word_count)
    if remaining < 1:
        raise ValueError('word_count must be >= 1')
    while remaining > 0:
        block_offset = index % _FR_BLOCK_WORDS
        chunk = min(remaining, _FR_BLOCK_WORDS - block_offset)
        yield index, chunk
        index += chunk
        remaining -= chunk


def _iter_fr_io_segments(start_index: int, word_count: int, max_chunk_words: int = _FR_IO_CHUNK_WORDS):
    if int(max_chunk_words) < 1:
        raise ValueError('max_chunk_words must be >= 1')
    for block_index, block_words in _iter_fr_segments(start_index, word_count):
        offset = 0
        while offset < block_words:
            chunk = min(block_words - offset, int(max_chunk_words))
            yield block_index + offset, chunk
            offset += chunk


def _fr_commit_blocks(start_index: int, word_count: int) -> List[int]:
    return [segment_start for segment_start, _ in _iter_fr_segments(start_index, word_count)]


def format_response_error(resp: ResponseFrame) -> str:
    msg = f'Response error rc=0x{resp.rc:02X}'
    if resp.rc == 0x10:
        # Some PLCs return the detailed error code in CMD with no data,
        # e.g. `80 10 01 00 40`. Others may carry it in the response data.
        err = resp.data[-1] if resp.data else resp.cmd
        detail = ERROR_CODE_DESCRIPTIONS.get(err, 'Unknown error code')
        return f'{msg}, error_code=0x{err:02X} ({detail}), data={resp.data.hex()}'
    return f'{msg}, data={resp.data.hex()}'


def _extract_response_error_code(frame: bytes | None) -> Optional[int]:
    if not frame:
        return None
    try:
        resp = parse_response(frame)
    except Exception:
        return None
    if resp.rc != 0x10:
        return None
    return resp.data[-1] if resp.data else resp.cmd


def _extract_relay_nak_error_code(frame: bytes | None) -> Optional[int]:
    if not frame:
        return None
    try:
        resp = parse_response(frame)
    except Exception:
        return None
    if resp.cmd != 0x60:
        return None
    current = resp
    while current.cmd == 0x60:
        if len(current.data) < 4:
            return None
        ack = current.data[3]
        inner_raw = current.data[4:]
        if ack != 0x06:
            if len(inner_raw) < 3:
                return None
            inner_length = inner_raw[0] | (inner_raw[1] << 8)
            if inner_length < 1 or len(inner_raw) < 2 + inner_length:
                return None
            return inner_raw[2]
        try:
            current, _padding = parse_relay_inner_response(inner_raw)
        except Exception:
            return None
    return None


class ToyopucClient:
    """Low-level TOYOPUC computer-link client.

    Use this class when you want explicit control over command families,
    numeric addresses, and transport settings. For string-address driven use,
    prefer `ToyopucHighLevelClient`.
    """
    def __init__(
        self,
        host: str,
        port: int,
        *,
        local_port: int = 0,
        protocol: str = 'tcp',
        timeout: float = 3.0,
        retries: int = 0,
        retry_delay: float = 0.2,
        recv_bufsize: int = 8192,
    ) -> None:
        self.host = host
        self.port = port
        self.local_port = int(local_port)
        self.protocol = protocol.lower()
        self.timeout = timeout
        self.retries = max(0, int(retries))
        self.retry_delay = float(retry_delay)
        self.recv_bufsize = recv_bufsize
        self._sock: Optional[socket.socket] = None
        self._last_tx: Optional[bytes] = None
        self._last_rx: Optional[bytes] = None
        self._fr_wait_prefers_a0: Optional[bool] = None
        self._relay_fr_wait_prefers_a0: Optional[bool] = None

    def __enter__(self) -> Self:
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def connect(self) -> None:
        if self._sock:
            return
        if self.protocol == 'tcp':
            sock = socket.create_connection((self.host, self.port), self.timeout)
        elif self.protocol == 'udp':
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            if self.local_port:
                sock.bind(('', self.local_port))
            sock.settimeout(self.timeout)
        else:
            raise ValueError("protocol must be 'tcp' or 'udp'")
        self._sock = sock

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            finally:
                self._sock = None
        self._last_tx = None
        self._last_rx = None

    @property
    def last_tx(self) -> Optional[bytes]:
        return self._last_tx

    @property
    def last_rx(self) -> Optional[bytes]:
        return self._last_rx

    def _recv_exact(self, n: int) -> bytes:
        assert self._sock is not None
        chunks = []
        remaining = n
        while remaining > 0:
            try:
                chunk = self._sock.recv(remaining)
            except socket.timeout as e:
                raise ToyopucTimeoutError('Receive timeout') from e
            if not chunk:
                raise ToyopucProtocolError('Connection closed while receiving')
            chunks.append(chunk)
            remaining -= len(chunk)
        return b''.join(chunks)

    def _send_and_recv(self, payload: bytes) -> ResponseFrame:
        attempt = 0
        last_err: Optional[Exception] = None
        while attempt <= self.retries:
            attempt += 1
            if not self._sock:
                self.connect()
            assert self._sock is not None
            self._last_tx = payload
            self._last_rx = None

            try:
                if self.protocol == 'tcp':
                    self._sock.sendall(payload)
                    header = self._recv_exact(4)
                    ll, lh = header[2], header[3]
                    length = ll | (lh << 8)
                    body = self._recv_exact(length)
                    frame = header + body
                else:
                    self._sock.sendto(payload, (self.host, self.port))
                    frame, _ = self._sock.recvfrom(self.recv_bufsize)
            except socket.timeout as e:
                last_err = ToyopucTimeoutError('Send/receive timeout')
                if attempt <= self.retries:
                    try:
                        self.close()
                    except Exception:
                        pass
                    import time

                    time.sleep(self.retry_delay)
                    continue
                raise last_err from e
            except OSError as e:
                last_err = ToyopucError('Socket error')
                if attempt <= self.retries:
                    try:
                        self.close()
                    except Exception:
                        pass
                    import time

                    time.sleep(self.retry_delay)
                    continue
                raise last_err from e

            self._last_rx = frame
            resp = parse_response(frame)
            if resp.ft != FT_RESPONSE:
                raise ToyopucProtocolError(f'Unexpected frame type: 0x{resp.ft:02X}')
            if resp.rc != 0x00:
                raise ToyopucError(format_response_error(resp))
            return resp

        if last_err:
            raise last_err
        raise ToyopucError('Send/receive failed')

    def send_raw(self, cmd: int, data: bytes = b'') -> ResponseFrame:
        payload = build_command(cmd, data)
        return self._send_and_recv(payload)

    def send_payload(self, payload: bytes) -> ResponseFrame:
        """Send a fully-built command payload and return the parsed response."""
        return self._send_and_recv(payload)

    def read_words(self, addr: int, count: int) -> List[int]:
        """Read one or more basic-area words with `CMD=1C`."""
        resp = self._send_and_recv(build_word_read(addr, count))
        if resp.cmd != 0x1C:
            raise ToyopucProtocolError('Unexpected CMD in response')
        return unpack_u16_le(resp.data)

    def write_words(self, addr: int, values: Iterable[int]) -> None:
        """Write one or more basic-area words with `CMD=1D`."""
        resp = self._send_and_recv(build_word_write(addr, values))
        if resp.cmd != 0x1D:
            raise ToyopucProtocolError('Unexpected CMD in response')

    def read_bytes(self, addr: int, count: int) -> bytes:
        """Read one or more basic-area bytes with `CMD=1E`."""
        resp = self._send_and_recv(build_byte_read(addr, count))
        if resp.cmd != 0x1E:
            raise ToyopucProtocolError('Unexpected CMD in response')
        return resp.data

    def write_bytes(self, addr: int, values: Iterable[int]) -> None:
        """Write one or more basic-area bytes with `CMD=1F`."""
        resp = self._send_and_recv(build_byte_write(addr, values))
        if resp.cmd != 0x1F:
            raise ToyopucProtocolError('Unexpected CMD in response')

    def read_bit(self, addr: int) -> bool:
        """Read one basic-area bit with `CMD=20`."""
        resp = self._send_and_recv(build_bit_read(addr))
        if resp.cmd != 0x20:
            raise ToyopucProtocolError('Unexpected CMD in response')
        if len(resp.data) != 1:
            raise ToyopucProtocolError('Bit read response must be 1 byte')
        return resp.data[0] != 0

    def write_bit(self, addr: int, value: bool) -> None:
        """Write one basic-area bit with `CMD=21`."""
        resp = self._send_and_recv(build_bit_write(addr, 1 if value else 0))
        if resp.cmd != 0x21:
            raise ToyopucProtocolError('Unexpected CMD in response')

    def read_words_multi(self, addrs: Iterable[int]) -> List[int]:
        """Read multiple non-contiguous basic-area words with `CMD=22`."""
        resp = self._send_and_recv(build_multi_word_read(addrs))
        if resp.cmd != 0x22:
            raise ToyopucProtocolError('Unexpected CMD in response')
        return unpack_u16_le(resp.data)

    def write_words_multi(self, pairs: Iterable[Tuple[int, int]]) -> None:
        """Write multiple non-contiguous basic-area words with `CMD=23`."""
        resp = self._send_and_recv(build_multi_word_write(pairs))
        if resp.cmd != 0x23:
            raise ToyopucProtocolError('Unexpected CMD in response')

    def read_bytes_multi(self, addrs: Iterable[int]) -> bytes:
        """Read multiple non-contiguous basic-area bytes with `CMD=24`."""
        resp = self._send_and_recv(build_multi_byte_read(addrs))
        if resp.cmd != 0x24:
            raise ToyopucProtocolError('Unexpected CMD in response')
        return resp.data

    def write_bytes_multi(self, pairs: Iterable[Tuple[int, int]]) -> None:
        """Write multiple non-contiguous basic-area bytes with `CMD=25`."""
        resp = self._send_and_recv(build_multi_byte_write(pairs))
        if resp.cmd != 0x25:
            raise ToyopucProtocolError('Unexpected CMD in response')

    def read_ext_words(self, no: int, addr: int, count: int) -> List[int]:
        """Read extended-area words with `CMD=94` using `(No., addr)`."""
        resp = self._send_and_recv(build_ext_word_read(no, addr, count))
        if resp.cmd != 0x94:
            raise ToyopucProtocolError('Unexpected CMD in response')
        return unpack_u16_le(resp.data)

    def write_ext_words(self, no: int, addr: int, values: Iterable[int]) -> None:
        """Write extended-area words with `CMD=95` using `(No., addr)`."""
        resp = self._send_and_recv(build_ext_word_write(no, addr, values))
        if resp.cmd != 0x95:
            raise ToyopucProtocolError('Unexpected CMD in response')

    def read_ext_bytes(self, no: int, addr: int, count: int) -> bytes:
        """Read extended-area bytes with `CMD=96` using `(No., addr)`."""
        resp = self._send_and_recv(build_ext_byte_read(no, addr, count))
        if resp.cmd != 0x96:
            raise ToyopucProtocolError('Unexpected CMD in response')
        return resp.data

    def write_ext_bytes(self, no: int, addr: int, values: Iterable[int]) -> None:
        """Write extended-area bytes with `CMD=97` using `(No., addr)`."""
        resp = self._send_and_recv(build_ext_byte_write(no, addr, values))
        if resp.cmd != 0x97:
            raise ToyopucProtocolError('Unexpected CMD in response')

    def read_ext_multi(
        self,
        bit_points: Iterable[Tuple[int, int, int]],
        byte_points: Iterable[Tuple[int, int]],
        word_points: Iterable[Tuple[int, int]],
    ) -> bytes:
        """Read mixed extended points with `CMD=98`.

        `bit_points` items are `(no, bit_no, addr)`.
        `byte_points` items are `(no, addr)`.
        `word_points` items are `(no, addr)`.
        """
        resp = self._send_and_recv(
            build_ext_multi_read(list(bit_points), list(byte_points), list(word_points))
        )
        if resp.cmd != 0x98:
            raise ToyopucProtocolError('Unexpected CMD in response')
        return resp.data

    def write_ext_multi(
        self,
        bit_points: Iterable[Tuple[int, int, int, int]],
        byte_points: Iterable[Tuple[int, int, int]],
        word_points: Iterable[Tuple[int, int, int]],
    ) -> None:
        """Write mixed extended points with `CMD=99`."""
        resp = self._send_and_recv(
            build_ext_multi_write(list(bit_points), list(byte_points), list(word_points))
        )
        if resp.cmd != 0x99:
            raise ToyopucProtocolError('Unexpected CMD in response')

    def pc10_block_read(self, addr32: int, count: int) -> bytes:
        """Read PC10 block data with `CMD=C2` from a 32-bit byte address."""
        resp = self._send_and_recv(build_pc10_block_read(addr32, count))
        if resp.cmd != 0xC2:
            raise ToyopucProtocolError('Unexpected CMD in response')
        return resp.data

    def pc10_block_write(self, addr32: int, data_bytes: bytes) -> None:
        """Write PC10 block data with `CMD=C3` to a 32-bit byte address."""
        resp = self._send_and_recv(build_pc10_block_write(addr32, data_bytes))
        if resp.cmd != 0xC3:
            raise ToyopucProtocolError('Unexpected CMD in response')

    def pc10_multi_read(self, payload: bytes) -> bytes:
        """Read PC10 multi-point data with `CMD=C4` using a prebuilt payload."""
        resp = self._send_and_recv(build_pc10_multi_read(payload))
        if resp.cmd != 0xC4:
            raise ToyopucProtocolError('Unexpected CMD in response')
        return resp.data

    def pc10_multi_write(self, payload: bytes) -> None:
        """Write PC10 multi-point data with `CMD=C5` using a prebuilt payload."""
        resp = self._send_and_recv(build_pc10_multi_write(payload))
        if resp.cmd != 0xC5:
            raise ToyopucProtocolError('Unexpected CMD in response')

    def read_fr_words(self, index: int, count: int) -> List[int]:
        """Read FR words via PC10 block read (`CMD=C2`).

        `FR` real-hardware access uses 32-bit PC10 addressing with
        `Ex No.=0x40-0x7F`, not `CMD=94`.
        """
        values: List[int] = []
        for chunk_index, chunk_words in _iter_fr_io_segments(index, count):
            data = self.pc10_block_read(encode_fr_word_addr32(chunk_index), chunk_words * 2)
            values.extend(unpack_u16_le(data))
        return values

    def write_fr_words(self, index: int, values: Iterable[int], *, commit: bool = False) -> None:
        """Write FR words via PC10 block write (`CMD=C3`).

        This updates the FR work area. Persisting the block to flash requires
        `CMD=CA`. Set `commit=True` to commit every affected FR block after the
        write completes.
        """
        self.write_fr_words_ex(index, values, commit=commit, wait=commit)

    def write_fr_words_ex(
        self,
        index: int,
        values: Iterable[int],
        *,
        commit: bool = False,
        wait: bool = False,
        timeout: float = 30.0,
        poll_interval: float = 0.2,
    ) -> None:
        """Write FR words, with optional commit and completion wait.

        When ``commit=True``, this follows the manual's 64-kbyte block unit:
        each affected FR block is written with `C3`, committed with `CA`, and
        optionally waited on before moving to the next block.
        """
        vals = [int(v) & 0xFFFF for v in values]
        if not vals:
            raise ValueError('values must contain at least one word')
        offset = 0
        for block_index, block_words in _iter_fr_segments(index, len(vals)):
            block_offset = 0
            while block_offset < block_words:
                chunk_words = min(block_words - block_offset, _FR_IO_CHUNK_WORDS)
                chunk_vals = vals[offset : offset + chunk_words]
                data = b''.join(v.to_bytes(2, 'little') for v in chunk_vals)
                self.pc10_block_write(encode_fr_word_addr32(block_index + block_offset), data)
                offset += chunk_words
                block_offset += chunk_words
            if commit:
                self.commit_fr_block(
                    block_index,
                    wait=wait,
                    timeout=timeout,
                    poll_interval=poll_interval,
                )

    def commit_fr_block(
        self,
        index: int,
        *,
        wait: bool = False,
        timeout: float = 30.0,
        poll_interval: float = 0.2,
    ) -> Optional[CpuStatusData]:
        """Commit the FR block containing `index` via `CMD=CA`.

        By default this waits until `Data7.bit4` (`under_writing_flash_register`)
        clears and raises on `Data7.bit5` (`abnormal_write_flash_register`).
        """
        self.fr_register(fr_block_ex_no(index))
        if wait:
            return self.wait_fr_write_complete(timeout=timeout, poll_interval=poll_interval)
        return None

    def commit_fr_range(
        self,
        index: int,
        count: int = 1,
        *,
        wait: bool = False,
        timeout: float = 30.0,
        poll_interval: float = 0.2,
    ) -> Optional[CpuStatusData]:
        """Commit every FR block touched by a contiguous word range."""
        last_status: Optional[CpuStatusData] = None
        for block_index in _fr_commit_blocks(index, count):
            last_status = self.commit_fr_block(
                block_index,
                wait=wait,
                timeout=timeout,
                poll_interval=poll_interval,
            )
        return last_status

    def write_fr_words_committed(self, index: int, values: Iterable[int]) -> None:
        """Write FR words and commit every affected FR block."""
        self.write_fr_words_ex(index, values, commit=True, wait=True)

    def fr_register(self, ex_no: int) -> None:
        """Issue the FR-register command `CMD=CA`."""
        resp = self._send_and_recv(build_fr_register(ex_no))
        if resp.cmd != 0xCA:
            raise ToyopucProtocolError('Unexpected CMD in response')

    def relay_command(self, link_no: int, station_no: int, inner_payload: bytes) -> ResponseFrame:
        """Wrap a command in one relay hop using `CMD=60`."""
        return self._send_and_recv(build_relay_command(link_no, station_no, inner_payload))

    def relay_nested(self, hops: Iterable[Tuple[int, int]], inner_payload: bytes) -> ResponseFrame:
        """Wrap a command in multiple relay hops using nested `CMD=60` frames."""
        return self._send_and_recv(build_relay_nested(list(hops), inner_payload))

    def send_via_relay(self, hops: str | Iterable[Tuple[int, int]], inner_payload: bytes) -> ResponseFrame:
        """Send a command through relay hops and return the final inner response."""
        outer = self.relay_nested(normalize_relay_hops(hops), inner_payload)
        layers, final = unwrap_relay_response_chain(outer)
        if final is None:
            last = layers[-1]
            raise ToyopucProtocolError(
                f"Relay NAK at link=0x{last.link_no:02X}, station=0x{last.station_no:04X}, ack=0x{last.ack:02X}"
            )
        return final

    def relay_read_words(self, hops: str | Iterable[Tuple[int, int]], addr: int, count: int) -> List[int]:
        """Read one or more basic-area words through relay hops."""
        resp = self.send_via_relay(hops, build_word_read(addr, count))
        if resp.cmd != 0x1C:
            raise ToyopucProtocolError('Unexpected CMD in relay word-read response')
        return unpack_u16_le(resp.data)

    def relay_write_words(self, hops: str | Iterable[Tuple[int, int]], addr: int, values: Iterable[int]) -> None:
        """Write one or more basic-area words through relay hops."""
        resp = self.send_via_relay(hops, build_word_write(addr, values))
        if resp.cmd != 0x1D:
            raise ToyopucProtocolError('Unexpected CMD in relay word-write response')

    def relay_read_clock(self, hops: str | Iterable[Tuple[int, int]]) -> ClockData:
        """Read the CPU clock through relay hops."""
        resp = self.send_via_relay(hops, build_clock_read())
        if resp.cmd != 0x32:
            raise ToyopucProtocolError('Unexpected CMD in relay clock response')
        try:
            return parse_clock_data(resp.data)
        except Exception as e:
            raise ToyopucProtocolError(
                f'Failed to parse relay clock response data={resp.data.hex()}'
            ) from e

    def relay_write_clock(self, hops: str | Iterable[Tuple[int, int]], value: datetime) -> None:
        """Set the CPU clock through relay hops via `CMD=32 / 71 00`."""
        weekday = (value.weekday() + 1) % 7
        resp = self.send_via_relay(
            hops,
            build_clock_write(
                value.second,
                value.minute,
                value.hour,
                value.day,
                value.month,
                value.year % 100,
                weekday,
            ),
        )
        if resp.cmd != 0x32:
            raise ToyopucProtocolError('Unexpected CMD in relay clock-write response')
        if resp.data != bytes([0x71, 0x00]):
            raise ToyopucProtocolError('Unexpected relay clock-write response body')

    def relay_read_cpu_status(self, hops: str | Iterable[Tuple[int, int]]) -> CpuStatusData:
        """Read the 8-byte CPU status block through relay hops."""
        resp = self.send_via_relay(hops, build_cpu_status_read())
        if resp.cmd != 0x32:
            raise ToyopucProtocolError('Unexpected CMD in relay CPU status response')
        try:
            return parse_cpu_status_data(resp.data)
        except Exception as e:
            raise ToyopucProtocolError(
                f'Failed to parse relay CPU status response data={resp.data.hex()}'
            ) from e

    def relay_read_cpu_status_a0_raw(self, hops: str | Iterable[Tuple[int, int]]) -> bytes:
        """Read raw 8-byte CPU status through relay hops via `CMD=A0 / 01 10`."""
        resp = self.send_via_relay(hops, build_cpu_status_read_a0())
        if resp.cmd != 0xA0:
            raise ToyopucProtocolError('Unexpected CMD in relay A0 CPU status response')
        try:
            return parse_cpu_status_data_a0_raw(resp.data)
        except Exception as e:
            raise ToyopucProtocolError(
                f'Failed to parse relay A0 CPU status response data={resp.data.hex()}'
            ) from e

    def relay_read_cpu_status_a0(self, hops: str | Iterable[Tuple[int, int]]) -> CpuStatusData:
        """Read decoded CPU status through relay hops via `CMD=A0 / 01 10`."""
        resp = self.send_via_relay(hops, build_cpu_status_read_a0())
        if resp.cmd != 0xA0:
            raise ToyopucProtocolError('Unexpected CMD in relay A0 CPU status response')
        try:
            return parse_cpu_status_data_a0(resp.data)
        except Exception as e:
            raise ToyopucProtocolError(
                f'Failed to parse relay A0 CPU status response data={resp.data.hex()}'
            ) from e

    def relay_write_fr_words(self, hops: str | Iterable[Tuple[int, int]], index: int, values: Iterable[int], *, commit: bool = False) -> None:
        """Write FR words through relay hops, optionally committing touched blocks."""
        self.relay_write_fr_words_ex(hops, index, values, commit=commit, wait=commit)

    def relay_write_fr_words_ex(
        self,
        hops: str | Iterable[Tuple[int, int]],
        index: int,
        values: Iterable[int],
        *,
        commit: bool = False,
        wait: bool = False,
        timeout: float = 30.0,
        poll_interval: float = 0.2,
    ) -> None:
        """Write FR words through relay hops, with optional commit and completion wait."""
        vals = [int(v) & 0xFFFF for v in values]
        if not vals:
            raise ValueError('values must contain at least one word')
        offset = 0
        for block_index, block_words in _iter_fr_segments(index, len(vals)):
            block_offset = 0
            while block_offset < block_words:
                chunk_words = min(block_words - block_offset, _FR_IO_CHUNK_WORDS)
                chunk_vals = vals[offset : offset + chunk_words]
                data = b''.join(v.to_bytes(2, 'little') for v in chunk_vals)
                resp = self.send_via_relay(
                    hops,
                    build_pc10_block_write(encode_fr_word_addr32(block_index + block_offset), data),
                )
                if resp.cmd != 0xC3:
                    raise ToyopucProtocolError('Unexpected CMD in relay FR block-write response')
                offset += chunk_words
                block_offset += chunk_words
            if commit:
                self.relay_commit_fr_block(
                    hops,
                    block_index,
                    wait=wait,
                    timeout=timeout,
                    poll_interval=poll_interval,
                )

    def relay_fr_register(self, hops: str | Iterable[Tuple[int, int]], ex_no: int) -> None:
        """Issue the FR-register command `CMD=CA` through relay hops."""
        resp = self.send_via_relay(hops, build_fr_register(ex_no))
        if resp.cmd != 0xCA:
            raise ToyopucProtocolError('Unexpected CMD in relay FR-register response')

    def relay_commit_fr_block(
        self,
        hops: str | Iterable[Tuple[int, int]],
        index: int,
        *,
        wait: bool = False,
        timeout: float = 30.0,
        poll_interval: float = 0.2,
    ) -> Optional[CpuStatusData]:
        """Commit the remote FR block containing `index` via relay `CMD=CA`."""
        self.relay_fr_register(hops, fr_block_ex_no(index))
        if wait:
            return self.relay_wait_fr_write_complete(hops, timeout=timeout, poll_interval=poll_interval)
        return None

    def relay_commit_fr_range(
        self,
        hops: str | Iterable[Tuple[int, int]],
        index: int,
        count: int = 1,
        *,
        wait: bool = False,
        timeout: float = 30.0,
        poll_interval: float = 0.2,
    ) -> Optional[CpuStatusData]:
        """Commit every FR block touched by a contiguous relay FR range."""
        last_status: Optional[CpuStatusData] = None
        for block_index in _fr_commit_blocks(index, count):
            last_status = self.relay_commit_fr_block(
                hops,
                block_index,
                wait=wait,
                timeout=timeout,
                poll_interval=poll_interval,
            )
        return last_status

    def relay_wait_fr_write_complete(
        self,
        hops: str | Iterable[Tuple[int, int]],
        *,
        timeout: float = 30.0,
        poll_interval: float = 0.2,
    ) -> CpuStatusData:
        """Poll remote FR flash-write completion status through relay hops."""
        deadline = time.monotonic() + max(0.0, float(timeout))
        interval = max(0.01, float(poll_interval))
        while True:
            use_a0 = self._relay_fr_wait_prefers_a0 is not False
            if use_a0:
                try:
                    status = self.relay_read_cpu_status_a0(hops)
                    self._relay_fr_wait_prefers_a0 = True
                except (ToyopucError, ToyopucProtocolError):
                    err = _extract_response_error_code(self.last_rx)
                    if err is None:
                        err = _extract_relay_nak_error_code(self.last_rx)
                    if err in (0x23, 0x24, 0x25, 0x26):
                        self._relay_fr_wait_prefers_a0 = False
                        status = self.relay_read_cpu_status(hops)
                    else:
                        raise
            else:
                status = self.relay_read_cpu_status(hops)
            if status.abnormal_write_flash_register:
                raise ToyopucError('FR flash write failed: abnormal_write_flash_register=1')
            if not status.under_writing_flash_register:
                return status
            if time.monotonic() >= deadline:
                raise ToyopucTimeoutError('Timed out waiting for relay FR flash write completion')
            time.sleep(interval)

    def read_clock(self) -> ClockData:
        """Read the CPU clock via `CMD=32 / 70 00`."""
        resp = self._send_and_recv(build_clock_read())
        if resp.cmd != 0x32:
            raise ToyopucProtocolError('Unexpected CMD in response')
        try:
            return parse_clock_data(resp.data)
        except Exception as e:
            raise ToyopucProtocolError(
                f'Failed to parse clock response data={resp.data.hex()}'
            ) from e

    def read_cpu_status(self) -> CpuStatusData:
        """Read the 8-byte CPU status block via `CMD=32 / 11 00`."""
        resp = self._send_and_recv(build_cpu_status_read())
        if resp.cmd != 0x32:
            raise ToyopucProtocolError('Unexpected CMD in response')
        try:
            return parse_cpu_status_data(resp.data)
        except Exception as e:
            raise ToyopucProtocolError(
                f'Failed to parse CPU status response data={resp.data.hex()}'
            ) from e

    def read_cpu_status_a0_raw(self) -> bytes:
        """Read raw 8-byte CPU status via `CMD=A0 / 01 10`.

        This command path is used in the flash/FR completion flow. The library
        currently returns the 8 raw status bytes because the exact bit mapping
        for this path has not been finalized yet.
        """
        resp = self._send_and_recv(build_cpu_status_read_a0())
        if resp.cmd != 0xA0:
            raise ToyopucProtocolError('Unexpected CMD in response')
        try:
            return parse_cpu_status_data_a0_raw(resp.data)
        except Exception as e:
            raise ToyopucProtocolError(
                f'Failed to parse A0 CPU status response data={resp.data.hex()}'
            ) from e

    def read_cpu_status_a0(self) -> CpuStatusData:
        """Read decoded CPU status via `CMD=A0 / 01 10`."""
        resp = self._send_and_recv(build_cpu_status_read_a0())
        if resp.cmd != 0xA0:
            raise ToyopucProtocolError('Unexpected CMD in response')
        try:
            return parse_cpu_status_data_a0(resp.data)
        except Exception as e:
            raise ToyopucProtocolError(
                f'Failed to parse A0 CPU status response data={resp.data.hex()}'
            ) from e

    def wait_fr_write_complete(self, *, timeout: float = 30.0, poll_interval: float = 0.2) -> CpuStatusData:
        """Poll FR flash-write completion status.

        Prefer `CMD=A0 / 01 10` when available. If the target rejects `A0`
        with an invalid-subcommand style error, fall back to normal CPU status
        `CMD=32 / 11 00`, which exposes the same `Data7` flash-write bits on
        the Nano 10GX tested in this project.
        """
        deadline = time.monotonic() + max(0.0, float(timeout))
        interval = max(0.01, float(poll_interval))
        while True:
            use_a0 = self._fr_wait_prefers_a0 is not False
            if use_a0:
                try:
                    status = self.read_cpu_status_a0()
                    self._fr_wait_prefers_a0 = True
                except (ToyopucError, ToyopucProtocolError):
                    err = _extract_response_error_code(self.last_rx)
                    if err in (0x23, 0x24, 0x25):
                        self._fr_wait_prefers_a0 = False
                        status = self.read_cpu_status()
                    else:
                        raise
            else:
                status = self.read_cpu_status()
            if status.abnormal_write_flash_register:
                raise ToyopucError('FR flash write failed: abnormal_write_flash_register=1')
            if not status.under_writing_flash_register:
                return status
            if time.monotonic() >= deadline:
                raise ToyopucTimeoutError('Timed out waiting for FR flash write completion')
            time.sleep(interval)

    def write_clock(self, value: datetime) -> None:
        """Set the CPU clock via `CMD=32 / 71 00`."""
        weekday = (value.weekday() + 1) % 7  # Python Monday=0, PLC Sunday=0
        resp = self._send_and_recv(
            build_clock_write(
                value.second,
                value.minute,
                value.hour,
                value.day,
                value.month,
                value.year % 100,
                weekday,
            )
        )
        if resp.cmd != 0x32:
            raise ToyopucProtocolError('Unexpected CMD in response')
        if resp.data != bytes([0x71, 0x00]):
            raise ToyopucProtocolError('Unexpected clock write response body')

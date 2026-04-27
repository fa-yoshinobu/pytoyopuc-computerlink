import pytest

from toyopuc import ToyopucClient, ToyopucError


class _FakeSocket:
    def __init__(self, responses: list[bytes]) -> None:
        self._responses = list(responses)
        self._current = b""
        self._offset = 0
        self.sent: list[bytes] = []

    def sendall(self, payload: bytes) -> None:
        self.sent.append(payload)
        self._current = self._responses.pop(0)
        self._offset = 0

    def recv_into(self, buffer, size: int = 0) -> int:
        requested = size or len(buffer)
        chunk = self._current[self._offset : self._offset + requested]
        buffer[: len(chunk)] = chunk
        self._offset += len(chunk)
        return len(chunk)

    def close(self) -> None:
        return None


def _response(cmd: int, data: bytes = b"", *, rc: int = 0x00) -> bytes:
    length = 1 + len(data)
    return bytes([0x80, rc, length & 0xFF, (length >> 8) & 0xFF, cmd & 0xFF]) + data


def test_send_and_recv_retries_response_error_0x73() -> None:
    sock = _FakeSocket(
        [
            _response(0x73, rc=0x10),
            _response(0x1C, b"\x34\x12"),
        ]
    )
    client = ToyopucClient("127.0.0.1", 1025, retries=1, retry_delay=0)
    client._sock = sock

    frame = client.send_raw(0x1C)

    assert frame.cmd == 0x1C
    assert frame.data == b"\x34\x12"
    assert len(sock.sent) == 2


def test_send_and_recv_exhausts_response_error_0x73_retries() -> None:
    sock = _FakeSocket([_response(0x73, rc=0x10)])
    client = ToyopucClient("127.0.0.1", 1025, retries=0, retry_delay=0)
    client._sock = sock

    with pytest.raises(ToyopucError, match="error_code=0x73"):
        client.send_raw(0x1C)

    assert len(sock.sent) == 1

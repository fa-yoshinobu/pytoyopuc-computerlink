import asyncio

import pytest

from toyopuc import (
    AsyncToyopucDeviceClient,
    ToyopucClient,
    ToyopucDeviceClient,
    encode_word_address,
    parse_address,
)


def _word_addr(text: str) -> int:
    return encode_word_address(parse_address(text, "word"))


class _DummyWordClient(ToyopucClient):
    def __init__(self) -> None:
        super().__init__("127.0.0.1", 1025)
        self.next_words: list[int] = []
        self.word_reads: list[tuple[int, int]] = []
        self.word_writes: list[tuple[int, list[int]]] = []

    def read_words(self, addr: int, count: int):
        self.word_reads.append((addr, count))
        result = self.next_words[:count]
        self.next_words = self.next_words[count:]
        return result

    def write_words(self, addr: int, values):
        self.word_writes.append((addr, list(values)))


class _DummyHighLevelClient(ToyopucDeviceClient):
    def __init__(self) -> None:
        super().__init__("127.0.0.1", 1025)
        self.word_map: dict[int, int] = {}
        self.word_reads: list[tuple[int, int]] = []
        self.word_writes: list[tuple[int, list[int]]] = []

    def read_words(self, addr: int, count: int):
        self.word_reads.append((addr, count))
        return [self.word_map[addr + offset] for offset in range(count)]

    def write_words(self, addr: int, values):
        self.word_writes.append((addr, list(values)))


class _DummyAsyncHighLevelClient(AsyncToyopucDeviceClient):
    def __init__(self) -> None:
        object.__setattr__(self, "_client", _DummyHighLevelClient())


def test_low_level_32bit_helpers_use_low_word_first() -> None:
    client = _DummyWordClient()
    client.next_words = [0x5678, 0x1234]
    assert client.read_dword(0x1100) == 0x12345678

    client.next_words = [0x0000, 0x3FC0]
    assert client.read_float32(0x1100) == pytest.approx(1.5)

    client.write_dword(0x1100, 0x12345678)
    assert client.word_writes[-1] == (0x1100, [0x5678, 0x1234])

    client.write_float32(0x1100, 1.5)
    assert client.word_writes[-1] == (0x1100, [0x0000, 0x3FC0])


def test_high_level_32bit_helpers_use_word_sequences() -> None:
    client = _DummyHighLevelClient()
    addr0 = _word_addr("B0000")
    addr1 = _word_addr("B0001")
    client.word_map = {addr0: 0x5678, addr1: 0x1234}

    assert client.read_dword("B0000") == 0x12345678
    # Batch optimization: consecutive words are fetched in one read_words(addr, 2) call
    assert client.word_reads == [(addr0, 2)]

    client.write_float32("B0000", 1.5)
    # Batch optimization: consecutive word write in one write_words(addr, [lo, hi]) call
    assert client.word_writes == [(addr0, [0x0000, 0x3FC0])]


def test_async_high_level_helpers_wrap_sync_implementation() -> None:
    client = _DummyAsyncHighLevelClient()
    addr0 = _word_addr("B0000")
    addr1 = _word_addr("B0001")
    client.word_map = {addr0: 0x5678, addr1: 0x1234}

    async def run_checks() -> None:
        assert await client.read_dword("B0000") == 0x12345678
        await client.write_float32("B0000", 1.5)

    asyncio.run(run_checks())

    assert client.word_reads == [(addr0, 2)]
    assert client.word_writes == [(addr0, [0x0000, 0x3FC0])]

from datetime import datetime

from toyopuc import (
    ToyopucClient,
    ToyopucDeviceClient,
    encode_word_address,
    parse_address,
    resolve_device,
)
from toyopuc.client import _extract_relay_nak_error_code
from toyopuc.protocol import (
    build_clock_write,
    build_command,
    build_ext_byte_write,
    build_ext_multi_read,
    build_ext_word_read,
    build_ext_word_write,
    build_fr_register,
    build_pc10_block_read,
    build_pc10_block_write,
    build_pc10_multi_read,
    build_pc10_multi_write,
    build_relay_command,
    build_relay_nested,
    build_word_read,
    build_word_write,
    parse_response,
)
from toyopuc.relay import (
    format_relay_hop,
    parse_relay_hops,
    unwrap_relay_response_chain,
)


def _word_addr(text: str) -> int:
    return encode_word_address(parse_address(text, "word"))


def _relay_success_response(inner_cmd: int, inner_data: bytes, *, link_no: int = 0x12, station_no: int = 0x0002):
    inner_raw = build_command(inner_cmd, inner_data)[2:]
    outer_raw = (
        bytes([0x80, 0x00])
        + build_command(
            0x60,
            bytes([link_no, station_no & 0xFF, (station_no >> 8) & 0xFF, 0x06]) + inner_raw,
        )[2:]
    )
    return parse_response(outer_raw)


def _pc10_multi_word_read_payload(addrs32):
    addrs32 = list(addrs32)
    payload = bytearray([0x00, 0x00, len(addrs32) & 0xFF, 0x00])
    for addr32 in addrs32:
        payload.extend(int(addr32).to_bytes(4, "little"))
    return bytes(payload)


def _pc10_multi_word_write_payload(items):
    items = list(items)
    payload = bytearray([0x00, 0x00, len(items) & 0xFF, 0x00])
    for addr32, _ in items:
        payload.extend(int(addr32).to_bytes(4, "little"))
    for _, value in items:
        payload.extend(int(value & 0xFFFF).to_bytes(2, "little"))
    return bytes(payload)


class _DummyRelayClient(ToyopucClient):
    def __init__(self, response):
        super().__init__("127.0.0.1", 1025)
        self.response = response
        self.last_hops = None
        self.last_inner = None

    def relay_nested(self, hops, inner_payload):
        self.last_hops = list(hops)
        self.last_inner = inner_payload
        return self.response


class _DummyRelayHighLevelClient(ToyopucDeviceClient):
    def __init__(self, response):
        super().__init__("127.0.0.1", 1025)
        self.response = response
        self.last_hops = None
        self.last_inner = None
        self.inner_calls = []

    def relay_nested(self, hops, inner_payload):
        self.last_hops = list(hops)
        self.last_inner = inner_payload
        self.inner_calls.append(inner_payload)
        return self.response


class _DummyDirectHighLevelClient(ToyopucDeviceClient):
    def __init__(self):
        super().__init__("127.0.0.1", 1025)
        self.pc10_block_reads = []
        self.pc10_multi_reads = []

    def pc10_block_read(self, addr32, count):
        self.pc10_block_reads.append((addr32, count))
        return bytes.fromhex("3412")

    def pc10_multi_read(self, payload):
        self.pc10_multi_reads.append(payload)
        return b""


class _DummyBatchDirectClient(ToyopucDeviceClient):
    def __init__(self):
        super().__init__("127.0.0.1", 1025)
        self.word_reads = []
        self.word_multi_reads = []
        self.word_writes = []
        self.word_multi_writes = []

    def read_words(self, addr, count):
        self.word_reads.append((addr, count))
        return [0x1000 + i for i in range(count)]

    def read_words_multi(self, addrs):
        addrs = list(addrs)
        self.word_multi_reads.append(addrs)
        return [0x2000 + i for i in range(len(addrs))]

    def write_words(self, addr, values):
        self.word_writes.append((addr, list(values)))

    def write_words_multi(self, pairs):
        self.word_multi_writes.append(list(pairs))


class _DummyAdvancedBatchDirectClient(ToyopucDeviceClient):
    def __init__(self):
        super().__init__("127.0.0.1", 1025)
        self.ext_multi_reads = []
        self.ext_multi_writes = []
        self.byte_multi_writes = []
        self.pc10_multi_reads = []
        self.pc10_multi_writes = []
        self.pc10_block_writes = []

    def read_ext_multi(self, bit_points, byte_points, word_points):
        bit_points = list(bit_points)
        byte_points = list(byte_points)
        word_points = list(word_points)
        self.ext_multi_reads.append((bit_points, byte_points, word_points))
        if bit_points:
            return bytes([0b01010101, 0b00000011])
        if byte_points:
            return bytes([0x21 + i for i in range(len(byte_points))])
        if word_points:
            return bytes.fromhex("34127856")
        return b""

    def write_ext_multi(self, bit_points, byte_points, word_points):
        self.ext_multi_writes.append((list(bit_points), list(byte_points), list(word_points)))

    def write_bytes_multi(self, pairs):
        self.byte_multi_writes.append(list(pairs))

    def pc10_multi_read(self, payload):
        self.pc10_multi_reads.append(payload)
        count = payload[2]
        data = bytearray(4)
        for i in range(count):
            data.extend((0x1234 + i * 0x4444).to_bytes(2, "little"))
        return bytes(data)

    def pc10_multi_write(self, payload):
        self.pc10_multi_writes.append(payload)

    def pc10_block_write(self, addr32, data_bytes):
        self.pc10_block_writes.append((addr32, bytes(data_bytes)))


def test_build_relay_command_wraps_single_hop():
    inner = build_word_read(_word_addr("D0100"), 3)
    frame = build_relay_command(0x02, 0x0003, inner)
    assert frame.hex() == "00000d00600203000505001c0011030000"


def test_build_relay_command_accepts_trimmed_inner():
    inner = build_word_read(_word_addr("D0100"), 3)
    trimmed = inner[2:]  # drop FT/RC
    frame = build_relay_command(0x02, 0x0003, trimmed)
    assert frame.hex() == "00000d00600203000505001c0011030000"


def test_build_relay_nested_matches_manual_wrapping():
    inner = build_word_read(_word_addr("D0100"), 3)
    nested = build_relay_nested([(0x02, 0x0003), (0x01, 0x0001)], inner)

    # manual two-hop wrap for comparison
    hop1 = build_relay_command(0x01, 0x0001, inner)
    manual_outer = build_relay_command(0x02, 0x0003, hop1[2:])

    assert nested == manual_outer


def test_parse_hops_accepts_tool_style():
    assert parse_relay_hops("P1-L2:N2") == [(0x12, 0x0002)]
    assert parse_relay_hops("1-2:2") == [(0x12, 0x0002)]


def test_format_hop_uses_p_style():
    assert format_relay_hop(0x12, 0x0002) == "P1-L2:N2 (0x12:0x0002)"


def test_unwrap_relay_response_handles_nested_success():
    outer = parse_response(bytes.fromhex("80001b006012020006130060120400060b00321100820000000000000e6807"))
    layers, final = unwrap_relay_response_chain(outer)
    assert len(layers) == 2
    assert final is not None
    assert final.cmd == 0x32
    assert final.data == bytes.fromhex("1100820000000000000e")


def test_unwrap_relay_response_returns_none_on_nak():
    outer = parse_response(bytes.fromhex("80000900601200001501006600"))
    layers, final = unwrap_relay_response_chain(outer)
    assert len(layers) == 1
    assert final is None


def test_extract_relay_nak_error_code_reads_inner_error():
    assert _extract_relay_nak_error_code(bytes.fromhex("80000900601202001501002400")) == 0x24


def test_client_relay_read_cpu_status_accepts_p_style_hops():
    outer = parse_response(bytes.fromhex("8000130060120200060b00321100810000000000000f12"))
    client = _DummyRelayClient(outer)
    status = client.relay_read_cpu_status("P1-L2:N2")
    assert client.last_hops == [(0x12, 0x0002)]
    assert status.run is True
    assert status.pc10_mode is True


def test_client_relay_read_cpu_status_a0_accepts_p_style_hops():
    outer = parse_response(bytes.fromhex("8000120060120200060b00a00110820000000000000e"))
    client = _DummyRelayClient(outer)
    status = client.relay_read_cpu_status_a0("P1-L2:N2")
    assert client.last_hops == [(0x12, 0x0002)]
    assert status.run is True


def test_client_relay_write_clock_accepts_p_style_hops():
    outer = parse_response(bytes.fromhex("80000a0060120200060300327100"))
    client = _DummyRelayClient(outer)
    value = datetime(2026, 3, 10, 15, 0, 0)
    client.relay_write_clock("P1-L2:N2", value)
    assert client.last_hops == [(0x12, 0x0002)]
    assert client.last_inner == build_clock_write(0, 0, 15, 10, 3, 26, 2)


def test_high_level_relay_read_words_accepts_string_device():
    outer = parse_response(bytes.fromhex("80000b006012020006030094341201"))
    client = _DummyRelayHighLevelClient(outer)
    value = client.relay_read_words("P1-L2:N2", "P1-D0000")
    assert client.last_hops == [(0x12, 0x0002)]
    assert value == [0x1234]
    resolved = resolve_device("P1-D0000")
    assert client.last_inner == build_ext_word_read(resolved.no, resolved.addr, 1)


def test_client_relay_write_words_accepts_p_style_hops():
    outer = parse_response(bytes.fromhex("80000800601202000601001d"))
    client = _DummyRelayClient(outer)
    client.relay_write_words("P1-L2:N2", _word_addr("D0000"), [0x1234])
    assert client.last_hops == [(0x12, 0x0002)]
    assert client.last_inner == build_word_write(_word_addr("D0000"), [0x1234])


def test_high_level_relay_write_words_accepts_string_device():
    outer = parse_response(bytes.fromhex("800008006012020006010095"))
    client = _DummyRelayHighLevelClient(outer)
    client.relay_write_words("P1-L2:N2", "P1-D0000", 0x1234)
    assert client.last_hops == [(0x12, 0x0002)]
    resolved = resolve_device("P1-D0000")
    assert client.last_inner == build_ext_word_write(resolved.no, resolved.addr, [0x1234])


def test_high_level_relay_read_accepts_basic_bit_device():
    outer = parse_response(bytes.fromhex("80000900601202000602009801"))
    client = _DummyRelayHighLevelClient(outer)
    value = client.relay_read("P1-L2:N2", "P1-M0000")
    assert value is True
    assert client.last_hops == [(0x12, 0x0002)]
    resolved = resolve_device("P1-M0000")
    assert client.last_inner == build_ext_multi_read([(resolved.no, resolved.bit_no, resolved.addr)], [], [])


def test_high_level_relay_write_accepts_ext_byte_device():
    outer = parse_response(bytes.fromhex("800008006012020006010097"))
    client = _DummyRelayHighLevelClient(outer)
    resolved = resolve_device("EX0000L")
    client.relay_write("P1-L2:N2", resolved, 0x7F)
    assert client.last_hops == [(0x12, 0x0002)]
    assert client.last_inner == build_ext_byte_write(resolved.no, resolved.addr, [0x7F])


def test_high_level_relay_read_accepts_pc10_word_device():
    outer = parse_response(bytes.fromhex("80000a0060120200060300c23412"))
    client = _DummyRelayHighLevelClient(outer)
    resolved = resolve_device("U08000")
    value = client.relay_read("P1-L2:N2", resolved)
    assert value == 0x1234
    assert client.last_hops == [(0x12, 0x0002)]
    assert client.last_inner == build_pc10_block_read(resolved.addr32, 2)


def test_high_level_relay_read_accepts_fr_word_device():
    outer = parse_response(bytes.fromhex("80000a0060120200060300c23412"))
    client = _DummyRelayHighLevelClient(outer)
    resolved = resolve_device("FR000000")
    value = client.relay_read("P1-L2:N2", resolved)
    assert value == 0x1234
    assert client.last_inner == build_pc10_block_read(resolved.addr32, 2)


def test_high_level_relay_write_allows_fr_ram_update():
    outer = parse_response(bytes.fromhex("8000080060120200060100c3"))
    client = _DummyRelayHighLevelClient(outer)
    resolved = resolve_device("FR000000")
    client.relay_write("P1-L2:N2", resolved, 0x1234)
    assert client.last_hops == [(0x12, 0x0002)]
    assert client.last_inner == build_pc10_block_write(resolved.addr32, bytes.fromhex("3412"))


def test_high_level_relay_commit_fr_uses_ca():
    outer = parse_response(bytes.fromhex("8000080060120200060100ca"))
    client = _DummyRelayHighLevelClient(outer)
    client.relay_commit_fr("P1-L2:N2", "FR000000")
    assert client.last_hops == [(0x12, 0x0002)]
    assert client.last_inner == build_fr_register(0x40)


def test_high_level_relay_read_many_preserves_input_order():
    outer = _relay_success_response(0x94, bytes.fromhex("34127856"))
    client = _DummyRelayHighLevelClient(outer)
    values = client.relay_read_many("P1-L2:N2", ["P1-D0000", "P1-D0001"])
    assert values == [0x1234, 0x5678]
    resolved = resolve_device("P1-D0000")
    assert client.inner_calls == [build_ext_word_read(resolved.no, resolved.addr, 2)]
    assert client.last_inner == build_ext_word_read(resolved.no, resolved.addr, 2)


def test_high_level_read_many_ext_word_sparse_uses_ext_multi_read():
    client = _DummyAdvancedBatchDirectClient()
    devices = ["U0000", "U0002"]
    values = client.read_many(devices)
    resolved = [resolve_device(d) for d in devices]

    assert values == [0x1234, 0x5678]
    assert client.ext_multi_reads == [([], [], [(_r.no, _r.addr) for _r in resolved])]


def test_high_level_read_many_ext_bit_sparse_unpacks_packed_multi_read():
    client = _DummyAdvancedBatchDirectClient()
    devices = [f"EM{i:04X}" for i in range(10)]
    resolved = [resolve_device(d) for d in devices]

    values = client.read_many(devices)

    assert values == [True, False, True, False, True, False, True, False, True, True]
    assert client.ext_multi_reads == [([(_r.no, _r.bit_no, _r.addr) for _r in resolved], [], [])]


def test_high_level_read_many_pc10_word_sparse_uses_multi_read():
    client = _DummyAdvancedBatchDirectClient()
    devices = ["U08000", "U08100"]
    resolved = [resolve_device(d) for d in devices]
    values = client.read_many(devices)

    assert values == [0x1234, 0x5678]
    assert client.pc10_multi_reads == [_pc10_multi_word_read_payload([_r.addr32 for _r in resolved])]


def test_high_level_read_many_basic_words_batches_consecutive_reads():
    client = _DummyBatchDirectClient()
    values = client.read_many(["B0000", "B0001"])

    assert values == [0x1000, 0x1001]
    assert client.word_reads == [(_word_addr("B0000"), 2)]
    assert client.word_multi_reads == []


def test_high_level_read_many_basic_words_batches_sparse_multi_reads():
    client = _DummyBatchDirectClient()
    values = client.read_many(["B0000", "B0002"])

    assert values == [0x2000, 0x2001]
    assert client.word_reads == []
    assert client.word_multi_reads == [[_word_addr("B0000"), _word_addr("B0002")]]


def test_high_level_write_many_basic_words_batches_consecutive_writes():
    client = _DummyBatchDirectClient()
    client.write_many({"B0000": 0x1234, "B0001": 0x5678})

    assert client.word_writes == [(_word_addr("B0000"), [0x1234, 0x5678])]
    assert client.word_multi_writes == []


def test_high_level_write_many_basic_words_batches_sparse_multi_writes():
    client = _DummyBatchDirectClient()
    client.write_many({"B0000": 0x1234, "B0002": 0x5678})

    assert client.word_writes == []
    assert client.word_multi_writes == [[(_word_addr("B0000"), 0x1234), (_word_addr("B0002"), 0x5678)]]


def test_high_level_write_many_basic_bytes_uses_multi_write():
    client = _DummyAdvancedBatchDirectClient()
    devices = {"B0000L": 0x12, "B0001H": 0x34}
    resolved = [resolve_device(d) for d in devices]

    client.write_many(devices)

    assert client.byte_multi_writes == [[(_r.basic_addr, v) for _r, v in zip(resolved, devices.values(), strict=False)]]


def test_high_level_write_many_ext_word_sparse_uses_ext_multi_write():
    client = _DummyAdvancedBatchDirectClient()
    items = {"U0000": 0x1234, "U0002": 0x5678}
    resolved = [resolve_device(d) for d in items]

    client.write_many(items)

    expected = [(_r.no, _r.addr, v) for _r, v in zip(resolved, items.values(), strict=False)]
    assert client.ext_multi_writes == [([], [], expected)]


def test_high_level_write_many_pc10_word_sparse_uses_multi_write():
    client = _DummyAdvancedBatchDirectClient()
    items = {"U08000": 0x1234, "U08100": 0x5678}
    resolved = [resolve_device(d) for d in items]

    client.write_many(items)

    assert client.pc10_multi_writes == [
        _pc10_multi_word_write_payload([(_r.addr32, v) for _r, v in zip(resolved, items.values(), strict=False)])
    ]


def test_high_level_relay_read_many_ext_bit_sparse_unpacks_packed_multi_read():
    devices = [f"EM{i:04X}" for i in range(10)]
    resolved = [resolve_device(d) for d in devices]
    outer = _relay_success_response(0x98, bytes([0b01010101, 0b00000011]))
    client = _DummyRelayHighLevelClient(outer)
    values = client.relay_read_many("P1-L2:N2", devices)

    assert values == [True, False, True, False, True, False, True, False, True, True]
    assert client.inner_calls == [build_ext_multi_read([(_r.no, _r.bit_no, _r.addr) for _r in resolved], [], [])]


def test_high_level_relay_read_many_pc10_word_sparse_uses_multi_read():
    devices = ["U08000", "U08100"]
    resolved = [resolve_device(d) for d in devices]
    payload = _pc10_multi_word_read_payload([_r.addr32 for _r in resolved])
    outer = _relay_success_response(0xC4, b"\x00\x00\x00\x00\x34\x12\x78\x56")
    client = _DummyRelayHighLevelClient(outer)

    values = client.relay_read_many("P1-L2:N2", devices)

    assert values == [0x1234, 0x5678]
    assert client.inner_calls == [build_pc10_multi_read(payload)]


def test_high_level_relay_write_many_batches_ext_word_writes():
    outer = _relay_success_response(0x95, b"")
    client = _DummyRelayHighLevelClient(outer)
    client.relay_write_many("P1-L2:N2", {"P1-D0000": 0x1234, "P1-D0001": 0x5678})
    assert client.last_hops == [(0x12, 0x0002)]
    resolved = resolve_device("P1-D0000")
    assert client.inner_calls == [build_ext_word_write(resolved.no, resolved.addr, [0x1234, 0x5678])]
    assert client.last_inner == build_ext_word_write(resolved.no, resolved.addr, [0x1234, 0x5678])


def test_high_level_relay_write_many_pc10_word_sparse_uses_multi_write():
    items = {"U08000": 0x1234, "U08100": 0x5678}
    resolved = [resolve_device(d) for d in items]
    payload = _pc10_multi_word_write_payload([(_r.addr32, v) for _r, v in zip(resolved, items.values(), strict=False)])
    outer = _relay_success_response(0xC5, b"")
    client = _DummyRelayHighLevelClient(outer)

    client.relay_write_many("P1-L2:N2", items)

    assert client.inner_calls == [build_pc10_multi_write(payload)]
    assert client.last_inner == build_pc10_multi_write(payload)

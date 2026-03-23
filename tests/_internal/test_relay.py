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
    build_ext_byte_write,
    build_ext_multi_read,
    build_ext_word_read,
    build_ext_word_write,
    build_fr_register,
    build_pc10_block_read,
    build_pc10_block_write,
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
    outer = parse_response(
        bytes.fromhex("80001b006012020006130060120400060b00321100820000000000000e6807")
    )
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
    assert (
        _extract_relay_nak_error_code(bytes.fromhex("80000900601202001501002400"))
        == 0x24
    )


def test_client_relay_read_cpu_status_accepts_p_style_hops():
    outer = parse_response(
        bytes.fromhex("8000130060120200060b00321100810000000000000f12")
    )
    client = _DummyRelayClient(outer)
    status = client.relay_read_cpu_status("P1-L2:N2")
    assert client.last_hops == [(0x12, 0x0002)]
    assert status.run is True
    assert status.pc10_mode is True


def test_client_relay_read_cpu_status_a0_accepts_p_style_hops():
    outer = parse_response(
        bytes.fromhex("8000120060120200060b00a00110820000000000000e")
    )
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
    assert client.last_inner == build_ext_word_write(
        resolved.no, resolved.addr, [0x1234]
    )


def test_high_level_relay_read_accepts_basic_bit_device():
    outer = parse_response(bytes.fromhex("80000900601202000602009801"))
    client = _DummyRelayHighLevelClient(outer)
    value = client.relay_read("P1-L2:N2", "P1-M0000")
    assert value is True
    assert client.last_hops == [(0x12, 0x0002)]
    resolved = resolve_device("P1-M0000")
    assert client.last_inner == build_ext_multi_read(
        [(resolved.no, resolved.bit_no, resolved.addr)], [], []
    )


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
    assert client.last_inner == build_pc10_block_write(
        resolved.addr32, bytes.fromhex("3412")
    )


def test_high_level_relay_commit_fr_uses_ca():
    outer = parse_response(bytes.fromhex("8000080060120200060100ca"))
    client = _DummyRelayHighLevelClient(outer)
    client.relay_commit_fr("P1-L2:N2", "FR000000")
    assert client.last_hops == [(0x12, 0x0002)]
    assert client.last_inner == build_fr_register(0x40)


def test_high_level_relay_read_many_preserves_input_order():
    outer = parse_response(bytes.fromhex("80000b006012020006030094341201"))
    client = _DummyRelayHighLevelClient(outer)
    values = client.relay_read_many("P1-L2:N2", ["P1-D0000", "P1-D0001"])
    assert values == [0x1234, 0x1234]
    resolved = resolve_device("P1-D0001")
    assert client.last_inner == build_ext_word_read(resolved.no, resolved.addr, 1)


def test_high_level_read_many_pc10_word_sparse_uses_block_read_only():
    client = _DummyDirectHighLevelClient()
    devices = ["U08000", "U08001", "U08100"]
    values = client.read_many(devices)
    resolved = [resolve_device(d) for d in devices]

    assert values == [0x1234, 0x1234, 0x1234]
    assert client.pc10_block_reads == [(_r.addr32, 2) for _r in resolved]
    assert client.pc10_multi_reads == []


def test_high_level_relay_read_many_pc10_word_sparse_uses_block_read_only():
    outer = parse_response(bytes.fromhex("80000a0060120200060300c23412"))
    client = _DummyRelayHighLevelClient(outer)
    devices = ["U08000", "U08100"]
    values = client.relay_read_many("P1-L2:N2", devices)
    resolved = [resolve_device(d) for d in devices]

    assert values == [0x1234, 0x1234]
    assert client.inner_calls == [
        build_pc10_block_read(_r.addr32, 2) for _r in resolved
    ]
    assert all(frame[4] == 0xC2 for frame in client.inner_calls)


def test_high_level_relay_write_many_uses_per_item_dispatch():
    outer = parse_response(bytes.fromhex("800008006012020006010095"))
    client = _DummyRelayHighLevelClient(outer)
    client.relay_write_many("P1-L2:N2", {"P1-D0000": 0x1234, "P1-D0001": 0x5678})
    assert client.last_hops == [(0x12, 0x0002)]
    resolved = resolve_device("P1-D0001")
    assert client.last_inner == build_ext_word_write(
        resolved.no, resolved.addr, [0x5678]
    )

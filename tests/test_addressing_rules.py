import pytest

from toyopuc.high_level import resolve_device


@pytest.mark.parametrize(
    "device",
    [
        "EP0FFW",
        "EP0FFL",
        "EP0FFH",
        "GMFFFW",
        "GMFFFL",
        "GMFFFH",
        "P1-M17FW",
        "P1-M17FL",
    ],
)
def test_derived_width_accept_cases(device: str) -> None:
    resolved = resolve_device(device)
    assert resolved.text == device


@pytest.mark.parametrize(
    "device",
    [
        "M0000W",
        "M0000L",
        "M0000H",
        "M17FW",
        "M17FL",
        "M17FH",
        "EP0000W",
        "EP0000L",
        "EP0000H",
        "GM1000W",
        "GM1000L",
        "GM1000H",
        "P1-M0000W",
    ],
)
def test_derived_width_reject_cases(device: str) -> None:
    with pytest.raises(ValueError):
        resolve_device(device)


def test_gx_gy_keep_explicit_names() -> None:
    gx = resolve_device("GX000W")
    gy = resolve_device("GY000W")

    assert gx.area == "GX"
    assert gy.area == "GY"
    assert gx.no == 0x07
    assert gy.no == 0x07


def test_gxy_is_not_supported_area() -> None:
    with pytest.raises(ValueError):
        resolve_device("GXY000W")


def test_gm_word_and_byte_address_spaces_are_consistent() -> None:
    gm_word = resolve_device("GM000W")
    gm_low = resolve_device("GM000L")
    gm_high = resolve_device("GM000H")

    assert gm_word.scheme == "ext-word"
    assert gm_word.no == 0x07
    assert gm_word.addr == 0x1000
    assert gm_low.scheme == "ext-byte"
    assert gm_low.no == 0x07
    assert gm_low.addr == 0x2000
    assert gm_high.addr == 0x2001


@pytest.mark.parametrize(
    "device",
    [
        "P0000",
        "K0000",
        "V0000",
        "T0000",
        "C0000",
        "L0000",
        "X0000",
        "Y0000",
        "M0000",
        "S0000",
        "N0000",
        "R0000",
        "D0000",
    ],
)
def test_prefix_required_areas_reject_unprefixed(device: str) -> None:
    with pytest.raises(ValueError, match="requires P1-/P2-/P3- prefix"):
        resolve_device(device)


@pytest.mark.parametrize(
    "device",
    [
        "P1-P0000",
        "P2-K0000",
        "P3-V0000",
        "P1-T0000",
        "P2-C0000",
        "P3-L0000",
        "P1-X0000",
        "P2-Y0000",
        "P3-M0000",
        "P1-S0000",
        "P2-N0000",
        "P3-R0000",
        "P1-D0000",
    ],
)
def test_prefix_required_areas_accept_prefixed(device: str) -> None:
    resolved = resolve_device(device)
    assert resolved.text == device

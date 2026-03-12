import pytest

from examples.device_monitor_gui import MonitorApp


def test_gui_accepts_prefixed_range_token() -> None:
    devices = MonitorApp.parse_and_validate_device_input("P1-D0000-D000F")
    assert len(devices) == 16
    assert devices[0] == "P1-D0000"
    assert devices[-1] == "P1-D000F"


def test_gui_rejects_unprefixed_d_word() -> None:
    with pytest.raises(ValueError, match="requires P1-/P2-/P3- prefix"):
        MonitorApp.parse_and_validate_device_input("D0000")


@pytest.mark.parametrize("text", ["M0000W", "P1-M0000W"])
def test_gui_rejects_forbidden_derived_forms(text: str) -> None:
    with pytest.raises(ValueError):
        MonitorApp.parse_and_validate_device_input(text)

"""API mouse button reports; no serial hardware required."""

from unittest.mock import Mock, patch

import pytest

from serial_hid_kvm.config import Config
from serial_hid_kvm.hid_mouse import Mouse
from serial_hid_kvm.hid_protocol import build_mouse_abs_packet, build_mouse_rel_packet
from serial_hid_kvm.server import ApiDispatcher, KvmHardware

ABS = build_mouse_abs_packet
REL = build_mouse_rel_packet


def _mouse(default="absolute"):
    dev = Mock()
    with patch("serial_hid_kvm.hid_mouse.atexit"):
        return Mouse(dev, 4096, 4096, button_mode=default), dev


def _sent(dev):
    return [c.args[0] for c in dev.send.call_args_list]


@pytest.mark.parametrize("default,override,expected", [
    ("absolute", None, [ABS(1, 10, 20), ABS(0, 10, 20)]),
    ("relative", None, [ABS(0, 10, 20), REL(1, 0, 0), ABS(0, 10, 20), REL(0, 0, 0)]),
    ("absolute", "relative", [ABS(0, 10, 20), REL(1, 0, 0), ABS(0, 10, 20), REL(0, 0, 0)]),
    ("relative", "absolute", [ABS(1, 10, 20), ABS(0, 10, 20)]),
])
def test_click_uses_default_or_override(monkeypatch, default, override, expected):
    monkeypatch.setattr("serial_hid_kvm.hid_mouse.time.sleep", lambda _: None)
    mouse, dev = _mouse(default)
    mouse.click("left", 10, 20, override)
    assert _sent(dev) == expected


def test_relative_drag():
    mouse, dev = _mouse("relative")
    mouse.mouse_down("right", 1, 2)
    mouse.move_absolute(3, 4)
    mouse.mouse_up("right", 5, 6)
    assert _sent(dev) == [
        ABS(0, 1, 2), REL(2, 0, 0),
        ABS(0, 3, 4),
        ABS(0, 5, 6), REL(0, 0, 0),
    ]


def test_unpositioned_click_is_relative_in_both_modes(monkeypatch):
    monkeypatch.setattr("serial_hid_kvm.hid_mouse.time.sleep", lambda _: None)
    for mode in ("absolute", "relative"):
        mouse, dev = _mouse(mode)
        mouse.click("middle")
        assert _sent(dev) == [REL(4, 0, 0), REL(0, 0, 0)]


def test_invalid_mode_rejected():
    with pytest.raises(ValueError):
        _mouse("bogus")
    mouse, dev = _mouse()
    with pytest.raises(ValueError):
        mouse.click("left", 1, 1, "bogus")
    with pytest.raises(ValueError):
        mouse.mouse_down("left", 1, 1, "bogus")
    mouse.move_absolute(1, 1)
    assert _sent(dev) == [ABS(0, 1, 1)]  # Rejected press left no held button.


@pytest.mark.parametrize("params,expected", [
    ({}, [ABS(0, 0, 0), REL(1, 0, 0)]),
    ({"button_mode": "absolute"}, [ABS(1, 0, 0)]),
])
def test_api_default_follows_config(params, expected):
    config = Config()
    config.mouse_button_mode = "relative"
    hw = KvmHardware(config)
    dev = Mock()
    hw.get_ch9329 = Mock(return_value=dev)
    with patch("serial_hid_kvm.hid_mouse.atexit"):
        ApiDispatcher(hw, config)._do_mouse_down({"x": 0, "y": 0, **params})
    assert _sent(dev) == expected

"""Tests for safe Wi-Fi channel switching."""

import pytest

from src import channel_switcher as switcher


def test_iw_switch_refuses_managed_client_interface(monkeypatch):
    monkeypatch.setattr(switcher, "_get_interface_type", lambda interface: "managed")
    success, message = switcher.switch_channel_iw("wlan0", 11)
    assert success is False
    assert "upstream home router" in message


def test_auto_switch_refuses_managed_interface_without_touching_hostapd(monkeypatch):
    monkeypatch.setattr(switcher, "get_current_channel", lambda interface: 6)
    monkeypatch.setattr(switcher, "_get_interface_type", lambda interface: "managed")
    monkeypatch.setattr(
        switcher, "switch_channel_hostapd",
        lambda *args, **kwargs: pytest.fail("must not restart unrelated hostapd"),
    )
    success, message = switcher.switch_channel("wlan0", 11)
    assert success is False
    assert "cannot change the upstream router's channel" in message


def test_auto_switch_rejects_unknown_interface_mode(monkeypatch):
    monkeypatch.setattr(switcher, "get_current_channel", lambda interface: 6)
    monkeypatch.setattr(switcher, "_get_interface_type", lambda interface: None)
    success, message = switcher.switch_channel("wlan0", 11)
    assert success is False
    assert "unknown" in message


def test_hostapd_switch_rejects_invalid_channel_without_editing(tmp_path, monkeypatch):
    config = tmp_path / "hostapd.conf"
    original = "interface=wlan0\nssid=TestNet\nchannel=6\n"
    config.write_text(original, encoding="utf-8")
    monkeypatch.setattr(
        switcher, "run_shell_command",
        lambda *args, **kwargs: pytest.fail("invalid channel must not restart service"),
    )
    success, message = switcher.switch_channel_hostapd(999, str(config))
    assert success is False
    assert "Invalid channel" in message
    assert config.read_text(encoding="utf-8") == original


def test_hostapd_switch_replaces_active_channel_and_removes_duplicates(tmp_path, monkeypatch):
    config = tmp_path / "hostapd.conf"
    config.write_text(
        "interface=wlan0\n# channel=3 is a comment\nchannel=6\nchannel = 1\nssid=TestNet\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        switcher, "run_shell_command", lambda *args, **kwargs: ("", "", 0)
    )
    monkeypatch.setattr(switcher.time, "sleep", lambda seconds: None)

    success, message = switcher.switch_channel_hostapd(11, str(config))
    updated = config.read_text(encoding="utf-8")
    assert success is True
    assert "channel=11\n" in updated
    assert "# channel=3 is a comment\n" in updated
    assert updated.count("channel=") == 2  # one active line plus the comment
    assert "ssid=TestNet\n" in updated


def test_hostapd_switch_rolls_back_config_when_restart_fails(tmp_path, monkeypatch):
    config = tmp_path / "hostapd.conf"
    original = "interface=wlan0\nssid=TestNet\nchannel=6\n"
    config.write_text(original, encoding="utf-8")
    calls = []

    def failed_restart(command, timeout=30):
        calls.append(command)
        return ("", "service unavailable", 1)

    monkeypatch.setattr(switcher, "run_shell_command", failed_restart)
    success, message = switcher.switch_channel_hostapd(11, str(config))
    assert success is False
    assert config.read_text(encoding="utf-8") == original
    assert "original config restored" in message
    assert len(calls) == 4  # systemctl + service, then rollback restarts


def test_hostapd_switch_updates_band_mode_for_five_ghz(tmp_path, monkeypatch):
    config = tmp_path / "hostapd.conf"
    config.write_text(
        "interface=wlan0\nhw_mode=g\nchannel=6\nssid=TestNet\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        switcher, "run_shell_command", lambda *args, **kwargs: ("", "", 0)
    )
    monkeypatch.setattr(switcher.time, "sleep", lambda seconds: None)

    success, message = switcher.switch_channel_hostapd(36, str(config))
    updated = config.read_text(encoding="utf-8")
    assert success is True
    assert "hw_mode=a\n" in updated
    assert "channel=36\n" in updated
    assert "hw_mode=g\n" not in updated

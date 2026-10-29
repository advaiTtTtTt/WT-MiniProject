"""Tests for the WiFi scanner module."""

import pytest
from src.scanner import (
    NetworkInfo,
    _parse_iw_scan,
    _parse_iwlist_scan,
    generate_demo_scan_data,
    _signal_bar,
)


class TestNetworkInfo:
    """Tests for NetworkInfo dataclass."""

    def test_default_values(self):
        net = NetworkInfo()
        assert net.ssid == ""
        assert net.signal_dbm == -100
        assert net.channel_width == 20

    def test_to_dict(self):
        net = NetworkInfo(ssid="Test", bssid="AA:BB:CC:DD:EE:FF", channel=6)
        d = net.to_dict()
        assert d["ssid"] == "Test"
        assert d["channel"] == 6

    def test_from_dict(self):
        d = {"ssid": "Test", "bssid": "AA:BB:CC:DD:EE:FF", "channel": 11, "signal_dbm": -45}
        net = NetworkInfo.from_dict(d)
        assert net.ssid == "Test"
        assert net.channel == 11
        assert net.signal_dbm == -45

    def test_from_dict_ignores_extra_keys(self):
        d = {"ssid": "Test", "unknown_key": "value", "channel": 1}
        net = NetworkInfo.from_dict(d)
        assert net.ssid == "Test"
        assert net.channel == 1


class TestIwScanParser:
    """Tests for iw scan output parser."""

    SAMPLE_IW_OUTPUT = """BSS aa:bb:cc:11:22:33(on wlan0)
\tTSF: 12345678 usec
\tfreq: 2412
\tcapability: ESS Privacy
\tsignal: -45.00 dBm
\tSSID: TestNetwork
\tRSN:\t * Version: 1

BSS aa:bb:cc:44:55:66(on wlan0)
\tfreq: 2437
\tsignal: -72.00 dBm
\tSSID: AnotherNet
"""

    def test_parse_basic_networks(self):
        networks = _parse_iw_scan(self.SAMPLE_IW_OUTPUT)
        assert len(networks) == 2

    def test_parse_ssid(self):
        networks = _parse_iw_scan(self.SAMPLE_IW_OUTPUT)
        assert networks[0].ssid == "TestNetwork"
        assert networks[1].ssid == "AnotherNet"

    def test_parse_bssid(self):
        networks = _parse_iw_scan(self.SAMPLE_IW_OUTPUT)
        assert networks[0].bssid == "AA:BB:CC:11:22:33"

    def test_parse_frequency_and_channel(self):
        networks = _parse_iw_scan(self.SAMPLE_IW_OUTPUT)
        assert networks[0].frequency == 2412
        assert networks[0].channel == 1
        assert networks[1].frequency == 2437
        assert networks[1].channel == 6

    def test_parse_signal(self):
        networks = _parse_iw_scan(self.SAMPLE_IW_OUTPUT)
        assert networks[0].signal_dbm == -45

    def test_parse_security(self):
        networks = _parse_iw_scan(self.SAMPLE_IW_OUTPUT)
        assert networks[0].security == "WPA2/WPA3"  # Has RSN

    def test_parse_empty_output(self):
        networks = _parse_iw_scan("")
        assert len(networks) == 0

    def test_parse_hidden_ssid(self):
        output = """BSS aa:bb:cc:11:22:33(on wlan0)
\tfreq: 2412
\tsignal: -50.00 dBm
\tSSID: 
"""
        networks = _parse_iw_scan(output)
        assert len(networks) == 1
        assert networks[0].ssid == "<Hidden>"


    def test_privacy_capability_is_not_reported_as_open(self):
        output = """BSS aa:bb:cc:11:22:33(on wlan0)
        freq: 2412
        signal: -65.00 dBm
        capability: ESS Privacy
        """
        networks = _parse_iw_scan(output)
        assert len(networks) == 1
        assert networks[0].security == "Encrypted"

    def test_scan_count_must_be_positive(self, monkeypatch):
        from src import scanner

        monkeypatch.setattr(
            scanner, "run_shell_command",
            lambda *args, **kwargs: pytest.fail("scan should not run for invalid count"),
        )
        with pytest.raises(ValueError, match="scan_count"):
            scanner.scan_networks("wlan0", 0)


class TestIwlistScanParser:
    """Tests for iwlist scan output parser."""

    SAMPLE_IWLIST_OUTPUT = """wlan0     Scan completed :
          Cell 01 - Address: AA:BB:CC:11:22:33
                    Channel:1
                    Frequency:2.412 GHz
                    Quality=70/100  Signal level=-45 dBm
                    ESSID:"TestNetwork"
                    Encryption key:on
                    IE: WPA Version 1
          Cell 02 - Address: AA:BB:CC:44:55:66
                    Channel:11
                    Frequency:2.462 GHz
                    Quality=40/100  Signal level=-68 dBm
                    ESSID:"OpenNetwork"
                    Encryption key:off
"""

    def test_parse_basic_networks(self):
        networks = _parse_iwlist_scan(self.SAMPLE_IWLIST_OUTPUT)
        assert len(networks) == 2

    def test_parse_channel(self):
        networks = _parse_iwlist_scan(self.SAMPLE_IWLIST_OUTPUT)
        assert networks[0].channel == 1
        assert networks[1].channel == 11

    def test_parse_signal_level(self):
        networks = _parse_iwlist_scan(self.SAMPLE_IWLIST_OUTPUT)
        assert networks[0].signal_dbm == -45

    def test_parse_open_network(self):
        networks = _parse_iwlist_scan(self.SAMPLE_IWLIST_OUTPUT)
        assert networks[1].security == "Open"


class TestDemoData:
    """Tests for demo data generation."""

    def test_generates_networks(self):
        networks = generate_demo_scan_data()
        assert len(networks) > 0

    def test_includes_multiple_channels(self):
        networks = generate_demo_scan_data()
        channels = {n.channel for n in networks}
        assert len(channels) >= 5

    def test_includes_both_bands(self):
        networks = generate_demo_scan_data()
        bands = {n.band for n in networks}
        assert "2.4GHz" in bands
        assert "5GHz" in bands

    def test_signal_quality_set(self):
        networks = generate_demo_scan_data()
        for net in networks:
            assert 0 <= net.signal_quality <= 100


class TestSignalBar:
    """Tests for signal bar visualization."""

    def test_strong_signal(self):
        bar = _signal_bar(90)
        assert "🟢" in bar

    def test_medium_signal(self):
        bar = _signal_bar(50)
        assert "🟡" in bar

    def test_weak_signal(self):
        bar = _signal_bar(20)
        assert "🔴" in bar

"""Tests for the WiFi channel analyzer module."""

import pytest
from src.scanner import NetworkInfo, generate_demo_scan_data
from src.analyzer import (
    ChannelScore,
    analyze_channels,
    get_best_channel,
)
from src.utils import channel_overlap_score, NON_OVERLAPPING_24GHZ


class TestChannelOverlap:
    """Tests for channel overlap calculation."""

    def test_same_channel_full_overlap(self):
        assert channel_overlap_score(6, 6) == 1.0

    def test_non_overlapping_channels(self):
        # Channels 1 and 6 are 25 MHz apart (5 channels * 5 MHz), > 22 MHz
        assert channel_overlap_score(1, 6) == 0.0

    def test_adjacent_channels_overlap(self):
        # Channels 1 and 2 are 5 MHz apart, within 22 MHz
        score = channel_overlap_score(1, 2)
        assert 0 < score < 1.0

    def test_channels_1_and_3(self):
        # 10 MHz apart, should overlap
        score = channel_overlap_score(1, 3)
        assert 0 < score < 1.0

    def test_channels_1_and_5(self):
        # 20 MHz apart, still overlaps (< 22 MHz)
        score = channel_overlap_score(1, 5)
        assert 0 < score < 1.0

    def test_channels_1_and_11(self):
        # 50 MHz apart, no overlap
        assert channel_overlap_score(1, 11) == 0.0

    def test_5ghz_same_channel(self):
        assert channel_overlap_score(36, 36) == 1.0

    def test_5ghz_different_channels(self):
        assert channel_overlap_score(36, 40) == 0.0

    def test_symmetric(self):
        assert channel_overlap_score(3, 6) == channel_overlap_score(6, 3)


class TestAnalyzeChannels:
    """Tests for channel congestion analysis."""

    def test_empty_networks(self):
        scores = analyze_channels([], band="2.4GHz")
        assert len(scores) == 13  # All 2.4 GHz channels
        for s in scores:
            assert s.ap_count == 0
            assert s.congestion_score == 0

    def test_single_network(self):
        networks = [
            NetworkInfo(ssid="Test", channel=6, signal_dbm=-50, band="2.4GHz"),
        ]
        scores = analyze_channels(networks, band="2.4GHz")

        ch6 = next(s for s in scores if s.channel == 6)
        assert ch6.ap_count == 1

        # Empty channels should have 0 direct APs
        ch11 = next(s for s in scores if s.channel == 11)
        assert ch11.ap_count == 0

    def test_crowded_channel_high_congestion(self):
        networks = [
            NetworkInfo(ssid=f"Net{i}", channel=6, signal_dbm=-40, band="2.4GHz")
            for i in range(5)
        ]
        scores = analyze_channels(networks, band="2.4GHz")

        ch6 = next(s for s in scores if s.channel == 6)
        ch11 = next(s for s in scores if s.channel == 11)

        assert ch6.congestion_score > ch11.congestion_score
        assert ch6.ap_count == 5

    def test_scores_sorted_by_congestion(self):
        networks = generate_demo_scan_data()
        scores = analyze_channels(networks, band="2.4GHz")

        for i in range(len(scores) - 1):
            assert scores[i].congestion_score <= scores[i + 1].congestion_score

    def test_recommendations_assigned(self):
        networks = generate_demo_scan_data()
        scores = analyze_channels(networks, band="2.4GHz")

        for s in scores:
            assert s.recommendation != ""

    def test_5ghz_analysis(self):
        networks = generate_demo_scan_data()
        scores = analyze_channels(networks, band="5GHz")

        assert len(scores) > 0
        for s in scores:
            assert s.band == "5GHz"


class TestGetBestChannel:
    """Tests for best channel recommendation."""

    def test_prefers_non_overlapping(self):
        networks = [
            NetworkInfo(ssid="Net", channel=1, signal_dbm=-40, band="2.4GHz"),
            NetworkInfo(ssid="Net2", channel=6, signal_dbm=-40, band="2.4GHz"),
        ]
        scores = analyze_channels(networks, band="2.4GHz")
        best = get_best_channel(scores, prefer_non_overlapping=True)

        assert best.channel in NON_OVERLAPPING_24GHZ

    def test_empty_scores(self):
        best = get_best_channel([], prefer_non_overlapping=True)
        assert best is None

    def test_returns_least_congested(self):
        networks = [
            NetworkInfo(ssid=f"Net{i}", channel=1, signal_dbm=-30, band="2.4GHz")
            for i in range(10)
        ]
        scores = analyze_channels(networks, band="2.4GHz")
        best = get_best_channel(scores)

        # Channel 1 is super crowded, best should NOT be channel 1
        # (among non-overlapping: 6 and 11 are empty)
        assert best.channel != 1


class TestChannelScore:
    """Tests for ChannelScore dataclass."""

    def test_to_dict(self):
        score = ChannelScore(channel=6, band="2.4GHz", ap_count=3, congestion_score=45.2)
        d = score.to_dict()
        assert d["channel"] == 6
        assert d["ap_count"] == 3
        assert d["congestion_score"] == 45.2

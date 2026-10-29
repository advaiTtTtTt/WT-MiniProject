"""Tests for the benchmark and comparator modules."""

import pytest
from src.benchmark import BenchmarkResult, generate_demo_benchmark
from src.comparator import compare_results


class TestBenchmarkResult:
    """Tests for BenchmarkResult dataclass."""

    def test_default_values(self):
        r = BenchmarkResult()
        assert r.throughput_mbps == 0.0
        assert r.latency_avg_ms == 0.0

    def test_to_dict(self):
        r = BenchmarkResult(label="test", throughput_mbps=50.5, channel=6)
        d = r.to_dict()
        assert d["label"] == "test"
        assert d["throughput_mbps"] == 50.5

    def test_from_dict(self):
        d = {"label": "before", "throughput_mbps": 80.0, "channel": 11}
        r = BenchmarkResult.from_dict(d)
        assert r.label == "before"
        assert r.throughput_mbps == 80.0


class TestDemoBenchmark:
    """Tests for demo benchmark data generation."""

    def test_generates_result(self):
        r = generate_demo_benchmark("before", 6)
        assert r.label == "before"
        assert r.channel == 6
        assert r.throughput_mbps > 0

    def test_crowded_channel_lower_throughput(self):
        crowded = generate_demo_benchmark("test", 6)    # Congestion = 0.8
        clear = generate_demo_benchmark("test", 11)      # Congestion = 0.1

        # Channel 6 (crowded) should have lower throughput than channel 11
        assert crowded.throughput_mbps < clear.throughput_mbps

    def test_crowded_channel_higher_latency(self):
        crowded = generate_demo_benchmark("test", 6)
        clear = generate_demo_benchmark("test", 11)

        assert crowded.latency_avg_ms > clear.latency_avg_ms

    def test_band_detection(self):
        r24 = generate_demo_benchmark("test", 6)
        r5 = generate_demo_benchmark("test", 36)

        assert r24.band == "2.4GHz"
        assert r5.band == "5GHz"


class TestCompareResults:
    """Tests for before/after comparison."""

    def test_throughput_improvement(self):
        before = BenchmarkResult(throughput_mbps=30.0, channel=6)
        after = BenchmarkResult(throughput_mbps=80.0, channel=11)

        comparison = compare_results(before, after)
        assert comparison["throughput_mbps"]["improved"] is True
        assert comparison["throughput_mbps"]["difference"] == 50.0

    def test_latency_improvement(self):
        before = BenchmarkResult(latency_avg_ms=25.0, channel=6)
        after = BenchmarkResult(latency_avg_ms=5.0, channel=11)

        comparison = compare_results(before, after)
        # Lower latency = improved
        assert comparison["latency_avg_ms"]["improved"] is True

    def test_no_improvement(self):
        before = BenchmarkResult(throughput_mbps=80.0, channel=11)
        after = BenchmarkResult(throughput_mbps=30.0, channel=6)

        comparison = compare_results(before, after)
        assert comparison["throughput_mbps"]["improved"] is False

    def test_percent_change(self):
        before = BenchmarkResult(throughput_mbps=50.0)
        after = BenchmarkResult(throughput_mbps=75.0)

        comparison = compare_results(before, after)
        assert comparison["throughput_mbps"]["percent_change"] == 50.0  # 50% increase

    def test_overall_improved(self):
        before = BenchmarkResult(
            throughput_mbps=30, latency_avg_ms=25,
            jitter_ms=10, packet_loss_percent=5, retransmissions=50,
        )
        after = BenchmarkResult(
            throughput_mbps=80, latency_avg_ms=5,
            jitter_ms=2, packet_loss_percent=0.5, retransmissions=5,
        )

        comparison = compare_results(before, after)
        assert comparison["overall_improved"] is True
        assert comparison["improvement_count"] == 5

    def test_channels_recorded(self):
        before = BenchmarkResult(channel=6)
        after = BenchmarkResult(channel=11)

        comparison = compare_results(before, after)
        assert comparison["before_channel"] == 6
        assert comparison["after_channel"] == 11

    def test_demo_data_comparison(self):
        """Integration test: demo data from crowded→clear should show improvement."""
        before = generate_demo_benchmark("before", 6)
        after = generate_demo_benchmark("after", 11)

        comparison = compare_results(before, after)
        assert comparison["overall_improved"] is True


class TestLiveBenchmarkFailureHandling:
    def test_ping_command_missing_is_not_zero_packet_loss(self, monkeypatch):
        from src import benchmark

        monkeypatch.setattr(
            benchmark, "run_shell_command",
            lambda *args, **kwargs: ("", "Command not found: ping", -1),
        )
        result = benchmark.run_ping_test("127.0.0.1", count=1)
        assert "error" in result
        assert "Command not found" in result["error"]
        assert "packet_loss_percent" not in result

    def test_ping_parses_real_statistics(self, monkeypatch):
        from src import benchmark

        output = (
            "4 packets transmitted, 4 received, 0% packet loss, time 600ms\\n"
            "rtt min/avg/max/mdev = 1.100/2.200/3.300/0.400 ms"
        )
        monkeypatch.setattr(
            benchmark, "run_shell_command",
            lambda *args, **kwargs: (output, "", 0),
        )
        result = benchmark.run_ping_test("127.0.0.1", count=4)
        assert result["packet_loss_percent"] == 0
        assert result["latency_avg_ms"] == 2.2
        assert result["jitter_ms"] == 0.4
        assert "error" not in result

    def test_incomplete_live_benchmark_records_errors(self, monkeypatch):
        from src import benchmark

        monkeypatch.setattr(benchmark, "run_iperf3_test", lambda *args, **kwargs: {})
        monkeypatch.setattr(
            benchmark, "run_ping_test",
            lambda *args, **kwargs: {"error": "ping is unavailable"},
        )
        result = benchmark.run_benchmark()
        assert result.source == "live"
        assert any(error.startswith("iperf3:") for error in result.errors)
        assert any(error.startswith("ping:") for error in result.errors)

    def test_demo_results_are_labelled_synthetic(self):
        from src.benchmark import generate_demo_benchmark

        result = generate_demo_benchmark("before", 6)
        assert result.source == "synthetic"
        assert result.errors == []

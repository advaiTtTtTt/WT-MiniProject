"""
Network Performance Benchmark Module

Measures throughput, latency, jitter, and packet loss using iperf3 and ping.
Stores results for before/after comparison.
"""

import json
import re
import statistics
import time
from dataclasses import dataclass, asdict

from .utils import (
    run_shell_command,
    check_tool_installed,
    load_config,
    save_json,
    timestamp,
)


@dataclass
class BenchmarkResult:
    """Results from a single benchmark run."""
    timestamp: str = ""
    channel: int = 0
    band: str = ""
    label: str = ""                    # "before" or "after"

    # Throughput (from iperf3)
    throughput_mbps: float = 0.0       # Average throughput in Mbps
    throughput_max_mbps: float = 0.0   # Peak throughput
    throughput_min_mbps: float = 0.0   # Minimum throughput

    # Latency (from ping)
    latency_avg_ms: float = 0.0       # Average RTT
    latency_min_ms: float = 0.0       # Min RTT
    latency_max_ms: float = 0.0       # Max RTT
    jitter_ms: float = 0.0            # Jitter (stddev of RTT)

    # Packet loss
    packet_loss_percent: float = 0.0   # Packet loss %

    # Retransmissions (TCP)
    retransmissions: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "BenchmarkResult":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def run_iperf3_test(
    server: str = "192.168.1.1",
    duration: int = 10,
    parallel: int = 4,
) -> dict:
    """
    Run an iperf3 throughput test.

    Args:
        server: iperf3 server address
        duration: Test duration in seconds
        parallel: Number of parallel streams

    Returns:
        Dict with throughput metrics, or empty dict on failure
    """
    if not check_tool_installed("iperf3"):
        print("  [!] iperf3 not installed. Install with: sudo apt install iperf3")
        return {}

    print(f"  [*] Running iperf3 test to {server} ({duration}s, {parallel} streams)...")

    stdout, stderr, rc = run_shell_command(
        [
            "iperf3",
            "-c", server,
            "-t", str(duration),
            "-P", str(parallel),
            "-J",  # JSON output
        ],
        timeout=duration + 15,
    )

    if rc != 0:
        print(f"  [!] iperf3 failed: {stderr.strip()}")
        return {}

    try:
        data = json.loads(stdout)
        end = data.get("end", {})
        sum_sent = end.get("sum_sent", {})
        sum_received = end.get("sum_received", {})

        result = {
            "throughput_mbps": sum_received.get("bits_per_second", 0) / 1_000_000,
            "throughput_sent_mbps": sum_sent.get("bits_per_second", 0) / 1_000_000,
            "retransmissions": sum_sent.get("retransmits", 0),
        }

        # Get per-interval data for min/max
        intervals = data.get("intervals", [])
        if intervals:
            interval_rates = [
                i.get("sum", {}).get("bits_per_second", 0) / 1_000_000
                for i in intervals
            ]
            result["throughput_max_mbps"] = max(interval_rates)
            result["throughput_min_mbps"] = min(interval_rates)

        return result

    except (json.JSONDecodeError, KeyError) as e:
        print(f"  [!] Failed to parse iperf3 output: {e}")
        return {}


def run_ping_test(
    target: str = "192.168.1.1",
    count: int = 30,
) -> dict:
    """
    Run a ping test to measure latency, jitter, and packet loss.

    Args:
        target: Target IP/hostname
        count: Number of pings

    Returns:
        Dict with latency metrics
    """
    print(f"  [*] Running ping test to {target} ({count} packets)...")

    stdout, stderr, rc = run_shell_command(
        ["ping", "-c", str(count), "-i", "0.2", target],
        timeout=count * 2 + 10,
    )

    result = {
        "latency_avg_ms": 0.0,
        "latency_min_ms": 0.0,
        "latency_max_ms": 0.0,
        "jitter_ms": 0.0,
        "packet_loss_percent": 0.0,
    }

    # Parse packet loss
    loss_match = re.search(r"(\d+\.?\d*)% packet loss", stdout)
    if loss_match:
        result["packet_loss_percent"] = float(loss_match.group(1))

    # Parse RTT statistics
    rtt_match = re.search(
        r"rtt min/avg/max/mdev\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)",
        stdout,
    )
    if rtt_match:
        result["latency_min_ms"] = float(rtt_match.group(1))
        result["latency_avg_ms"] = float(rtt_match.group(2))
        result["latency_max_ms"] = float(rtt_match.group(3))
        result["jitter_ms"] = float(rtt_match.group(4))

    return result


def run_benchmark(
    label: str = "test",
    channel: int = 0,
    band: str = "2.4GHz",
    server: str = "192.168.1.1",
    duration: int = 10,
    parallel: int = 4,
    ping_count: int = 30,
) -> BenchmarkResult:
    """
    Run a complete benchmark (iperf3 throughput + ping latency).

    Args:
        label: Label for this run ("before" or "after")
        channel: Current WiFi channel
        band: Current band
        server: Test server address
        duration: iperf3 duration
        parallel: iperf3 parallel streams
        ping_count: Number of ping packets

    Returns:
        BenchmarkResult with all metrics
    """
    result = BenchmarkResult(
        timestamp=timestamp(),
        channel=channel,
        band=band,
        label=label,
    )

    # Run iperf3
    iperf_data = run_iperf3_test(server, duration, parallel)
    if iperf_data:
        result.throughput_mbps = iperf_data.get("throughput_mbps", 0)
        result.throughput_max_mbps = iperf_data.get("throughput_max_mbps", 0)
        result.throughput_min_mbps = iperf_data.get("throughput_min_mbps", 0)
        result.retransmissions = iperf_data.get("retransmissions", 0)

    # Run ping test
    ping_data = run_ping_test(server, ping_count)
    result.latency_avg_ms = ping_data.get("latency_avg_ms", 0)
    result.latency_min_ms = ping_data.get("latency_min_ms", 0)
    result.latency_max_ms = ping_data.get("latency_max_ms", 0)
    result.jitter_ms = ping_data.get("jitter_ms", 0)
    result.packet_loss_percent = ping_data.get("packet_loss_percent", 0)

    return result


def generate_demo_benchmark(label: str, channel: int) -> BenchmarkResult:
    """
    Generate realistic demo benchmark data for testing.

    Simulates that a crowded channel (e.g., 6) has worse performance
    than a clear channel (e.g., 11).
    """
    import random
    random.seed(channel + (0 if label == "before" else 100))

    # Channels with more congestion → worse performance
    congestion_map = {
        1: 0.7,   # Crowded
        2: 0.6,
        3: 0.5,
        6: 0.8,   # Very crowded
        7: 0.6,
        9: 0.3,
        11: 0.1,  # Least crowded
        36: 0.05,
        48: 0.05,
    }

    congestion = congestion_map.get(channel, 0.3)

    # Base performance (on empty channel)
    base_throughput = 95.0    # Mbps
    base_latency = 2.0        # ms
    base_jitter = 0.5         # ms
    base_loss = 0.0            # %

    # Degradation based on congestion
    throughput = base_throughput * (1 - congestion * 0.7) + random.uniform(-5, 5)
    latency = base_latency + congestion * 25 + random.uniform(0, 3)
    jitter = base_jitter + congestion * 10 + random.uniform(0, 2)
    loss = base_loss + congestion * 5 + random.uniform(0, 1)
    retrans = int(congestion * 50 + random.randint(0, 10))

    return BenchmarkResult(
        timestamp=timestamp(),
        channel=channel,
        band="2.4GHz" if channel <= 13 else "5GHz",
        label=label,
        throughput_mbps=max(5, throughput),
        throughput_max_mbps=max(5, throughput + random.uniform(5, 15)),
        throughput_min_mbps=max(1, throughput - random.uniform(5, 15)),
        latency_avg_ms=max(0.5, latency),
        latency_min_ms=max(0.3, latency - random.uniform(0.5, 2)),
        latency_max_ms=latency + random.uniform(2, 10),
        jitter_ms=max(0.1, jitter),
        packet_loss_percent=max(0, min(100, loss)),
        retransmissions=max(0, retrans),
    )


def print_benchmark_result(result: BenchmarkResult):
    """Print a formatted benchmark result."""
    print(f"\n  📊 Benchmark Results ({result.label.upper()}) — Channel {result.channel}")
    print(f"  {'─' * 45}")
    print(f"  Throughput:    {result.throughput_mbps:>8.2f} Mbps (avg)")
    print(f"               {result.throughput_min_mbps:>8.2f} — {result.throughput_max_mbps:.2f} Mbps (range)")
    print(f"  Latency:      {result.latency_avg_ms:>8.2f} ms (avg)")
    print(f"               {result.latency_min_ms:>8.2f} — {result.latency_max_ms:.2f} ms (range)")
    print(f"  Jitter:       {result.jitter_ms:>8.2f} ms")
    print(f"  Packet Loss:  {result.packet_loss_percent:>8.2f} %")
    print(f"  Retransmits:  {result.retransmissions:>8d}")


# Allow running as module: python3 -m src.benchmark
if __name__ == "__main__":
    import sys

    config = load_config()

    print("\n⚡ Network Performance Benchmark")
    print("=" * 50)

    if "--demo" in sys.argv:
        print("[*] Using demo data\n")
        result = generate_demo_benchmark("test", 6)
    else:
        result = run_benchmark(
            label="test",
            server=config["iperf_server"],
            duration=config["iperf_duration"],
            parallel=config["iperf_parallel"],
        )

    print_benchmark_result(result)

    data = result.to_dict()
    path = save_json(data, f"benchmark_{result.label}_{timestamp()}.json")
    print(f"\n  [+] Results saved to {path}")

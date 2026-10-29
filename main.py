#!/usr/bin/env python3
"""
WiFi Channel Optimizer — Main CLI Entry Point

Usage:
    sudo python3 main.py              # Full workflow (scan → analyze → switch → compare)
    sudo python3 main.py --demo       # Demo mode (no WiFi adapter needed)
    sudo python3 main.py scan         # Scan only
    sudo python3 main.py analyze      # Analyze only (uses cached scan)
    sudo python3 main.py benchmark    # Benchmark only
    sudo python3 main.py compare      # Run full comparison
    sudo python3 main.py --help       # Show help
"""

import sys
import time

from src.utils import (
    print_banner,
    load_config,
    save_json,
    load_json,
    check_root,
    timestamp,
)
from src.scanner import (
    scan_networks,
    generate_demo_scan_data,
    print_scan_results,
    NetworkInfo,
)
from src.analyzer import (
    analyze_channels,
    get_best_channel,
    print_analysis,
    generate_channel_chart,
    generate_signal_heatmap,
)
from src.benchmark import (
    run_benchmark,
    generate_demo_benchmark,
    print_benchmark_result,
)
from src.channel_switcher import (
    get_current_channel,
    switch_channel,
    simulate_switch,
)
from src.comparator import (
    compare_results,
    print_comparison,
    generate_comparison_chart,
)


def cmd_scan(config: dict, demo: bool = False) -> list[NetworkInfo]:
    """Step 1: Scan nearby WiFi networks."""
    print("\n" + "=" * 60)
    print("  📡 STEP 1: Scanning Nearby WiFi Networks")
    print("=" * 60)

    if demo:
        print("  [*] Using demo data (no WiFi adapter needed)\n")
        networks = generate_demo_scan_data()
    else:
        check_root()
        print(f"  [*] Interface: {config['interface']}")
        print(f"  [*] Scans: {config['scan_count']}\n")
        networks = scan_networks(config["interface"], config["scan_count"])

    if not networks:
        print("  [!] No networks found!")
        return []

    print_scan_results(networks)

    # Save scan data
    scan_data = {
        "timestamp": timestamp(),
        "interface": config["interface"],
        "networks": [n.to_dict() for n in networks],
    }
    save_json(scan_data, "last_scan.json")
    print(f"\n  [+] Scan data saved ({len(networks)} networks)")

    return networks


def cmd_analyze(networks: list[NetworkInfo], band: str = "2.4GHz"):
    """Step 2: Analyze channel congestion."""
    print("\n" + "=" * 60)
    print("  📊 STEP 2: Analyzing Channel Congestion")
    print("=" * 60)

    scores = analyze_channels(networks, band=band)
    best = get_best_channel(scores)

    print(f"\n  --- {band} Channel Analysis ---\n")
    print_analysis(scores, best)

    if best:
        print(f"\n  ➤ Recommended channel: {best.channel}")
        print(f"    Congestion score: {best.congestion_score:.1f}%")
        print(f"    APs on channel: {best.ap_count}")
        print(f"    Status: {best.recommendation}")

    # Generate charts
    print("\n  [*] Generating charts...")
    chart_path = generate_channel_chart(scores, best)
    if chart_path:
        print(f"  [+] Channel chart: {chart_path}")

    heatmap_path = generate_signal_heatmap(networks)
    if heatmap_path:
        print(f"  [+] Signal heatmap: {heatmap_path}")

    # Save analysis
    analysis_data = {
        "timestamp": timestamp(),
        "band": band,
        "scores": [s.to_dict() for s in scores],
        "best_channel": best.to_dict() if best else None,
    }
    save_json(analysis_data, "last_analysis.json")

    return scores, best


def cmd_full_workflow(config: dict, demo: bool = False):
    """Run the complete workflow: scan → analyze → benchmark → switch → benchmark → compare."""

    # Step 1: Scan
    networks = cmd_scan(config, demo)
    if not networks:
        return

    # Step 2: Analyze
    band = config.get("band", "2.4GHz")
    scores, best = cmd_analyze(networks, band)

    if not best:
        print("\n  [!] Could not determine best channel. Aborting.")
        return

    # Determine current channel
    if demo:
        current_channel = 6  # Simulated: currently on crowded channel 6
    else:
        current_channel = get_current_channel(config["interface"])

    if current_channel is None:
        print("  [!] Could not determine the current channel; refusing to assume channel 6.")
        print("      Check the interface name and ensure it is an active AP/monitor interface.")
        return

    target_channel = best.channel

    print(f"\n  Current channel: {current_channel}")
    print(f"  Recommended channel: {target_channel}")

    if current_channel == target_channel:
        print("  [*] Already on the best channel! Running benchmark for reference...")
        if demo:
            result = generate_demo_benchmark("current", current_channel)
        else:
            result = run_benchmark(
                label="current",
                channel=current_channel,
                band=band,
                server=config["iperf_server"],
                duration=config["iperf_duration"],
                parallel=config["iperf_parallel"],
            )
        print_benchmark_result(result)
        return

    # Step 3: Benchmark BEFORE
    print("\n" + "=" * 60)
    print("  ⚡ STEP 3: Benchmarking BEFORE Channel Switch")
    print(f"  (Current channel: {current_channel})")
    print("=" * 60)

    if demo:
        before_result = generate_demo_benchmark("before", current_channel)
    else:
        before_result = run_benchmark(
            label="before",
            channel=current_channel,
            band=band,
            server=config["iperf_server"],
            duration=config["iperf_duration"],
            parallel=config["iperf_parallel"],
        )

    print_benchmark_result(before_result)
    save_json(before_result.to_dict(), "benchmark_before.json")
    if before_result.errors:
        print("  [!] Baseline benchmark incomplete; channel switch aborted to avoid a misleading comparison.")
        return

    # Step 4: Switch Channel
    print("\n" + "=" * 60)
    print("  🔄 STEP 4: Switching Channel")
    print(f"  Channel {current_channel} → Channel {target_channel}")
    print("=" * 60)

    if demo:
        switch_result = simulate_switch(current_channel, target_channel)
    else:
        success, msg = switch_channel(config["interface"], target_channel)
        print(f"\n  {'✅' if success else '❌'} {msg}")
        if not success:
            print("  [!] Channel switch failed. Aborting comparison.")
            return
        time.sleep(3)  # Wait for connection to stabilize

    # Step 5: Benchmark AFTER
    print("\n" + "=" * 60)
    print("  ⚡ STEP 5: Benchmarking AFTER Channel Switch")
    print(f"  (New channel: {target_channel})")
    print("=" * 60)

    if demo:
        after_result = generate_demo_benchmark("after", target_channel)
    else:
        after_result = run_benchmark(
            label="after",
            channel=target_channel,
            band=band,
            server=config["iperf_server"],
            duration=config["iperf_duration"],
            parallel=config["iperf_parallel"],
        )

    print_benchmark_result(after_result)
    save_json(after_result.to_dict(), "benchmark_after.json")
    if after_result.errors:
        print("  [!] After-switch benchmark incomplete; comparison aborted.")
        return

    # Step 6: Compare
    print("\n" + "=" * 60)
    print("  📊 STEP 6: Before vs After Comparison")
    print("=" * 60)

    comparison = compare_results(before_result, after_result)
    print_comparison(comparison)

    # Generate comparison chart
    chart_path = generate_comparison_chart(before_result, after_result)
    if chart_path:
        print(f"\n  [+] Comparison chart: {chart_path}")

    # Save full report
    report = {
        "timestamp": timestamp(),
        "config": config,
        "scan_summary": {
            "total_networks": len(networks),
            "band": band,
        },
        "channel_switch": {
            "from": current_channel,
            "to": target_channel,
        },
        "before": before_result.to_dict(),
        "after": after_result.to_dict(),
        "comparison": comparison,
    }
    report_path = save_json(report, f"full_report_{timestamp()}.json")
    print(f"  [+] Full report saved to: {report_path}")

    print("\n" + "=" * 60)
    print("  ✅ WiFi Channel Optimization Complete!")
    print("=" * 60)


def print_help():
    """Print usage help."""
    print("""
Usage: python3 main.py [command] [options]

Commands:
  (none)        Run full workflow (scan → analyze → switch → compare)
  scan          Scan nearby WiFi networks
  analyze       Analyze channel congestion (uses cached scan data)
  benchmark     Run a speed benchmark
  compare       Compare two benchmark results

Options:
  --demo        Use demo data (no WiFi adapter or root needed)
  --help        Show this help message

Examples:
  sudo python3 main.py --demo       # Full demo (recommended for testing)
  sudo python3 main.py scan         # Scan only
  sudo python3 main.py analyze      # Analyze cached scan
    """)


def main():
    """Main entry point."""
    print_banner()

    config = load_config()
    demo = "--demo" in sys.argv

    if "--help" in sys.argv or "-h" in sys.argv:
        print_help()
        return

    # Determine command
    commands = {"scan", "analyze", "benchmark", "compare"}
    command = None
    for arg in sys.argv[1:]:
        if arg in commands:
            command = arg
            break

    if command == "scan":
        cmd_scan(config, demo)

    elif command == "analyze":
        # Load cached scan
        scan_data = load_json("last_scan.json")
        if scan_data:
            networks = [NetworkInfo.from_dict(n) for n in scan_data["networks"]]
        elif demo:
            networks = generate_demo_scan_data()
        else:
            print("[!] No scan data found. Run 'scan' first or use --demo.")
            return
        cmd_analyze(networks, config.get("band", "2.4GHz"))

    elif command == "benchmark":
        print("\n⚡ Running Benchmark...")
        if demo:
            result = generate_demo_benchmark("test", 6)
        else:
            check_root()
            result = run_benchmark(
                label="test",
                server=config["iperf_server"],
                duration=config["iperf_duration"],
                parallel=config["iperf_parallel"],
            )
        print_benchmark_result(result)

    elif command == "compare":
        # Load saved benchmark data
        before_data = load_json("benchmark_before.json")
        after_data = load_json("benchmark_after.json")

        if before_data and after_data:
            from src.benchmark import BenchmarkResult
            before = BenchmarkResult.from_dict(before_data)
            after = BenchmarkResult.from_dict(after_data)
        elif demo:
            before = generate_demo_benchmark("before", 6)
            after = generate_demo_benchmark("after", 11)
        else:
            print("[!] No benchmark data found. Run full workflow first.")
            return

        try:
            comparison = compare_results(before, after)
        except ValueError as exc:
            print(f"[!] Cannot compare benchmark results: {exc}")
            return
        print_comparison(comparison)
        chart_path = generate_comparison_chart(before, after)
        if chart_path:
            print(f"\n  [+] Comparison chart: {chart_path}")

    else:
        # Full workflow
        cmd_full_workflow(config, demo)


if __name__ == "__main__":
    main()

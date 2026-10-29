"""
Before/After Comparison Module

Compares benchmark results before and after a channel switch.
Generates visual comparison charts and a summary report.
"""

from .benchmark import BenchmarkResult
from .utils import REPORTS_DIR, timestamp, save_json


def compare_results(before: BenchmarkResult, after: BenchmarkResult) -> dict:
    """
    Compare before and after benchmark results.

    Returns a dict with absolute and percentage differences for each metric.
    """

    if before.errors or after.errors:
        details = before.errors + after.errors
        raise ValueError(
            "Cannot compare incomplete benchmark results: " + "; ".join(details)
        )
    if before.source != after.source:
        raise ValueError(
            f"Cannot compare different data sources ({before.source!r} vs {after.source!r})."
        )

    def _delta(before_val: float, after_val: float, higher_is_better: bool = True) -> dict:
        diff = after_val - before_val
        # Percentage change from a zero baseline is undefined when the value
        # changes. Use None instead of Infinity so reports remain valid JSON.
        if before_val != 0:
            pct = round((diff / abs(before_val)) * 100, 1)
        else:
            pct = 0.0 if diff == 0 else None

        improved = (diff > 0) if higher_is_better else (diff < 0)

        return {
            "before": round(before_val, 2),
            "after": round(after_val, 2),
            "difference": round(diff, 2),
            "percent_change": pct,
            "improved": improved,
            "direction": "↑" if diff > 0 else "↓" if diff < 0 else "→",
        }

    comparison = {
        "before_channel": before.channel,
        "after_channel": after.channel,
        "throughput_mbps": _delta(before.throughput_mbps, after.throughput_mbps, higher_is_better=True),
        "latency_avg_ms": _delta(before.latency_avg_ms, after.latency_avg_ms, higher_is_better=False),
        "jitter_ms": _delta(before.jitter_ms, after.jitter_ms, higher_is_better=False),
        "packet_loss_percent": _delta(before.packet_loss_percent, after.packet_loss_percent, higher_is_better=False),
        "retransmissions": _delta(float(before.retransmissions), float(after.retransmissions), higher_is_better=False),
    }

    # Calculate overall improvement score
    improvements = [
        comparison["throughput_mbps"]["improved"],
        comparison["latency_avg_ms"]["improved"],
        comparison["jitter_ms"]["improved"],
        comparison["packet_loss_percent"]["improved"],
        comparison["retransmissions"]["improved"],
    ]
    comparison["improvement_count"] = sum(improvements)
    comparison["total_metrics"] = len(improvements)
    comparison["overall_improved"] = sum(improvements) >= 3  # Majority

    return comparison


def print_comparison(comparison: dict):
    """Print a formatted comparison report."""

    print(f"\n{'═' * 60}")
    print(f"  📊 BEFORE vs AFTER Comparison Report")
    print(f"  Channel {comparison['before_channel']} → Channel {comparison['after_channel']}")
    print(f"{'═' * 60}")

    metrics = [
        ("Throughput", "throughput_mbps", "Mbps", True),
        ("Avg Latency", "latency_avg_ms", "ms", False),
        ("Jitter", "jitter_ms", "ms", False),
        ("Packet Loss", "packet_loss_percent", "%", False),
        ("Retransmits", "retransmissions", "", False),
    ]

    for label, key, unit, higher_better in metrics:
        data = comparison[key]
        status = "✅" if data["improved"] else "❌" if not data["improved"] and data["difference"] != 0 else "➖"

        print(f"\n  {label}:")
        print(f"    Before:  {data['before']:>10.2f} {unit}")
        print(f"    After:   {data['after']:>10.2f} {unit}")
        change_sign = "+" if data["difference"] > 0 else ""
        pct = data["percent_change"]
        pct_label = "N/A" if pct is None else f"{('+' if pct > 0 else '')}{pct}%"
        print(f"    Change:  {change_sign}{data['difference']:>9.2f} {unit} ({pct_label}) {status}")

    # Overall verdict
    improved = comparison["improvement_count"]
    total = comparison["total_metrics"]

    print(f"\n{'─' * 60}")
    if comparison["overall_improved"]:
        print(f"  🎉 OVERALL: IMPROVED ({improved}/{total} metrics better)")
        print(f"     Channel switch was beneficial!")
    else:
        print(f"  ⚠️  OVERALL: MIXED ({improved}/{total} metrics better)")
        print(f"     Channel switch had limited impact.")
    print(f"{'═' * 60}")


def generate_comparison_chart(before: BenchmarkResult, after: BenchmarkResult) -> str | None:
    """
    Generate a side-by-side comparison bar chart.

    Returns file path of generated chart or None.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("  [!] matplotlib not installed. Skipping chart generation.")
        return None

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        f"Performance Comparison: Channel {before.channel} → Channel {after.channel}",
        fontsize=16, fontweight="bold",
    )

    bar_width = 0.35
    colors_before = "#e74c3c"  # Red
    colors_after = "#2ecc71"   # Green

    # 1. Throughput comparison
    ax = axes[0, 0]
    categories = ["Average", "Max", "Min"]
    before_vals = [before.throughput_mbps, before.throughput_max_mbps, before.throughput_min_mbps]
    after_vals = [after.throughput_mbps, after.throughput_max_mbps, after.throughput_min_mbps]

    x = range(len(categories))
    ax.bar([i - bar_width / 2 for i in x], before_vals, bar_width, label=f"Ch {before.channel} (Before)", color=colors_before)
    ax.bar([i + bar_width / 2 for i in x], after_vals, bar_width, label=f"Ch {after.channel} (After)", color=colors_after)
    ax.set_ylabel("Throughput (Mbps)")
    ax.set_title("Throughput (Higher = Better)")
    ax.set_xticks(list(x))
    ax.set_xticklabels(categories)
    ax.legend()

    # Add value labels
    for i, (bv, av) in enumerate(zip(before_vals, after_vals)):
        ax.text(i - bar_width / 2, bv + 0.5, f"{bv:.1f}", ha="center", va="bottom", fontsize=8)
        ax.text(i + bar_width / 2, av + 0.5, f"{av:.1f}", ha="center", va="bottom", fontsize=8)

    # 2. Latency comparison
    ax = axes[0, 1]
    categories = ["Avg RTT", "Min RTT", "Max RTT", "Jitter"]
    before_vals = [before.latency_avg_ms, before.latency_min_ms, before.latency_max_ms, before.jitter_ms]
    after_vals = [after.latency_avg_ms, after.latency_min_ms, after.latency_max_ms, after.jitter_ms]

    x = range(len(categories))
    ax.bar([i - bar_width / 2 for i in x], before_vals, bar_width, label=f"Ch {before.channel}", color=colors_before)
    ax.bar([i + bar_width / 2 for i in x], after_vals, bar_width, label=f"Ch {after.channel}", color=colors_after)
    ax.set_ylabel("Latency (ms)")
    ax.set_title("Latency (Lower = Better)")
    ax.set_xticks(list(x))
    ax.set_xticklabels(categories)
    ax.legend()

    # 3. Packet Loss & Retransmissions
    ax = axes[1, 0]
    categories = ["Packet Loss (%)", "Retransmissions"]
    before_vals = [before.packet_loss_percent, before.retransmissions]
    after_vals = [after.packet_loss_percent, after.retransmissions]

    x = range(len(categories))
    ax.bar([i - bar_width / 2 for i in x], before_vals, bar_width, label=f"Ch {before.channel}", color=colors_before)
    ax.bar([i + bar_width / 2 for i in x], after_vals, bar_width, label=f"Ch {after.channel}", color=colors_after)
    ax.set_ylabel("Count / %")
    ax.set_title("Packet Loss & Retransmissions (Lower = Better)")
    ax.set_xticks(list(x))
    ax.set_xticklabels(categories)
    ax.legend()

    # 4. Overall improvement summary (radar-style as horizontal bars)
    ax = axes[1, 1]
    comparison = compare_results(before, after)
    metric_names = ["Throughput", "Latency", "Jitter", "Pkt Loss", "Retransmits"]
    metric_keys = ["throughput_mbps", "latency_avg_ms", "jitter_ms", "packet_loss_percent", "retransmissions"]
    pct_changes = [comparison[k]["percent_change"] for k in metric_keys]

    # Undefined percentage changes (zero baseline) display as N/A without
    # creating non-standard JSON Infinity values or breaking chart arithmetic.
    display_changes = [
        (pct_changes[0] if pct_changes[0] is not None else 0.0),
        (-(pct_changes[1]) if pct_changes[1] is not None else 0.0),
        (-(pct_changes[2]) if pct_changes[2] is not None else 0.0),
        (-(pct_changes[3]) if pct_changes[3] is not None else 0.0),
        (-(pct_changes[4]) if pct_changes[4] is not None else 0.0),
    ]

    bar_colors = [
        "#7f8c8d" if pct_changes[i] is None else "#2ecc71" if v >= 0 else "#e74c3c"
        for i, v in enumerate(display_changes)
    ]
    y_pos = range(len(metric_names))

    ax.barh(list(y_pos), display_changes, color=bar_colors, edgecolor="black", linewidth=0.5)
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(metric_names)
    ax.set_xlabel("Improvement (%)")
    ax.set_title("Overall Improvement (Right = Better)")
    ax.axvline(x=0, color="black", linewidth=0.8)

    for i, v in enumerate(display_changes):
        label = "N/A" if pct_changes[i] is None else f"{v:+.1f}%"
        ax.text(v + (1 if v >= 0 else -1), i, label, va="center", fontsize=9)

    plt.tight_layout()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = REPORTS_DIR / f"comparison_{timestamp()}.png"
    plt.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close()

    return str(filepath)


# Allow running as module: python3 -m src.comparator
if __name__ == "__main__":
    from .benchmark import generate_demo_benchmark

    print("\n📊 Performance Comparison (Demo)")
    print("=" * 50)

    before = generate_demo_benchmark("before", channel=6)
    after = generate_demo_benchmark("after", channel=11)

    comparison = compare_results(before, after)
    print_comparison(comparison)

    chart_path = generate_comparison_chart(before, after)
    if chart_path:
        print(f"\n  [+] Comparison chart saved to: {chart_path}")

    # Save comparison data
    data = {
        "before": before.to_dict(),
        "after": after.to_dict(),
        "comparison": comparison,
    }
    path = save_json(data, "last_comparison.json")
    print(f"  [+] Comparison data saved to: {path}")

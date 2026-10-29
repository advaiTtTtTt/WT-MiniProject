"""
WiFi Channel Analyzer Module

Analyzes channel congestion from scan data. Calculates per-channel scores
considering AP count, signal strength, adjacent-channel interference,
and channel width overlap. Generates visual charts.
"""

import os
from collections import defaultdict
from dataclasses import dataclass

from .scanner import NetworkInfo
from .utils import (
    CHANNEL_FREQ_24GHZ,
    CHANNEL_FREQ_5GHZ,
    NON_OVERLAPPING_24GHZ,
    channel_overlap_score,
    is_24ghz,
    is_5ghz,
    load_json,
    save_json,
    timestamp,
    REPORTS_DIR,
)


@dataclass
class ChannelScore:
    """Analysis score for a single WiFi channel."""
    channel: int
    band: str
    ap_count: int = 0                   # Number of APs on this exact channel
    overlapping_ap_count: int = 0       # APs on overlapping channels
    total_interference_score: float = 0.0   # Weighted interference metric
    avg_signal_dbm: float = -100.0      # Average signal of APs on this channel
    strongest_signal_dbm: int = -100    # Strongest AP signal on this channel
    congestion_score: float = 0.0       # 0 = empty, 100 = very congested
    recommendation: str = ""            # "Best", "Good", "Moderate", "Avoid"

    def to_dict(self) -> dict:
        return {
            "channel": self.channel,
            "band": self.band,
            "ap_count": self.ap_count,
            "overlapping_ap_count": self.overlapping_ap_count,
            "total_interference_score": round(self.total_interference_score, 2),
            "avg_signal_dbm": round(self.avg_signal_dbm, 1),
            "strongest_signal_dbm": self.strongest_signal_dbm,
            "congestion_score": round(self.congestion_score, 1),
            "recommendation": self.recommendation,
        }


def analyze_channels(networks: list[NetworkInfo], band: str = "2.4GHz") -> list[ChannelScore]:
    """
    Analyze channel congestion from a list of scanned networks.

    For each channel, calculates:
    - Direct AP count (same channel)
    - Overlapping AP count (adjacent channels with spectral overlap)
    - Interference score (weighted by signal strength and overlap degree)
    - Congestion score (0-100, normalized)

    Args:
        networks: List of scanned NetworkInfo objects
        band: "2.4GHz" or "5GHz"

    Returns:
        List of ChannelScore objects, sorted by congestion (best first)
    """
    if band == "2.4GHz":
        all_channels = CHANNEL_FREQ_24GHZ
        filter_fn = is_24ghz
    else:
        all_channels = CHANNEL_FREQ_5GHZ
        filter_fn = is_5ghz

    # Filter networks for the target band
    band_networks = [n for n in networks if filter_fn(n.channel)]

    scores = []

    for target_ch in all_channels:
        score = ChannelScore(
            channel=target_ch,
            band=band,
        )

        signals_on_channel = []
        total_interference = 0.0

        for net in band_networks:
            overlap = channel_overlap_score(target_ch, net.channel)

            if overlap > 0:
                # Convert dBm to linear power for proper signal weighting
                # Signal closer to 0 dBm = stronger = more interference
                signal_weight = 10 ** (net.signal_dbm / 10.0)
                interference = overlap * signal_weight
                total_interference += interference

                if net.channel == target_ch:
                    score.ap_count += 1
                    signals_on_channel.append(net.signal_dbm)
                else:
                    score.overlapping_ap_count += 1

        score.total_interference_score = total_interference

        if signals_on_channel:
            score.avg_signal_dbm = sum(signals_on_channel) / len(signals_on_channel)
            score.strongest_signal_dbm = max(signals_on_channel)
        else:
            score.avg_signal_dbm = -100.0
            score.strongest_signal_dbm = -100

        scores.append(score)

    # Normalize congestion scores to 0-100
    max_interference = max(s.total_interference_score for s in scores) if scores else 1
    if max_interference > 0:
        for s in scores:
            # Congestion combines interference score with AP count
            interference_component = (s.total_interference_score / max_interference) * 70
            ap_count_component = min(s.ap_count * 10, 30)
            s.congestion_score = min(100.0, interference_component + ap_count_component)

    # Assign recommendations
    for s in scores:
        if s.congestion_score == 0:
            s.recommendation = "✅ Best"
        elif s.congestion_score < 25:
            s.recommendation = "🟢 Good"
        elif s.congestion_score < 50:
            s.recommendation = "🟡 Moderate"
        elif s.congestion_score < 75:
            s.recommendation = "🟠 Crowded"
        else:
            s.recommendation = "🔴 Avoid"

    # Sort by congestion score (best = lowest)
    scores.sort(key=lambda s: s.congestion_score)

    return scores


def get_best_channel(scores: list[ChannelScore], prefer_non_overlapping: bool = True) -> ChannelScore:
    """
    Get the best recommended channel.

    Args:
        scores: List of ChannelScore (already sorted by congestion)
        prefer_non_overlapping: If True, prefer channels 1, 6, 11 for 2.4GHz

    Returns:
        Best ChannelScore
    """
    if prefer_non_overlapping and scores and scores[0].band == "2.4GHz":
        non_overlap = [s for s in scores if s.channel in NON_OVERLAPPING_24GHZ]
        if non_overlap:
            return non_overlap[0]

    return scores[0] if scores else None


def print_analysis(scores: list[ChannelScore], best: ChannelScore | None = None):
    """Print channel analysis results in a formatted table."""
    try:
        from tabulate import tabulate
    except ImportError:
        print(f"\n{'Ch':>3} {'Band':<6} {'APs':>4} {'Overlap':>8} {'Congestion':>11} {'Recommendation':<15}")
        print("-" * 55)
        for s in scores:
            marker = " ◀ BEST" if best and s.channel == best.channel else ""
            print(
                f"{s.channel:>3} {s.band:<6} {s.ap_count:>4} {s.overlapping_ap_count:>8} "
                f"{s.congestion_score:>9.1f}% {s.recommendation:<15}{marker}"
            )
        return

    table_data = []
    for s in scores:
        marker = " ◀ BEST" if best and s.channel == best.channel else ""
        bar = _congestion_bar(s.congestion_score)
        table_data.append([
            s.channel,
            s.band,
            s.ap_count,
            s.overlapping_ap_count,
            f"{s.congestion_score:.1f}%",
            bar,
            f"{s.recommendation}{marker}",
        ])

    headers = ["Ch", "Band", "APs", "Overlap APs", "Congestion", "Visual", "Recommendation"]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))


def _congestion_bar(score: float) -> str:
    """Generate a visual congestion bar."""
    filled = int(score / 10)
    empty = 10 - filled
    return "█" * filled + "░" * empty


def generate_channel_chart(scores: list[ChannelScore], best: ChannelScore | None = None) -> str | None:
    """
    Generate a channel congestion bar chart and save it as PNG.

    Returns the file path of the generated chart, or None on failure.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")  # Non-interactive backend
        import matplotlib.pyplot as plt
    except ImportError:
        print("[!] matplotlib not installed. Skipping chart generation.")
        return None

    channels = [s.channel for s in scores]
    congestions = [s.congestion_score for s in scores]
    ap_counts = [s.ap_count for s in scores]

    # Color bars by congestion level
    colors = []
    for s in scores:
        if best and s.channel == best.channel:
            colors.append("#2ecc71")  # Green for best
        elif s.congestion_score < 25:
            colors.append("#27ae60")  # Green
        elif s.congestion_score < 50:
            colors.append("#f39c12")  # Yellow/Orange
        elif s.congestion_score < 75:
            colors.append("#e67e22")  # Orange
        else:
            colors.append("#e74c3c")  # Red

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={"height_ratios": [2, 1]})
    fig.suptitle("WiFi Channel Analysis", fontsize=16, fontweight="bold")

    # Top: Congestion score bar chart
    bars = ax1.bar([str(ch) for ch in channels], congestions, color=colors, edgecolor="black", linewidth=0.5)
    ax1.set_ylabel("Congestion Score (%)")
    ax1.set_xlabel("Channel")
    ax1.set_title("Channel Congestion (lower is better)")
    ax1.set_ylim(0, 105)
    ax1.axhline(y=25, color="green", linestyle="--", alpha=0.3, label="Good threshold")
    ax1.axhline(y=50, color="orange", linestyle="--", alpha=0.3, label="Moderate threshold")
    ax1.axhline(y=75, color="red", linestyle="--", alpha=0.3, label="High threshold")
    ax1.legend(loc="upper right")

    # Add AP count labels on bars
    for bar, count in zip(bars, ap_counts):
        if count > 0:
            ax1.text(
                bar.get_x() + bar.get_width() / 2., bar.get_height() + 1,
                f"{count} APs", ha="center", va="bottom", fontsize=8
            )

    # Bottom: AP count per channel
    ax2.bar([str(ch) for ch in channels], ap_counts, color="#3498db", edgecolor="black", linewidth=0.5)
    ax2.set_ylabel("Number of APs")
    ax2.set_xlabel("Channel")
    ax2.set_title("Access Points per Channel")

    if best:
        ax2.annotate(
            f"Best: Ch {best.channel}",
            xy=(str(best.channel), best.ap_count),
            fontsize=10, color="green", fontweight="bold",
            ha="center",
        )

    plt.tight_layout()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = REPORTS_DIR / f"channel_analysis_{timestamp()}.png"
    plt.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close()

    return str(filepath)


def generate_signal_heatmap(networks: list[NetworkInfo]) -> str | None:
    """
    Generate a signal strength heatmap across channels.

    Returns file path or None.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        return None

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.set_title("WiFi Signal Strength by Channel", fontsize=14, fontweight="bold")

    # Only 2.4 GHz for the heatmap
    nets_24 = [n for n in networks if is_24ghz(n.channel)]

    for net in nets_24:
        # Each channel occupies ~22 MHz (5 MHz spacing between channels)
        center = net.channel
        width = net.channel_width / 5  # Convert MHz to channel units

        # Color based on signal strength
        alpha = max(0.15, min(0.7, (net.signal_dbm + 100) / 70))
        color = "red" if net.signal_dbm > -50 else "orange" if net.signal_dbm > -65 else "blue"

        ax.barh(
            net.ssid[:20],
            width,
            left=center - width / 2,
            height=0.6,
            alpha=alpha,
            color=color,
            edgecolor="black",
            linewidth=0.5,
        )
        ax.text(center, net.ssid[:20], f"{net.signal_dbm}dBm", ha="center", va="center", fontsize=7)

    ax.set_xlabel("Channel")
    ax.set_xticks(range(1, 14))
    ax.set_xlim(0, 14)

    # Legend
    legend_elements = [
        mpatches.Patch(facecolor="red", alpha=0.5, label="Strong (> -50 dBm)"),
        mpatches.Patch(facecolor="orange", alpha=0.5, label="Medium (-50 to -65 dBm)"),
        mpatches.Patch(facecolor="blue", alpha=0.5, label="Weak (< -65 dBm)"),
    ]
    ax.legend(handles=legend_elements, loc="upper right")

    # Mark non-overlapping channels
    for ch in NON_OVERLAPPING_24GHZ:
        ax.axvline(x=ch, color="green", linestyle=":", alpha=0.4)

    plt.tight_layout()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = REPORTS_DIR / f"signal_heatmap_{timestamp()}.png"
    plt.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close()

    return str(filepath)


# Allow running as module: python3 -m src.analyzer
if __name__ == "__main__":
    import sys

    print("\n📊 WiFi Channel Analyzer")
    print("=" * 50)

    # Try to load cached scan data
    scan_data = load_json("last_scan.json")

    if scan_data is None:
        print("[!] No scan data found. Generating demo data...")
        from .scanner import generate_demo_scan_data
        networks = generate_demo_scan_data()
    else:
        networks = [NetworkInfo.from_dict(n) for n in scan_data["networks"]]
        print(f"[*] Loaded {len(networks)} networks from last scan")

    # Analyze 2.4 GHz
    print("\n--- 2.4 GHz Channel Analysis ---")
    scores_24 = analyze_channels(networks, band="2.4GHz")
    best_24 = get_best_channel(scores_24)
    print_analysis(scores_24, best_24)

    if best_24:
        print(f"\n  ➤ Recommended channel: {best_24.channel} (congestion: {best_24.congestion_score:.1f}%)")

    # Analyze 5 GHz
    nets_5 = [n for n in networks if is_5ghz(n.channel)]
    if nets_5:
        print("\n--- 5 GHz Channel Analysis ---")
        scores_5 = analyze_channels(networks, band="5GHz")
        best_5 = get_best_channel(scores_5, prefer_non_overlapping=False)
        print_analysis(scores_5, best_5)

    # Generate charts
    print("\n[*] Generating charts...")
    chart_path = generate_channel_chart(scores_24, best_24)
    if chart_path:
        print(f"  [+] Channel analysis chart: {chart_path}")

    heatmap_path = generate_signal_heatmap(networks)
    if heatmap_path:
        print(f"  [+] Signal heatmap: {heatmap_path}")

    # Save analysis
    analysis_data = {
        "timestamp": timestamp(),
        "band": "2.4GHz",
        "scores": [s.to_dict() for s in scores_24],
        "best_channel": best_24.to_dict() if best_24 else None,
    }
    path = save_json(analysis_data, "last_analysis.json")
    print(f"  [+] Analysis data saved to {path}")

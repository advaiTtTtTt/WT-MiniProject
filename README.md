# 📡 WiFi Channel Optimizer

A Python-based WiFi Channel Analyzer & Optimizer that scans nearby wireless networks, analyzes channel congestion, recommends optimal channels, and provides before/after performance comparisons.

> **Mini-Project for Wireless Technology**

## 🎯 Features

- **WiFi Scanner** — Scan all nearby WiFi networks with RSSI, channel, security info
- **Channel Analyzer** — Visualize channel congestion with heatmaps and bar charts
- **Optimal Channel Recommender** — Suggests the least congested channel
- **Channel Switcher** — Change your AP's channel (requires hostapd/root)
- **Performance Benchmarker** — Run iperf3 speed tests before & after switching
- **Comparison Dashboard** — Side-by-side visual comparison of throughput, latency, and signal quality

## 📋 Prerequisites

- **Linux** (tested on Debian/Ubuntu)
- **Python 3.10+** (the code uses Python 3.10 type-union syntax)
- **Root/sudo access** (for WiFi scanning and channel switching)
- **wireless-tools** or **iw** (for WiFi scanning)
- **iperf3** (for speed benchmarking — install with `sudo apt install iperf3`)
- **A reachable iperf3 server**; run `iperf3 -s` on the target host and set `iperf_server` to that host's IP
- **hostapd** (optional, for channel switching on AP mode)

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/advaiTtTtTt/WT-MiniProject.git
cd WT-MiniProject

# Create virtual environment & install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run the main application
sudo python3 main.py

# Or run individual modules:
sudo python3 -m src.scanner          # Scan nearby networks
python3 -m src.analyzer              # Analyze channel congestion (uses cached scan)
sudo python3 -m src.benchmark        # Run speed benchmark
sudo python3 -m src.channel_switcher # Switch AP channel
```

## 📁 Project Structure

```
wifi-channel-optimizer/
├── main.py                  # Main CLI entry point
├── requirements.txt         # Python dependencies
├── README.md
├── src/
│   ├── __init__.py
│   ├── scanner.py           # WiFi network scanner (iw/iwlist)
│   ├── analyzer.py          # Channel congestion analyzer
│   ├── channel_switcher.py  # AP channel switcher
│   ├── benchmark.py         # iperf3 throughput/latency benchmarker
│   ├── comparator.py        # Before/after comparison engine
│   └── utils.py             # Shared utilities
├── reports/                 # Generated reports & charts
│   └── .gitkeep
├── data/                    # Cached scan & benchmark data
│   └── .gitkeep
└── tests/
    ├── __init__.py
    ├── test_scanner.py
    ├── test_analyzer.py
    ├── test_benchmark.py
    └── test_channel_switcher.py
```

## 📊 How It Works

```
┌─────────────┐     ┌──────────────┐     ┌────────────────┐
│  1. SCAN    │────▶│  2. ANALYZE  │────▶│  3. RECOMMEND  │
│  Nearby APs │     │  Congestion  │     │  Best Channel  │
└─────────────┘     └──────────────┘     └────────────────┘
                                                 │
┌─────────────┐     ┌──────────────┐             │
│  5. COMPARE │◀────│  4. SWITCH   │◀────────────┘
│  Before/After│     │  Channel    │
└─────────────┘     └──────────────┘
```

### Step-by-Step:

1. **Scan** — Uses `iw dev <interface> scan` to discover all nearby access points
2. **Analyze** — Counts APs per channel, calculates overlap scores, measures signal levels
3. **Recommend** — Scores each channel (1-11 for 2.4GHz, more for 5GHz) and picks the best
4. **Switch** — Changes your AP channel via `iw` or `hostapd`
5. **Compare** — Runs iperf3 benchmarks before and after, generates comparison charts

## 🧪 Running Tests

```bash
python3 -m pytest tests/ -v
```

## 📈 Generated Output

Depending on the command and mode, the tool can generate:

- **Channel Congestion Chart** — congestion scores and access-point counts by channel
- **Signal Heatmap** — a visual representation of the scanned channel/signal distribution
- **Before/After Comparison Chart** — benchmark metric deltas and an overall improvement summary
- **JSON data files** — cached scan, analysis, and benchmark results under `data/`

Generated files are local outputs and are excluded from Git by the current `.gitignore`. Values produced with `--demo` are synthetic illustrations, not real Wi-Fi measurements.

## 🔧 Configuration

Edit `config.json` (auto-generated on first run) to customize:

```json
{
  "interface": "wlan0",
  "iperf_server": "192.168.1.1",
  "iperf_duration": 10,
  "iperf_parallel": 4,
  "band": "2.4GHz",
  "scan_count": 3
}
```

## ⚠️ Important Notes

- Live scanning generally requires **root privileges** (`sudo`) and the Linux `iw` or `iwlist` tools.
- Throughput benchmarking requires an `iperf3` server listening on the configured target; the default `192.168.1.1` works only if a server is actually running there.
- Channel switching operates on a supported local AP/monitor interface or a configured `hostapd` software AP. It does not remotely change an ordinary external router's settings.
- `--demo` uses synthetic scan data and a formula-based benchmark generator. Demo numbers must not be described as real-world performance gains.
- Validate live scanning, channel switching, and before/after benchmarks on suitable hardware before claiming a measured improvement.

## 📚 Wireless Concepts Covered

| Concept | How This Project Demonstrates It |
|---|---|
| **Frequency Channels** | Scans and maps 2.4GHz (ch 1-13) and 5GHz channels |
| **Co-channel Interference** | Counts overlapping APs on same channel |
| **Adjacent Channel Interference** | Calculates overlap scores for nearby channels |
| **RSSI / Signal Strength** | Measures and compares dBm values |
| **RSSI-based Signal Quality** | Converts reported signal strength (dBm) to a heuristic quality percentage |
| **Throughput / Data Rate** | Measures real Mbps with iperf3 |
| **CSMA/CA** | Explains why more APs = more contention |
| **Channel Bonding** | Detects 20/40/80 MHz channel widths |

## 📄 License

MIT License — feel free to use for your academic project!

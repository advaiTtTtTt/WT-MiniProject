# WiFi Channel Optimizer — Project Status & Roadmap

**Repository:** https://github.com/advaiTtTtTt/WT-MiniProject  
**Last reviewed:** October 29, 2026  
**Status:** Core CLI modules and demo mode are present in the repository. Automated CI is being added in this branch; live hardware validation remains pending.  
**Original workspace:** `/storage/emulated/10/Documents/.gemini/antigravity/scratch/wifi-channel-optimizer`

---

## 1. Implementation Present

- **`main.py`:** CLI workflow for `scan`, `analyze`, `benchmark`, and `compare`, plus `--demo`.
- **`src/utils.py`:** Channel/frequency mapping for selected 2.4 GHz and 5 GHz channels, 2.4 GHz spectral-overlap heuristic, RSSI-to-quality heuristic, subprocess helpers, configuration and JSON persistence.
- **`src/scanner.py`:** Parsers for `iw` and `iwlist` scan output, multi-pass aggregation, terminal tables, and synthetic scan data for demonstrations.
- **`src/analyzer.py`:** Channel congestion/interference scoring, recommendation logic, congestion chart, and signal heatmap.
- **`src/channel_switcher.py`:** Local interface channel switching and `hostapd` configuration support, plus simulated switching.
- **`src/benchmark.py`:** `iperf3` throughput and retransmission collection, ping latency/jitter/loss parsing, and synthetic demo metrics.
- **`src/comparator.py`:** Before/after calculations and a comparison visualization.
- **Tests:** Three pytest files cover scanner, analyzer, benchmark, and comparator behavior.

## 2. Verification Evidence and Caveats

- The test files contain **56 test functions**: 23 in `tests/test_scanner.py`, 19 in `tests/test_analyzer.py`, and 14 in `tests/test_benchmark.py`.
- Earlier project notes report `56 passed in 0.12s`. This audit confirmed the test files and function count, but could not independently verify that run from GitHub. The current `main` commit has no reported status checks or workflow run evidence.
- This branch adds a GitHub Actions workflow to run `pytest` on pull requests and pushes. Check the pull-request result before merging.
- **Demo benchmarks are synthetic, not real measurements.** `generate_demo_benchmark()` uses a fixed channel-congestion map and seeded pseudo-random values. The throughput, latency, jitter, packet-loss, and retransmission values shown by demo mode illustrate the algorithm; they do not prove that changing a physical channel improved a real network.
- Generated charts and JSON reports are local outputs. The current `.gitignore` excludes generated PNG/PDF files and most files under `data/` and `reports/`; only placeholder files are tracked unless generated artifacts are deliberately added.

## 3. Live Deployment Requirements

- Use a Linux system with compatible wireless tools and a Wi-Fi interface that can perform the requested scan.
- Throughput tests need a reachable `iperf3` server. Start it on the target machine with `iperf3 -s` and set `iperf_server` in `config.json` to its address. The default `192.168.1.1` is not guaranteed to have an iperf3 server.
- Channel switching requires a compatible local AP/monitor interface or a valid `hostapd` software-AP setup. The application does not remotely configure a typical external home router.
- The real-hardware scan, channel-switch, and before/after benchmark path has **not** been verified by this repository audit.

## 4. Remaining Work

1. Confirm the new GitHub Actions test workflow passes before merging this branch.
2. Run and document a live scan on the intended lab hardware.
3. Perform before/after measurements against a reachable test server under reasonably consistent conditions; keep actual measurements separate from demo output.
4. Prepare the final mini-project report and presentation with clearly labelled measured results and simulated examples.

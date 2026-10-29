# WiFi Channel Optimizer — Project Status & Roadmap

**Repository:** https://github.com/advaiTtTtTt/WT-MiniProject  
**Review branch:** `audit/docs-and-ci`  
**Last reviewed:** October 29, 2026  
**Status:** Core CLI, analysis, benchmark, comparison, and channel-switching code is implemented. Regression tests and CI have been added. Real hardware validation remains pending.  
**Original workspace:** `/storage/emulated/10/Documents/.gemini/antigravity/scratch/wifi-channel-optimizer`

---

## 1. Implementation

- **`main.py`:** CLI workflow for `scan`, `analyze`, `benchmark`, and `compare`, plus a `--demo` end-to-end path.
- **`src/utils.py`:** Channel/frequency mapping for selected 2.4 GHz and 5 GHz channels, spectral-overlap heuristic, RSSI-to-quality heuristic, subprocess helpers, configuration and JSON persistence.
- **`src/scanner.py`:** Parsers for `iw` and `iwlist` output, multi-pass scan aggregation, terminal tables, and synthetic scan data. Encrypted networks reported through the `Privacy` capability flag are no longer mislabelled as open.
- **`src/analyzer.py`:** Channel congestion/interference scores, recommendations, channel congestion chart, and signal heatmap.
- **`src/channel_switcher.py`:** Direct switching is restricted to AP/monitor interfaces; automatic mode refuses to change the upstream router through a managed/client interface. Hostapd config updates validate channels, keep `hw_mode` aligned with 2.4/5 GHz, write atomically, and restore the original config when restarts fail.
- **`src/benchmark.py`:** `iperf3` throughput/retransmission collection, ping latency/jitter/loss parsing, explicit error reporting for failed tools or invalid output, and clearly labelled synthetic demo results. The demo generator no longer mutates Python's process-wide random state.
- **`src/comparator.py`:** Before/after deltas and comparison charts. Incomplete or mixed-source results are rejected, and percentage changes from zero baselines are JSON-safe.
- **Tests:** Scanner, analyzer, benchmark/comparator, and channel-switcher regression tests.

## 2. Automated Verification

- The new suite contains **72 pytest tests**:
  - `tests/test_scanner.py`: 25
  - `tests/test_analyzer.py`: 19
  - `tests/test_benchmark.py`: 21
  - `tests/test_channel_switcher.py`: 7
- GitHub Actions completed successfully on Python 3.10 and 3.12 for commit `44d2ef4`: **72 passed in 0.19s**.
- A full CLI demo smoke-test step (`python main.py --demo`) has been added to the workflow; its latest run must be green before the pull request is ready to merge.
- The default `main` branch has not been changed by this audit. The changes are on `audit/docs-and-ci` in Pull Request #1.

## 3. Important Limitations

- **Demo benchmarks are synthetic, not real measurements.** `generate_demo_benchmark()` uses a fixed channel-congestion map and seeded pseudo-random values. Demo output illustrates the algorithm; it does not prove that changing a physical channel improved a real network.
- Generated charts and JSON reports are local outputs. The current `.gitignore` excludes generated PNG/PDF files and most files under `data/` and `reports/`; only placeholders are tracked unless outputs are deliberately added.
- Live scanning, channel switching, and real before/after performance gains have **not** been verified on physical hardware by this audit.

## 4. Requirements for Live Demonstration

1. Use Linux with compatible wireless tools and a Wi-Fi interface that can scan.
2. For throughput tests, start a server on a reachable target with `iperf3 -s` and set `iperf_server` in `config.json` to that host's address. The default `192.168.1.1` works only if an iperf3 server is actually running there.
3. Channel switching requires an AP/monitor interface or an explicitly configured hostapd software AP. The software cannot remotely change the channel of a typical external home router.
4. Run before/after tests under consistent conditions and report only measured results as real-world improvements.

## 5. Remaining Work

1. Confirm the latest CI run, including the complete demo smoke test, passes.
2. Conduct a live test on the intended lab hardware and document the interface mode and any regulatory/channel limitations.
3. Prepare the mini-project report and presentation with measured results clearly separated from synthetic examples.
4. Optionally develop a web dashboard after the live path is validated.

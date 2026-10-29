"""
WiFi Network Scanner Module

Scans nearby WiFi networks using Linux wireless tools (iw/iwlist).
Extracts SSID, BSSID, channel, frequency, signal strength, and security info.
"""

import re
import statistics
from dataclasses import dataclass, field, asdict

from .utils import (
    freq_to_channel,
    run_shell_command,
    check_root,
    load_config,
    save_json,
    load_json,
    dbm_to_quality,
    get_band,
    timestamp,
)


@dataclass
class NetworkInfo:
    """Represents a scanned WiFi network."""
    ssid: str = ""
    bssid: str = ""
    frequency: int = 0       # MHz
    channel: int = 0
    signal_dbm: int = -100   # dBm
    signal_quality: int = 0  # 0-100%
    security: str = "Open"
    channel_width: int = 20  # MHz (20, 40, 80, 160)
    band: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "NetworkInfo":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def _parse_iw_scan(output: str) -> list[NetworkInfo]:
    """
    Parse output from 'iw dev <iface> scan' command.

    The output is structured as blocks separated by 'BSS' lines.
    """
    networks = []
    current = None

    for line in output.splitlines():
        line = line.strip()

        # New BSS block
        bss_match = re.match(r"BSS\s+([0-9a-f:]{17})", line, re.IGNORECASE)
        if bss_match:
            if current:
                networks.append(current)
            current = NetworkInfo(bssid=bss_match.group(1).upper())
            continue

        if current is None:
            continue

        # SSID
        ssid_match = re.match(r"SSID:\s*(.*)", line)
        if ssid_match:
            current.ssid = ssid_match.group(1).strip()
            if not current.ssid:
                current.ssid = "<Hidden>"
            continue

        # Frequency
        freq_match = re.match(r"freq:\s*(\d+)", line)
        if freq_match:
            current.frequency = int(freq_match.group(1))
            ch = freq_to_channel(current.frequency)
            if ch:
                current.channel = ch
                current.band = get_band(ch)
            continue

        # Signal strength
        signal_match = re.match(r"signal:\s*(-?\d+\.?\d*)\s*dBm", line)
        if signal_match:
            current.signal_dbm = int(float(signal_match.group(1)))
            current.signal_quality = dbm_to_quality(current.signal_dbm)
            continue

        # Channel width (from HT/VHT capabilities)
        if "channel width:" in line.lower():
            width_match = re.search(r"(\d+)\s*MHz", line)
            if width_match:
                current.channel_width = int(width_match.group(1))
            continue

        # Security detection
        if "RSN:" in line or "WPA:" in line:
            current.security = "WPA2/WPA3"
        elif "WEP" in line:
            current.security = "WEP"
        elif "privacy" in line.lower():
            # The capability flag is reported as "Privacy" by iw. Compare
            # case-insensitively so encrypted networks are not presented as open.
            if current.security == "Open":
                current.security = "Encrypted"

    # Don't forget the last network
    if current:
        networks.append(current)

    return networks


def _parse_iwlist_scan(output: str) -> list[NetworkInfo]:
    """
    Parse output from 'iwlist <iface> scan' command.
    Fallback parser for systems without 'iw'.
    """
    networks = []
    current = None

    for line in output.splitlines():
        line = line.strip()

        # New cell
        cell_match = re.match(
            r"Cell\s+\d+\s+-\s+Address:\s*([0-9A-Fa-f:]{17})", line
        )
        if cell_match:
            if current:
                networks.append(current)
            current = NetworkInfo(bssid=cell_match.group(1).upper())
            continue

        if current is None:
            continue

        # Channel
        ch_match = re.match(r"Channel:(\d+)", line)
        if ch_match:
            current.channel = int(ch_match.group(1))
            current.band = get_band(current.channel)
            continue

        # Frequency
        freq_match = re.match(r"Frequency:(\d+\.?\d*)\s*GHz", line)
        if freq_match:
            current.frequency = int(float(freq_match.group(1)) * 1000)
            continue

        # Quality and signal
        quality_match = re.search(
            r"Quality[=:](\d+)/(\d+)\s+Signal level[=:](-?\d+)\s*dBm", line
        )
        if quality_match:
            current.signal_quality = int(
                100 * int(quality_match.group(1)) / int(quality_match.group(2))
            )
            current.signal_dbm = int(quality_match.group(3))
            continue

        # ESSID
        essid_match = re.match(r'ESSID:"(.*)"', line)
        if essid_match:
            current.ssid = essid_match.group(1)
            if not current.ssid:
                current.ssid = "<Hidden>"
            continue

        # Encryption
        enc_match = re.match(r"Encryption key:(on|off)", line)
        if enc_match:
            if enc_match.group(1) == "off":
                current.security = "Open"
            continue

        # WPA
        if "WPA" in line.upper():
            current.security = "WPA2/WPA3"

    if current:
        networks.append(current)

    return networks


def scan_networks(interface: str = "wlan0", scan_count: int = 3) -> list[NetworkInfo]:
    """
    Scan for nearby WiFi networks using iw or iwlist.

    Performs multiple scans and merges results for better coverage.
    Uses the strongest signal seen for each BSSID.

    Args:
        interface: WiFi interface name (e.g., 'wlan0')
        scan_count: Number of scans to perform for better coverage

    Returns:
        List of NetworkInfo objects for all discovered networks
    """
    if not isinstance(interface, str) or not interface.strip():
        raise ValueError("interface must be a non-empty interface name")
    if isinstance(scan_count, bool) or not isinstance(scan_count, int) or scan_count < 1:
        raise ValueError("scan_count must be a positive integer")

    all_networks: dict[str, NetworkInfo] = {}

    for i in range(scan_count):
        print(f"  [*] Scan {i + 1}/{scan_count}...")

        # Try 'iw' first (modern)
        stdout, stderr, rc = run_shell_command(
            ["iw", "dev", interface, "scan"], timeout=15
        )
        if rc == 0 and stdout.strip():
            networks = _parse_iw_scan(stdout)
        else:
            # Fallback to 'iwlist'
            stdout, stderr, rc = run_shell_command(
                ["iwlist", interface, "scan"], timeout=15
            )
            if rc == 0 and stdout.strip():
                networks = _parse_iwlist_scan(stdout)
            else:
                print(f"  [!] Scan {i + 1} failed: {stderr.strip()}")
                continue

        # Merge — keep the strongest signal for each BSSID
        for net in networks:
            if net.bssid in all_networks:
                if net.signal_dbm > all_networks[net.bssid].signal_dbm:
                    all_networks[net.bssid] = net
            else:
                all_networks[net.bssid] = net

    result = sorted(all_networks.values(), key=lambda n: n.signal_dbm, reverse=True)
    print(f"  [+] Found {len(result)} unique networks")
    return result


def generate_demo_scan_data() -> list[NetworkInfo]:
    """
    Generate realistic demo scan data for testing without a WiFi adapter.
    Simulates a crowded apartment environment.
    """
    import random
    random.seed(42)

    demo_networks = [
        # Channel 1 — very crowded
        NetworkInfo("HomeNet-5G", "AA:BB:CC:11:22:33", 2412, 1, -35, 0, "WPA2/WPA3", 20, "2.4GHz"),
        NetworkInfo("Neighbor_WiFi", "AA:BB:CC:11:22:34", 2412, 1, -55, 0, "WPA2/WPA3", 20, "2.4GHz"),
        NetworkInfo("CoffeeShop", "AA:BB:CC:11:22:35", 2412, 1, -65, 0, "WPA2/WPA3", 20, "2.4GHz"),
        NetworkInfo("IoT-Device-1", "AA:BB:CC:11:22:36", 2412, 1, -72, 0, "WPA2/WPA3", 20, "2.4GHz"),
        NetworkInfo("SmartTV", "AA:BB:CC:11:22:37", 2412, 1, -78, 0, "Open", 20, "2.4GHz"),
        # Channel 2 (overlaps with 1) — some
        NetworkInfo("Guest_Net", "AA:BB:CC:22:22:33", 2417, 2, -60, 0, "WPA2/WPA3", 20, "2.4GHz"),
        # Channel 3 (overlaps with 1 and 6)
        NetworkInfo("OldRouter", "AA:BB:CC:33:22:33", 2422, 3, -70, 0, "WEP", 20, "2.4GHz"),
        # Channel 6 — crowded
        NetworkInfo("Apt-6B", "AA:BB:CC:66:22:33", 2437, 6, -42, 0, "WPA2/WPA3", 40, "2.4GHz"),
        NetworkInfo("Printer_WiFi", "AA:BB:CC:66:22:34", 2437, 6, -58, 0, "WPA2/WPA3", 20, "2.4GHz"),
        NetworkInfo("MyRouter", "AA:BB:CC:66:22:35", 2437, 6, -50, 0, "WPA2/WPA3", 20, "2.4GHz"),
        NetworkInfo("FreeWiFi", "AA:BB:CC:66:22:36", 2437, 6, -80, 0, "Open", 20, "2.4GHz"),
        # Channel 7 (overlaps with 6)
        NetworkInfo("SecureNet", "AA:BB:CC:77:22:33", 2442, 7, -68, 0, "WPA2/WPA3", 20, "2.4GHz"),
        # Channel 9
        NetworkInfo("LabWiFi", "AA:BB:CC:99:22:33", 2452, 9, -75, 0, "WPA2/WPA3", 20, "2.4GHz"),
        # Channel 11 — least crowded
        NetworkInfo("Ch11_Net", "AA:BB:CC:BB:22:33", 2462, 11, -62, 0, "WPA2/WPA3", 20, "2.4GHz"),
        # 5 GHz networks
        NetworkInfo("HomeNet-5G-AC", "AA:BB:CC:55:22:33", 5180, 36, -45, 0, "WPA2/WPA3", 80, "5GHz"),
        NetworkInfo("Office5G", "AA:BB:CC:55:22:34", 5240, 48, -55, 0, "WPA2/WPA3", 80, "5GHz"),
    ]

    # Update signal quality
    for net in demo_networks:
        net.signal_quality = dbm_to_quality(net.signal_dbm)

    return demo_networks


def print_scan_results(networks: list[NetworkInfo]):
    """Print a formatted table of scan results."""
    try:
        from tabulate import tabulate
    except ImportError:
        # Fallback if tabulate not installed
        print(f"\n{'SSID':<25} {'BSSID':<20} {'Ch':>3} {'Band':<6} {'Signal':>7} {'Quality':>8} {'Security':<12}")
        print("-" * 90)
        for net in networks:
            print(
                f"{net.ssid:<25} {net.bssid:<20} {net.channel:>3} {net.band:<6} "
                f"{net.signal_dbm:>5} dBm {net.signal_quality:>5}% {net.security:<12}"
            )
        return

    table_data = []
    for net in networks:
        signal_bar = _signal_bar(net.signal_quality)
        table_data.append([
            net.ssid[:24],
            net.bssid,
            net.channel,
            net.band,
            f"{net.signal_dbm} dBm",
            f"{net.signal_quality}%",
            signal_bar,
            net.security,
            f"{net.channel_width} MHz",
        ])

    headers = ["SSID", "BSSID", "Ch", "Band", "Signal", "Quality", "Strength", "Security", "Width"]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))


def _signal_bar(quality: int) -> str:
    """Generate a visual signal strength bar."""
    filled = quality // 10
    empty = 10 - filled
    if quality >= 70:
        return "█" * filled + "░" * empty + " 🟢"
    elif quality >= 40:
        return "█" * filled + "░" * empty + " 🟡"
    else:
        return "█" * filled + "░" * empty + " 🔴"


# Allow running as module: python3 -m src.scanner
if __name__ == "__main__":
    import sys

    config = load_config()
    use_demo = "--demo" in sys.argv

    print("\n📡 WiFi Network Scanner")
    print("=" * 50)

    if use_demo:
        print("[*] Using demo data (no WiFi adapter needed)\n")
        networks = generate_demo_scan_data()
    else:
        check_root()
        print(f"[*] Scanning on interface: {config['interface']}")
        print(f"[*] Performing {config['scan_count']} scans...\n")
        networks = scan_networks(config["interface"], config["scan_count"])

    if not networks:
        print("[!] No networks found.")
        sys.exit(1)

    print_scan_results(networks)

    # Save scan data
    scan_data = {
        "timestamp": timestamp(),
        "interface": config["interface"],
        "networks": [n.to_dict() for n in networks],
    }
    path = save_json(scan_data, "last_scan.json")
    print(f"\n[+] Scan data saved to {path}")

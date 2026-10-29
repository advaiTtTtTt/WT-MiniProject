"""
Shared utility functions for the WiFi Channel Optimizer.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Project directories
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"
CONFIG_FILE = PROJECT_ROOT / "config.json"

# 2.4 GHz channel center frequencies (MHz)
CHANNEL_FREQ_24GHZ = {
    1: 2412, 2: 2417, 3: 2422, 4: 2427, 5: 2432,
    6: 2437, 7: 2442, 8: 2447, 9: 2452, 10: 2457,
    11: 2462, 12: 2467, 13: 2472,
}

# 5 GHz channel center frequencies (MHz) — common ones
CHANNEL_FREQ_5GHZ = {
    36: 5180, 40: 5200, 44: 5220, 48: 5240,
    52: 5260, 56: 5280, 60: 5300, 64: 5320,
    100: 5500, 104: 5520, 108: 5540, 112: 5560,
    116: 5580, 120: 5600, 124: 5620, 128: 5640,
    132: 5660, 136: 5680, 140: 5700, 144: 5720,
    149: 5745, 153: 5765, 157: 5785, 161: 5805, 165: 5825,
}

# Non-overlapping channels for 2.4 GHz
NON_OVERLAPPING_24GHZ = [1, 6, 11]

# All channels combined
ALL_CHANNELS = {**CHANNEL_FREQ_24GHZ, **CHANNEL_FREQ_5GHZ}


def freq_to_channel(freq_mhz: int) -> int | None:
    """Convert a frequency in MHz to a WiFi channel number."""
    for channel, freq in ALL_CHANNELS.items():
        if freq == freq_mhz:
            return channel
    return None


def channel_to_freq(channel: int) -> int | None:
    """Convert a WiFi channel number to frequency in MHz."""
    return ALL_CHANNELS.get(channel)


def is_24ghz(channel: int) -> bool:
    """Check if a channel is in the 2.4 GHz band."""
    return channel in CHANNEL_FREQ_24GHZ


def is_5ghz(channel: int) -> bool:
    """Check if a channel is in the 5 GHz band."""
    return channel in CHANNEL_FREQ_5GHZ


def get_band(channel: int) -> str:
    """Return the band string for a given channel."""
    if is_24ghz(channel):
        return "2.4GHz"
    elif is_5ghz(channel):
        return "5GHz"
    return "Unknown"


def dbm_to_quality(dbm: int) -> int:
    """
    Convert signal strength in dBm to quality percentage (0-100).
    Based on common heuristic: quality = 2 * (dBm + 100), clamped to [0, 100].
    """
    quality = 2 * (dbm + 100)
    return max(0, min(100, quality))


def channel_overlap_score(ch1: int, ch2: int) -> float:
    """
    Calculate the overlap between two 2.4GHz channels.
    Each channel is 22 MHz wide, spaced 5 MHz apart.
    Returns a value from 0.0 (no overlap) to 1.0 (same channel).
    Only applies to 2.4 GHz channels; 5 GHz channels don't overlap.
    """
    if is_5ghz(ch1) or is_5ghz(ch2):
        return 1.0 if ch1 == ch2 else 0.0

    if not (is_24ghz(ch1) and is_24ghz(ch2)):
        return 0.0

    freq1 = CHANNEL_FREQ_24GHZ[ch1]
    freq2 = CHANNEL_FREQ_24GHZ[ch2]
    separation = abs(freq1 - freq2)

    # Each channel is 22 MHz wide, so two channels overlap if
    # their center frequencies are less than 22 MHz apart
    channel_width = 22  # MHz
    if separation >= channel_width:
        return 0.0

    return 1.0 - (separation / channel_width)


def run_shell_command(cmd: list[str], timeout: int = 30) -> tuple[str, str, int]:
    """
    Run a shell command and return (stdout, stderr, returncode).
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", f"Command timed out after {timeout}s", -1
    except FileNotFoundError:
        return "", f"Command not found: {cmd[0]}", -1


def load_config() -> dict:
    """Load configuration from config.json, or create default if missing."""
    default_config = {
        "interface": "wlan0",
        "iperf_server": "192.168.1.1",
        "iperf_duration": 10,
        "iperf_parallel": 4,
        "band": "2.4GHz",
        "scan_count": 3,
    }

    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                config = json.load(f)
            # Merge with defaults for any missing keys
            for key, value in default_config.items():
                config.setdefault(key, value)
            return config
        except (json.JSONDecodeError, IOError):
            print(f"[!] Warning: Could not parse {CONFIG_FILE}, using defaults.")

    # Create default config file
    with open(CONFIG_FILE, "w") as f:
        json.dump(default_config, f, indent=2)
    print(f"[+] Created default config at {CONFIG_FILE}")

    return default_config


def save_json(data: dict | list, filename: str, directory: Path = DATA_DIR) -> Path:
    """Save data as JSON to the data directory."""
    directory.mkdir(parents=True, exist_ok=True)
    filepath = directory / filename
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)
    return filepath


def load_json(filename: str, directory: Path = DATA_DIR) -> dict | list | None:
    """Load JSON data from the data directory."""
    filepath = directory / filename
    if not filepath.exists():
        return None
    try:
        with open(filepath) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def timestamp() -> str:
    """Return a formatted timestamp string."""
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def check_root():
    """Check if the script is running with root privileges."""
    if os.geteuid() != 0:
        print("[!] This operation requires root privileges.")
        print("    Please run with: sudo python3 main.py")
        sys.exit(1)


def check_tool_installed(tool_name: str) -> bool:
    """Check if a command-line tool is installed."""
    stdout, stderr, rc = run_shell_command(["which", tool_name])
    return rc == 0


def print_banner():
    """Print the application banner."""
    banner = """
╔══════════════════════════════════════════════════════╗
║           📡 WiFi Channel Optimizer v1.0             ║
║     Scan · Analyze · Switch · Compare · Optimize     ║
╚══════════════════════════════════════════════════════╝
    """
    print(banner)

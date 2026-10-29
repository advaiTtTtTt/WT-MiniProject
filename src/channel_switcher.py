"""
WiFi Channel Switcher Module

Changes the WiFi channel of the local access point using iw or hostapd.
Supports both direct channel switching (for devices in AP mode) and
hostapd configuration updates.
"""

import os
import re
import time
from pathlib import Path

from .utils import (
    run_shell_command,
    check_root,
    load_config,
    is_24ghz,
    is_5ghz,
    channel_to_freq,
    get_band,
)



def _get_interface_type(interface: str) -> str | None:
    """Return interface mode reported by iw (managed, AP, monitor, etc.)."""
    stdout, _, rc = run_shell_command(["iw", "dev", interface, "info"])
    if rc != 0:
        return None
    match = re.search(r"^\s*type\s+(\S+)", stdout, re.IGNORECASE | re.MULTILINE)
    return match.group(1).lower() if match else None


def _atomic_write(path: Path, content: str) -> None:
    """Atomically replace a config file while preserving its permission bits."""
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        mode = path.stat().st_mode & 0o777
        with open(temp_path, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass

def get_current_channel(interface: str = "wlan0") -> int | None:
    """
    Get the current operating channel of a WiFi interface.

    Returns the channel number or None if it cannot be determined.
    """
    # Try 'iw' first
    stdout, stderr, rc = run_shell_command(["iw", "dev", interface, "info"])
    if rc == 0:
        match = re.search(r"channel\s+(\d+)", stdout)
        if match:
            return int(match.group(1))

    # Fallback to 'iwconfig'
    stdout, stderr, rc = run_shell_command(["iwconfig", interface])
    if rc == 0:
        match = re.search(r"Channel[=:](\d+)", stdout)
        if match:
            return int(match.group(1))

        # Try frequency
        match = re.search(r"Frequency[=:](\d+\.?\d*)\s*GHz", stdout)
        if match:
            from .utils import freq_to_channel
            freq_mhz = int(float(match.group(1)) * 1000)
            return freq_to_channel(freq_mhz)

    return None


def switch_channel_iw(interface: str, channel: int) -> tuple[bool, str]:
    """Switch a compatible AP/monitor interface using iw."""
    freq = channel_to_freq(channel)
    if freq is None:
        return False, f"Invalid channel number: {channel}"
    if not isinstance(interface, str) or not interface.strip():
        return False, "A non-empty Wi-Fi interface name is required."

    interface_type = _get_interface_type(interface)
    if interface_type not in {"ap", "monitor"}:
        mode = interface_type or "unknown"
        return False, (
            f"Refusing direct channel switch on {interface!r}: interface mode is {mode!r}. "
            "Direct iw switching is limited to AP or monitor interfaces; it cannot "
            "change the channel of an upstream home router."
        )

    print(f"  [*] Switching {interface} to channel {channel} ({freq} MHz)...")
    stdout, stderr, rc = run_shell_command(
        ["iw", "dev", interface, "set", "channel", str(channel)]
    )
    if rc == 0:
        return True, f"Successfully switched to channel {channel}"

    stdout, stderr, rc = run_shell_command(
        ["iw", "dev", interface, "set", "freq", str(freq)]
    )
    if rc == 0:
        return True, f"Successfully switched to channel {channel} ({freq} MHz)"

    return False, f"Failed to switch channel: {stderr.strip() or stdout.strip() or 'iw command failed'}"

def switch_channel_hostapd(channel: int, config_path: str = "/etc/hostapd/hostapd.conf") -> tuple[bool, str]:
    """Update a hostapd config and restart the service, rolling back on failure."""
    if channel_to_freq(channel) is None:
        return False, f"Invalid channel number: {channel}"

    config_file = Path(config_path)
    try:
        original_text = config_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False, f"hostapd config not found at {config_path}"
    except PermissionError:
        return False, f"Permission denied reading {config_path}"
    except OSError as exc:
        return False, f"Could not read {config_path}: {exc}"

    # Replace one active channel directive and remove duplicates. Preserve
    # comments and every other hostapd setting.
    new_lines = []
    channel_written = False
    for line in original_text.splitlines(keepends=True):
        if re.match(r"^\s*channel\s*=", line) and not channel_written:
            new_lines.append(f"channel={channel}\n")
            channel_written = True
        elif re.match(r"^\s*channel\s*=", line):
            continue
        else:
            new_lines.append(line)
    if not channel_written:
        if new_lines and not new_lines[-1].endswith(("\n", "\r")):
            new_lines[-1] += "\n"
        new_lines.append(f"channel={channel}\n")
    updated_text = "".join(new_lines)

    try:
        _atomic_write(config_file, updated_text)
    except OSError as exc:
        return False, f"Could not update {config_path}: {exc}"

    print(f"  [*] Updated {config_path} with channel={channel}")
    print("  [*] Restarting hostapd...")
    _, stderr, rc = run_shell_command(
        ["systemctl", "restart", "hostapd"], timeout=10
    )
    if rc != 0:
        _, stderr, rc = run_shell_command(
            ["service", "hostapd", "restart"], timeout=10
        )
    if rc == 0:
        time.sleep(2)
        return True, f"Successfully switched hostapd to channel {channel}"

    restart_error = stderr.strip() or "restart command failed"
    try:
        _atomic_write(config_file, original_text)
    except OSError as exc:
        return False, (
            f"Failed to restart hostapd ({restart_error}) and failed to restore "
            f"the original configuration ({exc}). Inspect {config_path} immediately."
        )

    # Best-effort restart with the original configuration.
    _, _, rollback_rc = run_shell_command(
        ["systemctl", "restart", "hostapd"], timeout=10
    )
    if rollback_rc != 0:
        _, _, rollback_rc = run_shell_command(
            ["service", "hostapd", "restart"], timeout=10
        )
    if rollback_rc == 0:
        return False, f"Failed to switch channel ({restart_error}); original config restored."
    return False, (
        f"Failed to switch channel ({restart_error}); original config restored, "
        "but restarting hostapd with the original config also failed. Check service status."
    )

def switch_channel(
    interface: str = "wlan0",
    channel: int = 1,
    method: str = "auto",
) -> tuple[bool, str]:
    """
    Switch WiFi channel using the best available method.

    Args:
        interface: WiFi interface name
        channel: Target channel number
        method: "auto", "iw", or "hostapd"

    Returns:
        (success: bool, message: str)
    """
    band = get_band(channel)
    print(f"\n🔄 Channel Switch")
    print(f"   Interface: {interface}")
    print(f"   Target: Channel {channel} ({band})")

    # Validate channel
    if not is_24ghz(channel) and not is_5ghz(channel):
        return False, f"Invalid channel: {channel}"

    # Get current channel for comparison
    current = get_current_channel(interface)
    if current:
        print(f"   Current: Channel {current}")
        if current == channel:
            return True, f"Already on channel {channel}"

    if method not in {"auto", "iw", "hostapd"}:
        return False, f"Invalid switching method: {method!r}. Use 'auto', 'iw', or 'hostapd'."

    if method == "hostapd":
        return switch_channel_hostapd(channel)
    if method == "iw":
        return switch_channel_iw(interface, channel)

    # Auto mode must not treat a normal Wi-Fi client interface as an AP. A
    # failed attempt on wlan0 must not restart an unrelated hostapd service.
    interface_type = _get_interface_type(interface)
    if interface_type not in {"ap", "monitor"}:
        mode = interface_type or "unknown"
        return False, (
            f"Refusing automatic channel switch: {interface!r} is in {mode!r} mode. "
            "A managed/client interface cannot change the upstream router's channel. "
            "Use a local AP/monitor interface, or explicitly select method='hostapd' "
            "for a hostapd access point you administer."
        )

    success, msg = switch_channel_iw(interface, channel)
    if success:
        return success, msg
    if interface_type == "ap":
        print("  [*] Direct iw method failed on an AP interface; trying hostapd...")
        return switch_channel_hostapd(channel)
    return False, msg


def simulate_switch(current_channel: int, target_channel: int) -> dict:
    """
    Simulate a channel switch for demo/testing purposes.
    Returns a simulated result dictionary.
    """
    print(f"\n🔄 [SIMULATED] Channel Switch")
    print(f"   Current: Channel {current_channel} ({get_band(current_channel)})")
    print(f"   Target:  Channel {target_channel} ({get_band(target_channel)})")
    print(f"   Status:  ✅ Simulated switch successful")

    return {
        "success": True,
        "previous_channel": current_channel,
        "new_channel": target_channel,
        "method": "simulated",
        "message": f"Simulated switch from channel {current_channel} to {target_channel}",
    }


# Allow running as module: python3 -m src.channel_switcher
if __name__ == "__main__":
    import sys

    config = load_config()

    print("\n🔄 WiFi Channel Switcher")
    print("=" * 50)

    if "--simulate" in sys.argv:
        simulate_switch(6, 11)
    else:
        check_root()

        if len(sys.argv) < 2:
            print("Usage: python3 -m src.channel_switcher <channel> [--method iw|hostapd]")
            print("       python3 -m src.channel_switcher --simulate")
            sys.exit(1)

        target = int(sys.argv[1])
        method = "auto"
        if "--method" in sys.argv:
            idx = sys.argv.index("--method")
            if idx + 1 < len(sys.argv):
                method = sys.argv[idx + 1]

        success, msg = switch_channel(config["interface"], target, method)
        print(f"\n  {'✅' if success else '❌'} {msg}")

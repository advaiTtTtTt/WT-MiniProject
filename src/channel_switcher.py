"""
WiFi Channel Switcher Module

Changes the WiFi channel of the local access point using iw or hostapd.
Supports both direct channel switching (for devices in AP mode) and
hostapd configuration updates.
"""

import re
import time

from .utils import (
    run_shell_command,
    check_root,
    load_config,
    is_24ghz,
    is_5ghz,
    channel_to_freq,
    get_band,
)


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
    """
    Switch WiFi channel using the 'iw' command.

    This works when the device is in AP/Monitor mode.

    Args:
        interface: WiFi interface name
        channel: Target channel number

    Returns:
        (success: bool, message: str)
    """
    freq = channel_to_freq(channel)
    if freq is None:
        return False, f"Invalid channel number: {channel}"

    print(f"  [*] Switching {interface} to channel {channel} ({freq} MHz)...")

    # Method 1: Direct channel set via iw
    stdout, stderr, rc = run_shell_command(
        ["iw", "dev", interface, "set", "channel", str(channel)]
    )
    if rc == 0:
        return True, f"Successfully switched to channel {channel}"

    # Method 2: Set via frequency
    stdout, stderr, rc = run_shell_command(
        ["iw", "dev", interface, "set", "freq", str(freq)]
    )
    if rc == 0:
        return True, f"Successfully switched to channel {channel} ({freq} MHz)"

    return False, f"Failed to switch channel: {stderr.strip()}"


def switch_channel_hostapd(channel: int, config_path: str = "/etc/hostapd/hostapd.conf") -> tuple[bool, str]:
    """
    Switch WiFi channel by modifying hostapd configuration and restarting.

    This is the recommended method when running as a software access point.

    Args:
        channel: Target channel number
        config_path: Path to hostapd.conf

    Returns:
        (success: bool, message: str)
    """
    try:
        with open(config_path) as f:
            config_lines = f.readlines()
    except FileNotFoundError:
        return False, f"hostapd config not found at {config_path}"
    except PermissionError:
        return False, f"Permission denied reading {config_path}"

    # Update the channel line
    new_lines = []
    channel_found = False
    for line in config_lines:
        if line.strip().startswith("channel="):
            new_lines.append(f"channel={channel}\n")
            channel_found = True
        else:
            new_lines.append(line)

    if not channel_found:
        new_lines.append(f"channel={channel}\n")

    # Write updated config
    try:
        with open(config_path, "w") as f:
            f.writelines(new_lines)
    except PermissionError:
        return False, f"Permission denied writing to {config_path}"

    print(f"  [*] Updated {config_path} with channel={channel}")

    # Restart hostapd
    print("  [*] Restarting hostapd...")
    stdout, stderr, rc = run_shell_command(
        ["systemctl", "restart", "hostapd"], timeout=10
    )

    if rc == 0:
        time.sleep(2)  # Wait for AP to come back up
        return True, f"Successfully switched hostapd to channel {channel}"

    # Try direct restart
    stdout, stderr, rc = run_shell_command(
        ["service", "hostapd", "restart"], timeout=10
    )
    if rc == 0:
        time.sleep(2)
        return True, f"Successfully switched hostapd to channel {channel}"

    return False, f"Failed to restart hostapd: {stderr.strip()}"


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

    if method == "hostapd":
        return switch_channel_hostapd(channel)
    elif method == "iw":
        return switch_channel_iw(interface, channel)
    else:
        # Auto: try iw first, then hostapd
        success, msg = switch_channel_iw(interface, channel)
        if success:
            return success, msg

        print("  [*] iw method failed, trying hostapd...")
        return switch_channel_hostapd(channel)


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

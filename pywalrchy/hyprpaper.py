from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from pywalrchy.config import HYPRPAPER_CONF
from pywalrchy.theme import Theme


def apply_wallpapers(theme: Theme) -> None:
    if not theme.monitor_wallpapers:
        return

    # Write config so a fresh hyprpaper start picks it up correctly
    lines: list[str] = []
    for mw in theme.monitor_wallpapers:
        lines.append(f"preload = {mw.path}")
    lines.append("")
    for mw in theme.monitor_wallpapers:
        lines.append(f"wallpaper = {mw.monitor},{mw.path}")
    lines.append("")
    HYPRPAPER_CONF.write_text("\n".join(lines))

    running = subprocess.run(["pgrep", "-x", "hyprpaper"], capture_output=True).returncode == 0

    if running:
        # Preload ALL wallpapers first, then wait, then set — avoids the race
        # condition where wallpaper is set before hyprpaper finishes preloading it.
        for mw in theme.monitor_wallpapers:
            subprocess.run(
                ["hyprctl", "hyprpaper", "preload", str(mw.path)],
                capture_output=True,
            )
        time.sleep(0.4)
        for mw in theme.monitor_wallpapers:
            subprocess.run(
                ["hyprctl", "hyprpaper", "wallpaper", f"{mw.monitor},{mw.path}"],
                capture_output=True,
            )
    else:
        # Not running — just start it; it reads the conf on startup
        subprocess.Popen(["hyprpaper"])


def get_monitors() -> list[str]:
    result = subprocess.run(
        ["hyprctl", "monitors", "-j"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    monitors = json.loads(result.stdout)
    return [m["name"] for m in monitors]

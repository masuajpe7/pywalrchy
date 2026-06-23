from __future__ import annotations

import subprocess
from pathlib import Path

from pywalrchy.config import HYPRPAPER_CONF
from pywalrchy.theme import Theme


def apply_wallpapers(theme: Theme) -> None:
    if not theme.monitor_wallpapers:
        return

    lines: list[str] = []
    for mw in theme.monitor_wallpapers:
        lines.append(f"preload = {mw.path}")
    lines.append("")
    for mw in theme.monitor_wallpapers:
        lines.append(f"wallpaper = {mw.monitor},{mw.path}")
    lines.append("")

    HYPRPAPER_CONF.write_text("\n".join(lines))

    # Apply live without full restart when hyprpaper is running
    result = subprocess.run(["pgrep", "-x", "hyprpaper"], capture_output=True)
    if result.returncode == 0:
        for mw in theme.monitor_wallpapers:
            subprocess.run(
                ["hyprctl", "hyprpaper", "preload", str(mw.path)],
                capture_output=True,
            )
            subprocess.run(
                ["hyprctl", "hyprpaper", "wallpaper",
                 f"{mw.monitor},{mw.path}"],
                capture_output=True,
            )
    else:
        subprocess.Popen(["hyprpaper"])


def get_monitors() -> list[str]:
    result = subprocess.run(
        ["hyprctl", "monitors", "-j"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    import json
    monitors = json.loads(result.stdout)
    return [m["name"] for m in monitors]

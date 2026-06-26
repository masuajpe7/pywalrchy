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

    # Themes without a pywalrchy.toml get monitor="unassigned" as a fallback
    # from the backgrounds/ scanner. hyprpaper ignores those entries, so detect
    # that case and apply the first background to every real monitor instead.
    assigned = [mw for mw in theme.monitor_wallpapers if mw.monitor != "unassigned"]

    if not assigned:
        result = subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True, text=True)
        if result.returncode != 0:
            return
        monitors = [m["name"] for m in json.loads(result.stdout)]
        first = str(theme.monitor_wallpapers[0].path)
        pairs = [(m, first) for m in monitors]
    else:
        pairs = [(mw.monitor, str(mw.path)) for mw in assigned]

    blocks = [f"wallpaper {{\n    monitor = {m}\n    path = {p}\n    fit_mode = cover\n}}" for m, p in pairs]
    HYPRPAPER_CONF.write_text("\n\n".join(blocks) + "\n")

    # hyprpaper 0.8.x uses the hyprwire binary protocol — hyprctl hyprpaper IPC
    # commands no longer work. Restart hyprpaper so it reads the updated config.
    subprocess.run(["pkill", "-x", "hyprpaper"], capture_output=True)
    time.sleep(0.3)
    # start_new_session=True detaches hyprpaper from the pywalrchy process group
    # so it keeps running after the TUI is closed.
    subprocess.Popen(["uwsm-app", "--", "hyprpaper"], start_new_session=True)


def get_monitors() -> list[str]:
    result = subprocess.run(
        ["hyprctl", "monitors", "-j"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    monitors = json.loads(result.stdout)
    return [m["name"] for m in monitors]

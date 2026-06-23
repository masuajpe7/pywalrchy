from __future__ import annotations

import json
import subprocess
from pathlib import Path

from pywalrchy.config import COLOR_KEYS, WAL_CACHE


def extract_colors(image: Path) -> dict[str, str]:
    subprocess.run(
        ["wal", "-i", str(image), "-n", "-q"],
        check=True,
    )
    return parse_wal_cache()


def parse_wal_cache() -> dict[str, str]:
    colors_json = WAL_CACHE / "colors.json"
    if not colors_json.exists():
        raise FileNotFoundError("wal cache not found — run wal first")

    data = json.loads(colors_json.read_text())
    special = data["special"]
    raw = data["colors"]

    colors: dict[str, str] = {
        "background": special["background"].lower(),
        "foreground": special["foreground"].lower(),
        "cursor": special["cursor"].lower(),
        "selection_background": raw["color1"].lower(),
        "selection_foreground": special["background"].lower(),
        "accent": raw["color4"].lower(),
    }
    for i in range(16):
        key = f"color{i}"
        colors[key] = raw[key].lower()

    return {k: colors[k] for k in COLOR_KEYS if k in colors}

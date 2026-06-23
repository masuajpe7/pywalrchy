from __future__ import annotations

import subprocess

from pywalrchy.theme import Theme


def apply_theme(theme: Theme) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["omarchy-theme-set", theme.name],
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "OMARCHY_THEME_SKIP_BACKGROUND": "1"},
    )

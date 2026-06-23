from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from pywalrchy.config import (
    COLOR_KEYS,
    OMARCHY_CURRENT,
    OMARCHY_STOCK_THEMES,
    OMARCHY_THEMES,
)


@dataclass
class MonitorWallpaper:
    monitor: str
    path: Path


@dataclass
class Theme:
    name: str
    path: Path
    is_stock: bool = False
    colors: dict[str, str] = field(default_factory=dict)
    monitor_wallpapers: list[MonitorWallpaper] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return self.name.lower().replace(" ", "-")

    @property
    def colors_file(self) -> Path:
        return self.path / "colors.toml"

    @property
    def meta_file(self) -> Path:
        return self.path / "pywalrchy.toml"

    @property
    def backgrounds_dir(self) -> Path:
        return self.path / "backgrounds"

    def load(self) -> None:
        if self.colors_file.exists():
            raw = self.colors_file.read_text()
            self.colors = _parse_colors_toml(raw)
        if self.meta_file.exists():
            meta = tomllib.loads(self.meta_file.read_text())
            monitors = meta.get("monitors", {})
            self.monitor_wallpapers = [
                MonitorWallpaper(monitor=m, path=self.path / p)
                for m, p in monitors.items()
                if (self.path / p).exists()
            ]
        # Fall back to scanning backgrounds/ when no pywalrchy metadata exists
        if not self.monitor_wallpapers and self.backgrounds_dir.exists():
            _IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
            for f in sorted(self.backgrounds_dir.iterdir()):
                if f.is_file() and f.suffix.lower() in _IMAGE_EXTS:
                    self.monitor_wallpapers.append(
                        MonitorWallpaper(monitor="unassigned", path=f)
                    )

    def save_colors(self) -> None:
        lines = []
        for key in COLOR_KEYS:
            if key in self.colors:
                lines.append(f'{key} = "{self.colors[key]}"')
        self.colors_file.write_text("\n".join(lines) + "\n")

    def save_meta(self) -> None:
        lines = ["[monitors]"]
        for mw in self.monitor_wallpapers:
            rel = mw.path.relative_to(self.path)
            lines.append(f'"{mw.monitor}" = "{rel}"')
        self.meta_file.write_text("\n".join(lines) + "\n")

    def add_wallpaper(self, src: Path, monitor: str) -> Path:
        self.backgrounds_dir.mkdir(exist_ok=True)
        dest = self.backgrounds_dir / f"{monitor}{src.suffix}"
        import shutil
        shutil.copy2(src, dest)
        self.monitor_wallpapers = [
            mw for mw in self.monitor_wallpapers if mw.monitor != monitor
        ]
        self.monitor_wallpapers.append(MonitorWallpaper(monitor=monitor, path=dest))
        return dest

    def wallpaper_for(self, monitor: str) -> Path | None:
        for mw in self.monitor_wallpapers:
            if mw.monitor == monitor:
                return mw.path
        return None


def _parse_colors_toml(text: str) -> dict[str, str]:
    colors: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'^(\w+)\s*=\s*["\']?(#[0-9a-fA-F]{6})["\']?', line)
        if m:
            colors[m.group(1)] = m.group(2).lower()
    return colors


def list_themes() -> list[Theme]:
    themes: list[Theme] = []

    for path in sorted(OMARCHY_THEMES.iterdir()):
        if path.is_dir():
            t = Theme(name=path.name, path=path, is_stock=False)
            t.load()
            themes.append(t)

    stock_names = {t.name for t in themes}
    for path in sorted(OMARCHY_STOCK_THEMES.iterdir()):
        if path.is_dir() and path.name not in stock_names:
            t = Theme(name=path.name, path=path, is_stock=True)
            t.load()
            themes.append(t)

    return themes


def active_theme_name() -> str | None:
    name_file = OMARCHY_CURRENT / "theme.name"
    if name_file.exists():
        return name_file.read_text().strip()
    return None


def load_current_colors() -> dict[str, str]:
    """Return the colors of the currently active Omarchy theme."""
    colors_file = OMARCHY_CURRENT / "theme" / "colors.toml"
    if colors_file.exists():
        return _parse_colors_toml(colors_file.read_text())
    return {}


def create_theme(name: str) -> Theme:
    slug = name.lower().replace(" ", "-")
    path = OMARCHY_THEMES / slug
    path.mkdir(parents=True, exist_ok=True)
    (path / "backgrounds").mkdir(exist_ok=True)
    return Theme(name=slug, path=path, is_stock=False)

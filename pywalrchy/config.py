from pathlib import Path

HOME = Path.home()
OMARCHY_THEMES = HOME / ".config/omarchy/themes"
OMARCHY_STOCK_THEMES = HOME / ".local/share/omarchy/themes"
OMARCHY_CURRENT = HOME / ".config/omarchy/current"
HYPRPAPER_CONF = HOME / ".config/hypr/hyprpaper.conf"
WAL_CACHE = HOME / ".cache/wal"

OMARCHY_THEMES.mkdir(parents=True, exist_ok=True)

COLOR_KEYS = [
    "background", "foreground", "cursor",
    "selection_background", "selection_foreground",
    "accent",
    "color0", "color1", "color2", "color3",
    "color4", "color5", "color6", "color7",
    "color8", "color9", "color10", "color11",
    "color12", "color13", "color14", "color15",
]

COLOR_LABELS = {
    "background": "Background",
    "foreground": "Foreground",
    "cursor": "Cursor",
    "selection_background": "Sel. Background",
    "selection_foreground": "Sel. Foreground",
    "accent": "Accent",
    "color0": "Black",
    "color1": "Red",
    "color2": "Green",
    "color3": "Yellow",
    "color4": "Blue",
    "color5": "Magenta",
    "color6": "Cyan",
    "color7": "White",
    "color8": "Br. Black",
    "color9": "Br. Red",
    "color10": "Br. Green",
    "color11": "Br. Yellow",
    "color12": "Br. Blue",
    "color13": "Br. Magenta",
    "color14": "Br. Cyan",
    "color15": "Br. White",
}

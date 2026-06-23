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
    "selection_background": "Selection BG",
    "selection_foreground": "Selection FG",
    "accent": "Accent",
    "color0": "Shadows",
    "color1": "Errors",
    "color2": "Success",
    "color3": "Warnings",
    "color4": "Links / Info",
    "color5": "Special / Tags",
    "color6": "Strings / Types",
    "color7": "UI Text",
    "color8": "Comments / Dim",
    "color9": "Bright Errors",
    "color10": "Bright Success",
    "color11": "Bright Warnings",
    "color12": "Bright Links",
    "color13": "Bright Special",
    "color14": "Bright Strings",
    "color15": "Bold Text",
}

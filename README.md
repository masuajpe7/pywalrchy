# pywalrchy

A terminal UI for creating and managing [Omarchy](https://omarchy.org/) themes powered by [pywal](https://github.com/dylanaraps/pywal).

Upload a wallpaper → pywal extracts a color palette → a full Omarchy theme is created. Supports per-monitor wallpapers via [hyprpaper](https://github.com/hyprwm/hyprpaper).

![screenshot placeholder]

## Features

- **Create themes** — pick a wallpaper, pywal generates the color palette automatically
- **Edit themes** — adjust any of the 22 color slots with an interactive palette editor
- **Per-monitor wallpapers** — assign different wallpapers to each display (e.g. `eDP-1` and `HDMI-A-1`)
- **Theme browser** — preview the palette, terminal colors, and wallpapers before applying
- **Stock theme editor** — fork any built-in Omarchy theme and customize it
- **System theme** — the app's own colors follow whichever Omarchy theme is active at launch

## Requirements

### System (must be installed)

| Tool | Purpose |
|------|---------|
| [Omarchy](https://omarchy.org/) | The desktop system this tool manages themes for |
| [pywal](https://github.com/dylanaraps/pywal) (`wal` command) | Extracts color palettes from wallpapers |
| [hyprpaper](https://github.com/hyprwm/hyprpaper) | Per-monitor wallpaper daemon (Wayland) |
| `hyprctl` | Comes with [Hyprland](https://hyprland.org/), used for monitor detection |

### Optional

| Tool | Purpose |
|------|---------|
| [chafa](https://hpjansson.org/chafa/) | In-app wallpaper thumbnails in the terminal |
| `imv` / `nsxiv` / `feh` | Image viewer for opening wallpapers — falls back to `xdg-open` |

### Python

- Python 3.11+
- [Textual](https://github.com/Textualize/textual) 8.0+ (installed automatically)

## Install

```bash
# Install pywal (AUR)
yay -S python-pywal

# Install hyprpaper
yay -S hyprpaper

# Optional but recommended
yay -S chafa imv

# Install pywalrchy
pip install --user git+https://github.com/maxiciber/pywalrchy.git

# Or clone and install in editable mode for development
git clone https://github.com/maxiciber/pywalrchy.git
cd pywalrchy
pip install --user -e .
```

## Usage

```bash
pywalrchy
```

### Key bindings

| Key | Action |
|-----|--------|
| `n` | New theme |
| `e` | Edit selected theme |
| `a` | Apply selected theme to the system |
| `d` | Delete selected theme |
| `r` | Refresh theme list |
| `q` | Quit |

Inside the theme editor:

| Key | Action |
|-----|--------|
| `Ctrl+S` | Save changes |
| `Ctrl+A` | Save and apply |

## How it works

1. You name a theme and pick a wallpaper per monitor in the wizard
2. pywal runs `wal -i <wallpaper> -n` to extract 22 colors from the image
3. pywalrchy saves a `colors.toml` and `pywalrchy.toml` in `~/.config/omarchy/themes/<name>/`
4. Applying a theme runs `omarchy-theme-set <name>` (skipping its background setter) then tells hyprpaper to load the right wallpaper on each monitor

Themes live in `~/.config/omarchy/themes/` alongside Omarchy's stock themes in `~/.local/share/omarchy/themes/`.

## License

MIT

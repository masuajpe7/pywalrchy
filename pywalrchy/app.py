from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.color import Color
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widget import Widget
from textual.widgets import (
    Button,
    DirectoryTree,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Select,
    Static,
)

from textual.theme import Theme as TextualTheme

from pywalrchy import __version__
from pywalrchy.config import COLOR_KEYS, COLOR_LABELS, OMARCHY_THEMES
from pywalrchy.hyprpaper import apply_wallpapers, get_monitors
from pywalrchy import omarchy as omarchy_mod
from pywalrchy import pywal
from pywalrchy.theme import (
    MonitorWallpaper,
    Theme,
    active_theme_name,
    create_theme,
    list_themes,
    load_current_colors,
)


# ── Wallpaper row widget ───────────────────────────────────────────────────────

class WallpaperRow(Horizontal):
    """A single wallpaper entry: monitor label + Open button, composed properly."""

    DEFAULT_CSS = """
    WallpaperRow { height: 2; align: left middle; }
    WallpaperRow Label { width: 1fr; }
    """

    def __init__(self, mw: MonitorWallpaper, **kwargs):
        super().__init__(**kwargs)
        self._mw = mw

    def compose(self) -> ComposeResult:
        tag = (
            f"[dim]{self._mw.monitor}[/]"
            if self._mw.monitor == "unassigned"
            else f"[bold]{self._mw.monitor}[/]"
        )
        yield Label(f"{tag}  {self._mw.path.name}")
        btn = Button("Open", classes="btn-open-wp", variant="default")
        btn.data = self._mw.path  # type: ignore[attr-defined]
        yield btn


# ── Wallpaper editor row ──────────────────────────────────────────────────────

class WallpaperEditorRow(Widget):
    """Wallpaper row for the theme editor — two rows: filename on top, controls below."""

    DEFAULT_CSS = """
    WallpaperEditorRow {
        layout: vertical;
        height: auto;
        border: round $surface-darken-2;
        margin-bottom: 1;
        padding: 0 1;
    }
    WallpaperEditorRow .wp-filename {
        height: 2;
        content-align: left middle;
        text-style: bold;
        padding: 0 1;
    }
    WallpaperEditorRow .wp-controls {
        layout: horizontal;
        height: 3;
        align: left middle;
    }
    WallpaperEditorRow .wp-controls Select { width: 22; }
    WallpaperEditorRow .btn-row-browse { width: 10; margin-left: 1; }
    WallpaperEditorRow .btn-row-remove { width: 10; margin-left: 1; }
    """

    class BrowseRequested(Message):
        def __init__(self, row: "WallpaperEditorRow") -> None:
            self.row = row
            super().__init__()

    class Removed(Message):
        def __init__(self, row: "WallpaperEditorRow") -> None:
            self.row = row
            super().__init__()

    def __init__(self, mw: MonitorWallpaper, monitors: list[str], **kwargs):
        super().__init__(**kwargs)
        self._mw = mw
        self._monitors = monitors

    @property
    def current_monitor(self) -> str:
        try:
            val = self.query_one(Select).value
            return str(val) if val is not Select.BLANK else self._mw.monitor
        except Exception:
            return self._mw.monitor

    @property
    def current_path(self) -> Path:
        return self._mw.path

    def update_path(self, path: Path) -> None:
        self._mw = MonitorWallpaper(monitor=self._mw.monitor, path=path)
        try:
            self.query_one(".wp-filename", Label).update(path.name)
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        yield Label(self._mw.path.name, classes="wp-filename")
        with Horizontal(classes="wp-controls"):
            opts = [(m, m) for m in self._monitors]
            cur = self._mw.monitor
            if cur not in self._monitors:
                opts.insert(0, (cur, cur))
            yield Select(opts, value=cur, allow_blank=False)
            yield Button("Browse", classes="btn-row-browse", variant="default")
            yield Button("Remove", classes="btn-row-remove", variant="error")

    @on(Button.Pressed, ".btn-row-browse")
    def _request_browse(self) -> None:
        self.post_message(self.BrowseRequested(self))

    @on(Button.Pressed, ".btn-row-remove")
    def _request_remove(self) -> None:
        self.post_message(self.Removed(self))


# ── File browser ──────────────────────────────────────────────────────────────

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp"}
_PICTURES_DIR = Path.home() / "Pictures"
_BROWSE_START = _PICTURES_DIR if _PICTURES_DIR.exists() else Path.home()


class ImageDirectoryTree(DirectoryTree):
    """DirectoryTree that shows only directories and image files."""

    def filter_paths(self, paths):
        return [
            p for p in paths
            if p.is_dir() or p.suffix.lower() in _IMAGE_EXTS
        ]


class FileBrowserScreen(ModalScreen):
    """Full-screen file browser for picking a wallpaper image."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    FileBrowserScreen {
        align: center middle;
    }
    FileBrowserScreen #fb-dialog {
        width: 80%;
        height: 80%;
        border: thick $accent;
        background: $surface;
    }
    FileBrowserScreen #fb-hint {
        padding: 0 1;
        color: $text-muted;
        height: 1;
    }
    FileBrowserScreen ImageDirectoryTree {
        height: 1fr;
    }
    FileBrowserScreen #fb-selected {
        height: 2;
        padding: 0 1;
        color: $accent;
        border-top: solid $surface-darken-2;
    }
    FileBrowserScreen #fb-buttons {
        height: 3;
        align: right middle;
        padding: 0 1;
        border-top: solid $surface-darken-2;
    }
    """

    def __init__(self, start: Path = _BROWSE_START, **kwargs):
        super().__init__(**kwargs)
        self._start = start
        self._chosen: Path | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="fb-dialog"):
            yield Label(
                "Navigate to an image file and press [bold]Enter[/] to select it.",
                id="fb-hint",
            )
            yield ImageDirectoryTree(self._start, id="fb-tree")
            yield Label("No file selected", id="fb-selected")
            with Horizontal(id="fb-buttons"):
                yield Button("Select", id="fb-ok", variant="primary", disabled=True)
                yield Button("Cancel", id="fb-cancel")

    @on(DirectoryTree.FileSelected)
    def file_highlighted(self, event: DirectoryTree.FileSelected) -> None:
        path = event.path
        if path.suffix.lower() in _IMAGE_EXTS:
            self._chosen = path
            self.query_one("#fb-selected", Label).update(str(path))
            self.query_one("#fb-ok", Button).disabled = False
        else:
            self._chosen = None
            self.query_one("#fb-selected", Label).update("[dim]Not an image file[/]")
            self.query_one("#fb-ok", Button).disabled = True

    @on(Button.Pressed, "#fb-ok")
    def confirm(self) -> None:
        self.dismiss(self._chosen)

    @on(Button.Pressed, "#fb-cancel")
    def action_cancel(self) -> None:
        self.dismiss(None)


# ── Helpers ────────────────────────────────────────────────────────────────────

def open_in_viewer(path: Path) -> None:
    for viewer in ["imv", "nsxiv", "feh", "eog", "xdg-open"]:
        if shutil.which(viewer):
            subprocess.Popen([viewer, str(path)])
            return


def _fg_for(hex_color: str) -> str:
    try:
        c = Color.parse(hex_color)
        luma = 0.299 * c.r + 0.587 * c.g + 0.114 * c.b
        return "#000000" if luma > 128 else "#ffffff"
    except Exception:
        return "#ffffff"


def _lighten(hex_color: str, amount: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r = min(255, int(r + (255 - r) * amount))
    g = min(255, int(g + (255 - g) * amount))
    b = min(255, int(b + (255 - b) * amount))
    return f"#{r:02x}{g:02x}{b:02x}"


def build_textual_theme(colors: dict[str, str]) -> TextualTheme:
    bg  = colors.get("background", "#1e1e2e")
    fg  = colors.get("foreground", "#cdd6f4")
    acc = colors.get("accent",     "#89b4fa")
    c1  = colors.get("color1",     "#f38ba8")
    c2  = colors.get("color2",     "#a6e3a1")
    c3  = colors.get("color3",     "#f9e2af")
    c4  = colors.get("color4",     "#89b4fa")
    c5  = colors.get("color5",     "#f5c2e7")

    # Determine light vs dark from background luminosity
    try:
        bc = Color.parse(bg)
        luma = 0.299 * bc.r + 0.587 * bc.g + 0.114 * bc.b
        dark = luma < 128
    except Exception:
        dark = True

    surface = _lighten(bg, 0.06)
    panel   = _lighten(bg, 0.10)

    return TextualTheme(
        name="omarchy",
        primary=acc,
        secondary=c5,
        accent=acc,
        foreground=fg,
        background=bg,
        surface=surface,
        panel=panel,
        success=c2,
        warning=c3,
        error=c1,
        dark=dark,
    )


# ── Terminal preview widget ────────────────────────────────────────────────────

class TerminalPreview(Static):
    """Simulated terminal session rendered with the theme's colors."""

    DEFAULT_CSS = """
    TerminalPreview {
        height: 1fr;
        padding: 1 2;
        overflow-y: auto;
    }
    """

    def refresh_colors(self, colors: dict[str, str]) -> None:
        bg  = colors.get("background", "#1e1e2e")
        fg  = colors.get("foreground", "#cdd6f4")
        acc = colors.get("accent",     "#89b4fa")
        c1  = colors.get("color1",     "#f38ba8")
        c2  = colors.get("color2",     "#a6e3a1")
        c3  = colors.get("color3",     "#f9e2af")
        c4  = colors.get("color4",     "#89b4fa")
        c5  = colors.get("color5",     "#f5c2e7")
        c6  = colors.get("color6",     "#94e2d5")
        c8  = colors.get("color8",     "#585b70")

        prompt = f"[bold {acc}]user@host[/] [{c4}]~/projects[/] [{c8}]on[/] [{c5}] main[/]"
        arrow  = f"[bold {acc}]❯[/]"

        lines = [
            prompt,
            f"{arrow} [{c6}]ls[/] [{c4}]--color[/]",
            f"[bold {c4}]docs/[/]  [bold {c4}]src/[/]  [{fg}]README.md[/]  [{fg}]pyproject.toml[/]",
            "",
            prompt,
            f"{arrow} [{c6}]git[/] status",
            f"[{fg}]On branch[/] [{c4}]main[/]",
            f"[{c1}]  modified:[/]  [{fg}]src/app.py[/]",
            f"[{c2}]  new file:[/]  [{fg}]docs/INSTALL.md[/]",
            f"[{c8}]  untracked: build/[/]",
            "",
            prompt,
            f"{arrow} [{c6}]python[/] main.py",
            f"[{c2}]✓[/]  Server started on port [{c4}]8080[/]",
            f"[{c3}]⚠[/]  Config missing, using defaults",
            f"[{c1}]✗[/]  Connection refused: localhost:5432",
            "",
            f"[{c8}]──────────────── editor preview ────────────────[/]",
            f"[{c8}]# theme manager for omarchy[/]",
            f"[{c1}]class[/] [{c2}]PywalrchyApp[/]([{c4}]App[/]):",
            f"    [{c1}]def[/] [{c2}]on_mount[/]([{c6}]self[/]) -> [{c4}]None[/]:",
            f"        [{c6}]self[/].push_screen([{c3}]ThemeBrowserScreen[/]())",
            "",
            f"    [{c1}]def[/] [{c2}]apply_theme[/]([{c6}]self[/], [{c6}]name[/]: [{c4}]str[/]):",
            f"        [{c8}]# applies omarchy + hyprpaper[/]",
            f"        [{c6}]result[/] = [{c5}]omarchy[/].apply([{c6}]name[/])",
            f"        [{c1}]return[/] [{c6}]result[/]",
        ]
        self.update("\n".join(lines))


# ── Wallpaper info widget ──────────────────────────────────────────────────────

class WallpaperInfo(Static):
    """Shows wallpaper filename, size, and open button hint."""

    DEFAULT_CSS = """
    WallpaperInfo {
        height: auto;
        padding: 0 1;
        color: $text-muted;
    }
    """

    def set_wallpaper(self, mw: MonitorWallpaper | None) -> None:
        if mw is None:
            self.update("[dim]No wallpaper selected[/]")
            return

        path = mw.path
        try:
            size_kb = path.stat().st_size // 1024
            size_str = f"{size_kb} KB" if size_kb < 1024 else f"{size_kb // 1024} MB"
        except Exception:
            size_str = "?"

        lines = [
            f"[bold]{path.name}[/]",
            f"[dim]{mw.monitor}  ·  {size_str}  ·  {path.suffix.lstrip('.').upper()}[/]",
            f"[dim]{path}[/]",
        ]

        if not shutil.which("chafa"):
            lines.append("[dim]Install chafa for in-app thumbnail[/]")

        self.update("\n".join(lines))

    @work(thread=True)
    def set_chafa(self, path: Path) -> None:
        try:
            result = subprocess.run(
                ["chafa", "--size", "44x12", "--format", "symbols", str(path)],
                capture_output=True, text=True, timeout=6,
            )
            if result.returncode == 0:
                from rich.text import Text
                rendered = Text.from_ansi(result.stdout)
                self.app.call_from_thread(self.update, rendered)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass


# ── Color swatch widget ────────────────────────────────────────────────────────

class ColorSwatch(Widget):
    DEFAULT_CSS = """
    ColorSwatch {
        width: 1fr;
        height: 3;
        border: tall transparent;
        padding: 0 1;
        content-align: center middle;
    }
    ColorSwatch:focus { border: tall $accent; }
    ColorSwatch:hover { border: tall $primary; }
    """

    class Clicked(Message):
        def __init__(self, key: str) -> None:
            self.key = key
            super().__init__()

    def __init__(self, key: str, hex_color: str, **kwargs):
        super().__init__(**kwargs)
        self.key = key
        self.hex_color = hex_color
        self.can_focus = True

    def render(self) -> str:
        label = COLOR_LABELS.get(self.key, self.key)
        return f"{label}\n{self.hex_color}"

    def on_mount(self) -> None:
        self._apply_color()

    def _apply_color(self) -> None:
        try:
            self.styles.background = self.hex_color
            self.styles.color = _fg_for(self.hex_color)
        except Exception:
            pass

    def update_color(self, hex_color: str) -> None:
        self.hex_color = hex_color
        self._apply_color()
        self.refresh()

    def on_click(self) -> None:
        self.post_message(self.Clicked(self.key))

    def on_key(self, event) -> None:
        if event.key == "enter":
            self.post_message(self.Clicked(self.key))


# ── Palette editor ─────────────────────────────────────────────────────────────

class PaletteEditor(Widget):
    DEFAULT_CSS = """
    PaletteEditor { height: auto; }
    PaletteEditor .palette-grid {
        layout: grid;
        grid-size: 3;
        grid-gutter: 1;
        height: auto;
        padding: 1;
    }
    PaletteEditor .edit-row {
        height: 3;
        padding: 0 1;
        display: none;
    }
    PaletteEditor .edit-row.visible { display: block; }
    """

    class ColorsChanged(Message):
        def __init__(self, colors: dict[str, str]) -> None:
            self.colors = colors
            super().__init__()

    def __init__(self, colors: dict[str, str], **kwargs):
        super().__init__(**kwargs)
        self._data = dict(colors)
        self._editing_key: str | None = None

    def compose(self) -> ComposeResult:
        with Container(classes="palette-grid"):
            for key in COLOR_KEYS:
                yield ColorSwatch(key=key, hex_color=self._data.get(key, "#000000"), id=f"swatch-{key}")
        with Horizontal(classes="edit-row", id="edit-row"):
            yield Label("", id="edit-label")
            yield Input(placeholder="#rrggbb", id="color-input")
            yield Button("Set", id="btn-set", variant="primary")
            yield Button("✕", id="btn-cancel")

    @on(ColorSwatch.Clicked)
    def start_editing(self, event: ColorSwatch.Clicked) -> None:
        self._editing_key = event.key
        self.query_one("#edit-row").add_class("visible")
        self.query_one("#edit-label", Label).update(f"{COLOR_LABELS.get(event.key, event.key)}: ")
        inp = self.query_one("#color-input", Input)
        inp.value = self._data.get(event.key, "#000000")
        inp.focus()

    @on(Button.Pressed, "#btn-set")
    @on(Input.Submitted, "#color-input")
    def confirm_edit(self, _=None) -> None:
        if not self._editing_key:
            return
        inp = self.query_one("#color-input", Input)
        value = inp.value.strip()
        if not value.startswith("#"):
            value = "#" + value
        if not re.match(r"^#[0-9a-fA-F]{6}$", value):
            inp.add_class("error")
            return
        inp.remove_class("error")
        value = value.lower()
        self._data[self._editing_key] = value
        self.query_one(f"#swatch-{self._editing_key}", ColorSwatch).update_color(value)
        self._editing_key = None
        self.query_one("#edit-row").remove_class("visible")
        self.post_message(self.ColorsChanged(dict(self._data)))

    @on(Button.Pressed, "#btn-cancel")
    def cancel_edit(self) -> None:
        self._editing_key = None
        self.query_one("#edit-row").remove_class("visible")

    def reload(self, colors: dict[str, str]) -> None:
        self._data = dict(colors)
        for key in COLOR_KEYS:
            try:
                self.query_one(f"#swatch-{key}", ColorSwatch).update_color(colors.get(key, "#000000"))
            except Exception:
                pass


# ── Confirm modal ──────────────────────────────────────────────────────────────

class ConfirmModal(ModalScreen):
    DEFAULT_CSS = """
    ConfirmModal { align: center middle; }
    ConfirmModal #dialog {
        width: 60; height: auto;
        border: thick $accent;
        background: $surface;
        padding: 2 4;
    }
    ConfirmModal #buttons { margin-top: 1; align: center middle; }
    """

    def __init__(self, message: str, **kwargs):
        super().__init__(**kwargs)
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.message)
            with Horizontal(id="buttons"):
                yield Button("Yes", id="yes", variant="error")
                yield Button("No", id="no")

    @on(Button.Pressed, "#yes")
    def confirm(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no")
    def deny(self) -> None:
        self.dismiss(False)


# ── Theme editor screen ────────────────────────────────────────────────────────

class ThemeEditorScreen(Screen):
    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+a", "apply", "Apply"),
    ]

    DEFAULT_CSS = """
    ThemeEditorScreen #editor-layout {
        layout: grid;
        grid-size: 2;
        height: 1fr;
    }
    ThemeEditorScreen #left-panel, ThemeEditorScreen #right-panel {
        border: round $primary;
        padding: 1;
    }
    ThemeEditorScreen .panel-title {
        text-style: bold; color: $accent; margin-bottom: 1;
    }
    ThemeEditorScreen #wallpaper-list { height: 1fr; }
    ThemeEditorScreen #add-section { height: auto; margin-top: 1; }
    ThemeEditorScreen #add-row { height: 3; }
    ThemeEditorScreen #monitor-select { width: 20; }
    ThemeEditorScreen #wp-path-input { width: 1fr; }
    """

    def __init__(self, theme: Theme, **kwargs):
        super().__init__(**kwargs)
        self.theme = theme
        self._monitors = get_monitors()
        self._colors = dict(theme.colors)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="editor-layout"):
            with ScrollableContainer(id="left-panel"):
                yield Label(f"Colors — {self.theme.name}", classes="panel-title")
                yield PaletteEditor(self._colors, id="palette")
            with Vertical(id="right-panel"):
                yield Label("Wallpapers per monitor", classes="panel-title")
                yield ScrollableContainer(id="wallpaper-list")
                with Vertical(id="add-section"):
                    yield Label("Add wallpaper:", classes="panel-title")
                    with Horizontal(id="add-row"):
                        yield Select(
                            [(m, m) for m in self._monitors],
                            id="monitor-select", prompt="Monitor",
                        )
                        yield Input(placeholder="Path to image", id="wp-path-input")
                        yield Button("Browse…", id="btn-browse-editor", variant="default")
                        yield Button("Add", id="btn-add-wp", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_wallpaper_list()

    def _refresh_wallpaper_list(self) -> None:
        container = self.query_one("#wallpaper-list")
        container.remove_children()
        if not self.theme.monitor_wallpapers:
            container.mount(Label("[dim]No wallpapers assigned yet.[/]"))
            return
        for mw in self.theme.monitor_wallpapers:
            container.mount(WallpaperEditorRow(mw, self._monitors))

    @on(WallpaperEditorRow.BrowseRequested)
    def browse_row(self, event: WallpaperEditorRow.BrowseRequested) -> None:
        row = event.row

        def _on_pick(path: Path | None) -> None:
            if path:
                row.update_path(path)

        self.app.push_screen(FileBrowserScreen(), callback=_on_pick)

    @on(WallpaperEditorRow.Removed)
    def remove_row(self, event: WallpaperEditorRow.Removed) -> None:
        event.row.remove()
        remaining = list(self.query(WallpaperEditorRow))
        if not remaining:
            self.query_one("#wallpaper-list").mount(Label("[dim]No wallpapers assigned yet.[/]"))

    @on(PaletteEditor.ColorsChanged)
    def colors_updated(self, event: PaletteEditor.ColorsChanged) -> None:
        self._colors = event.colors

    @on(Button.Pressed, "#btn-browse-editor")
    def browse_add_input(self) -> None:
        def _on_pick(path: Path | None) -> None:
            if path:
                self.query_one("#wp-path-input", Input).value = str(path)

        self.app.push_screen(FileBrowserScreen(), callback=_on_pick)

    @on(Button.Pressed, "#btn-add-wp")
    def add_wallpaper(self) -> None:
        monitor = self.query_one("#monitor-select", Select).value
        path_str = self.query_one("#wp-path-input", Input).value.strip()
        if not monitor or monitor is Select.BLANK or not path_str:
            self.notify("Select a monitor and enter a path.", severity="error")
            return
        src = Path(path_str).expanduser()
        if not src.exists():
            self.notify(f"File not found: {src}", severity="error")
            return
        self.theme.add_wallpaper(src, str(monitor))
        self.query_one("#wp-path-input", Input).value = ""
        self._refresh_wallpaper_list()
        self.notify(f"Wallpaper added for {monitor}.")

    def action_save(self) -> None:
        self.theme.colors = self._colors
        self.theme.save_colors()
        # Persist wallpaper assignments from current rows
        self.theme.backgrounds_dir.mkdir(exist_ok=True)
        new_wallpapers: list[MonitorWallpaper] = []
        for row in self.query(WallpaperEditorRow):
            monitor = row.current_monitor
            src = row.current_path
            if not src.exists():
                continue
            if src.parent != self.theme.backgrounds_dir:
                dest = self.theme.backgrounds_dir / f"{monitor}{src.suffix}"
                shutil.copy2(src, dest)
                src = dest
            new_wallpapers.append(MonitorWallpaper(monitor=monitor, path=src))
        self.theme.monitor_wallpapers = new_wallpapers
        self.theme.save_meta()
        self.notify("Theme saved.")

    @work(thread=True)
    def action_apply(self) -> None:
        self.app.call_from_thread(self.action_save)
        result = omarchy_mod.apply_theme(self.theme)
        if result.returncode != 0:
            self.app.call_from_thread(self.notify, f"omarchy error: {result.stderr}", severity="error")
            return
        apply_wallpapers(self.theme)
        self.app.call_from_thread(self.notify, "Theme applied!")

    def action_go_back(self) -> None:
        self.app.pop_screen()


# ── New theme wizard ───────────────────────────────────────────────────────────

class WizardScreen(Screen):
    BINDINGS = [Binding("escape", "go_back", "Back")]

    DEFAULT_CSS = """
    WizardScreen #wizard-body { padding: 2 4; height: 1fr; }
    WizardScreen .step-title { text-style: bold; color: $accent; margin-bottom: 1; }
    WizardScreen .step-hint { color: $text-muted; margin-bottom: 1; }
    WizardScreen #wallpaper-assignments { height: auto; margin-bottom: 1; }
    WizardScreen #monitor-sel { width: 20; }
    WizardScreen #wp-input { width: 1fr; }
    WizardScreen #step-nav { dock: bottom; height: 3; align: right middle; padding: 0 2; }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._step = 1
        self._theme_name = ""
        self._colors: dict[str, str] = {}
        self._monitors = get_monitors()
        self._assignments: dict[str, Path] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield ScrollableContainer(id="wizard-body")
        with Horizontal(id="step-nav"):
            yield Button("← Back", id="btn-prev")
            yield Button("Next →", id="btn-next", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self._render_step()

    def _render_step(self) -> None:
        body = self.query_one("#wizard-body")
        body.remove_children()
        self.query_one("#btn-prev", Button).disabled = self._step == 1

        if self._step == 1:
            self.query_one("#btn-next", Button).label = "Next →"
            body.mount(Label("Step 1 of 4 — Theme name", classes="step-title"))
            body.mount(Label("Give this theme a unique name.", classes="step-hint"))
            inp = Input(value=self._theme_name, placeholder="e.g. ocean-dark", id="name-input")
            body.mount(inp)
            inp.focus()

        elif self._step == 2:
            self.query_one("#btn-next", Button).label = "Next →"
            body.mount(Label("Step 2 of 4 — Assign wallpapers", classes="step-title"))
            body.mount(Label(
                "Assign a wallpaper to each monitor. Colors will be extracted from the first one.",
                classes="step-hint",
            ))
            assignments_box = Vertical(id="wallpaper-assignments")
            body.mount(assignments_box)
            self._refresh_assignments(assignments_box)
            body.mount(Select([(m, m) for m in self._monitors], id="monitor-sel", prompt="Monitor"))
            body.mount(Input(placeholder="Path to image file", id="wp-input"))
            body.mount(Button("Browse…", id="btn-browse-wizard", variant="default"))
            body.mount(Button("Add ↵", id="btn-add-wp", variant="success"))

        elif self._step == 3:
            self.query_one("#btn-next", Button).label = "Next →"
            body.mount(Label("Step 3 of 4 — Edit colors", classes="step-title"))
            body.mount(Label("Colors extracted from wallpaper. Click any swatch to edit.", classes="step-hint"))
            if self._colors:
                body.mount(PaletteEditor(self._colors, id="palette"))
            else:
                body.mount(Label("[dim]No colors available.[/]"))

        elif self._step == 4:
            self.query_one("#btn-next", Button).label = "Finish & Apply"
            body.mount(Label("Step 4 of 4 — Confirm", classes="step-title"))
            body.mount(Label(f"Name:      [bold]{self._theme_name}[/]"))
            body.mount(Label(f"Monitors:  {len(self._assignments)} wallpaper(s)"))
            body.mount(Label(f"Colors:    {len(self._colors)} defined"))
            for mon, path in self._assignments.items():
                body.mount(Label(f"  [dim]{mon}[/] → {path.name}"))
            body.mount(Label("\nPress [bold]Finish & Apply[/] to create and activate the theme."))

    def _refresh_assignments(self, container: Widget | None = None) -> None:
        if container is None:
            try:
                container = self.query_one("#wallpaper-assignments")
            except Exception:
                return
        container.remove_children()
        if not self._assignments:
            container.mount(Label("[dim]No wallpapers assigned yet.[/]"))
            return
        for monitor, path in self._assignments.items():
            container.mount(Label(f"  [bold]{monitor}[/] → {path.name}"))

    @on(Button.Pressed, "#btn-browse-wizard")
    def browse_wizard(self) -> None:
        def _on_pick(path: Path | None) -> None:
            if path:
                try:
                    self.query_one("#wp-input", Input).value = str(path)
                except Exception:
                    pass

        self.app.push_screen(FileBrowserScreen(), callback=_on_pick)

    @on(Button.Pressed, "#btn-add-wp")
    def add_assignment(self) -> None:
        monitor = self.query_one("#monitor-sel", Select).value
        path_str = self.query_one("#wp-input", Input).value.strip()
        if not monitor or monitor is Select.BLANK or not path_str:
            self.notify("Select a monitor and enter a path.", severity="error")
            return
        src = Path(path_str).expanduser()
        if not src.exists():
            self.notify(f"File not found: {src}", severity="error")
            return
        self._assignments[str(monitor)] = src
        self.query_one("#wp-input", Input).value = ""
        self._refresh_assignments()

    @on(Button.Pressed, "#btn-next")
    def next_step(self) -> None:
        if self._step == 1:
            name = ""
            try:
                name = self.query_one("#name-input", Input).value.strip()
            except Exception:
                pass
            if not name:
                self.notify("Please enter a theme name.", severity="error")
                return
            self._theme_name = name
            self._step = 2
            self._render_step()
        elif self._step == 2:
            if not self._assignments:
                self.notify("Assign at least one wallpaper.", severity="error")
                return
            self._extract_colors()
        elif self._step == 3:
            try:
                self._colors = dict(self.query_one("#palette", PaletteEditor)._data)
            except Exception:
                pass
            self._step = 4
            self._render_step()
        elif self._step == 4:
            self._finish()

    @on(Button.Pressed, "#btn-prev")
    def prev_step(self) -> None:
        if self._step > 1:
            self._step -= 1
            self._render_step()

    @on(PaletteEditor.ColorsChanged)
    def colors_updated(self, event: PaletteEditor.ColorsChanged) -> None:
        self._colors = event.colors

    @work(thread=True)
    def _extract_colors(self) -> None:
        first = next(iter(self._assignments.values()))
        try:
            self._colors = pywal.extract_colors(first)
            self.app.call_from_thread(self._go_to_color_step)
        except Exception as e:
            self.app.call_from_thread(self.notify, f"Color extraction failed: {e}", severity="error")

    def _go_to_color_step(self) -> None:
        self._step = 3
        self._render_step()

    @work(thread=True)
    def _finish(self) -> None:
        theme = create_theme(self._theme_name)
        theme.colors = self._colors
        theme.save_colors()
        for monitor, src in self._assignments.items():
            theme.add_wallpaper(src, monitor)
        theme.save_meta()
        result = omarchy_mod.apply_theme(theme)
        if result.returncode != 0:
            self.app.call_from_thread(self.notify, f"omarchy error: {result.stderr}", severity="error")
            return
        apply_wallpapers(theme)
        self.app.call_from_thread(self._done, theme)

    def _done(self, theme: Theme) -> None:
        self.notify(f"Theme '{theme.name}' created and applied!")
        self.app.pop_screen()

    def action_go_back(self) -> None:
        self.app.pop_screen()


# ── Main theme browser ─────────────────────────────────────────────────────────

class ThemeBrowserScreen(Screen):
    BINDINGS = [
        Binding("n", "new_theme", "New"),
        Binding("e", "edit_theme", "Edit"),
        Binding("a", "apply_theme", "Apply"),
        Binding("d", "delete_theme", "Delete"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    DEFAULT_CSS = """
    ThemeBrowserScreen #browser-layout {
        layout: grid;
        grid-size: 3;
        grid-columns: 1fr 2fr 2fr;
        height: 1fr;
    }
    ThemeBrowserScreen #theme-list-panel {
        border: round $primary;
        padding: 1;
    }
    ThemeBrowserScreen #detail-panel {
        border: round $primary;
        padding: 1;
    }
    ThemeBrowserScreen #preview-panel {
        border: round $primary;
        padding: 1;
    }
    ThemeBrowserScreen .panel-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    ThemeBrowserScreen #wp-info {
        height: 5;
        padding: 0 1;
        color: $text-muted;
        border: dashed $surface-darken-1;
        margin-bottom: 1;
    }
    ThemeBrowserScreen #detail-colors {
        layout: grid;
        grid-size: 3;
        grid-gutter: 1;
        height: auto;
        padding: 1;
    }
    ThemeBrowserScreen #wallpaper-section {
        height: auto;
    }
    ThemeBrowserScreen .mini-swatch {
        height: 3;
        content-align: center middle;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._themes: list[Theme] = []
        self._selected_idx: int = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="browser-layout"):
            with Vertical(id="theme-list-panel"):
                yield Label("Themes", classes="panel-title")
                yield ListView(id="theme-listview")
            with ScrollableContainer(id="detail-panel"):
                yield Label("", id="detail-title", classes="panel-title")
                yield Vertical(id="wallpaper-section")
                yield WallpaperInfo(id="wp-info")
                yield Label("Color palette", classes="panel-title", id="colors-title")
                yield Container(id="detail-colors")
            with Vertical(id="preview-panel"):
                yield Label("Terminal Preview", classes="panel-title")
                yield TerminalPreview(id="term-preview")
        yield Footer()

    def on_mount(self) -> None:
        self._load_themes()

    def _load_themes(self) -> None:
        self._themes = list_themes()
        active = active_theme_name()
        lv = self.query_one("#theme-listview", ListView)
        lv.clear()
        for theme in self._themes:
            marker = " ●" if theme.name == active else ""
            stock = " [dim][stock][/]" if theme.is_stock else ""
            lv.append(ListItem(Label(f"{theme.name}{marker}{stock}")))
        # Use call_after_refresh so the ListView has finished its own layout
        # pass before we try to update the detail panel. Direct calls here
        # race with the ListView.Highlighted events fired by lv.append().
        if self._themes:
            self.call_after_refresh(self._show_detail, 0)

    @on(ListView.Highlighted)
    def list_highlighted(self, event: ListView.Highlighted) -> None:
        lv = self.query_one("#theme-listview", ListView)
        idx = lv.index
        if idx is not None and idx < len(self._themes):
            self._selected_idx = idx
            self._show_detail(idx)

    def _show_detail(self, idx: int) -> None:
        if idx >= len(self._themes):
            return
        theme = self._themes[idx]
        active = active_theme_name()

        # Title
        active_badge = "[green]● Active  [/]" if theme.name == active else ""
        stock_badge = "  [dim][stock][/]" if theme.is_stock else ""
        self.query_one("#detail-title", Label).update(
            f"{active_badge}[bold]{theme.name}[/]{stock_badge}"
        )

        # Wallpaper list
        wp_section = self.query_one("#wallpaper-section")
        wp_section.remove_children()
        if theme.monitor_wallpapers:
            for mw in theme.monitor_wallpapers:
                wp_section.mount(WallpaperRow(mw))
        else:
            wp_section.mount(Label("[dim]No wallpapers[/]"))

        # Wallpaper info / thumbnail for first wallpaper
        wp_info = self.query_one("#wp-info", WallpaperInfo)
        first_mw = theme.monitor_wallpapers[0] if theme.monitor_wallpapers else None
        wp_info.set_wallpaper(first_mw)
        if first_mw and shutil.which("chafa"):
            wp_info.set_chafa(first_mw.path)

        # Color swatches
        colors_panel = self.query_one("#detail-colors")
        colors_panel.remove_children()
        for key in COLOR_KEYS:
            hex_val = theme.colors.get(key, "#333333")
            label = COLOR_LABELS.get(key, key)
            swatch = Static(f"[bold]{label}[/]\n{hex_val}", classes="mini-swatch")
            try:
                swatch.styles.background = hex_val
                swatch.styles.color = _fg_for(hex_val)
            except Exception:
                pass
            colors_panel.mount(swatch)

        # Terminal preview
        self.query_one("#term-preview", TerminalPreview).refresh_colors(theme.colors)

    @on(Button.Pressed, ".btn-open-wp")
    def open_wallpaper(self, event: Button.Pressed) -> None:
        path = getattr(event.button, "data", None)
        if path:
            open_in_viewer(path)
            self.notify(f"Opening {path.name} in imv…")

    def _selected_theme(self) -> Theme | None:
        idx = self.query_one("#theme-listview", ListView).index
        if idx is None or idx >= len(self._themes):
            return None
        return self._themes[idx]

    def action_new_theme(self) -> None:
        self.app.push_screen(WizardScreen(), callback=self._on_return)

    def action_edit_theme(self) -> None:
        theme = self._selected_theme()
        if theme is None:
            return
        if theme.is_stock:
            theme = self._fork_stock_theme(theme)
        self.app.push_screen(ThemeEditorScreen(theme), callback=self._on_return)

    def _fork_stock_theme(self, stock: Theme) -> Theme:
        dest = OMARCHY_THEMES / stock.name
        dest.mkdir(parents=True, exist_ok=True)
        if stock.colors_file.exists():
            shutil.copy2(stock.colors_file, dest / "colors.toml")
        dest_bg = dest / "backgrounds"
        dest_bg.mkdir(exist_ok=True)
        if stock.backgrounds_dir.exists():
            for f in stock.backgrounds_dir.iterdir():
                if f.is_file():
                    shutil.copy2(f, dest_bg / f.name)
        user_theme = Theme(name=stock.name, path=dest, is_stock=False)
        user_theme.load()
        self.notify(f"Forked '{stock.name}' to your themes — changes won't be lost on updates.")
        return user_theme

    @work(thread=True)
    def action_apply_theme(self) -> None:
        theme = self._selected_theme()
        if theme is None:
            return
        result = omarchy_mod.apply_theme(theme)
        if result.returncode != 0:
            self.app.call_from_thread(self.notify, f"omarchy error: {result.stderr}", severity="error")
            return
        apply_wallpapers(theme)
        self.app.call_from_thread(self.notify, f"Applied: {theme.name}")
        self.app.call_from_thread(self._load_themes)

    def action_delete_theme(self) -> None:
        theme = self._selected_theme()
        if theme is None:
            return
        if theme.is_stock:
            self.notify("Cannot delete stock themes.", severity="warning")
            return
        self.app.push_screen(
            ConfirmModal(f"Delete '{theme.name}'? This cannot be undone."),
            callback=lambda confirmed: self._do_delete(theme, confirmed),
        )

    def _do_delete(self, theme: Theme, confirmed: bool) -> None:
        if not confirmed:
            return
        shutil.rmtree(theme.path)
        self._load_themes()
        self.notify(f"Deleted: {theme.name}")

    def action_refresh(self) -> None:
        self._load_themes()
        self.notify("Themes refreshed.")

    def _on_return(self, _=None) -> None:
        self._load_themes()

    def action_quit(self) -> None:
        self.app.exit()


# ── App ────────────────────────────────────────────────────────────────────────

class PywalrchyApp(App):
    TITLE = f"pywalrchy {__version__}"
    SUB_TITLE = "Omarchy wallpaper & theme manager"
    CSS = """
    Screen { background: $surface; }
    """

    def on_mount(self) -> None:
        colors = load_current_colors()
        if colors:
            self.register_theme(build_textual_theme(colors))
            self.theme = "omarchy"
        self.push_screen(ThemeBrowserScreen())

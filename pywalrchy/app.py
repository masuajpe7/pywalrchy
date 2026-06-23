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
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Select,
    Static,
)

from pywalrchy import __version__
from pywalrchy.config import COLOR_KEYS, COLOR_LABELS
from pywalrchy.hyprpaper import apply_wallpapers, get_monitors
from pywalrchy import omarchy as omarchy_mod
from pywalrchy import pywal
from pywalrchy.theme import Theme, MonitorWallpaper, active_theme_name, create_theme, list_themes


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
        self.colors = dict(colors)
        self._editing_key: str | None = None

    def compose(self) -> ComposeResult:
        with Container(classes="palette-grid"):
            for key in COLOR_KEYS:
                yield ColorSwatch(key=key, hex_color=self.colors.get(key, "#000000"), id=f"swatch-{key}")
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
        inp.value = self.colors.get(event.key, "#000000")
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
        self.colors[self._editing_key] = value
        self.query_one(f"#swatch-{self._editing_key}", ColorSwatch).update_color(value)
        self._editing_key = None
        self.query_one("#edit-row").remove_class("visible")
        self.post_message(self.ColorsChanged(dict(self.colors)))

    @on(Button.Pressed, "#btn-cancel")
    def cancel_edit(self) -> None:
        self._editing_key = None
        self.query_one("#edit-row").remove_class("visible")

    def reload(self, colors: dict[str, str]) -> None:
        self.colors = dict(colors)
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
    ThemeEditorScreen .wallpaper-row {
        height: 2; padding: 0 1; align: left middle;
    }
    ThemeEditorScreen .wallpaper-row Label { width: 1fr; }
    ThemeEditorScreen #add-row { height: 3; margin-top: 1; }
    ThemeEditorScreen #monitor-select { width: 20; }
    ThemeEditorScreen #wp-info-editor { height: 5; padding: 0 1; color: $text-muted; }
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
                yield Static("", id="wp-info-editor")
                yield ScrollableContainer(id="wallpaper-list")
                yield Label("Add wallpaper:", classes="panel-title")
                with Horizontal(id="add-row"):
                    yield Select(
                        [(m, m) for m in self._monitors],
                        id="monitor-select", prompt="Monitor",
                    )
                    yield Input(placeholder="Path to image", id="wp-path-input")
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
            row = Horizontal(classes="wallpaper-row")
            lbl = Label(f"[bold]{mw.monitor}[/]  {mw.path.name}")
            btn = Button("Open", classes="btn-open-wp", variant="default")
            btn.data = mw.path  # type: ignore[attr-defined]
            row.mount(lbl, btn)
            container.mount(row)

    @on(Button.Pressed, ".btn-open-wp")
    def open_wallpaper(self, event: Button.Pressed) -> None:
        path = getattr(event.button, "data", None)
        if path:
            open_in_viewer(path)

    @on(PaletteEditor.ColorsChanged)
    def colors_updated(self, event: PaletteEditor.ColorsChanged) -> None:
        self._colors = event.colors

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
            body.mount(Button("Add", id="btn-add-wp", variant="success"))

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
                self._colors = dict(self.query_one("#palette", PaletteEditor).colors)
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
    ThemeBrowserScreen .wallpaper-row {
        height: 2;
        align: left middle;
    }
    ThemeBrowserScreen .wallpaper-row Label { width: 1fr; }
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
        if self._themes:
            self._show_detail(0)

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
                row = Horizontal(classes="wallpaper-row")
                tag = f"[dim]{mw.monitor}[/]" if mw.monitor == "unassigned" else f"[bold]{mw.monitor}[/]"
                lbl = Label(f"{tag}  {mw.path.name}")
                btn = Button("Open", classes="btn-open-wp", variant="default")
                btn.data = mw.path  # type: ignore[attr-defined]
                row.mount(lbl, btn)
                wp_section.mount(row)
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
            self.notify("Stock themes are read-only. Create a new theme to customise.", severity="warning")
            return
        self.app.push_screen(ThemeEditorScreen(theme), callback=self._on_return)

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
        self.push_screen(ThemeBrowserScreen())

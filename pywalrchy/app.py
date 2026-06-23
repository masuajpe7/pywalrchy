from __future__ import annotations

import re
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
from pywalrchy.theme import Theme, active_theme_name, create_theme, list_themes


# ── Color swatch widget ────────────────────────────────────────────────────────

class ColorSwatch(Widget):
    """A colored block showing a hex value, clickable to edit."""

    DEFAULT_CSS = """
    ColorSwatch {
        width: 1fr;
        height: 3;
        border: tall transparent;
        padding: 0 1;
        content-align: center middle;
    }
    ColorSwatch:focus {
        border: tall $accent;
    }
    ColorSwatch:hover {
        border: tall $primary;
    }
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
            color = Color.parse(self.hex_color)
            r, g, b = color.r, color.g, color.b
            luma = 0.299 * r + 0.587 * g + 0.114 * b
            fg = "#000000" if luma > 128 else "#ffffff"
            self.styles.background = self.hex_color
            self.styles.color = fg
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
    """Grid of color swatches with inline editing."""

    DEFAULT_CSS = """
    PaletteEditor {
        height: auto;
    }
    PaletteEditor .palette-grid {
        layout: grid;
        grid-size: 4;
        grid-gutter: 1;
        height: auto;
        padding: 1;
    }
    PaletteEditor .edit-row {
        height: 3;
        padding: 0 1;
        display: none;
    }
    PaletteEditor .edit-row.visible {
        display: block;
    }
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
                hex_val = self.colors.get(key, "#000000")
                yield ColorSwatch(key=key, hex_color=hex_val, id=f"swatch-{key}")
        with Horizontal(classes="edit-row", id="edit-row"):
            yield Label("Hex: ", id="edit-label")
            yield Input(placeholder="#rrggbb", id="color-input")
            yield Button("Set", id="btn-set", variant="primary")
            yield Button("Cancel", id="btn-cancel")

    @on(ColorSwatch.Clicked)
    def start_editing(self, event: ColorSwatch.Clicked) -> None:
        self._editing_key = event.key
        edit_row = self.query_one("#edit-row")
        edit_row.add_class("visible")
        label = self.query_one("#edit-label", Label)
        label.update(f"{COLOR_LABELS.get(event.key, event.key)}: ")
        inp = self.query_one("#color-input", Input)
        inp.value = self.colors.get(event.key, "#000000")
        inp.focus()

    @on(Button.Pressed, "#btn-set")
    def confirm_edit(self) -> None:
        self._apply_edit()

    @on(Button.Pressed, "#btn-cancel")
    def cancel_edit(self) -> None:
        self._editing_key = None
        self.query_one("#edit-row").remove_class("visible")

    @on(Input.Submitted, "#color-input")
    def input_submitted(self) -> None:
        self._apply_edit()

    def _apply_edit(self) -> None:
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
        swatch = self.query_one(f"#swatch-{self._editing_key}", ColorSwatch)
        swatch.update_color(value)
        self._editing_key = None
        self.query_one("#edit-row").remove_class("visible")
        self.post_message(self.ColorsChanged(dict(self.colors)))

    def reload(self, colors: dict[str, str]) -> None:
        self.colors = dict(colors)
        for key in COLOR_KEYS:
            try:
                swatch = self.query_one(f"#swatch-{key}", ColorSwatch)
                swatch.update_color(colors.get(key, "#000000"))
            except Exception:
                pass


# ── Edit hex modal ─────────────────────────────────────────────────────────────

class ConfirmModal(ModalScreen):
    """Simple yes/no confirmation."""

    DEFAULT_CSS = """
    ConfirmModal {
        align: center middle;
    }
    ConfirmModal #dialog {
        width: 60;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 2 4;
    }
    ConfirmModal #buttons {
        margin-top: 1;
        align: center middle;
    }
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
    """Edit colors and wallpapers for an existing custom theme."""

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
    ThemeEditorScreen #left-panel {
        border: round $primary;
        padding: 1;
    }
    ThemeEditorScreen #right-panel {
        border: round $primary;
        padding: 1;
    }
    ThemeEditorScreen .panel-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    ThemeEditorScreen .wallpaper-item {
        height: 2;
        padding: 0 1;
    }
    ThemeEditorScreen #add-wallpaper-row {
        height: 3;
        margin-top: 1;
    }
    ThemeEditorScreen #monitor-select {
        width: 20;
    }
    ThemeEditorScreen #wp-path-input {
        width: 1fr;
    }
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
                yield Label("Add wallpaper:", classes="panel-title")
                with Horizontal(id="add-wallpaper-row"):
                    monitor_opts = [(m, m) for m in self._monitors]
                    yield Select(
                        monitor_opts,
                        id="monitor-select",
                        prompt="Monitor",
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
            container.mount(Label("No wallpapers assigned yet."))
            return
        for mw in self.theme.monitor_wallpapers:
            row = Horizontal(classes="wallpaper-item")
            row.mount(Label(f"[bold]{mw.monitor}[/] → {mw.path.name}"))
            container.mount(row)

    @on(PaletteEditor.ColorsChanged)
    def colors_updated(self, event: PaletteEditor.ColorsChanged) -> None:
        self._colors = event.colors

    @on(Button.Pressed, "#btn-add-wp")
    def add_wallpaper(self) -> None:
        monitor_sel = self.query_one("#monitor-select", Select)
        path_inp = self.query_one("#wp-path-input", Input)
        monitor = monitor_sel.value
        path_str = path_inp.value.strip()
        if not monitor or monitor is Select.BLANK or not path_str:
            self.notify("Select a monitor and enter a path.", severity="error")
            return
        src = Path(path_str).expanduser()
        if not src.exists():
            self.notify(f"File not found: {src}", severity="error")
            return
        self.theme.add_wallpaper(src, str(monitor))
        path_inp.value = ""
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
            self.app.call_from_thread(
                self.notify, f"omarchy error: {result.stderr}", severity="error"
            )
            return
        apply_wallpapers(self.theme)
        self.app.call_from_thread(self.notify, "Theme applied!")

    def action_go_back(self) -> None:
        self.app.pop_screen()


# ── New theme wizard ───────────────────────────────────────────────────────────

class WizardScreen(Screen):
    """Multi-step wizard: name → wallpapers → colors → apply."""

    BINDINGS = [Binding("escape", "go_back", "Back")]

    DEFAULT_CSS = """
    WizardScreen #wizard-body {
        padding: 2 4;
        height: 1fr;
    }
    WizardScreen .step-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    WizardScreen .step-hint {
        color: $text-muted;
        margin-bottom: 1;
    }
    WizardScreen .row {
        height: 3;
        margin-bottom: 1;
        align: left middle;
    }
    WizardScreen #monitor-sel {
        width: 20;
    }
    WizardScreen #wp-input {
        width: 1fr;
    }
    WizardScreen #wallpaper-assignments {
        height: auto;
        margin-bottom: 1;
    }
    WizardScreen #step-nav {
        dock: bottom;
        height: 3;
        align: right middle;
        padding: 0 2;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._step = 1
        self._theme_name = ""
        self._theme: Theme | None = None
        self._colors: dict[str, str] = {}
        self._monitors = get_monitors()
        self._assignments: dict[str, Path] = {}  # monitor → src path

    def compose(self) -> ComposeResult:
        yield Header()
        yield ScrollableContainer(id="wizard-body")
        with Horizontal(id="step-nav"):
            yield Button("Back", id="btn-prev")
            yield Button("Next →", id="btn-next", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self._render_step()

    def _render_step(self) -> None:
        body = self.query_one("#wizard-body")
        body.remove_children()
        prev_btn = self.query_one("#btn-prev", Button)
        next_btn = self.query_one("#btn-next", Button)
        prev_btn.disabled = self._step == 1

        if self._step == 1:
            next_btn.label = "Next →"
            body.mount(Label("Step 1 — Theme name", classes="step-title"))
            body.mount(Label("Give this theme a name.", classes="step-hint"))
            inp = Input(
                value=self._theme_name,
                placeholder="e.g. my-ocean-theme",
                id="name-input",
            )
            body.mount(inp)
            inp.focus()

        elif self._step == 2:
            next_btn.label = "Next →"
            body.mount(Label("Step 2 — Assign wallpapers", classes="step-title"))
            body.mount(
                Label(
                    "Assign a wallpaper to each monitor. "
                    "The first one will be used for color extraction.",
                    classes="step-hint",
                )
            )
            assignments_display = Vertical(id="wallpaper-assignments")
            body.mount(assignments_display)
            self._refresh_assignments(assignments_display)

            with Horizontal(classes="row"):
                monitor_opts = [(m, m) for m in self._monitors]
                sel = Select(monitor_opts, id="monitor-sel", prompt="Monitor")
                inp = Input(placeholder="Path to image", id="wp-input")
                btn = Button("Add", id="btn-add-wp", variant="success")
            body.mount(sel)
            body.mount(inp)
            body.mount(btn)

        elif self._step == 3:
            next_btn.label = "Next →"
            body.mount(Label("Step 3 — Edit colors", classes="step-title"))
            body.mount(
                Label("Colors extracted from wallpaper. Click any swatch to edit.", classes="step-hint")
            )
            if self._colors:
                body.mount(PaletteEditor(self._colors, id="palette"))
            else:
                body.mount(Label("No colors extracted yet."))

        elif self._step == 4:
            next_btn.label = "Finish & Apply"
            body.mount(Label("Step 4 — Confirm", classes="step-title"))
            body.mount(Label(f"Theme: [bold]{self._theme_name}[/]"))
            body.mount(Label(f"Monitors: {len(self._assignments)} wallpaper(s) assigned"))
            body.mount(Label(f"Colors: {len(self._colors)} defined"))
            body.mount(Label("\nPress [bold]Finish & Apply[/] to create and activate the theme."))

    def _refresh_assignments(self, container: Widget | None = None) -> None:
        if container is None:
            try:
                container = self.query_one("#wallpaper-assignments")
            except Exception:
                return
        container.remove_children()
        if not self._assignments:
            container.mount(Label("No wallpapers assigned yet."))
            return
        for monitor, path in self._assignments.items():
            container.mount(Label(f"  [bold]{monitor}[/] → {path.name}"))

    @on(Button.Pressed, "#btn-add-wp")
    def add_assignment(self) -> None:
        try:
            monitor = self.query_one("#monitor-sel", Select).value
            path_str = self.query_one("#wp-input", Input).value.strip()
        except Exception:
            return
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
                palette = self.query_one("#palette", PaletteEditor)
                self._colors = dict(palette.colors)
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
        first_path = next(iter(self._assignments.values()))
        try:
            colors = pywal.extract_colors(first_path)
            self._colors = colors
            self.app.call_from_thread(self._go_to_color_step)
        except Exception as e:
            self.app.call_from_thread(
                self.notify, f"Color extraction failed: {e}", severity="error"
            )

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
            self.app.call_from_thread(
                self.notify, f"omarchy error: {result.stderr}", severity="error"
            )
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
    """Home screen — lists all themes."""

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
        grid-size: 2;
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
    ThemeBrowserScreen .panel-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    ThemeBrowserScreen .active-badge {
        color: $success;
    }
    ThemeBrowserScreen .stock-badge {
        color: $text-muted;
    }
    ThemeBrowserScreen #detail-colors {
        layout: grid;
        grid-size: 4;
        grid-gutter: 1;
        height: auto;
        padding: 1;
    }
    ThemeBrowserScreen .mini-swatch {
        height: 2;
        content-align: center middle;
    }
    ThemeBrowserScreen #detail-info {
        margin-bottom: 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._themes: list[Theme] = []
        self._selected_idx = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="browser-layout"):
            with Vertical(id="theme-list-panel"):
                yield Label("Themes", classes="panel-title")
                yield ListView(id="theme-listview")
            with ScrollableContainer(id="detail-panel"):
                yield Label("Theme detail", classes="panel-title", id="detail-title")
                yield Vertical(id="detail-info")
                yield Label("Color palette", classes="panel-title")
                yield Horizontal(id="detail-colors")
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
            stock = " [stock]" if theme.is_stock else ""
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

        title = self.query_one("#detail-title", Label)
        title.update(
            f"{'[green]● Active[/] ' if theme.name == active else ''}"
            f"[bold]{theme.name}[/]"
            f"{'  [dim][stock][/]' if theme.is_stock else ''}"
        )

        info = self.query_one("#detail-info")
        info.remove_children()
        wp_count = len(theme.monitor_wallpapers)
        info.mount(Label(f"Wallpapers: {wp_count}"))
        for mw in theme.monitor_wallpapers:
            info.mount(Label(f"  [dim]{mw.monitor}[/] → {mw.path.name}"))

        colors_panel = self.query_one("#detail-colors")
        colors_panel.remove_children()
        for key in COLOR_KEYS[:16]:
            hex_val = theme.colors.get(key, "#333333")
            label = COLOR_LABELS.get(key, key)
            swatch = Static(f"[bold]{label}[/]\n{hex_val}", classes="mini-swatch")
            try:
                color = Color.parse(hex_val)
                r, g, b = color.r, color.g, color.b
                luma = 0.299 * r + 0.587 * g + 0.114 * b
                fg = "black" if luma > 128 else "white"
                swatch.styles.background = hex_val
                swatch.styles.color = fg
            except Exception:
                pass
            colors_panel.mount(swatch)

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
            self.notify("Cannot edit stock themes. Fork it first by creating a new theme.", severity="warning")
            return
        self.app.push_screen(ThemeEditorScreen(theme), callback=self._on_return)

    @work(thread=True)
    def action_apply_theme(self) -> None:
        theme = self._selected_theme()
        if theme is None:
            return
        result = omarchy_mod.apply_theme(theme)
        if result.returncode != 0:
            self.app.call_from_thread(
                self.notify, f"omarchy error: {result.stderr}", severity="error"
            )
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
            ConfirmModal(f"Delete theme '{theme.name}'? This cannot be undone."),
            callback=lambda confirmed: self._do_delete(theme, confirmed),
        )

    def _do_delete(self, theme: Theme, confirmed: bool) -> None:
        if not confirmed:
            return
        import shutil
        shutil.rmtree(theme.path)
        self._load_themes()
        self.notify(f"Deleted: {theme.name}")

    def action_refresh(self) -> None:
        self._load_themes()

    def _on_return(self, _=None) -> None:
        self._load_themes()

    def action_quit(self) -> None:
        self.app.exit()


# ── App ────────────────────────────────────────────────────────────────────────

class PywalrchyApp(App):
    TITLE = f"pywalrchy {__version__}"
    SUB_TITLE = "Omarchy theme manager"
    CSS = """
    Screen {
        background: $surface;
    }
    """

    def on_mount(self) -> None:
        self.push_screen(ThemeBrowserScreen())

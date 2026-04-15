"""Optional system-tray icon.

Shows Polyglot's current state (idle / recording / transcribing) and a
menu for quickly switching language, toggling provider, or quitting. The
tray is best-effort: if pystray/Pillow aren't installed, polyglot.py
will run fine without it.
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

log = logging.getLogger("polyglot.tray")

if TYPE_CHECKING:
    from polyglot import PolyglotApp


def _make_icon(color: tuple[int, int, int]):
    from PIL import Image, ImageDraw  # type: ignore

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Rounded-square background
    d.rounded_rectangle([(4, 4), (size - 4, size - 4)], radius=14, fill=color)
    # Microphone capsule
    d.rounded_rectangle(
        [(size // 2 - 8, 16), (size // 2 + 8, 36)],
        radius=8,
        fill=(255, 255, 255, 230),
    )
    # Stand
    d.rectangle([(size // 2 - 1, 38), (size // 2 + 1, 48)], fill=(255, 255, 255, 230))
    d.rectangle([(size // 2 - 10, 47), (size // 2 + 10, 50)], fill=(255, 255, 255, 230))
    return img


COLORS = {
    "idle":          (124, 92, 255),   # violet
    "recording":     (239, 68, 68),    # red
    "transcribing":  (245, 158, 11),   # amber
}


class TrayIcon:
    def __init__(self, app: "PolyglotApp") -> None:
        try:
            import pystray  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "pystray is not installed. Run: pip install pystray pillow"
            ) from exc
        self._pystray = pystray
        self.app = app
        self._icon = None
        self._state = "idle"
        self._lock = threading.Lock()

    def _build_menu(self):
        pystray = self._pystray

        def quit_app(icon, item):  # noqa: ARG001
            log.info("quit from tray")
            icon.stop()

        def toggle_record(icon, item):  # noqa: ARG001
            self.app.toggle_recording()

        return pystray.Menu(
            pystray.MenuItem(
                lambda text: f"Status: {self._state.capitalize()}",
                None,
                enabled=False,
            ),
            pystray.MenuItem(
                lambda text: f"Language: {self.app.config.language}",
                None,
                enabled=False,
            ),
            pystray.MenuItem(
                lambda text: f"Hotkey: {self.app.config.hotkey}",
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Start / stop dictation", toggle_record, default=True),
            pystray.MenuItem("Quit", quit_app),
        )

    def run(self) -> None:
        pystray = self._pystray
        icon = pystray.Icon(
            "polyglot",
            icon=_make_icon(COLORS["idle"]),
            title="Polyglot — idle",
            menu=self._build_menu(),
        )
        self._icon = icon
        icon.run()

    def set_state(self, state: str) -> None:
        with self._lock:
            self._state = state
        if self._icon is None:
            return
        try:
            self._icon.icon = _make_icon(COLORS.get(state, COLORS["idle"]))
            self._icon.title = f"Polyglot — {state}"
        except Exception as exc:
            log.debug("tray update failed: %s", exc)

    def notify(self, message: str) -> None:
        if self._icon is None:
            return
        try:
            self._icon.notify(message, "Polyglot")
        except Exception as exc:
            log.debug("tray notify failed: %s", exc)

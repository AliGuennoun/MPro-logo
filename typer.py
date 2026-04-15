"""Cross-platform text insertion.

Two strategies:

1. 'paste' (default) — push text onto the OS clipboard, then synthesize the
   paste hotkey (Cmd+V on macOS, Ctrl+V elsewhere). This is the most reliable
   way to insert arbitrary Unicode (emoji, Arabic, CJK, diacritics) into any
   application without losing characters to dead-key or layout translation.

2. 'keystrokes' — type each character via pynput. Works without the
   clipboard but can mangle characters on non-US keyboard layouts.

Both strategies restore whatever was already on the clipboard when possible.
"""
from __future__ import annotations

import logging
import platform
import time

log = logging.getLogger("polyglot.typer")


class TextTyper:
    def __init__(self, method: str = "paste") -> None:
        self.method = method.lower()
        self._is_macos = platform.system() == "Darwin"
        self._kb = None

    def type_text(self, text: str) -> None:
        if not text:
            return
        if self.method == "paste":
            self._type_via_paste(text)
        else:
            self._type_via_keystrokes(text)

    # ---------------- paste ----------------
    def _type_via_paste(self, text: str) -> None:
        try:
            import pyperclip  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "The 'pyperclip' package is required for paste mode. "
                "Install with: pip install pyperclip"
            ) from exc

        # Save previous clipboard so we don't clobber it forever.
        try:
            previous = pyperclip.paste()
        except Exception:
            previous = None

        pyperclip.copy(text)
        # Small delay to let the clipboard settle (matters on Windows/X11).
        time.sleep(0.05)
        self._send_paste_hotkey()
        # Restore clipboard after a beat so the paste has time to land.
        if previous is not None:
            def _restore() -> None:
                try:
                    time.sleep(0.4)
                    pyperclip.copy(previous)
                except Exception:
                    pass

            import threading

            threading.Thread(target=_restore, daemon=True).start()

    def _send_paste_hotkey(self) -> None:
        self._ensure_kb()
        from pynput.keyboard import Key

        modifier = Key.cmd if self._is_macos else Key.ctrl
        with self._kb.pressed(modifier):
            self._kb.press("v")
            self._kb.release("v")

    # ---------------- keystrokes ----------------
    def _type_via_keystrokes(self, text: str) -> None:
        self._ensure_kb()
        # Type in small chunks so we don't overwhelm slow target apps.
        for chunk_start in range(0, len(text), 50):
            self._kb.type(text[chunk_start : chunk_start + 50])
            time.sleep(0.02)

    # ---------------- shared ----------------
    def _ensure_kb(self) -> None:
        if self._kb is None:
            from pynput.keyboard import Controller  # type: ignore

            self._kb = Controller()

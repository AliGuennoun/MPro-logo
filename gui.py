"""Modern desktop GUI for Polyglot (CustomTkinter).

The window shows live state + transcript history and exposes every mode
(Dictate / Translate / Cleanup / Both) without needing to edit a JSON
file. It's optional — polyglot.py will run headless with --no-gui — but
it's the nicest way to use the translation + cleanup features.

Threading:
  • Tk must run on the main thread. The hotkey listener and transcription
    pipeline run on background threads.
  • Any UI mutation from a background thread must be scheduled on the Tk
    thread via self.root.after(0, callback).
"""
from __future__ import annotations

import logging
import threading
import tkinter as tk
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Optional

log = logging.getLogger("polyglot.gui")

try:
    import customtkinter as ctk
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "customtkinter is required for the GUI.\n"
        "Install with: pip install customtkinter"
    ) from exc

if TYPE_CHECKING:
    from polyglot import PolyglotApp


# Curated source-language list for the "Language" picker. Whisper/Groq
# accept the ISO-639-1 code; "auto" means let Whisper detect.
SOURCE_LANGUAGES = [
    ("Auto-detect", "auto"),
    ("English", "en"), ("French", "fr"), ("Spanish", "es"), ("German", "de"),
    ("Italian", "it"), ("Portuguese", "pt"), ("Dutch", "nl"), ("Polish", "pl"),
    ("Russian", "ru"), ("Ukrainian", "uk"), ("Turkish", "tr"), ("Greek", "el"),
    ("Arabic", "ar"), ("Hebrew", "he"), ("Persian", "fa"), ("Urdu", "ur"),
    ("Hindi", "hi"), ("Bengali", "bn"), ("Tamil", "ta"), ("Telugu", "te"),
    ("Chinese", "zh"), ("Japanese", "ja"), ("Korean", "ko"), ("Vietnamese", "vi"),
    ("Thai", "th"), ("Indonesian", "id"), ("Malay", "ms"), ("Swahili", "sw"),
    ("Afrikaans", "af"), ("Czech", "cs"), ("Hungarian", "hu"), ("Romanian", "ro"),
    ("Swedish", "sv"), ("Norwegian", "no"), ("Danish", "da"), ("Finnish", "fi"),
    ("Catalan", "ca"), ("Welsh", "cy"), ("Icelandic", "is"),
]

# Target languages for the translator — displayed by English name since
# we pass the name verbatim into the system prompt.
TARGET_LANGUAGES = [
    "English", "French", "Spanish", "German", "Italian", "Portuguese",
    "Dutch", "Polish", "Russian", "Ukrainian", "Turkish", "Greek",
    "Arabic", "Hebrew", "Persian", "Urdu",
    "Hindi", "Bengali", "Tamil", "Telugu",
    "Chinese (Simplified)", "Chinese (Traditional)", "Japanese", "Korean",
    "Vietnamese", "Thai", "Indonesian", "Malay", "Swahili",
    "Czech", "Hungarian", "Romanian", "Swedish", "Norwegian", "Danish",
    "Finnish", "Catalan", "Welsh",
]

MODE_LABELS = [
    ("Dictate — just transcribe", "dictate"),
    ("Translate — transcribe → translate", "translate"),
    ("Clean up — fix filler words & grammar", "cleanup"),
    ("Both — type translation, show both", "both"),
]


# -------------------------------- Helpers --------------------------------
def _lang_name_to_code(name: str) -> str:
    for label, code in SOURCE_LANGUAGES:
        if label == name:
            return code
    return "auto"


def _lang_code_to_name(code: str) -> str:
    for label, c in SOURCE_LANGUAGES:
        if c == code:
            return label
    return "Auto-detect"


def _mode_label_to_value(label: str) -> str:
    for l, v in MODE_LABELS:
        if l == label:
            return v
    return "dictate"


def _mode_value_to_label(value: str) -> str:
    for l, v in MODE_LABELS:
        if v == value:
            return l
    return MODE_LABELS[0][0]


# ================================ Main UI ================================
class PolyglotGUI:
    def __init__(self, app: "PolyglotApp") -> None:
        self.app = app
        self.config = app.config

        ctk.set_appearance_mode(self.config.theme if self.config.theme in ("dark", "light") else "system")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("Polyglot — AI Voice Dictation")
        self.root.geometry("780x620")
        self.root.minsize(640, 480)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._building = True
        self._history: list[dict] = []
        self._build_ui()
        self._building = False

        # Wire app events so the GUI stays in sync with the background pipeline.
        app.on_state_change = self._on_state_change  # type: ignore[attr-defined]
        app.on_transcription = self._on_transcription  # type: ignore[attr-defined]
        app.on_error = self._on_error  # type: ignore[attr-defined]

    # ---------------- Construction ----------------
    def _build_ui(self) -> None:
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(2, weight=1)

        # Header -------------------------------------------------------------
        header = ctk.CTkFrame(self.root, corner_radius=0, height=72)
        header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header.grid_columnconfigure(1, weight=1)

        self.status_dot = ctk.CTkLabel(
            header, text="●", font=ctk.CTkFont(size=22), text_color="#6b7489"
        )
        self.status_dot.grid(row=0, column=0, padx=(18, 8), pady=16, sticky="w")

        title = ctk.CTkLabel(
            header,
            text="Polyglot",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        title.grid(row=0, column=1, sticky="w", pady=(12, 0))

        self.status_label = ctk.CTkLabel(
            header,
            text="Ready — press the hotkey anywhere to dictate",
            font=ctk.CTkFont(size=12),
            text_color=("#4b5468", "#9aa3b9"),
        )
        self.status_label.grid(row=1, column=1, sticky="w", pady=(0, 12))

        self.hotkey_badge = ctk.CTkLabel(
            header,
            text=self._pretty_hotkey(self.config.hotkey),
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#e3e6ef", "#1a1f2e"),
            corner_radius=999,
            padx=14,
            pady=4,
        )
        self.hotkey_badge.grid(row=0, column=2, rowspan=2, padx=18, pady=16, sticky="e")

        # Controls row ------------------------------------------------------
        controls = ctk.CTkFrame(self.root, corner_radius=0)
        controls.grid(row=1, column=0, sticky="ew", padx=0, pady=(1, 1))
        for c in range(4):
            controls.grid_columnconfigure(c, weight=1)

        self._labeled(controls, "Mode", 0, 0)
        self.mode_var = ctk.StringVar(value=_mode_value_to_label(self.config.mode))
        self.mode_menu = ctk.CTkOptionMenu(
            controls,
            variable=self.mode_var,
            values=[l for l, _ in MODE_LABELS],
            command=self._on_mode_changed,
        )
        self.mode_menu.grid(row=1, column=0, padx=(16, 8), pady=(0, 12), sticky="ew")

        self._labeled(controls, "Source language", 0, 1)
        self.lang_var = ctk.StringVar(value=_lang_code_to_name(self.config.language))
        self.lang_menu = ctk.CTkOptionMenu(
            controls,
            variable=self.lang_var,
            values=[l for l, _ in SOURCE_LANGUAGES],
            command=self._on_language_changed,
        )
        self.lang_menu.grid(row=1, column=1, padx=8, pady=(0, 12), sticky="ew")

        self._labeled(controls, "Translate to", 0, 2)
        self.target_var = ctk.StringVar(value=self.config.target_language)
        self.target_menu = ctk.CTkOptionMenu(
            controls,
            variable=self.target_var,
            values=TARGET_LANGUAGES,
            command=self._on_target_changed,
        )
        self.target_menu.grid(row=1, column=2, padx=8, pady=(0, 12), sticky="ew")

        self._labeled(controls, "Type into focused app", 0, 3)
        self.autotype_var = ctk.BooleanVar(value=self.config.auto_type)
        self.autotype_switch = ctk.CTkSwitch(
            controls,
            text="",
            variable=self.autotype_var,
            command=self._on_autotype_changed,
        )
        self.autotype_switch.grid(row=1, column=3, padx=(8, 16), pady=(0, 12), sticky="w")

        self._refresh_target_state()

        # Transcript area ---------------------------------------------------
        self.transcript = ctk.CTkTextbox(
            self.root,
            wrap="word",
            font=ctk.CTkFont(size=14),
            corner_radius=0,
            activate_scrollbars=True,
        )
        self.transcript.grid(row=2, column=0, sticky="nsew")
        self.transcript.configure(state="disabled")
        self._write_placeholder()

        # Bottom bar -------------------------------------------------------
        bottom = ctk.CTkFrame(self.root, corner_radius=0, height=64)
        bottom.grid(row=3, column=0, sticky="ew", padx=0, pady=(1, 0))
        bottom.grid_columnconfigure(0, weight=1)

        self.record_btn = ctk.CTkButton(
            bottom,
            text="●  Start",
            font=ctk.CTkFont(size=14, weight="bold"),
            width=140,
            height=40,
            corner_radius=999,
            fg_color="#7c5cff",
            hover_color="#6a4ce8",
            command=self._on_record_clicked,
        )
        self.record_btn.grid(row=0, column=0, padx=(16, 8), pady=12, sticky="w")

        ctk.CTkButton(
            bottom, text="Copy", width=80, height=36, corner_radius=999,
            fg_color="transparent", border_width=1, command=self._on_copy_clicked,
        ).grid(row=0, column=1, padx=4, pady=12)

        ctk.CTkButton(
            bottom, text="Clear", width=80, height=36, corner_radius=999,
            fg_color="transparent", border_width=1, command=self._on_clear_clicked,
        ).grid(row=0, column=2, padx=4, pady=12)

        ctk.CTkButton(
            bottom, text="Settings", width=100, height=36, corner_radius=999,
            fg_color="transparent", border_width=1, command=self._on_settings_clicked,
        ).grid(row=0, column=3, padx=(4, 16), pady=12)

    def _labeled(self, parent, text: str, row: int, col: int) -> None:
        lbl = ctk.CTkLabel(
            parent, text=text.upper(),
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=("#6b7489", "#6b7489"),
        )
        lbl.grid(row=row, column=col, padx=(16 if col == 0 else 8, 8), pady=(12, 0), sticky="w")

    def _pretty_hotkey(self, hk: str) -> str:
        return (
            hk.replace("<", "").replace(">", "")
              .replace("ctrl", "Ctrl").replace("alt", "Alt").replace("shift", "Shift")
              .replace("cmd", "⌘").replace("space", "Space")
              .replace("+", " + ")
        )

    def _write_placeholder(self) -> None:
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.insert(
            "1.0",
            "Your dictations will appear here.\n\n"
            f"Press {self._pretty_hotkey(self.config.hotkey)} anywhere on your "
            "desktop, speak in any language, and pause. Polyglot will transcribe "
            "and (optionally) translate your words.\n",
        )
        self.transcript.configure(state="disabled")

    # ---------------- Events from app (background threads) ----------------
    def _on_state_change(self, state: str) -> None:
        self.root.after(0, self._apply_state, state)

    def _on_transcription(self, result) -> None:
        self.root.after(0, self._append_history, result)

    def _on_error(self, message: str) -> None:
        self.root.after(0, self._show_error, message)

    def _apply_state(self, state: str) -> None:
        if state == "recording":
            self.status_dot.configure(text_color="#ef4444")
            self.status_label.configure(text="Recording… speak now")
            self.record_btn.configure(text="●  Stop", fg_color="#ef4444", hover_color="#dc2626")
        elif state == "transcribing":
            self.status_dot.configure(text_color="#f59e0b")
            self.status_label.configure(text="Transcribing…")
            self.record_btn.configure(text="...  Wait", fg_color="#f59e0b", hover_color="#d97706")
        else:  # idle
            self.status_dot.configure(text_color="#22c55e")
            self.status_label.configure(text="Ready — press the hotkey anywhere to dictate")
            self.record_btn.configure(text="●  Start", fg_color="#7c5cff", hover_color="#6a4ce8")

    def _append_history(self, result) -> None:
        # result is a TranscriptionResult; fall back to str() for safety.
        original = getattr(result, "original", str(result))
        processed = getattr(result, "processed", None)
        mode = getattr(result, "processing_mode", None)
        ts = datetime.now().strftime("%H:%M:%S")

        self.transcript.configure(state="normal")
        # First insertion clears the placeholder.
        if not self._history:
            self.transcript.delete("1.0", "end")

        header = f"[{ts}] "
        self.transcript.insert("end", header, ("muted",))
        self.transcript.insert("end", f"{original}\n")
        if processed and processed != original:
            arrow = "→ " + (f"({mode}) " if mode else "")
            self.transcript.insert("end", "         " + arrow, ("muted",))
            self.transcript.insert("end", f"{processed}\n", ("accent",))
        self.transcript.insert("end", "\n")

        self.transcript.tag_config("muted", foreground="#6b7489")
        self.transcript.tag_config("accent", foreground="#7c5cff")

        self.transcript.configure(state="disabled")
        self.transcript.see("end")
        self._history.append({"original": original, "processed": processed, "ts": ts})

    def _show_error(self, message: str) -> None:
        self.status_label.configure(text=f"⚠ {message}", text_color="#ef4444")
        # Also log it in the transcript for visibility.
        self.transcript.configure(state="normal")
        self.transcript.insert("end", f"[error] {message}\n\n", ("error",))
        self.transcript.tag_config("error", foreground="#ef4444")
        self.transcript.configure(state="disabled")
        self.transcript.see("end")
        # Revert status colour after a bit.
        self.root.after(4000, lambda: self.status_label.configure(
            text="Ready — press the hotkey anywhere to dictate",
            text_color=("#4b5468", "#9aa3b9"),
        ))

    # ---------------- UI callbacks ----------------
    def _on_mode_changed(self, label: str) -> None:
        if self._building:
            return
        self.config.mode = _mode_label_to_value(label)
        self._refresh_target_state()
        self._persist_config()

    def _on_language_changed(self, label: str) -> None:
        if self._building:
            return
        self.config.language = _lang_name_to_code(label)
        # Reflect into the live transcriber so next dictation uses it.
        self.app.transcriber.language = None if self.config.language == "auto" else self.config.language
        self._persist_config()

    def _on_target_changed(self, value: str) -> None:
        if self._building:
            return
        self.config.target_language = value
        self._persist_config()

    def _on_autotype_changed(self) -> None:
        if self._building:
            return
        self.config.auto_type = bool(self.autotype_var.get())
        self._persist_config()

    def _refresh_target_state(self) -> None:
        # Disable the target-language picker when translation isn't active.
        needs_target = self.config.mode in ("translate", "both")
        state = "normal" if needs_target else "disabled"
        self.target_menu.configure(state=state)

    def _on_record_clicked(self) -> None:
        self.app.toggle_recording()

    def _on_copy_clicked(self) -> None:
        if not self._history:
            return
        text = "\n\n".join(
            (h.get("processed") or h["original"]) for h in self._history
        )
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_label.configure(text="Copied to clipboard")
        self.root.after(1500, lambda: self.status_label.configure(
            text="Ready — press the hotkey anywhere to dictate",
            text_color=("#4b5468", "#9aa3b9"),
        ))

    def _on_clear_clicked(self) -> None:
        self._history.clear()
        self._write_placeholder()

    def _on_settings_clicked(self) -> None:
        SettingsDialog(self.root, self.app, on_saved=self._on_settings_saved)

    def _on_settings_saved(self) -> None:
        # Refresh display to reflect any changed settings.
        self.hotkey_badge.configure(text=self._pretty_hotkey(self.config.hotkey))
        self.lang_var.set(_lang_code_to_name(self.config.language))
        self.mode_var.set(_mode_value_to_label(self.config.mode))
        self.target_var.set(self.config.target_language)
        self._refresh_target_state()

    # ---------------- Lifecycle ----------------
    def _on_close(self) -> None:
        # Fully quit the app when the window is closed (simpler UX than
        # hide-to-tray, since the tray icon may not always be available).
        self.root.destroy()

    def _persist_config(self) -> None:
        from config import save_config

        try:
            save_config(self.config)
        except Exception as exc:
            log.warning("could not save config: %s", exc)

    def run(self) -> None:
        self.root.mainloop()


# ============================ Settings dialog ============================
class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, app: "PolyglotApp", on_saved: Optional[Callable[[], None]] = None):
        super().__init__(parent)
        self.app = app
        self.config = app.config
        self.on_saved = on_saved
        self.title("Settings")
        self.geometry("540x560")
        self.resizable(False, False)
        # Modal behaviour
        self.transient(parent)
        self.grab_set()

        pad = {"padx": 20, "pady": (8, 0)}

        # API Key + base URL
        self._section("Provider", row=0)

        self._field("API key", row=1, pad=pad)
        self.api_key_entry = ctk.CTkEntry(self, show="•")
        self.api_key_entry.insert(0, self.config.api_key)
        self.api_key_entry.grid(row=2, column=0, sticky="ew", padx=20)

        self._field("Base URL (for Groq, OpenRouter, …)", row=3, pad=pad)
        self.base_url_entry = ctk.CTkEntry(self)
        self.base_url_entry.insert(0, self.config.base_url)
        self.base_url_entry.grid(row=4, column=0, sticky="ew", padx=20)

        # Models
        self._section("Models", row=5)

        self._field("Transcription model", row=6, pad=pad)
        self.model_entry = ctk.CTkEntry(self)
        self.model_entry.insert(0, self.config.model)
        self.model_entry.grid(row=7, column=0, sticky="ew", padx=20)

        self._field("LLM model (for translate / cleanup)", row=8, pad=pad)
        self.llm_entry = ctk.CTkEntry(self)
        self.llm_entry.insert(0, self.config.llm_model)
        self.llm_entry.grid(row=9, column=0, sticky="ew", padx=20)

        # Hotkey + audio
        self._section("Input", row=10)

        self._field("Hotkey (pynput format)", row=11, pad=pad)
        self.hotkey_entry = ctk.CTkEntry(self)
        self.hotkey_entry.insert(0, self.config.hotkey)
        self.hotkey_entry.grid(row=12, column=0, sticky="ew", padx=20)

        # Silence thresholds (sliders)
        self._field("Silence auto-stop (seconds, 0 = disabled)", row=13, pad=pad)
        self.silence_slider = ctk.CTkSlider(self, from_=0, to=5, number_of_steps=50)
        self.silence_slider.set(self.config.silence_duration)
        self.silence_slider.grid(row=14, column=0, sticky="ew", padx=20)

        self._field("Silence threshold (higher = needs louder voice)", row=15, pad=pad)
        self.threshold_slider = ctk.CTkSlider(self, from_=0.001, to=0.1, number_of_steps=100)
        self.threshold_slider.set(self.config.silence_threshold)
        self.threshold_slider.grid(row=16, column=0, sticky="ew", padx=20)

        # Buttons
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=20, column=0, sticky="ew", padx=16, pady=16)
        btns.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            btns, text="Cancel", fg_color="transparent", border_width=1,
            width=100, command=self.destroy,
        ).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(
            btns, text="Save", width=100, command=self._save,
        ).grid(row=0, column=2)

        self.grid_columnconfigure(0, weight=1)

    def _section(self, title: str, row: int) -> None:
        lbl = ctk.CTkLabel(self, text=title.upper(),
                           font=ctk.CTkFont(size=10, weight="bold"),
                           text_color=("#6b7489", "#6b7489"))
        lbl.grid(row=row, column=0, sticky="w", padx=20, pady=(16, 4))

    def _field(self, text: str, row: int, pad: dict) -> None:
        lbl = ctk.CTkLabel(self, text=text, font=ctk.CTkFont(size=12))
        lbl.grid(row=row, column=0, sticky="w", **pad)

    def _save(self) -> None:
        from config import save_config

        c = self.config
        c.api_key = self.api_key_entry.get().strip()
        c.base_url = self.base_url_entry.get().strip()
        c.model = self.model_entry.get().strip() or "whisper-1"
        c.llm_model = self.llm_entry.get().strip() or "llama-3.3-70b-versatile"
        new_hotkey = self.hotkey_entry.get().strip() or c.hotkey
        hotkey_changed = new_hotkey != c.hotkey
        c.hotkey = new_hotkey
        c.silence_duration = float(self.silence_slider.get())
        c.silence_threshold = float(self.threshold_slider.get())

        # Push changes into live components.
        self.app.transcriber.api_key = c.api_key
        self.app.transcriber.base_url = c.base_url or None
        self.app.transcriber.model = c.model
        # Force client recreation so the new credentials are used.
        self.app.transcriber._client = None  # type: ignore[attr-defined]
        if self.app.postprocessor is not None:
            self.app.postprocessor.api_key = c.api_key
            self.app.postprocessor.base_url = c.base_url or None
            self.app.postprocessor.model = c.llm_model
            self.app.postprocessor._client = None  # type: ignore[attr-defined]
        self.app.recorder.silence_duration = c.silence_duration
        self.app.recorder.silence_threshold = c.silence_threshold

        save_config(c)

        if hotkey_changed:
            # Defer to main thread: rebinding touches pynput's thread.
            self.app.request_hotkey_rebind(c.hotkey)  # type: ignore[attr-defined]

        if self.on_saved is not None:
            self.on_saved()
        self.destroy()

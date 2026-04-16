"""Polyglot — AI voice dictation for your entire desktop.

Press a global hotkey anywhere (Word, your browser, chat, email, your terminal)
and start speaking. Polyglot records, transcribes with an AI model that
supports 99+ languages with automatic language detection, optionally
translates or cleans the result, and types it into whatever text field is
focused.

Run with: python polyglot.py  (or `polyglot.bat` on Windows after install)
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from config import Config, load_config, save_config
from recorder import Recorder
from transcriber import Transcriber, TranscriptionError
from typer import TextTyper

try:
    from postprocess import PostProcessor, PostprocessError
except ImportError:  # pragma: no cover
    PostProcessor = None  # type: ignore
    PostprocessError = Exception  # type: ignore

try:
    from pynput import keyboard
except ImportError as exc:  # pragma: no cover
    sys.stderr.write(
        "Missing dependency 'pynput'. Run: pip install -r requirements.txt\n"
    )
    raise

try:
    from tray import TrayIcon  # optional
except Exception:  # pragma: no cover - tray is optional
    TrayIcon = None  # type: ignore

log = logging.getLogger("polyglot")


@dataclass
class TranscriptionResult:
    """Result object emitted to `on_transcription` callbacks."""
    original: str
    processed: Optional[str] = None       # translation or cleanup output
    processing_mode: Optional[str] = None  # "translate", "cleanup", "custom"

    @property
    def final_text(self) -> str:
        return self.processed or self.original


class PolyglotApp:
    """Glues the hotkey, recorder, transcriber, post-processor, and typer together."""

    STATE_IDLE = "idle"
    STATE_RECORDING = "recording"
    STATE_TRANSCRIBING = "transcribing"

    def __init__(self, config: Config):
        self.config = config
        self.recorder = Recorder(
            sample_rate=config.sample_rate,
            channels=1,
            silence_threshold=config.silence_threshold,
            silence_duration=config.silence_duration,
            on_auto_stop=self._handle_auto_stop,
        )
        self.transcriber = Transcriber(
            provider=config.provider,
            api_key=config.api_key,
            model=config.model,
            language=None if config.language == "auto" else config.language,
            base_url=config.base_url or None,
        )
        self.postprocessor: Optional[PostProcessor] = None
        if PostProcessor is not None and config.api_key:
            try:
                self.postprocessor = PostProcessor(
                    api_key=config.api_key,
                    base_url=config.base_url or None,
                    model=config.llm_model,
                )
            except Exception as exc:  # pragma: no cover
                log.warning("could not initialise postprocessor: %s", exc)

        self.typer = TextTyper(method=config.typing_method)
        self.state = self.STATE_IDLE
        self._lock = threading.Lock()
        self.tray: Optional[object] = None

        # Event hooks for optional frontends (GUI, tray, tests…).
        self.on_state_change: Optional[Callable[[str], None]] = None
        self.on_transcription: Optional[Callable[[TranscriptionResult], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

        # Hotkey rebinding plumbing (populated by main()).
        self._rebind_hotkey: Optional[Callable[[str], None]] = None

    # ---------------- State helpers ----------------
    def _set_state(self, new_state: str) -> None:
        with self._lock:
            self.state = new_state
        log.info("state → %s", new_state)
        self._emit_state(new_state)

    def _emit_state(self, new_state: str) -> None:
        if self.tray is not None:
            try:
                self.tray.set_state(new_state)  # type: ignore[attr-defined]
            except Exception:
                pass
        if self.on_state_change is not None:
            try:
                self.on_state_change(new_state)
            except Exception as exc:
                log.warning("on_state_change raised: %s", exc)

    def is_busy(self) -> bool:
        return self.state == self.STATE_TRANSCRIBING

    # ---------------- Hotkey actions ----------------
    def toggle_recording(self) -> None:
        """Toggle recording on/off. Called from the hotkey thread or GUI."""
        if self.is_busy():
            log.debug("ignoring toggle: transcription in flight")
            return
        if self.state == self.STATE_IDLE:
            self._start_recording()
        else:
            self._stop_and_transcribe()

    def _handle_auto_stop(self) -> None:
        """Called from the recorder thread when the VAD detects end of speech."""
        log.debug("auto-stop signal received")
        self._stop_and_transcribe()

    # ---------------- Core pipeline ----------------
    def _start_recording(self) -> None:
        self._set_state(self.STATE_RECORDING)
        try:
            self.recorder.start()
        except Exception as exc:
            log.error("Could not start recording: %s", exc)
            self._emit_error(f"Mic error: {exc}")
            self._set_state(self.STATE_IDLE)

    def _stop_and_transcribe(self) -> None:
        with self._lock:
            if self.state != self.STATE_RECORDING:
                log.debug("ignoring stop: state=%s", self.state)
                return
            self.state = self.STATE_TRANSCRIBING
        self._emit_state(self.STATE_TRANSCRIBING)

        try:
            audio_path = self.recorder.stop_and_save()
        except Exception as exc:
            log.error("Could not stop recording: %s", exc)
            self._emit_error(f"Recorder error: {exc}")
            self._set_state(self.STATE_IDLE)
            return

        if audio_path is None:
            log.info("no audio captured")
            self._emit_error("No speech detected")
            self._set_state(self.STATE_IDLE)
            return

        threading.Thread(
            target=self._run_transcription, args=(audio_path,), daemon=True
        ).start()

    def _run_transcription(self, audio_path: str) -> None:
        try:
            original = self.transcriber.transcribe(audio_path)
        except TranscriptionError as exc:
            log.error("transcription failed: %s", exc)
            self._emit_error(f"Transcription failed: {exc}")
            self._set_state(self.STATE_IDLE)
            return
        except Exception as exc:  # pragma: no cover
            log.exception("unexpected transcription error")
            self._emit_error(f"Unexpected error: {exc}")
            self._set_state(self.STATE_IDLE)
            return
        finally:
            try:
                import os

                os.unlink(audio_path)
            except OSError:
                pass

        original = (original or "").strip()
        if not original:
            log.info("no speech detected")
            self._emit_error("No speech detected")
            self._set_state(self.STATE_IDLE)
            return

        # Post-process according to the configured mode.
        processed: Optional[str] = None
        mode = (self.config.mode or "dictate").lower()
        try:
            if mode == "translate" and self.postprocessor is not None:
                processed = self.postprocessor.translate(
                    original, self.config.target_language
                )
            elif mode == "cleanup" and self.postprocessor is not None:
                processed = self.postprocessor.cleanup(original)
            elif mode == "both" and self.postprocessor is not None:
                processed = self.postprocessor.translate(
                    original, self.config.target_language
                )
            elif self.postprocessor is None and mode in ("translate", "cleanup", "both"):
                log.warning("mode=%s but post-processor unavailable", mode)
                self._emit_error(
                    "Post-processor needs an API key — open Settings to configure."
                )
        except PostprocessError as exc:
            log.error("post-processing failed: %s", exc)
            self._emit_error(f"Post-processing failed: {exc}")
            # Fall through: we'll still emit the raw transcription below.

        result = TranscriptionResult(
            original=original,
            processed=processed,
            processing_mode=mode if processed else None,
        )

        to_type = result.final_text
        if self.config.add_trailing_space and not to_type.endswith(" "):
            to_type += " "

        if self.config.auto_type:
            log.info("typing %d chars", len(to_type))
            try:
                self.typer.type_text(to_type)
            except Exception as exc:
                log.error("typing failed: %s", exc)
                self._emit_error(f"Could not type text: {exc}")
        else:
            log.info("auto_type disabled — %d chars shown only", len(to_type))

        # Notify frontends (GUI, tray, custom callbacks).
        if self.on_transcription is not None:
            try:
                self.on_transcription(result)
            except Exception as exc:
                log.warning("on_transcription raised: %s", exc)

        self._set_state(self.STATE_IDLE)

    # ---------------- Hotkey rebind ----------------
    def request_hotkey_rebind(self, new_hotkey: str) -> None:
        if self._rebind_hotkey is not None:
            self._rebind_hotkey(new_hotkey)

    # ---------------- Misc ----------------
    def _emit_error(self, message: str) -> None:
        log.info("NOTIFY: %s", message)
        if self.tray is not None:
            try:
                self.tray.notify(message)  # type: ignore[attr-defined]
            except Exception:
                pass
        if self.on_error is not None:
            try:
                self.on_error(message)
            except Exception as exc:
                log.warning("on_error raised: %s", exc)

    def shutdown(self) -> None:
        try:
            self.recorder.close()
        except Exception:
            pass


# ============================== entry point ==============================
def _build_hotkey_listener(app: PolyglotApp, hotkey: str) -> keyboard.GlobalHotKeys:
    log.info("registering hotkey: %s", hotkey)
    listener = keyboard.GlobalHotKeys({hotkey: app.toggle_recording})
    listener.daemon = True
    return listener


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="polyglot",
        description="AI voice dictation for your desktop — works in any text field.",
    )
    parser.add_argument("--config", help="Path to config file (defaults to ~/.polyglot/config.json)")
    parser.add_argument("--language", help='BCP-47 code (e.g. "es", "fr", "zh") or "auto"')
    parser.add_argument("--hotkey", help='Toggle hotkey, e.g. "<ctrl>+<alt>+<space>"')
    parser.add_argument("--mode", choices=["dictate", "translate", "cleanup", "both"],
                        help="Override the post-processing mode")
    parser.add_argument("--target-language", help='Target for "translate" / "both" mode, e.g. "French"')
    parser.add_argument("--no-gui", action="store_true", help="Run headless (tray only) — no desktop window")
    parser.add_argument("--no-tray", action="store_true", help="Disable the system-tray icon")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    parser.add_argument("--list-devices", action="store_true", help="List input devices and exit")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.list_devices:
        try:
            import sounddevice as sd

            print(sd.query_devices())
        except Exception as exc:
            print(f"Could not list devices: {exc}", file=sys.stderr)
            return 1
        return 0

    config = load_config(args.config)
    if args.language:
        config.language = args.language
    if args.hotkey:
        config.hotkey = args.hotkey
    if args.mode:
        config.mode = args.mode
    if args.target_language:
        config.target_language = args.target_language
    if args.no_gui:
        config.show_gui = False

    if not config.api_key and config.provider == "openai":
        sys.stderr.write(
            "\nNo API key found.\n"
            "Set OPENAI_API_KEY in your environment, or open Settings inside the app,\n"
            "or edit the config file at:\n"
            f"  {config.path}\n\n"
        )
        # Keep going anyway — the GUI can let the user paste a key.

    app = PolyglotApp(config)

    # Build the hotkey listener and give the app a way to rebind at runtime.
    listener_state = {"listener": _build_hotkey_listener(app, config.hotkey)}
    listener_state["listener"].start()

    def _rebind(new_hotkey: str) -> None:
        try:
            listener_state["listener"].stop()
        except Exception:
            pass
        listener_state["listener"] = _build_hotkey_listener(app, new_hotkey)
        listener_state["listener"].start()
        log.info("hotkey rebound to %s", new_hotkey)

    app._rebind_hotkey = _rebind

    # Optional system tray (works alongside the GUI)
    if TrayIcon is not None and not args.no_tray:
        try:
            app.tray = TrayIcon(app)
            threading.Thread(target=app.tray.run, daemon=True).start()  # type: ignore[attr-defined]
            log.info("tray icon started")
        except Exception as exc:
            log.warning("tray unavailable: %s", exc)

    # GUI (default) or headless console mode
    if config.show_gui:
        try:
            from gui import PolyglotGUI

            print("\n  Polyglot — GUI launching. The hotkey works everywhere, in or out of focus.\n")
            gui = PolyglotGUI(app)
            try:
                gui.run()
            finally:
                try:
                    listener_state["listener"].stop()
                except Exception:
                    pass
                app.shutdown()
            return 0
        except ImportError as exc:
            log.warning("GUI unavailable (%s). Falling back to headless mode.", exc)

    # Headless fallback (tray only, or nothing if --no-tray)
    print(
        f"\n  Polyglot ready — press {config.hotkey} to dictate in {config.language}.\n"
        f"  Transcribed text is typed into whatever window has focus.\n"
        f"  Ctrl+C here to quit.\n"
    )

    stop_event = threading.Event()

    def _sig_handler(signum, frame):  # noqa: ARG001
        log.info("signal %s received, shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _sig_handler)
    try:
        signal.signal(signal.SIGTERM, _sig_handler)
    except (AttributeError, ValueError):
        pass

    try:
        while not stop_event.is_set():
            time.sleep(0.25)
    finally:
        try:
            listener_state["listener"].stop()
        except Exception:
            pass
        app.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

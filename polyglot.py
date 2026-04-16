"""Polyglot — AI voice dictation for your entire desktop.

Press a global hotkey anywhere (Word, your browser, chat, email, your terminal)
and start speaking. Polyglot records, transcribes with an AI model that
supports 99+ languages with automatic language detection, then types the
result into whatever text field is focused.

Run with: python -m polyglot
Or:       python polyglot.py
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from typing import Optional

from config import Config, load_config
from recorder import Recorder
from transcriber import Transcriber, TranscriptionError
from typer import TextTyper

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


class PolyglotApp:
    """Glues the hotkey, recorder, transcriber, and typer together."""

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
        )
        self.typer = TextTyper(method=config.typing_method)
        self.state = self.STATE_IDLE
        self._lock = threading.Lock()
        self.tray: Optional[object] = None

    # ---------------- State helpers ----------------
    def _set_state(self, new_state: str) -> None:
        with self._lock:
            self.state = new_state
        log.info("state → %s", new_state)
        if self.tray is not None:
            try:
                self.tray.set_state(new_state)  # type: ignore[attr-defined]
            except Exception:
                pass

    def is_busy(self) -> bool:
        return self.state == self.STATE_TRANSCRIBING

    # ---------------- Hotkey actions ----------------
    def toggle_recording(self) -> None:
        """Toggle recording on/off. Called from the hotkey thread."""
        if self.is_busy():
            log.debug("ignoring hotkey: transcription in flight")
            return
        if self.state == self.STATE_IDLE:
            self._start_recording()
        else:
            self._stop_and_transcribe()

    def _handle_auto_stop(self) -> None:
        """Called from the recorder thread when the VAD detects end of speech."""
        log.debug("auto-stop signal received")
        self._stop_and_transcribe()

    def push_to_talk_press(self) -> None:
        if self.is_busy() or self.state == self.STATE_RECORDING:
            return
        self._start_recording()

    def push_to_talk_release(self) -> None:
        if self.state == self.STATE_RECORDING:
            self._stop_and_transcribe()

    # ---------------- Core pipeline ----------------
    def _start_recording(self) -> None:
        self._set_state(self.STATE_RECORDING)
        try:
            self.recorder.start()
        except Exception as exc:
            log.error("Could not start recording: %s", exc)
            self._notify(f"Mic error: {exc}")
            self._set_state(self.STATE_IDLE)

    def _stop_and_transcribe(self) -> None:
        # Claim exclusive ownership of the state transition so that an
        # auto-stop firing at the same instant as a hotkey press can't run
        # this pipeline twice.
        with self._lock:
            if self.state != self.STATE_RECORDING:
                log.debug("ignoring stop: state=%s", self.state)
                return
            self.state = self.STATE_TRANSCRIBING
        if self.tray is not None:
            try:
                self.tray.set_state(self.STATE_TRANSCRIBING)  # type: ignore[attr-defined]
            except Exception:
                pass

        try:
            audio_path = self.recorder.stop_and_save()
        except Exception as exc:
            log.error("Could not stop recording: %s", exc)
            self._set_state(self.STATE_IDLE)
            return

        if audio_path is None:
            log.info("no audio captured")
            self._notify("No speech detected")
            self._set_state(self.STATE_IDLE)
            return

        threading.Thread(
            target=self._run_transcription, args=(audio_path,), daemon=True
        ).start()

    def _run_transcription(self, audio_path: str) -> None:
        try:
            text = self.transcriber.transcribe(audio_path)
        except TranscriptionError as exc:
            log.error("transcription failed: %s", exc)
            self._notify(f"Transcription failed: {exc}")
            self._set_state(self.STATE_IDLE)
            return
        except Exception as exc:  # pragma: no cover
            log.exception("unexpected transcription error")
            self._notify(f"Unexpected error: {exc}")
            self._set_state(self.STATE_IDLE)
            return
        finally:
            try:
                import os

                os.unlink(audio_path)
            except OSError:
                pass

        text = (text or "").strip()
        if not text:
            log.info("no speech detected")
            self._notify("No speech detected")
            self._set_state(self.STATE_IDLE)
            return

        if self.config.add_trailing_space:
            text += " "
        log.info("typing %d chars", len(text))
        try:
            self.typer.type_text(text)
        except Exception as exc:
            log.error("typing failed: %s", exc)
            self._notify(f"Could not type text: {exc}")
        self._set_state(self.STATE_IDLE)

    # ---------------- Misc ----------------
    def _notify(self, message: str) -> None:
        log.info("NOTIFY: %s", message)
        # Tray notification if available (best-effort)
        if self.tray is not None:
            try:
                self.tray.notify(message)  # type: ignore[attr-defined]
            except Exception:
                pass

    def shutdown(self) -> None:
        try:
            self.recorder.close()
        except Exception:
            pass


def _build_hotkey_listener(app: PolyglotApp) -> keyboard.GlobalHotKeys:
    """Register the configured hotkeys with pynput."""
    hotkey = app.config.hotkey
    log.info("registering hotkey: %s", hotkey)
    mapping = {hotkey: app.toggle_recording}
    listener = keyboard.GlobalHotKeys(mapping)
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

    if not config.api_key and config.provider == "openai":
        sys.stderr.write(
            "\nNo OpenAI API key found.\n"
            "Set OPENAI_API_KEY in your environment, or edit the config file at:\n"
            f"  {config.path}\n"
            "Alternatively, set provider=\"local\" to use on-device Whisper.\n\n"
        )
        return 2

    app = PolyglotApp(config)
    listener = _build_hotkey_listener(app)
    listener.start()

    # Optional system tray
    if TrayIcon is not None and not args.no_tray:
        try:
            app.tray = TrayIcon(app)
            threading.Thread(target=app.tray.run, daemon=True).start()  # type: ignore[attr-defined]
            log.info("tray icon started")
        except Exception as exc:
            log.warning("tray unavailable: %s", exc)

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
        listener.stop()
        app.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

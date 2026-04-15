"""Configuration loading + persistence for Polyglot.

Config lives at ~/.polyglot/config.json. First launch writes a default file.
Environment variables (OPENAI_API_KEY, POLYGLOT_HOTKEY, POLYGLOT_LANGUAGE)
override file values so CI / shared setups are easy.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger("polyglot.config")

DEFAULT_CONFIG_DIR = Path.home() / ".polyglot"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.json"


@dataclass
class Config:
    # --- transcription ---
    provider: str = "openai"            # "openai" or "local"
    model: str = "whisper-1"            # whisper-1 (API) or tiny/base/small/medium/large-v3 (local)
    language: str = "auto"              # ISO-639-1 code (e.g. "en") or "auto"
    api_key: str = ""                   # set via env var OPENAI_API_KEY preferred

    # --- audio capture ---
    sample_rate: int = 16000
    silence_threshold: float = 0.012    # RMS threshold (0..1) for silence detection
    silence_duration: float = 1.5       # seconds of silence before auto-stop

    # --- output ---
    typing_method: str = "paste"        # "paste" (recommended) or "keystrokes"
    add_trailing_space: bool = True     # append a space after each dictation

    # --- hotkey ---
    # pynput GlobalHotKeys syntax. Default is Ctrl+Alt+Space which rarely conflicts.
    hotkey: str = "<ctrl>+<alt>+<space>"

    # --- bookkeeping ---
    path: str = str(DEFAULT_CONFIG_PATH)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("path", None)
        # Never persist the key if it came from env
        if os.environ.get("OPENAI_API_KEY") and self.api_key == os.environ["OPENAI_API_KEY"]:
            d["api_key"] = ""
        return d


def _apply_env(cfg: Config) -> None:
    env_key = os.environ.get("OPENAI_API_KEY")
    if env_key:
        cfg.api_key = env_key
    env_lang = os.environ.get("POLYGLOT_LANGUAGE")
    if env_lang:
        cfg.language = env_lang
    env_hotkey = os.environ.get("POLYGLOT_HOTKEY")
    if env_hotkey:
        cfg.hotkey = env_hotkey
    env_provider = os.environ.get("POLYGLOT_PROVIDER")
    if env_provider:
        cfg.provider = env_provider


def load_config(path: Optional[str] = None) -> Config:
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    cfg = Config(path=str(cfg_path))

    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            for field_name, value in data.items():
                if hasattr(cfg, field_name) and field_name != "path":
                    setattr(cfg, field_name, value)
            log.debug("loaded config from %s", cfg_path)
        except Exception as exc:
            log.warning("could not parse %s: %s (using defaults)", cfg_path, exc)
    else:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            cfg_path.write_text(
                json.dumps(cfg.to_dict(), indent=2), encoding="utf-8"
            )
            log.info("wrote default config to %s", cfg_path)
        except OSError as exc:
            log.warning("could not write default config: %s", exc)

    _apply_env(cfg)
    return cfg


def save_config(cfg: Config) -> None:
    try:
        Path(cfg.path).parent.mkdir(parents=True, exist_ok=True)
        Path(cfg.path).write_text(json.dumps(cfg.to_dict(), indent=2), encoding="utf-8")
    except OSError as exc:
        log.warning("could not save config: %s", exc)

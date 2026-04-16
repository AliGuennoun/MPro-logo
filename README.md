# Polyglot — AI voice dictation for your entire desktop

Polyglot is a downloadable, always-running desktop dictation tool. Press a
global hotkey in **any** app — Word, Google Docs, your browser, Slack, your
terminal, a Photoshop text layer — speak, and Polyglot types your words
where your cursor is. It supports **every language OpenAI's Whisper model
understands** (99+ languages with automatic detection) and can also run
fully offline with the local Whisper model.

It's a lightweight Python app (single virtualenv, cross-platform) —
not a web page, not a chat window.

## How it works

```
   Hotkey (Ctrl+Alt+Space)
            │
            ▼
   🎙 Record mic audio  ──▶  🧠 Whisper transcribes (auto-detects language)
                                       │
                                       ▼
                            ⌨ Paste into focused app
```

Because Polyglot uses clipboard-paste by default, it can insert **any**
Unicode: Mandarin, Arabic (RTL), Hindi, emoji, mathematical symbols —
whatever Whisper hears.

## Features

- **Works in every app** — paste-based insertion reaches any text field.
- **Every language Whisper knows** — auto-detects or force a specific one.
- **Modern GUI** with live status, transcript history, and in-app settings.
- **Live translation** — speak in any language, have the translation typed
  into your app in real time (powered by an LLM; Groq or OpenAI).
- **Clean-up mode** — auto-remove filler words ("um", "uh", "you know") and
  fix punctuation/grammar without changing meaning.
- **Global hotkey** toggles recording (default `Ctrl + Alt + Space`) — works
  even when the Polyglot window isn't focused.
- **Voice-activity auto-stop** — stop speaking and it finishes on its own.
- **Multiple providers** — OpenAI, Groq (free tier, no CC), OpenRouter,
  DeepInfra, self-hosted vLLM — anything OpenAI-compatible via `base_url`.
- **Fully offline option** — run `openai-whisper` locally (privacy-first).
- **System-tray icon** shows idle / recording / transcribing state.
- **Cross-platform** — macOS, Linux (X11/Wayland), Windows 10+.

## Install

### macOS / Linux

```bash
git clone https://github.com/aliguennoun/mpro-logo.git polyglot
cd polyglot
./install.sh
```

The installer creates a `.venv` and drops a `polyglot` launcher in the
folder.

### Windows

```
git clone https://github.com/aliguennoun/mpro-logo.git polyglot
cd polyglot
install.bat
```

Produces a `polyglot.bat` launcher.

### Manual / any OS

```bash
python -m venv .venv
source .venv/bin/activate       # or: .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

## OS-specific permissions

Polyglot needs permission to listen to the mic *and* to post keystrokes.

- **macOS** — on first launch, macOS will prompt for **Microphone**,
  **Accessibility**, and **Input Monitoring** access. Grant all three in
  *System Settings → Privacy & Security*. You have to re-launch after
  granting Accessibility.
- **Linux (X11)** — should work out of the box. On Wayland you may need
  to run under XWayland, or swap `typing_method` to `keystrokes` and use
  a tool like `wtype` — YMMV across compositors.
- **Windows** — just run it. If antivirus flags pynput's global key hook,
  allow it; it's only watching for your configured hotkey.

## Configure

Most people never need to edit config files — just open **Settings** from
the GUI. But for power users, on first run Polyglot writes
`~/.polyglot/config.json`:

```json
{
  "provider": "openai",
  "model": "whisper-1",
  "language": "auto",
  "api_key": "",
  "base_url": "",
  "mode": "dictate",
  "target_language": "English",
  "llm_model": "llama-3.3-70b-versatile",
  "sample_rate": 16000,
  "silence_threshold": 0.012,
  "silence_duration": 1.5,
  "typing_method": "paste",
  "add_trailing_space": true,
  "auto_type": true,
  "show_gui": true,
  "theme": "dark",
  "hotkey": "<ctrl>+<alt>+<space>"
}
```

| Key                 | Notes                                                             |
| ------------------- | ----------------------------------------------------------------- |
| `provider`          | `openai` (API) or `local` (offline, needs `openai-whisper`)       |
| `model`             | `whisper-1` for OpenAI; `whisper-large-v3-turbo` for Groq; `base`/`small`/`medium`/`large-v3` locally |
| `language`          | ISO-639-1 (`en`, `fr`, `zh`, …) or `auto`                         |
| `base_url`          | Point at any OpenAI-compatible endpoint (Groq, OpenRouter, self-hosted, …) |
| `mode`              | `dictate` \| `translate` \| `cleanup` \| `both`                   |
| `target_language`   | Used in `translate` / `both` — any language name (`French`, `Japanese`, …) |
| `llm_model`         | Chat model for post-processing (translation / cleanup)            |
| `auto_type`         | `false` = show in GUI only, don't type into the focused app       |
| `show_gui`          | `false` = headless (equivalent to `--no-gui`)                     |
| `hotkey`            | pynput syntax — `<ctrl>+<alt>+<space>`, `<cmd>+<shift>+d`, etc.  |
| `typing_method`     | `paste` (reliable Unicode) or `keystrokes`                        |
| `silence_duration`  | Seconds of silence before auto-stop. Set to `0` to disable.       |
| `silence_threshold` | RMS threshold (0..1). Raise if your mic is noisy.                 |

### Using Groq (free, no credit card)

Groq hosts Whisper-large-v3 and Llama-3.3-70B on a free tier — ideal if
you don't want an OpenAI billing account:

```bash
export OPENAI_API_KEY=gsk_...                              # Groq key
export POLYGLOT_BASE_URL=https://api.groq.com/openai/v1
export POLYGLOT_MODEL=whisper-large-v3-turbo
```

Or paste the key + base URL into **Settings → Provider** in the GUI.

Set your API key via environment variable (recommended) so it never
touches the config file:

```bash
export OPENAI_API_KEY=sk-...
```

Env overrides: `POLYGLOT_LANGUAGE`, `POLYGLOT_HOTKEY`, `POLYGLOT_PROVIDER`.

## Usage

1. Start it: `./polyglot` (or `polyglot.bat` on Windows).
2. Focus any text field anywhere on your system.
3. Press **Ctrl + Alt + Space**.
4. Speak. Stop speaking. Polyglot types your words where the cursor is.
5. Press the hotkey again any time to start a new dictation.

Useful CLI flags:

```bash
polyglot --language es                      # Force Spanish for this session
polyglot --mode translate --target-language French
polyglot --mode cleanup                     # Strip filler words / fix grammar
polyglot --hotkey "<cmd>+<shift>+d"         # Rebind hotkey on the fly
polyglot --no-gui                           # Headless / tray-only
polyglot --no-tray                          # Skip the tray icon
polyglot --list-devices                     # Show input devices
polyglot -v                                 # Verbose logs
```

### Modes explained

| Mode       | What happens                                                     |
| ---------- | ---------------------------------------------------------------- |
| `dictate`  | Speak → transcribe → type. No LLM calls.                         |
| `translate`| Speak in any language → LLM translates → translation is typed.   |
| `cleanup`  | Speak → LLM removes "um"/"uh", fixes grammar → cleaned text typed. |
| `both`     | Same as `translate`, plus the original is kept in the GUI history. |

## Offline mode

Want Polyglot to never talk to the cloud?

```bash
pip install openai-whisper
# ffmpeg is also required — e.g. brew install ffmpeg / apt install ffmpeg
```

Edit the config: `"provider": "local"` and pick a model — `small` is a
good CPU/accuracy trade-off.

## Build a standalone binary

Optional: ship `polyglot` as a single executable (no Python needed on
the target machine):

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed \
  --name Polyglot polyglot.py
```

## Project layout

```
polyglot.py        # Entry point (hotkey + orchestration)
gui.py             # Modern CustomTkinter window + settings dialog
recorder.py        # Mic capture + voice-activity auto-stop
transcriber.py     # OpenAI-compatible Whisper + local whisper backends
postprocess.py     # LLM translate / cleanup via chat completions
typer.py           # Clipboard-paste / keystroke text insertion
tray.py            # Optional system-tray icon
config.py          # JSON config + env var overrides
requirements.txt
install.sh         # macOS / Linux installer
install.bat        # Windows installer
```

## License

MIT

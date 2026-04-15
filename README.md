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
- **Global hotkey** toggles recording (default `Ctrl + Alt + Space`).
- **Voice-activity auto-stop** — stop speaking and it finishes on its own.
- **Two transcription backends** — OpenAI API (fast, no GPU) or fully
  offline `openai-whisper` (privacy-first; CPU or GPU).
- **System-tray icon** shows idle / recording / transcribing state.
- **Zero-cost hotkey**: rich configurability via a single JSON file.
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

On first run, Polyglot writes `~/.polyglot/config.json`:

```json
{
  "provider": "openai",
  "model": "whisper-1",
  "language": "auto",
  "api_key": "",
  "sample_rate": 16000,
  "silence_threshold": 0.012,
  "silence_duration": 1.5,
  "typing_method": "paste",
  "add_trailing_space": true,
  "hotkey": "<ctrl>+<alt>+<space>"
}
```

| Key                 | Notes                                                             |
| ------------------- | ----------------------------------------------------------------- |
| `provider`          | `openai` (API) or `local` (offline, needs `openai-whisper`)       |
| `model`             | `whisper-1` for API; `base`/`small`/`medium`/`large-v3` locally   |
| `language`          | ISO-639-1 (`en`, `fr`, `zh`, …) or `auto`                         |
| `hotkey`            | pynput syntax — `<ctrl>+<alt>+<space>`, `<cmd>+<shift>+d`, etc.  |
| `typing_method`     | `paste` (reliable Unicode) or `keystrokes`                        |
| `silence_duration`  | Seconds of silence before auto-stop. Set to `0` to disable.       |
| `silence_threshold` | RMS threshold (0..1). Raise if your mic is noisy.                 |

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
polyglot --language es              # Force Spanish for this session
polyglot --hotkey "<cmd>+<shift>+d" # Rebind hotkey on the fly
polyglot --list-devices             # Show input devices
polyglot --no-tray                  # Skip the tray icon
polyglot -v                         # Verbose logs
```

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
recorder.py        # Mic capture + voice-activity auto-stop
transcriber.py     # OpenAI Whisper API + local whisper backends
typer.py           # Clipboard-paste / keystroke text insertion
tray.py            # Optional system-tray icon
config.py          # JSON config + env var overrides
requirements.txt
install.sh         # macOS / Linux installer
install.bat        # Windows installer
```

## License

MIT

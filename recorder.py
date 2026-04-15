"""Microphone recorder with optional voice-activity auto-stop.

The recorder spins up a background thread that writes audio frames into an
in-memory buffer. Calling stop_and_save() returns a path to a WAV file on
disk that the transcriber can read. If silence_duration is > 0, the
recorder will also auto-stop after that many seconds of silence.
"""
from __future__ import annotations

import logging
import queue
import tempfile
import threading
import wave
from typing import Optional

log = logging.getLogger("polyglot.recorder")


class Recorder:
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        silence_threshold: float = 0.012,
        silence_duration: float = 1.5,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self._stream = None
        self._thread: Optional[threading.Thread] = None
        self._queue: "queue.Queue" = queue.Queue()
        self._stop_event = threading.Event()
        self._frames: list[bytes] = []
        self._recording = False
        # Lazy-loaded so cold import doesn't require audio libs
        self._sd = None
        self._np = None

    # ---------------- lifecycle ----------------
    def start(self) -> None:
        if self._recording:
            log.warning("start() called while already recording")
            return
        self._lazy_import()

        self._frames = []
        self._stop_event.clear()

        def _callback(indata, frames, time_info, status):  # noqa: ARG001
            if status:
                log.debug("sd status: %s", status)
            # Copy: sounddevice reuses its buffer
            self._queue.put(indata.copy())

        self._stream = self._sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            callback=_callback,
        )
        self._stream.start()
        self._recording = True
        self._thread = threading.Thread(target=self._drain, daemon=True)
        self._thread.start()
        log.info("recording started (%d Hz, %d ch)", self.sample_rate, self.channels)

    def stop_and_save(self) -> Optional[str]:
        """Stop the stream and write a WAV file. Returns path or None if empty."""
        if not self._recording:
            return None

        self._stop_event.set()
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception as exc:
            log.warning("stream close error: %s", exc)
        self._stream = None
        self._recording = False

        if self._thread is not None:
            self._thread.join(timeout=2.0)

        # Drain any residual frames from the queue
        while True:
            try:
                self._frames.append(self._queue.get_nowait().tobytes())
            except queue.Empty:
                break

        if not self._frames:
            log.info("no frames captured")
            return None

        total_bytes = sum(len(f) for f in self._frames)
        # 16-bit PCM => 2 bytes/sample
        samples = total_bytes / 2 / self.channels
        seconds = samples / self.sample_rate
        log.info("captured %.2fs of audio (%d bytes)", seconds, total_bytes)

        if seconds < 0.25:
            log.info("recording too short (<0.25s), discarding")
            return None

        return self._write_wav()

    def close(self) -> None:
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass

    # ---------------- internals ----------------
    def _lazy_import(self) -> None:
        if self._sd is None:
            import sounddevice as sd  # noqa: WPS433
            import numpy as np        # noqa: WPS433

            self._sd = sd
            self._np = np

    def _drain(self) -> None:
        """Pull frames off the queue + monitor for trailing silence."""
        silent_seconds = 0.0
        has_spoken = False
        frame_seconds = 0.0
        while not self._stop_event.is_set():
            try:
                frame = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            self._frames.append(frame.tobytes())

            # VAD: compute RMS of this frame (normalised to 0..1)
            if self.silence_duration > 0:
                audio_f = frame.astype(self._np.float32) / 32768.0
                rms = float(self._np.sqrt(self._np.mean(audio_f ** 2)))
                frame_seconds = len(frame) / self.sample_rate
                if rms >= self.silence_threshold:
                    has_spoken = True
                    silent_seconds = 0.0
                elif has_spoken:
                    silent_seconds += frame_seconds
                    if silent_seconds >= self.silence_duration:
                        log.info("auto-stop: %.2fs of silence", silent_seconds)
                        self._stop_event.set()
                        break

    def _write_wav(self) -> str:
        fd, path = tempfile.mkstemp(prefix="polyglot-", suffix=".wav")
        import os

        os.close(fd)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # int16
            wf.setframerate(self.sample_rate)
            wf.writeframes(b"".join(self._frames))
        log.debug("wrote wav %s", path)
        return path

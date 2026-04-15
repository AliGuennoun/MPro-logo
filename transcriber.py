"""Transcription backend.

Two providers:
 - openai  → OpenAI's Whisper API (whisper-1). 99+ languages, auto-detect.
 - local   → openai-whisper package running on your machine (fully offline).

The local backend is lazy-loaded so users on the API path don't need torch.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger("polyglot.transcriber")


class TranscriptionError(RuntimeError):
    pass


class Transcriber:
    def __init__(
        self,
        provider: str = "openai",
        api_key: Optional[str] = None,
        model: str = "whisper-1",
        language: Optional[str] = None,
    ) -> None:
        self.provider = provider.lower()
        self.api_key = api_key
        self.model = model
        self.language = language
        self._client = None
        self._local_model = None

    def transcribe(self, audio_path: str) -> str:
        if self.provider == "openai":
            return self._transcribe_openai(audio_path)
        if self.provider == "local":
            return self._transcribe_local(audio_path)
        raise TranscriptionError(f"Unknown provider: {self.provider}")

    # ---------------- OpenAI API ----------------
    def _transcribe_openai(self, audio_path: str) -> str:
        if not self.api_key:
            raise TranscriptionError("OPENAI_API_KEY is not set")

        if self._client is None:
            try:
                from openai import OpenAI  # type: ignore
            except ImportError as exc:
                raise TranscriptionError(
                    "The 'openai' package is required. Install with: pip install openai"
                ) from exc
            self._client = OpenAI(api_key=self.api_key)

        kwargs: dict = {
            "model": self.model,
            "response_format": "text",
        }
        if self.language:
            kwargs["language"] = self.language

        try:
            with open(audio_path, "rb") as audio_file:
                resp = self._client.audio.transcriptions.create(
                    file=audio_file, **kwargs
                )
        except Exception as exc:
            raise TranscriptionError(str(exc)) from exc

        # response_format=text returns a plain string
        if isinstance(resp, str):
            return resp
        # Some SDK versions return an object with .text
        return getattr(resp, "text", "") or ""

    # ---------------- Local Whisper ----------------
    def _transcribe_local(self, audio_path: str) -> str:
        if self._local_model is None:
            try:
                import whisper  # type: ignore
            except ImportError as exc:
                raise TranscriptionError(
                    "Local transcription needs the 'openai-whisper' package.\n"
                    "Install with: pip install openai-whisper\n"
                    "(also requires ffmpeg on your PATH)."
                ) from exc
            log.info("loading local whisper model: %s", self.model)
            self._local_model = whisper.load_model(self.model)

        try:
            result = self._local_model.transcribe(
                audio_path,
                language=self.language,          # None → auto-detect
                fp16=False,
                verbose=False,
            )
        except Exception as exc:
            raise TranscriptionError(str(exc)) from exc
        return (result.get("text") or "").strip()

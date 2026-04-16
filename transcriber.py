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
        base_url: Optional[str] = None,
    ) -> None:
        self.provider = provider.lower()
        self.api_key = api_key
        self.model = model
        self.language = language
        self.base_url = base_url or None
        self._client = None
        self._local_model = None

    def transcribe(self, audio_path: str) -> str:
        if self.provider == "openai":
            return self._transcribe_openai(audio_path)
        if self.provider == "local":
            return self._transcribe_local(audio_path)
        raise TranscriptionError(f"Unknown provider: {self.provider}")

    # ---------------- OpenAI-compatible API ----------------
    def _transcribe_openai(self, audio_path: str) -> str:
        if not self.api_key:
            raise TranscriptionError("API key is not set (OPENAI_API_KEY)")

        if self._client is None:
            try:
                from openai import OpenAI  # type: ignore
            except ImportError as exc:
                raise TranscriptionError(
                    "The 'openai' package is required. Install with: pip install openai"
                ) from exc
            client_kwargs: dict = {"api_key": self.api_key}
            if self.base_url:
                client_kwargs["base_url"] = self.base_url
                log.info("using base_url: %s", self.base_url)
            self._client = OpenAI(**client_kwargs)

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
            # Surface the most useful bit of the provider's error instead
            # of dumping the full JSON response into every log line.
            msg = str(exc)
            body = getattr(exc, "body", None)
            if isinstance(body, dict):
                err = body.get("error")
                if isinstance(err, dict) and err.get("message"):
                    msg = err["message"]
            raise TranscriptionError(msg) from exc

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

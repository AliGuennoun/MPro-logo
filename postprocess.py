"""Post-processing — route a raw transcript through an LLM.

Two built-in pipelines:

  translate(text, target)  → Render the transcript in another language.
  cleanup(text)            → Strip filler words, fix punctuation + grammar.

The chat endpoint we call is OpenAI-compatible, so the same base URL you
pointed Whisper at (Groq / OpenRouter / DeepInfra / local vLLM / …) will
usually serve a chat model too.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger("polyglot.postprocess")


class PostprocessError(RuntimeError):
    pass


TRANSLATE_SYSTEM = (
    "You are a professional translator. Translate the user's message into {target}. "
    "Output ONLY the translation with no commentary, no quotes, no explanations, "
    "no prefixes like 'Translation:'. Preserve the tone, register, and meaning faithfully. "
    "If the input is already in {target}, repeat it verbatim."
)

CLEANUP_SYSTEM = (
    "You are an editor cleaning up raw voice transcription. "
    "Remove filler words (um, uh, you know, like, I mean), "
    "fix obvious grammatical slips, add proper punctuation and capitalisation, "
    "and split into paragraphs if the text is long. "
    "Preserve the speaker's meaning exactly — do NOT rephrase, summarise, or add content. "
    "Output ONLY the cleaned text."
)


class PostProcessor:
    """Thin wrapper around an OpenAI-compatible chat completion endpoint."""

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        model: str = "llama-3.3-70b-versatile",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url or None
        self.model = model
        self._client = None

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:
            raise PostprocessError(
                "The 'openai' package is required. Install with: pip install openai"
            ) from exc
        kwargs: dict = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        self._client = OpenAI(**kwargs)

    def _chat(self, system: str, user: str, temperature: float = 0.2) -> str:
        self._ensure_client()
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
            )
        except Exception as exc:
            msg = str(exc)
            body = getattr(exc, "body", None)
            if isinstance(body, dict):
                err = body.get("error")
                if isinstance(err, dict) and err.get("message"):
                    msg = err["message"]
            raise PostprocessError(msg) from exc
        choice = resp.choices[0] if getattr(resp, "choices", None) else None
        content = getattr(choice.message, "content", "") if choice else ""
        return (content or "").strip()

    def translate(self, text: str, target_language: str) -> str:
        if not text.strip():
            return ""
        system = TRANSLATE_SYSTEM.format(target=target_language)
        log.info("translating %d chars → %s", len(text), target_language)
        return self._chat(system, text, temperature=0.2)

    def cleanup(self, text: str) -> str:
        if not text.strip():
            return ""
        log.info("cleaning up %d chars", len(text))
        return self._chat(CLEANUP_SYSTEM, text, temperature=0.1)

    def custom(self, text: str, system_prompt: str) -> str:
        if not text.strip() or not system_prompt.strip():
            return text
        log.info("running custom prompt on %d chars", len(text))
        return self._chat(system_prompt, text, temperature=0.3)

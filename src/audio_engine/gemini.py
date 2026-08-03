"""Narrow Google Gen AI adapter for Gemini multi-speaker TTS."""

from __future__ import annotations

import re

from google import genai
from google.genai import types

from audio_engine.artifacts import TtsSegmentPrompt
from audio_engine.tts import (
    SpeechRendererCapabilities,
    SpeechRendererConfigurationError,
    SpeechRendererError,
    SpeechResponse,
    TtsPreparationError,
    renderer_capabilities,
    renderer_input,
)

DEFAULT_REQUEST_TIMEOUT_SECONDS = 180
_VOICE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_SUPPORTED_VOICES = frozenset(
    {
        "Achernar",
        "Achird",
        "Algenib",
        "Algieba",
        "Alnilam",
        "Aoede",
        "Autonoe",
        "Callirrhoe",
        "Charon",
        "Despina",
        "Enceladus",
        "Erinome",
        "Fenrir",
        "Gacrux",
        "Iapetus",
        "Kore",
        "Laomedeia",
        "Leda",
        "Orus",
        "Puck",
        "Pulcherrima",
        "Rasalgethi",
        "Sadachbia",
        "Sadaltager",
        "Schedar",
        "Sulafat",
        "Umbriel",
        "Vindemiatrix",
        "Zephyr",
        "Zubenelgenubi",
    }
)


class GeminiSpeechRenderer:
    """Render prepared requests with one bounded, non-retrying SDK call."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        client: genai.Client | None = None,
    ) -> None:
        if not api_key:
            raise SpeechRendererConfigurationError("Gemini API key is empty")
        if timeout_seconds < 1 or timeout_seconds > 15 * 60:
            raise SpeechRendererConfigurationError("Gemini request timeout is invalid")
        try:
            self._capabilities = renderer_capabilities("gemini", model)
        except TtsPreparationError as error:
            raise SpeechRendererConfigurationError(
                "configured Gemini model has no supported capability record"
            ) from error
        self._client = client or genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=timeout_seconds * 1_000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    @property
    def capabilities(self) -> SpeechRendererCapabilities:
        return self._capabilities

    def render(self, request: TtsSegmentPrompt) -> SpeechResponse:
        if request.provider != "gemini" or request.model != self.capabilities.model:
            raise SpeechRendererConfigurationError(
                "prepared request does not match the configured Gemini model"
            )
        if len(request.hosts) != 2:
            raise SpeechRendererConfigurationError("Gemini TTS requires exactly two hosts")
        voices = [host.voice for host in request.hosts]
        if len(set(voices)) != 2 or any(
            not _VOICE_NAME.fullmatch(voice) or voice not in _SUPPORTED_VOICES for voice in voices
        ):
            raise SpeechRendererConfigurationError(
                "Gemini hosts require two distinct supported prebuilt voices"
            )
        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                    speaker_voice_configs=[
                        types.SpeakerVoiceConfig(
                            speaker=host.name,
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=host.voice
                                )
                            ),
                        )
                        for host in request.hosts
                    ]
                )
            ),
        )
        try:
            response = self._client.models.generate_content(  # pyright: ignore[reportUnknownMemberType]
                model=self.capabilities.model,
                contents=renderer_input(request),
                config=config,
            )
        except Exception as error:
            raise SpeechRendererError("Gemini speech request failed") from error
        return _speech_response(response)


def _speech_response(response: types.GenerateContentResponse) -> SpeechResponse:
    audio_parts: list[bytes] = []
    mime_type: str | None = None
    text_parts: list[str] = []
    for candidate in response.candidates or []:
        if candidate.content is None:
            continue
        for part in candidate.content.parts or []:
            if part.text:
                text_parts.append(part.text)
            if part.inline_data is None or not part.inline_data.data:
                continue
            part_mime = part.inline_data.mime_type
            if audio_parts and part_mime != mime_type:
                raise SpeechRendererError("Gemini returned inconsistent audio media types")
            mime_type = part_mime
            audio_parts.append(part.inline_data.data)
    return SpeechResponse(
        audio=b"".join(audio_parts) if audio_parts else None,
        mime_type=mime_type,
        text="\n".join(text_parts) if text_parts else None,
    )

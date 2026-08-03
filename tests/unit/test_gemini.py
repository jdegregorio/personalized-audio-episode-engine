from __future__ import annotations

from typing import cast

import pytest
from google import genai
from google.genai import types

import audio_engine.gemini as gemini_module
from audio_engine.gemini import GeminiSpeechRenderer
from audio_engine.tts import (
    SpeechRendererConfigurationError,
    SpeechRendererError,
    renderer_input,
)
from scripts.smoke_gemini import build_live_prompt


class _FakeModels:
    def __init__(self, response: types.GenerateContentResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs: object) -> types.GenerateContentResponse:
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class _FakeClient:
    def __init__(self, response: types.GenerateContentResponse | Exception) -> None:
        self.models = _FakeModels(response)


def _response(*parts: types.Part) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(parts=list(parts)))]
    )


def test_gemini_renderer_builds_exact_two_speaker_audio_request() -> None:
    response = _response(
        types.Part(inline_data=types.Blob(data=b"pcm", mime_type="audio/L16;rate=24000"))
    )
    client = _FakeClient(response)
    prompt = build_live_prompt("Kore", "Charon")
    renderer = GeminiSpeechRenderer(
        api_key="fake-key",
        model=prompt.model,
        client=cast(genai.Client, client),
    )

    rendered = renderer.render(prompt)

    assert rendered.audio == b"pcm"
    assert rendered.mime_type == "audio/L16;rate=24000"
    assert rendered.text is None
    assert len(client.models.calls) == 1
    call = client.models.calls[0]
    assert call["model"] == "gemini-3.1-flash-tts-preview"
    assert call["contents"] == renderer_input(prompt)
    config = call["config"]
    assert isinstance(config, types.GenerateContentConfig)
    dumped = config.model_dump(mode="json", exclude_none=True)
    assert dumped["response_modalities"] == ["AUDIO"]
    assert dumped["speech_config"]["multi_speaker_voice_config"]["speaker_voice_configs"] == [
        {"speaker": "Maya", "voice_config": {"prebuilt_voice_config": {"voice_name": "Kore"}}},
        {
            "speaker": "Daniel",
            "voice_config": {"prebuilt_voice_config": {"voice_name": "Charon"}},
        },
    ]


def test_gemini_renderer_surfaces_text_for_generic_rejection() -> None:
    client = _FakeClient(_response(types.Part(text="not audio")))
    renderer = GeminiSpeechRenderer(
        api_key="fake-key",
        model="gemini-3.1-flash-tts-preview",
        client=cast(genai.Client, client),
    )

    response = renderer.render(build_live_prompt("Kore", "Charon"))

    assert response.audio is None
    assert response.text == "not audio"


@pytest.mark.parametrize(
    ("female", "male"),
    [("unknown", "Charon"), ("Kore", "Kore"), ("Kore!", "Charon")],
)
def test_gemini_renderer_rejects_invalid_voice_configuration(female: str, male: str) -> None:
    client = _FakeClient(_response())
    renderer = GeminiSpeechRenderer(
        api_key="fake-key",
        model="gemini-3.1-flash-tts-preview",
        client=cast(genai.Client, client),
    )

    with pytest.raises(SpeechRendererConfigurationError, match="distinct supported"):
        renderer.render(build_live_prompt(female, male))

    assert not client.models.calls


@pytest.mark.parametrize("error", [TimeoutError(), RuntimeError("HTTP 500"), RuntimeError("429")])
def test_gemini_renderer_redacts_provider_exception_details(error: Exception) -> None:
    client = _FakeClient(error)
    renderer = GeminiSpeechRenderer(
        api_key="secret-key",
        model="gemini-3.1-flash-tts-preview",
        client=cast(genai.Client, client),
    )

    with pytest.raises(SpeechRendererError, match="Gemini speech request failed") as raised:
        renderer.render(build_live_prompt("Kore", "Charon"))

    assert "secret-key" not in str(raised.value)


def test_gemini_renderer_rejects_unknown_model_and_invalid_timeout() -> None:
    with pytest.raises(SpeechRendererConfigurationError, match="API key is empty"):
        GeminiSpeechRenderer(api_key="", model="gemini-3.1-flash-tts-preview")
    with pytest.raises(SpeechRendererConfigurationError, match="capability record"):
        GeminiSpeechRenderer(api_key="fake", model="future-model")
    with pytest.raises(SpeechRendererConfigurationError, match="timeout"):
        GeminiSpeechRenderer(
            api_key="fake",
            model="gemini-3.1-flash-tts-preview",
            timeout_seconds=0,
        )


def test_gemini_renderer_configures_bounded_timeout_and_disables_sdk_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def client_factory(**kwargs: object) -> genai.Client:
        captured.update(kwargs)
        return cast(genai.Client, _FakeClient(_response()))

    monkeypatch.setattr(gemini_module.genai, "Client", client_factory)

    GeminiSpeechRenderer(
        api_key="fake",
        model="gemini-3.1-flash-tts-preview",
        timeout_seconds=42,
    )

    options = captured["http_options"]
    assert isinstance(options, types.HttpOptions)
    assert options.timeout == 42_000
    assert options.retry_options is not None
    assert options.retry_options.attempts == 1


def test_gemini_renderer_rejects_request_model_mismatch_and_mixed_audio_types() -> None:
    client = _FakeClient(
        _response(
            types.Part(inline_data=types.Blob(data=b"first", mime_type="audio/L16;rate=24000")),
            types.Part(inline_data=types.Blob(data=b"second", mime_type="audio/wav")),
        )
    )
    renderer = GeminiSpeechRenderer(
        api_key="fake",
        model="gemini-3.1-flash-tts-preview",
        client=cast(genai.Client, client),
    )
    mismatched = build_live_prompt("Kore", "Charon").model_copy(update={"model": "other"})

    with pytest.raises(SpeechRendererConfigurationError, match="does not match"):
        renderer.render(mismatched)
    with pytest.raises(SpeechRendererError, match="inconsistent audio media types"):
        renderer.render(build_live_prompt("Kore", "Charon"))

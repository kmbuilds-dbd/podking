from __future__ import annotations

import json
from pathlib import Path

import pytest

from podking.worker.tts.scripter import (
    ScriptSegment,
    ScripterError,
    write_script,
)


class StubAnthropic:
    """Returns canned messages.create responses."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.messages = self

    def create(self, **kwargs):  # mimic AsyncAnthropic.messages.create
        self.calls.append(kwargs)
        text = self._responses.pop(0)

        class _Block:
            def __init__(self, t: str) -> None:
                self.text = t

        class _Msg:
            def __init__(self, t: str) -> None:
                self.content = [_Block(t)]
                self.stop_reason = "end_turn"

        async def _aresult():
            return _Msg(text)
        return _aresult()


@pytest.mark.asyncio
async def test_write_script_parses_segments() -> None:
    canned = json.dumps([
        {"speaker": "A", "text": "Hey welcome back."},
        {"speaker": "B", "text": "Yeah today we're talking about TTS."},
    ])
    summary = {"tldr": "intro", "key_points": ["a", "b"], "quotes": []}

    segments = await write_script(
        summary=summary,
        anthropic_key="sk-fake",
        episode_title="Test Episode",
        client_factory=lambda key: StubAnthropic([canned]),
    )

    assert len(segments) == 2
    assert isinstance(segments[0], ScriptSegment)
    assert segments[0].speaker == "A"
    assert segments[1].speaker == "B"


@pytest.mark.asyncio
async def test_write_script_retries_once_on_bad_json() -> None:
    summary = {"tldr": "x", "key_points": ["x"], "quotes": []}
    good = json.dumps([{"speaker": "A", "text": "hi"}])

    stub = StubAnthropic(["not json at all", good])
    segments = await write_script(
        summary=summary,
        anthropic_key="sk-fake",
        episode_title="t",
        client_factory=lambda key: stub,
    )
    assert len(segments) == 1
    assert len(stub.calls) == 2  # retried once with stricter reminder
    # The second call should include a "respond with valid JSON only" hint
    second_system = stub.calls[1]["system"]
    assert any("JSON" in str(s).upper() for s in second_system)


@pytest.mark.asyncio
async def test_write_script_fails_after_two_bad_attempts() -> None:
    summary = {"tldr": "x", "key_points": [], "quotes": []}
    stub = StubAnthropic(["garbage 1", "garbage 2"])
    with pytest.raises(ScripterError, match="non-JSON"):
        await write_script(
            summary=summary,
            anthropic_key="sk-fake",
            episode_title="t",
            client_factory=lambda key: stub,
        )


@pytest.mark.asyncio
async def test_write_script_rejects_invalid_speaker() -> None:
    summary = {"tldr": "x", "key_points": [], "quotes": []}
    bad = json.dumps([{"speaker": "C", "text": "hi"}])
    good = json.dumps([{"speaker": "A", "text": "hi"}])
    stub = StubAnthropic([bad, good])
    segments = await write_script(
        summary=summary,
        anthropic_key="sk-fake",
        episode_title="t",
        client_factory=lambda key: stub,
    )
    assert segments[0].speaker == "A"

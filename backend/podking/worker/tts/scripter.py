"""Stage 1 — Claude writes a two-host script from a summary."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import anthropic

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
PROMPT_PATH = Path(__file__).parent / "prompt.md"


class ScripterError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScriptSegment:
    speaker: str  # "A" or "B"
    text: str


_PROMPT_CACHE: str | None = None


def _load_prompt() -> str:
    global _PROMPT_CACHE
    if _PROMPT_CACHE is None:
        _PROMPT_CACHE = PROMPT_PATH.read_text(encoding="utf-8")
    return _PROMPT_CACHE


def _default_client_factory(api_key: str) -> Any:
    return anthropic.AsyncAnthropic(api_key=api_key)


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    # Pattern 1: entire response is a fenced block
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    # Pattern 2: response contains a fenced block somewhere (preamble allowed)
    inner = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if inner:
        return inner.group(1).strip()
    # Pattern 3: response contains a bare JSON array somewhere
    if not text.startswith("["):
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]
    return text


def _parse_segments(raw: str) -> list[ScriptSegment]:
    text = _strip_fences(raw)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ScripterError(f"Claude returned non-JSON: {exc}") from exc
    if not isinstance(parsed, list) or not parsed:
        raise ScripterError("Script must be a non-empty JSON array")
    segments: list[ScriptSegment] = []
    for i, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise ScripterError(f"Segment {i} is not an object")
        speaker = item.get("speaker")
        body = item.get("text")
        if speaker not in ("A", "B"):
            raise ScripterError(f"Segment {i} has invalid speaker {speaker!r}")
        if not isinstance(body, str) or not body.strip():
            raise ScripterError(f"Segment {i} has empty text")
        segments.append(ScriptSegment(speaker=speaker, text=body.strip()))
    return segments


def _build_user_message(summary: dict[str, Any], episode_title: str) -> str:
    return (
        f"Episode title: {episode_title}\n\n"
        f"Summary JSON:\n{json.dumps(summary, ensure_ascii=False, indent=2)}"
    )


async def _call_claude_once(client: Any, system_text: str, user_msg: str) -> str:
    """Call Claude once, retrying transient HTTP errors with backoff.

    Returns the raw text content of the first reply block.
    """
    for attempt in range(3):
        try:
            message = await client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=[{"type": "text", "text": system_text}],
                messages=[{"role": "user", "content": user_msg}],
            )
            block = message.content[0]
            return getattr(block, "text", "") or ""
        except anthropic.APIStatusError as exc:
            if exc.status_code in (429, 500, 502, 503) and attempt < 2:
                import asyncio
                await asyncio.sleep(2 ** attempt * 2)
                continue
            raise ScripterError(
                f"Claude {exc.status_code}: {exc.message}"
            ) from exc
    raise ScripterError("Claude call failed after retries")


async def write_script(
    *,
    summary: dict[str, Any],
    anthropic_key: str,
    episode_title: str,
    client_factory: Callable[[str], Any] = _default_client_factory,
) -> list[ScriptSegment]:
    """Ask Claude for the script; retry once with a stricter reminder on bad JSON.

    On second failure raises `ScripterError`.
    """
    client = client_factory(anthropic_key)
    base_system = _load_prompt()
    user_msg = _build_user_message(summary, episode_title)

    last_error: ScripterError | None = None
    for attempt in range(2):
        system_text = base_system
        if attempt == 1 and last_error is not None:
            system_text = (
                base_system
                + "\n\nIMPORTANT: Your previous reply was not valid JSON. "
                "Respond ONLY with the JSON array — no markdown fences, "
                "no preamble, no trailing text."
            )
        raw = await _call_claude_once(client, system_text, user_msg)
        try:
            return _parse_segments(raw)
        except ScripterError as exc:
            last_error = exc
    raise last_error if last_error is not None else ScripterError(
        "Claude call failed for unknown reason"
    )

"""Claude summarization via Anthropic SDK."""
from __future__ import annotations

import json
import re

import anthropic

MODEL = "claude-sonnet-4-6"


def _extract_json(raw: str) -> dict[str, object]:
    """Parse a JSON object from Claude's response, tolerating markdown fences
    and prose preambles."""
    text = raw.strip()
    # ```json ... ``` or ``` ... ``` fences
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # Fall back: take the substring from the first '{' to the last '}'
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    return json.loads(text)  # type: ignore[no-any-return]

SCHEMA_SYSTEM = """\
You are a precise summarizer. Given a transcript, produce a JSON object with these exact keys:
- "tldr": one to two sentences describing what the episode is about and who is on it (string)
- "key_points": list of 5-12 takeaway strings. Each may be a single sentence or a short paragraph (up to ~6 sentences). Length and depth are guided by the analysis-style instructions below.
- "quotes": list of objects {"text": str, "speaker": str or null} for notable verbatim quotes (0-5)
- "suggested_tags": list of 2-6 lowercase topic tags (strings)

Respond ONLY with the JSON object, no markdown, no explanation."""


class ClaudeError(RuntimeError):
    pass


async def summarize(
    transcript: str, system_prompt: str, api_key: str
) -> dict[str, object]:
    """Return structured summary dict."""
    client = anthropic.AsyncAnthropic(api_key=api_key)

    extra = system_prompt.strip()
    user_system = (
        f"{SCHEMA_SYSTEM}\n\nAdditional guidance for analysis style and focus:\n{extra}"
        if extra
        else SCHEMA_SYSTEM
    )

    for attempt in range(3):
        try:
            message = await client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=[
                    {
                        "type": "text",
                        "text": user_system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {"role": "user", "content": f"Transcript:\n\n{transcript}"}
                ],
            )
            block = message.content[0]
            raw = block.text if hasattr(block, "text") else ""
            try:
                return _extract_json(raw)
            except json.JSONDecodeError as exc:
                preview = raw[:300].replace("\n", " ")
                raise ClaudeError(
                    f"Claude returned non-JSON ({exc}); "
                    f"stop_reason={message.stop_reason}; "
                    f"first 300 chars: {preview!r}"
                ) from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code in (429, 500, 502, 503) and attempt < 2:
                import asyncio
                await asyncio.sleep(2 ** attempt * 2)
                continue
            raise ClaudeError(f"Claude {exc.status_code}: {exc.message}") from exc

    raise ClaudeError("Claude summarization failed after retries")

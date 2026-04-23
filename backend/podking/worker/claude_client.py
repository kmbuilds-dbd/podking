"""Claude summarization via Anthropic SDK."""
from __future__ import annotations

import json

import anthropic

MODEL = "claude-sonnet-4-6"

SYSTEM = """\
You are a precise summarizer. Given a transcript, produce a JSON object with these exact keys:
- "tldr": one-sentence summary (string)
- "key_points": list of 3-7 concise bullet strings
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

    user_system = system_prompt.strip() or SYSTEM

    for attempt in range(3):
        try:
            message = await client.messages.create(
                model=MODEL,
                max_tokens=2048,
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
            return json.loads(raw)  # type: ignore[no-any-return]
        except anthropic.APIStatusError as exc:
            if exc.status_code in (429, 500, 502, 503) and attempt < 2:
                import asyncio
                await asyncio.sleep(2 ** attempt * 2)
                continue
            raise ClaudeError(f"Claude {exc.status_code}: {exc.message}") from exc
        except json.JSONDecodeError as exc:
            raise ClaudeError(f"Claude returned non-JSON: {exc}") from exc

    raise ClaudeError("Claude summarization failed after retries")

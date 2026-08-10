"""Public, token-gated reader pages.

Each summary has a clean HTML representation served at
/reader/{token}/{summary_id}.html. The token is the user's feed_token
(opaque, regenerable). ElevenReader, Pocket, browser reader mode, and
any other "paste a link" reading app fetch this URL and parse the
HTML themselves — we just return a minimal article.

This route is intentionally outside the authenticated /api/* prefix
because podcast/reader apps cannot present session cookies. The token
in the URL is the bearer credential.
"""
from __future__ import annotations

import html
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from podking.deps import get_db
from podking.models import Summary, User

router = APIRouter()


def _h(value: object) -> str:
    """HTML-escape any value for safe interpolation."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _render_generic_section(key: str, value: object) -> str:
    """Render an arbitrary prompt-defined output field (e.g. PLAYER_NOTES)
    as escaped HTML: strings as paragraphs, lists as <ol>, dicts as lines."""
    heading = f"<section><h2>{_h(key.replace('_', ' '))}</h2>"
    if isinstance(value, str):
        return heading + f"<p>{_h(value)}</p></section>"
    if isinstance(value, list):
        items = []
        for item in value:
            if isinstance(item, dict):
                line = "; ".join(
                    f"{k}: {v}" for k, v in item.items() if v not in (None, "")
                )
                items.append(f"<li>{_h(line)}</li>")
            else:
                items.append(f"<li>{_h(item)}</li>")
        if not items:
            return ""
        return heading + "<ol>" + "".join(items) + "</ol></section>"
    if isinstance(value, dict):
        line = "; ".join(
            f"{k}: {v}" for k, v in value.items() if v not in (None, "")
        )
        if not line:
            return ""
        return heading + f"<p>{_h(line)}</p></section>"
    return ""


def _render_summary(summary: Summary) -> str:
    content = summary.content or {}
    tldr = content.get("tldr") if isinstance(content, dict) else None
    key_points = content.get("key_points") if isinstance(content, dict) else None
    if key_points is None and isinstance(content, dict):
        # Custom prompts may use their own key name (e.g. "KEY_POINTS").
        key_points = content.get("KEY_POINTS")
    quotes = content.get("quotes") if isinstance(content, dict) else None

    title = summary.episode.title if summary.episode else None
    author = summary.episode.author if summary.episode else None
    source_url = summary.episode.source_url if summary.episode else None

    title_str = title or "Summary"
    byline_parts = [p for p in [author, "Summarized via podking"] if p]
    byline = " · ".join(byline_parts)

    parts: list[str] = []
    parts.append(
        '<header><h1>' + _h(title_str) + '</h1>'
        '<p class="byline">' + _h(byline) + '</p></header>'
    )

    if tldr:
        parts.append(
            '<section><h2>TL;DR</h2><p>' + _h(tldr) + '</p></section>'
        )

    if isinstance(key_points, list) and key_points:
        items = "".join(f"<li>{_h(p)}</li>" for p in key_points if p)
        parts.append(
            '<section><h2>Key takeaways</h2><ol>' + items + '</ol></section>'
        )

    if isinstance(quotes, list) and quotes:
        blocks: list[str] = []
        for q in quotes:
            if not isinstance(q, dict):
                continue
            text = q.get("text")
            speaker = q.get("speaker")
            if not text:
                continue
            speaker_html = (
                f'<footer>— {_h(speaker)}</footer>' if speaker else ""
            )
            blocks.append(
                f'<blockquote><p>{_h(text)}</p>{speaker_html}</blockquote>'
            )
        if blocks:
            parts.append(
                '<section><h2>Notable quotes</h2>' + "".join(blocks) + '</section>'
            )

    # Custom analysis prompts may define additional output fields
    # (PLAYER_NOTES, notable_disagreements, ...) — render them generically.
    if isinstance(content, dict):
        for key, value in content.items():
            if key in ("tldr", "key_points", "KEY_POINTS", "quotes", "suggested_tags"):
                continue
            section = _render_generic_section(key, value)
            if section:
                parts.append(section)

    if source_url:
        parts.append(
            '<footer class="source"><p>Original episode: '
            f'<a href="{_h(source_url)}">{_h(source_url)}</a></p></footer>'
        )

    body = "\n".join(parts)

    # Minimal inline styles so a browser-based view is also pleasant.
    # ElevenReader / readability parsers strip styles anyway.
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_h(title_str)}</title>
<meta name="description" content="{_h(tldr or title_str)}">
<style>
  body {{
    font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    max-width: 680px; margin: 2rem auto; padding: 0 1rem; color: #111;
  }}
  h1 {{ font-size: 1.6rem; line-height: 1.3; margin-bottom: 0.25rem; }}
  h2 {{
    font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em;
    color: #6b7280; margin-top: 2rem; margin-bottom: 0.5rem;
  }}
  .byline {{
    color: #6b7280; font-size: 0.9rem; margin: 0 0 1.5rem;
    border-bottom: 1px solid #e5e7eb; padding-bottom: 1rem;
  }}
  ol, ul {{ padding-left: 1.25rem; }}
  ol li {{ margin-bottom: 0.75rem; }}
  blockquote {{
    border-left: 4px solid #d1d5db; margin: 0 0 1rem; padding: 0 0 0 1rem;
    font-style: italic; color: #374151;
  }}
  blockquote footer {{
    font-size: 0.85rem; color: #6b7280; font-style: normal; margin-top: 0.25rem;
  }}
  .source {{
    margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid #e5e7eb;
    font-size: 0.85rem; color: #6b7280;
  }}
  .source a {{ color: inherit; }}
</style>
</head>
<body>
<article>
{body}
</article>
</body>
</html>"""


@router.get("/reader/{token}/{summary_id}.html", response_class=HTMLResponse)
async def reader_summary(
    token: str,
    summary_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Serve a summary as a minimal HTML article. No auth — gated only by
    the user's per-account feed_token in the path."""
    user_result = await db.execute(
        select(User).where(User.feed_token == token)
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="reader link not found")

    summary_result = await db.execute(
        select(Summary)
        .where(Summary.id == summary_id, Summary.user_id == user.id)
        .options(selectinload(Summary.episode))
    )
    summary = summary_result.scalar_one_or_none()
    if summary is None:
        raise HTTPException(status_code=404, detail="summary not found")

    return HTMLResponse(content=_render_summary(summary))

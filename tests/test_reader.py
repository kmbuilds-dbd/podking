"""Public, token-gated reader page."""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select


async def _seed_summary_with_token(client: AsyncClient) -> tuple[str, str]:
    """Set the seeded user's feed_token and create a summary; return
    (token, summary_id)."""
    from podking.db import get_sessionmaker
    from podking.models import Episode, Summary, User

    sm = get_sessionmaker()
    async with sm() as db:
        user = (await db.execute(select(User))).scalar_one()
        user.feed_token = "test-token-abc123"

        episode = Episode(
            user_id=user.id,
            source_type="podcast",
            source_url="https://example.com/ep",
            external_id="reader-test",
            title="The Title We Expect To See",
            author="Some Publisher",
        )
        db.add(episode)
        await db.flush()

        summary = Summary(
            user_id=user.id,
            episode_id=episode.id,
            system_prompt="x",
            model="claude-sonnet-4-6",
            content={
                "tldr": "A pulled-out lede sentence.",
                "key_points": ["First point.", "Second point."],
                "quotes": [
                    {"text": "Memorable line", "speaker": "Guest"},
                ],
                "suggested_tags": ["tag-a", "tag-b"],
            },
        )
        db.add(summary)
        await db.commit()
        return "test-token-abc123", str(summary.id)


@pytest.mark.asyncio
async def test_reader_renders_summary_html(seeded_client: AsyncClient) -> None:
    token, summary_id = await _seed_summary_with_token(seeded_client)

    resp = await seeded_client.get(f"/reader/{token}/{summary_id}.html")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")

    body = resp.text
    # Title, byline, TL;DR, key points, quote — all must appear.
    assert "The Title We Expect To See" in body
    assert "Some Publisher" in body
    assert "A pulled-out lede sentence." in body
    assert "First point." in body
    assert "Second point." in body
    assert "Memorable line" in body
    assert "Guest" in body


@pytest.mark.asyncio
async def test_reader_renders_custom_prompt_sections(
    seeded_client: AsyncClient,
) -> None:
    """Custom analysis prompts may define their own output fields (e.g. the
    fantasy style's PLAYER_NOTES / KEY_POINTS); the reader must render them
    and treat the custom takeaway key as the takeaways list."""
    from podking.db import get_sessionmaker
    from podking.models import Episode, Summary, User

    sm = get_sessionmaker()
    async with sm() as db:
        user = (await db.execute(select(User))).scalar_one()
        user.feed_token = "custom-token"
        ep = Episode(
            user_id=user.id,
            source_type="podcast",
            source_url="https://example.com/ep",
            external_id="custom-key-test",
            title="Fantasy ep",
        )
        db.add(ep)
        await db.flush()
        s = Summary(
            user_id=user.id,
            episode_id=ep.id,
            system_prompt="fantasy",
            model="claude-sonnet-4-6",
            content={
                "tldr": "A fantasy football episode.",
                "KEY_POINTS": ["Takeaway one.", "Takeaway two."],
                "PLAYER_NOTES": [
                    {
                        "player": "Drake Maye",
                        "team_position": "QB, NE",
                        "take": "High",
                        "summary": "Sharp in camp.",
                        "speaker": "Host A",
                    }
                ],
                "notable_disagreements": ["Hosts split on A.J. Brown."],
                "quotes": [],
                "suggested_tags": ["fantasy football"],
            },
        )
        db.add(s)
        await db.commit()
        sid = str(s.id)

    resp = await seeded_client.get(f"/reader/custom-token/{sid}.html")
    assert resp.status_code == 200
    body = resp.text
    assert "Takeaway one." in body  # custom takeaway key rendered as list
    assert "PLAYER NOTES" in body  # extra section heading
    assert "Drake Maye" in body
    assert "QB, NE" in body
    assert "notable disagreements" in body


@pytest.mark.asyncio
async def test_reader_404_for_invalid_token(seeded_client: AsyncClient) -> None:
    _, summary_id = await _seed_summary_with_token(seeded_client)
    resp = await seeded_client.get(f"/reader/wrong-token/{summary_id}.html")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reader_404_when_summary_belongs_to_other_user(
    seeded_client: AsyncClient,
) -> None:
    """Another user's token + this user's summary id → 404. Token is the
    bearer credential and only authorizes its own user's summaries."""
    from podking.db import get_sessionmaker
    from podking.models import User, UserSettings

    token, summary_id = await _seed_summary_with_token(seeded_client)

    # Create a different user with their own different token.
    sm = get_sessionmaker()
    async with sm() as db:
        other = User(
            email="other@example.com",
            google_sub="other-sub",
            display_name="Other",
            feed_token="other-token",
        )
        db.add(other)
        await db.flush()
        db.add(UserSettings(user_id=other.id, system_prompt=""))
        await db.commit()

    # Fetching with the OTHER user's token + this summary's id → 404.
    resp = await seeded_client.get(f"/reader/other-token/{summary_id}.html")
    assert resp.status_code == 404

    # Wrong token shape never wins, even with someone else's valid token.
    assert token != "other-token"


@pytest.mark.asyncio
async def test_reader_404_for_missing_summary(seeded_client: AsyncClient) -> None:
    token, _ = await _seed_summary_with_token(seeded_client)
    resp = await seeded_client.get(f"/reader/{token}/{uuid.uuid4()}.html")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reader_escapes_html_in_summary_content(
    seeded_client: AsyncClient,
) -> None:
    """Summary content is user-controlled (via Claude's output). Make sure
    raw <script> tags etc. don't pass through unescaped."""
    from podking.db import get_sessionmaker
    from podking.models import Episode, Summary, User

    sm = get_sessionmaker()
    async with sm() as db:
        user = (await db.execute(select(User))).scalar_one()
        user.feed_token = "esc-token"
        ep = Episode(
            user_id=user.id,
            source_type="podcast",
            source_url="https://example.com/ep",
            external_id="esc-test",
            title="<script>alert(1)</script>",
        )
        db.add(ep)
        await db.flush()
        s = Summary(
            user_id=user.id,
            episode_id=ep.id,
            system_prompt="x",
            model="claude-sonnet-4-6",
            content={
                "tldr": "<img src=x onerror=alert(1)>",
                "key_points": ["</script><script>1</script>"],
                "quotes": [],
                "suggested_tags": [],
            },
        )
        db.add(s)
        await db.commit()
        sid = str(s.id)

    resp = await seeded_client.get(f"/reader/esc-token/{sid}.html")
    assert resp.status_code == 200
    body = resp.text
    # The literal raw payloads must NOT appear; their escaped equivalents must.
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
    assert "<img src=x onerror=alert(1)>" not in body

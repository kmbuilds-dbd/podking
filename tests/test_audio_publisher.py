from __future__ import annotations

import subprocess
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from podking.worker.tts.publisher import (
    PublisherError,
    PublishContext,
    PublishedEpisode,
    publish_audio_episode,
)


def _init_bare_repo(tmp_path: Path) -> Path:
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    return bare


def _seed_initial_commit(bare: Path, tmp_path: Path) -> None:
    """Bare repos need an initial commit on the default branch so push works.
    Seed one empty commit on `main`."""
    work = tmp_path / "_seed"
    subprocess.run(["git", "clone", str(bare), str(work)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(work), "checkout", "-B", "main"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(work), "commit", "--allow-empty", "-m", "init"],
        check=True, capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        },
    )
    subprocess.run(
        ["git", "-C", str(work), "push", "-u", "origin", "main"],
        check=True, capture_output=True,
    )


def _make_mp3(path: Path) -> None:
    from pydub import AudioSegment
    AudioSegment.silent(duration=500, frame_rate=44100).export(
        str(path), format="mp3", bitrate="128k"
    )


@pytest.mark.asyncio
async def test_publish_audio_episode_writes_mp3_and_feed(tmp_path: Path) -> None:
    bare = _init_bare_repo(tmp_path)
    _seed_initial_commit(bare, tmp_path)

    mp3 = tmp_path / "ep.mp3"
    _make_mp3(mp3)

    ep_id = uuid.uuid4()
    ctx = PublishContext(
        clone_url=f"file://{bare}",
        base_url="https://example.test/podking-audio",
        feed_token="tok123",
        owner_email="me@example.com",
        show_name="Podking",
        show_description="My personal feed",
        language="en",
    )

    new_ep = PublishedEpisode(
        id=ep_id, mp3_path=mp3, mp3_filename=f"{ep_id}.mp3",
        title="Test Episode", description="hello",
        duration="0:30", duration_sec=30, size_bytes=mp3.stat().st_size,
        pub_date="Thu, 15 May 2026 12:00:00 GMT",
    )

    url = await publish_audio_episode(
        new_episode=new_ep,
        live_episodes=[new_ep],
        archived_filenames=[],
        ctx=ctx,
    )

    check = tmp_path / "_check"
    subprocess.run(["git", "clone", str(bare), str(check)], check=True, capture_output=True)
    feed_path = check / "u" / "tok123" / "feed.xml"
    mp3_published = check / "u" / "tok123" / "episodes" / f"{ep_id}.mp3"
    assert feed_path.exists()
    assert mp3_published.exists()
    tree = ET.parse(feed_path)
    items = tree.findall(".//item")
    assert len(items) == 1
    assert items[0].find("title").text == "Test Episode"
    assert url == f"{ctx.base_url}/u/{ctx.feed_token}/episodes/{ep_id}.mp3"


@pytest.mark.asyncio
async def test_publish_drops_archived_mp3s(tmp_path: Path) -> None:
    bare = _init_bare_repo(tmp_path)
    _seed_initial_commit(bare, tmp_path)

    old_mp3 = tmp_path / "old.mp3"
    _make_mp3(old_mp3)
    old_id = uuid.uuid4()
    ctx = PublishContext(
        clone_url=f"file://{bare}",
        base_url="https://example.test/podking-audio",
        feed_token="tokABC",
        owner_email="me@example.com",
        show_name="Podking",
        show_description="My personal feed",
        language="en",
    )
    old_ep = PublishedEpisode(
        id=old_id, mp3_path=old_mp3, mp3_filename=f"{old_id}.mp3",
        title="Old", description="o", duration="0:30", duration_sec=30,
        size_bytes=old_mp3.stat().st_size,
        pub_date="Thu, 14 May 2026 12:00:00 GMT",
    )
    await publish_audio_episode(
        new_episode=old_ep, live_episodes=[old_ep],
        archived_filenames=[], ctx=ctx,
    )

    new_mp3 = tmp_path / "new.mp3"
    _make_mp3(new_mp3)
    new_id = uuid.uuid4()
    new_ep = PublishedEpisode(
        id=new_id, mp3_path=new_mp3, mp3_filename=f"{new_id}.mp3",
        title="New", description="n", duration="0:30", duration_sec=30,
        size_bytes=new_mp3.stat().st_size,
        pub_date="Thu, 15 May 2026 12:00:00 GMT",
    )
    await publish_audio_episode(
        new_episode=new_ep,
        live_episodes=[new_ep],
        archived_filenames=[old_ep.mp3_filename],
        ctx=ctx,
    )

    check = tmp_path / "_check2"
    subprocess.run(["git", "clone", str(bare), str(check)], check=True, capture_output=True)
    assert not (check / "u" / "tokABC" / "episodes" / old_ep.mp3_filename).exists()
    assert (check / "u" / "tokABC" / "episodes" / new_ep.mp3_filename).exists()


@pytest.mark.asyncio
async def test_publish_escapes_xml_special_chars_in_title(tmp_path: Path) -> None:
    """Titles with '<' must be HTML-escaped by Jinja's autoescape — verify."""
    bare = _init_bare_repo(tmp_path)
    _seed_initial_commit(bare, tmp_path)

    mp3 = tmp_path / "ep.mp3"
    _make_mp3(mp3)

    ep = PublishedEpisode(
        id=uuid.uuid4(), mp3_path=mp3, mp3_filename="x.mp3",
        title="Curly <quotes> & ampersands",
        description="ok", duration="0:30", duration_sec=30,
        size_bytes=mp3.stat().st_size,
        pub_date="Thu, 15 May 2026 12:00:00 GMT",
    )
    ctx = PublishContext(
        clone_url=f"file://{bare}",
        base_url="https://example.test/x",
        feed_token="tokXYZ",
        owner_email="m@m",
        show_name="P",
        show_description="d",
        language="en",
    )
    await publish_audio_episode(
        new_episode=ep, live_episodes=[ep], archived_filenames=[], ctx=ctx,
    )

    check = tmp_path / "_check3"
    subprocess.run(["git", "clone", str(bare), str(check)], check=True, capture_output=True)
    feed_xml = (check / "u" / "tokXYZ" / "feed.xml").read_text(encoding="utf-8")
    # Title was escaped (no raw '<' inside item)
    tree = ET.fromstring(feed_xml)
    items = tree.findall(".//item")
    assert items[0].find("title").text == "Curly <quotes> & ampersands"

"""Stage 3 — clone the shared repo, drop the MP3, regenerate feed.xml, push.

Concurrency: callers serialize with an `asyncio.Lock`. We're defensive
against non-fast-forward push (retry pull --rebase + push up to 3x).
"""
from __future__ import annotations

import asyncio
import re as _re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_DIR = Path(__file__).parent
TEMPLATE_NAME = "feed_template.xml"
PUSH_RETRY_LIMIT = 3

_PAT_RE = _re.compile(r"https://[^/@\s]*:[^/@\s]*@")


def _redact_clone_url(url: str) -> str:
    """Replace any embedded `user:pat@` in an https clone URL."""
    return _PAT_RE.sub("https://<redacted>@", url)


def _redact_pat(text: str) -> str:
    """Strip any embedded `user:pat@` patterns from arbitrary text (e.g. git stderr)."""
    return _PAT_RE.sub("https://<redacted>@", text)


class PublisherError(RuntimeError):
    pass


@dataclass(frozen=True)
class PublishedEpisode:
    id: object  # uuid.UUID stringifies fine in templates
    mp3_path: Path
    mp3_filename: str
    title: str
    description: str
    duration: str            # "MM:SS" or "H:MM:SS"
    duration_sec: int
    size_bytes: int
    pub_date: str            # RFC 2822


@dataclass(frozen=True)
class PublishContext:
    clone_url: str           # https://x-access-token:PAT@github.com/REPO.git OR file://...
    base_url: str            # https://USER.github.io/podking-audio
    feed_token: str
    owner_email: str
    show_name: str
    show_description: str
    language: str


_GIT_ENV = {
    "GIT_AUTHOR_NAME": "podking",
    "GIT_AUTHOR_EMAIL": "podking@localhost",
    "GIT_COMMITTER_NAME": "podking",
    "GIT_COMMITTER_EMAIL": "podking@localhost",
    # Sandbox: ignore the user's ~/.gitconfig and system gitconfig.
    "HOME": "/nonexistent",
    "GIT_CONFIG_NOSYSTEM": "1",
    # Cover both /usr/bin/git (Xcode CLT, Linux) and /opt/homebrew/bin/git
    # (macOS Apple Silicon homebrew).
    "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:  # type: ignore[type-arg]
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        env=_GIT_ENV,
    )
    if result.returncode != 0:
        raise PublisherError(
            f"git {' '.join(args)} failed (rc={result.returncode}): "
            f"{_redact_pat(result.stderr.strip())}"
        )
    return result


def _render_feed(
    live_episodes: list[PublishedEpisode], ctx: PublishContext
) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["xml"]),
        keep_trailing_newline=True,
    )
    template = env.get_template(TEMPLATE_NAME)
    episodes_for_template = [
        {
            "title": ep.title,
            "description": ep.description,
            "pub_date": ep.pub_date,
            "url": f"{ctx.base_url}/u/{ctx.feed_token}/episodes/{ep.mp3_filename}",
            "size_bytes": ep.size_bytes,
            "duration": ep.duration,
        }
        for ep in live_episodes
    ]
    rendered = template.render(
        show_name=ctx.show_name,
        description=ctx.show_description,
        owner_email=ctx.owner_email,
        base_url=ctx.base_url,
        language=ctx.language,
        episodes=episodes_for_template,
    )
    try:
        ET.fromstring(rendered)
    except ET.ParseError as exc:
        raise PublisherError(f"Rendered feed.xml is not well-formed: {exc}") from exc
    return rendered


def _do_publish_sync(
    *,
    new_episode: PublishedEpisode,
    live_episodes: list[PublishedEpisode],
    archived_filenames: list[str],
    ctx: PublishContext,
) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        clone_result = subprocess.run(
            ["git", "clone", "--depth", "1", ctx.clone_url, str(repo)],
            capture_output=True, text=True,
            env=_GIT_ENV,
        )
        if clone_result.returncode != 0:
            safe_url = _redact_clone_url(ctx.clone_url)
            raise PublisherError(
                f"git clone {safe_url} failed (rc={clone_result.returncode}): "
                f"{_redact_pat(clone_result.stderr.strip())}"
            )

        user_dir = repo / "u" / ctx.feed_token
        episodes_dir = user_dir / "episodes"
        episodes_dir.mkdir(parents=True, exist_ok=True)

        dest = episodes_dir / new_episode.mp3_filename
        shutil.copy2(str(new_episode.mp3_path), str(dest))

        for filename in archived_filenames:
            stale = episodes_dir / filename
            if stale.exists():
                stale.unlink()

        rendered = _render_feed(live_episodes, ctx)
        (user_dir / "feed.xml").write_text(rendered, encoding="utf-8")

        _git(repo, "add", ".")
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo), capture_output=True, text=True, env=_GIT_ENV,
        )
        if status_result.returncode != 0:
            raise PublisherError(
                f"git status failed (rc={status_result.returncode}): "
                f"{status_result.stderr.strip()}"
            )
        if not status_result.stdout.strip():
            return f"{ctx.base_url}/u/{ctx.feed_token}/episodes/{new_episode.mp3_filename}"
        _git(repo, "commit", "-m", f"Audio: {new_episode.title}")

        for attempt in range(PUSH_RETRY_LIMIT):
            try:
                _git(repo, "push", "origin", "HEAD")
                break
            except PublisherError as exc:
                if attempt == PUSH_RETRY_LIMIT - 1:
                    raise
                msg = str(exc)
                if "non-fast-forward" in msg or "rejected" in msg or "fetch first" in msg:
                    _git(repo, "pull", "--rebase", "origin", "HEAD")
                    continue
                raise

        return f"{ctx.base_url}/u/{ctx.feed_token}/episodes/{new_episode.mp3_filename}"


async def publish_audio_episode(
    *,
    new_episode: PublishedEpisode,
    live_episodes: list[PublishedEpisode],
    archived_filenames: list[str],
    ctx: PublishContext,
) -> str:
    """Publish one episode to the shared repo. Returns the public MP3 URL.

    `live_episodes` is the set of rows that should appear in feed.xml after
    this publish — already sorted newest-first by the caller, length <= 30.
    `archived_filenames` is the set of MP3 filenames to unlink from the
    repo (covers regenerate + user-initiated delete + retention prune).
    """
    return await asyncio.to_thread(
        _do_publish_sync,
        new_episode=new_episode,
        live_episodes=live_episodes,
        archived_filenames=archived_filenames,
        ctx=ctx,
    )

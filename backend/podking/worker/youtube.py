"""YouTube helpers: caption probe + audio download via yt-dlp."""
from __future__ import annotations

import asyncio
import json
import re
import tempfile
from pathlib import Path


class YtDlpError(RuntimeError):
    pass


async def _run(*args: str) -> tuple[str, str]:
    proc = await asyncio.create_subprocess_exec(
        "yt-dlp",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return stdout.decode(), stderr.decode()


def extract_video_id(url: str) -> str:
    patterns = [
        r"youtube\.com/watch\?v=([\w-]{11})",
        r"youtu\.be/([\w-]{11})",
        r"youtube\.com/shorts/([\w-]{11})",
        r"youtube\.com/embed/([\w-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    raise YtDlpError(f"Cannot extract video ID from URL: {url}")


async def fetch_metadata(url: str) -> dict[str, object]:
    stdout, stderr = await _run("--dump-json", "--skip-download", "--no-warnings", url)
    if not stdout.strip():
        raise YtDlpError(f"yt-dlp metadata failed: {stderr[:500]}")
    return json.loads(stdout)  # type: ignore[no-any-return]


async def probe_captions(url: str) -> list[str]:
    """Return list of available caption languages (empty = none available)."""
    stdout, _ = await _run("--list-subs", "--skip-download", "--no-warnings", url)
    languages: list[str] = []
    for line in stdout.splitlines():
        # Lines like: "en   English  vtt, ttml, srv3, srv2, srv1"
        m = re.match(r"^(\w[\w-]*)[ \t]", line)
        if m and m.group(1) not in ("Language", "Available"):
            languages.append(m.group(1))
    return languages


async def download_captions(url: str, lang: str = "en") -> str:
    """Download auto/manual captions and return plain text."""
    with tempfile.TemporaryDirectory() as tmpdir:
        stdout, stderr = await _run(
            "--write-auto-sub",
            "--write-sub",
            "--sub-lang", lang,
            "--sub-format", "vtt",
            "--skip-download",
            "--no-warnings",
            "-o", str(Path(tmpdir) / "%(id)s"),
            url,
        )
        vtt_files = list(Path(tmpdir).glob("*.vtt"))
        if not vtt_files:
            raise YtDlpError(f"Caption download failed: {stderr[:500]}")
        return _vtt_to_text(vtt_files[0].read_text())


def _vtt_to_text(vtt: str) -> str:
    """Strip VTT metadata and deduplicate caption lines."""
    seen: set[str] = set()
    lines: list[str] = []
    for line in vtt.splitlines():
        line = line.strip()
        if not line or line.startswith("WEBVTT") or "-->" in line or line.isdigit():
            continue
        # Strip VTT tags like <00:00:00.000>, <c>, </c>
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if clean and clean not in seen:
            seen.add(clean)
            lines.append(clean)
    return " ".join(lines)


async def download_audio(url: str, output_path: Path) -> None:
    """Download best audio to output_path (m4a)."""
    _, stderr = await _run(
        "-f", "bestaudio",
        "--extract-audio",
        "--audio-format", "m4a",
        "--no-warnings",
        "-o", str(output_path),
        url,
    )
    if not output_path.exists():
        raise YtDlpError(f"Audio download failed: {stderr[:500]}")

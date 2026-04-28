"""YouTube helpers: caption probe + audio download via yt-dlp."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import tempfile
from pathlib import Path

from podking.config import get_settings

log = logging.getLogger(__name__)


class YtDlpError(RuntimeError):
    pass


_materialized_cookies_path: str | None = None
_logged_cookies_diag = False

# YouTube auth cookies that must be present for an authenticated request.
# Their presence is the cheapest signal that the export was from a logged-in
# browser session and survived transport.
_REQUIRED_AUTH_COOKIES = ("SID", "HSID", "SSID", "APISID", "SAPISID")


def _log_cookies_diag(source: str, path: str) -> None:
    """One-shot diagnostic log: file size + which YouTube auth cookies are
    present. Helps distinguish between empty env var, mangled content, and
    stale cookies when YouTube's bot check keeps firing."""
    global _logged_cookies_diag
    if _logged_cookies_diag:
        return
    _logged_cookies_diag = True
    try:
        text = Path(path).read_text()
    except OSError as exc:
        log.warning("yt-dlp cookies unreadable: source=%s path=%s err=%s", source, path, exc)
        return
    data_lines = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
    names = {ln.split("\t")[5] for ln in data_lines if ln.count("\t") >= 6}
    present = [c for c in _REQUIRED_AUTH_COOKIES if c in names]
    missing = [c for c in _REQUIRED_AUTH_COOKIES if c not in names]
    log.info(
        "yt-dlp cookies loaded: source=%s path=%s bytes=%d data_lines=%d "
        "auth_present=%s auth_missing=%s",
        source, path, len(text), len(data_lines), present, missing,
    )
    if missing:
        log.warning(
            "yt-dlp cookies missing key auth cookies %s — YouTube will likely "
            "still reject as bot traffic. Re-export from a logged-in session.",
            missing,
        )


def cookies_path() -> str | None:
    """Resolve the cookies file yt-dlp should use.

    Precedence: explicit file path wins; otherwise raw cookie content from
    settings is materialized to a temp file once per process so PaaS users
    can supply cookies via a multi-line env var.
    """
    global _materialized_cookies_path
    settings = get_settings()
    if settings.yt_dlp_cookies_file:
        _log_cookies_diag("file", settings.yt_dlp_cookies_file)
        return settings.yt_dlp_cookies_file
    if not settings.yt_dlp_cookies:
        _log_no_cookies()
        return None
    if _materialized_cookies_path is None:
        path = Path(tempfile.gettempdir()) / "podking-yt-cookies.txt"
        path.write_text(settings.yt_dlp_cookies)
        # Cookies can refresh tokens; keep mode permissive enough for that
        # but locked down from other users on the host.
        path.chmod(0o600)
        _materialized_cookies_path = str(path)
    _log_cookies_diag("env", _materialized_cookies_path)
    return _materialized_cookies_path


_logged_no_cookies = False


def _log_no_cookies() -> None:
    """Make 'no cookies configured' explicit in logs so we can distinguish
    'env var didn't arrive' from 'old code without diagnostics'."""
    global _logged_no_cookies
    if _logged_no_cookies:
        return
    _logged_no_cookies = True
    log.warning(
        "yt-dlp cookies NOT configured: neither YT_DLP_COOKIES_FILE nor "
        "YT_DLP_COOKIES is set in the environment. YouTube will reject "
        "requests from this server's IP as bot traffic."
    )


def _auth_args() -> list[str]:
    """Cookies + PO token provider args for yt-dlp. Cookies prove who we are;
    the PO token proves the request originated somewhere YouTube tolerates,
    which is necessary on datacenter IPs even when cookies are valid."""
    args: list[str] = []
    path = cookies_path()
    if path:
        args += ["--cookies", path]
    pot_url = get_settings().yt_dlp_pot_provider_url
    if pot_url:
        args += ["--extractor-args", f"youtubepot-bgutilhttp:base_url={pot_url}"]
    return args


async def _run(*args: str) -> tuple[str, str]:
    proc = await asyncio.create_subprocess_exec(
        "yt-dlp",
        *_auth_args(),
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
        log.warning("yt-dlp metadata failed for %s: %s", url, stderr)
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

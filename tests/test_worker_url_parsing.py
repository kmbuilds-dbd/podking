"""Unit tests for URL parsing helpers in the worker."""
from __future__ import annotations

import pytest

from podking.worker.youtube import extract_video_id, YtDlpError
from podking.worker.podcast import parse_apple_podcast_ids, PodcastError
from podking.worker.runner import _parse_duration


class TestExtractVideoId:
    def test_watch_url(self) -> None:
        assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_url(self) -> None:
        assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_shorts_url(self) -> None:
        assert extract_video_id("https://youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_embed_url(self) -> None:
        assert extract_video_id("https://youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_invalid_raises(self) -> None:
        with pytest.raises(YtDlpError):
            extract_video_id("https://example.com/not-youtube")


class TestParseApplePodcastIds:
    def test_standard_url(self) -> None:
        url = "https://podcasts.apple.com/us/podcast/my-show/id123456?i=7890"
        podcast_id, episode_id = parse_apple_podcast_ids(url)
        assert podcast_id == "123456"
        assert episode_id == "7890"

    def test_missing_episode_raises(self) -> None:
        with pytest.raises(PodcastError):
            parse_apple_podcast_ids("https://podcasts.apple.com/us/podcast/id123456")

    def test_missing_podcast_raises(self) -> None:
        with pytest.raises(PodcastError):
            parse_apple_podcast_ids("https://podcasts.apple.com/us/podcast/show?i=7890")


class TestParseDuration:
    def test_hms(self) -> None:
        assert _parse_duration("1:30:45") == 5445

    def test_ms(self) -> None:
        assert _parse_duration("5:30") == 330

    def test_seconds_string(self) -> None:
        assert _parse_duration("90") == 90

    def test_invalid_returns_zero(self) -> None:
        assert _parse_duration("not-a-duration") == 0

    def test_empty_returns_zero(self) -> None:
        assert _parse_duration("") == 0

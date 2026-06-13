import unittest
from unittest.mock import patch

from ytm import (
    _add_playlist_items_chunked,
    _missing_expected_video_ids,
)


class FakeYTMusic:
    def __init__(self, fail_after_write=False, fail_reads=False):
        self.video_ids = []
        self.fail_after_write = fail_after_write
        self.fail_reads = fail_reads
        self.add_calls = 0
        self.read_calls = 0

    def get_playlist(self, _playlist_id, limit=None):
        self.read_calls += 1
        if self.fail_reads:
            raise KeyError("Unable to find 'contents' using path")
        self.assert_limit = limit
        return {
            "tracks": [{"videoId": video_id} for video_id in self.video_ids]
        }

    def add_playlist_items(self, _playlist_id, video_ids, duplicates=True):
        self.add_calls += 1
        self.video_ids.extend(video_ids)
        if self.fail_after_write and self.add_calls == 1:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")


class PlaylistWriteTests(unittest.TestCase):
    def test_missing_ids_preserves_duplicate_occurrences(self):
        self.assertEqual(
            _missing_expected_video_ids(["a", "a", "b"], ["a", "b"]),
            ["a"],
        )

    @patch("ytm.YTMUSIC_PLAYLIST_ADD_CHUNK_SIZE", 2)
    @patch("ytm.YTMUSIC_PLAYLIST_ADD_RETRY_COOLDOWN_SECONDS", 0)
    @patch("ytm.YTMUSIC_SEARCH_DELAY_SECONDS", 0)
    def test_ambiguous_response_is_reconciled_without_duplicates(self):
        ytmusic = FakeYTMusic(fail_after_write=True)

        _add_playlist_items_chunked(
            ytmusic,
            "playlist",
            ["a", "b", "c"],
        )

        self.assertEqual(ytmusic.video_ids, ["a", "b", "c"])
        self.assertEqual(ytmusic.add_calls, 2)

    @patch("ytm.YTMUSIC_PLAYLIST_ADD_CHUNK_SIZE", 2)
    @patch("ytm.YTMUSIC_SEARCH_DELAY_SECONDS", 0)
    def test_successful_writes_do_not_require_playlist_reads(self):
        ytmusic = FakeYTMusic(fail_reads=True)

        _add_playlist_items_chunked(
            ytmusic,
            "playlist",
            ["a", "b", "c"],
        )

        self.assertEqual(ytmusic.video_ids, ["a", "b", "c"])
        self.assertEqual(ytmusic.read_calls, 0)

    @patch("ytm.YTMUSIC_PLAYLIST_ADD_CHUNK_SIZE", 2)
    @patch("ytm.YTMUSIC_PLAYLIST_ADD_RETRIES", 1)
    @patch("ytm.YTMUSIC_PLAYLIST_ADD_RETRY_COOLDOWN_SECONDS", 0)
    @patch("ytm.YTMUSIC_SEARCH_DELAY_SECONDS", 0)
    def test_unreadable_reconciliation_does_not_resend_uncertain_chunk(self):
        ytmusic = FakeYTMusic(fail_after_write=True, fail_reads=True)

        with self.assertRaisesRegex(Exception, "readable playlist"):
            _add_playlist_items_chunked(
                ytmusic,
                "playlist",
                ["a", "b"],
            )

        self.assertEqual(ytmusic.video_ids, ["a", "b"])
        self.assertEqual(ytmusic.add_calls, 1)


if __name__ == "__main__":
    unittest.main()

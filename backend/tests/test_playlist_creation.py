import unittest
from unittest.mock import patch

from ytm import _create_playlist_resilient


class FakeYTMusic:
    def __init__(self, create_side_effects, library_snapshots):
        self.create_side_effects = list(create_side_effects)
        self.library_snapshots = list(library_snapshots)
        self.create_calls = 0

    def create_playlist(self, _title, _description, _privacy):
        self.create_calls += 1
        result = self.create_side_effects.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def get_library_playlists(self, limit=None):
        self.asserted_limit = limit
        if len(self.library_snapshots) > 1:
            return self.library_snapshots.pop(0)
        return self.library_snapshots[0]


class PlaylistCreationTests(unittest.TestCase):
    @patch("ytm.YTMUSIC_PLAYLIST_CREATE_RECONCILE_DELAY_SECONDS", 0)
    def test_recovers_playlist_created_despite_empty_response(self):
        ytmusic = FakeYTMusic(
            [ValueError("Expecting value: line 1 column 1 (char 0)")],
            [
                [{"playlistId": "old", "title": "Existing"}],
                [
                    {"playlistId": "old", "title": "Existing"},
                    {"playlistId": "new", "title": "Transfer"},
                ],
            ],
        )

        playlist_id = _create_playlist_resilient(ytmusic, "Transfer")

        self.assertEqual(playlist_id, "new")
        self.assertEqual(ytmusic.create_calls, 1)

    @patch("ytm.YTMUSIC_PLAYLIST_CREATE_RECONCILE_ATTEMPTS", 1)
    @patch("ytm.YTMUSIC_PLAYLIST_CREATE_RECONCILE_DELAY_SECONDS", 0)
    def test_retries_when_ambiguous_creation_did_not_create_playlist(self):
        ytmusic = FakeYTMusic(
            [
                ValueError("Expecting value: line 1 column 1 (char 0)"),
                "created-on-retry",
            ],
            [[{"playlistId": "old", "title": "Existing"}]],
        )

        playlist_id = _create_playlist_resilient(ytmusic, "Transfer")

        self.assertEqual(playlist_id, "created-on-retry")
        self.assertEqual(ytmusic.create_calls, 2)


if __name__ == "__main__":
    unittest.main()

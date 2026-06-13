import unittest

from ytm import MIN_MATCH_SCORE, _score_result


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.track = {
            "name": "Endless Seeker",
            "artists": ["Rute"],
            "album": "Endless Seeker",
        }

    def test_rejects_exact_title_with_wrong_artist(self):
        result = {
            "title": "Endless Seeker",
            "artists": [{"name": "Unrelated Artist"}],
        }

        self.assertLess(_score_result(self.track, result), MIN_MATCH_SCORE)

    def test_accepts_artist_name_in_title_when_uploader_is_different(self):
        result = {
            "title": "Rute - Endless Seeker",
            "artists": [{"name": "Official Upload Channel"}],
        }

        self.assertGreaterEqual(_score_result(self.track, result), MIN_MATCH_SCORE)

    def test_rejects_sped_up_version_for_original_track(self):
        result = {
            "title": "Endless Seeker (Sped Up)",
            "artists": [{"name": "Rute"}],
            "album": {"name": "Endless Seeker"},
        }

        self.assertLess(_score_result(self.track, result), MIN_MATCH_SCORE)

    def test_rejects_remix_version_for_original_track(self):
        result = {
            "title": "Endless Seeker Remix",
            "artists": [{"name": "Rute"}],
            "album": {"name": "Endless Seeker"},
        }

        self.assertLess(_score_result(self.track, result), MIN_MATCH_SCORE)

    def test_rejects_remix_marker_in_album_metadata(self):
        result = {
            "title": "Endless Seeker",
            "artists": [{"name": "Rute"}],
            "album": {"name": "Endless Seeker Remixed"},
        }

        self.assertLess(_score_result(self.track, result), MIN_MATCH_SCORE)

    def test_rejects_compact_and_alternative_remix_labels(self):
        for title in [
            "Endless Seeker REMIX2026",
            "Endless Seeker Rework",
            "Endless Seeker Bootleg",
            "Endless Seeker Mash-Up",
            "Endless Seeker VIP",
        ]:
            with self.subTest(title=title):
                result = {
                    "title": title,
                    "artists": [{"name": "Rute"}],
                    "album": {"name": "Endless Seeker"},
                }
                self.assertLess(
                    _score_result(self.track, result),
                    MIN_MATCH_SCORE,
                )

    def test_accepts_matching_original(self):
        result = {
            "title": "Endless Seeker",
            "artists": [{"name": "Rute"}],
            "album": {"name": "Endless Seeker"},
        }

        self.assertGreaterEqual(_score_result(self.track, result), MIN_MATCH_SCORE)


if __name__ == "__main__":
    unittest.main()

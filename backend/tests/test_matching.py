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

    def test_rejects_acapella_versions_for_original_track(self):
        for title in [
            "Endless Seeker Acapella",
            "Endless Seeker A Cappella",
            "Endless Seeker Vocals Only",
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

    def test_rejects_common_alternative_arrangements(self):
        for title in [
            "Endless Seeker Orchestral Version",
            "Endless Seeker Symphonic",
            "Endless Seeker Acoustic",
            "Endless Seeker Unplugged",
            "Endless Seeker Piano Version",
            "Endless Seeker String Quartet",
            "Endless Seeker Demo",
            "Endless Seeker Alternate Take",
            "Endless Seeker Dub Version",
            "Endless Seeker Lo-Fi Version",
            "Endless Seeker 8D Audio",
            "Endless Seeker Bass Boosted",
            "Endless Seeker Clean Version",
            "Endless Seeker Metal Version",
            "Endless Seeker TV Size",
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

    def test_accepts_normal_release_labels(self):
        for title in [
            "Endless Seeker (Original Mix)",
            "Endless Seeker (Album Version)",
            "Endless Seeker Official Audio",
            "Endless Seeker Lyrics",
        ]:
            with self.subTest(title=title):
                result = {
                    "title": title,
                    "artists": [{"name": "Rute"}],
                    "album": {"name": "Endless Seeker"},
                }
                self.assertGreaterEqual(
                    _score_result(self.track, result),
                    MIN_MATCH_SCORE,
                )

    def test_accepts_same_version_when_youtube_uses_parentheses(self):
        cases = [
            (
                "Penso a te 2015 - Matt Joe Remix",
                "Penso a te 2015 (Matt Joe Remix)",
                "DJ Matrix",
            ),
            (
                "Red Devils (feat. Skioffi) - Gabry Ponte Remix",
                "Red Devils (feat. Skioffi) (Gabry Ponte Remix)",
                "DJ Matrix",
            ),
            (
                "No Control - Extended Mix",
                "No Control (Extended Mix)",
                "Manuel",
            ),
            (
                "Give It To Me - Remix",
                "Give It To Me (Remix)",
                "ronixd",
            ),
            (
                "Bury the Light - Game Edit",
                "Bury the Light (Game Edit)",
                "Casey Edwards",
            ),
        ]

        for spotify_title, youtube_title, artist in cases:
            with self.subTest(title=spotify_title):
                track = {
                    "name": spotify_title,
                    "artists": [artist],
                    "album": spotify_title,
                }
                result = {
                    "title": youtube_title,
                    "artists": [{"name": artist}],
                }
                self.assertGreaterEqual(
                    _score_result(track, result),
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

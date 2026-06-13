import unittest

from ytm import (
    _search_queries,
    _similarity,
    _transliteration_variants,
)


class TransliterationTests(unittest.TestCase):
    def test_japanese_uses_hepburn_variant(self):
        variants = _transliteration_variants("花冷え。")
        self.assertIn("hanabie.", variants)

    def test_cyrillic_matches_latin_result(self):
        self.assertGreaterEqual(_similarity("Борис Ельцин", "Boris Eltsin"), 0.8)

    def test_greek_matches_latin_result(self):
        self.assertGreaterEqual(_similarity("άνθρωποι", "anthropoi"), 0.9)

    def test_chinese_and_korean_add_ascii_variants(self):
        for value in ("深圳", "화성시"):
            variants = _transliteration_variants(value)
            self.assertTrue(any(candidate.isascii() for candidate in variants[1:]))

    def test_arabic_hebrew_and_hindi_add_ascii_variants(self):
        for value in ("دمنهور", "אברהם", "महासमुंद"):
            variants = _transliteration_variants(value)
            self.assertTrue(any(candidate.isascii() for candidate in variants[1:]))

    def test_queries_keep_original_and_transliterated_text(self):
        queries = _search_queries(
            {
                "name": "άνθρωποι",
                "artists": ["Борис"],
                "album": None,
            }
        )
        self.assertTrue(any("άνθρωποι" in query for query in queries))
        self.assertTrue(any("anthropoi" in query for query in queries))
        self.assertTrue(any("Boris" in query for query in queries))


if __name__ == "__main__":
    unittest.main()

"""The translators: response parsing and the bundled dictionary.

Nothing here touches the network; the Google response shapes are real captures
from the endpoint.
"""

import unittest

from macarony import translate


class ParseGoogleTests(unittest.TestCase):
    def test_a_latin_script_response(self):
        payload = [[["Vogel", "bird", None, None, 10], [None, None, None, "bərd"]]]
        self.assertEqual(translate._parse_google(payload), ("Vogel", None))

    def test_a_non_latin_response_carries_a_romanization(self):
        payload = [[["птица", "bird", None, None, 10], [None, None, "ptitsa", "bərd"]]]
        self.assertEqual(translate._parse_google(payload), ("птица", "ptitsa"))

    def test_chunks_are_joined_in_order(self):
        payload = [[["der ", "the ", None, None, 1], ["Vogel", "bird", None, None, 1]]]
        self.assertEqual(translate._parse_google(payload), ("der Vogel", None))

    def test_malformed_payloads_do_not_raise(self):
        for payload in [None, [], [None], "nonsense", [[]], [[None]], [["" ]]]:
            self.assertEqual(translate._parse_google(payload), ("", None))


class LanguageNameTests(unittest.TestCase):
    def test_known_code(self):
        self.assertEqual(translate.language_name("sv"), "Swedish")

    def test_unknown_code_falls_back_to_itself(self):
        self.assertEqual(translate.language_name("xx"), "xx")


class OfflineTranslatorTests(unittest.TestCase):
    def setUp(self):
        self.translator = translate.OfflineTranslator()

    def test_known_word(self):
        results = self.translator.translate("bird", ["de", "pl"])
        self.assertEqual(results["de"]["text"], "Vogel")
        self.assertEqual(results["pl"]["text"], "ptak")
        self.assertIsNone(results["de"]["error"])

    def test_lookup_is_case_insensitive(self):
        self.assertEqual(self.translator.translate("Bird", ["de"])["de"]["text"], "Vogel")

    def test_unknown_word_reports_an_error_per_language(self):
        results = self.translator.translate("zebra", ["de", "fr"])
        self.assertEqual(sorted(results), ["de", "fr"])
        for result in results.values():
            self.assertIn("not in the offline dictionary", result["error"])
            self.assertEqual(result["text"], "")

    def test_a_language_the_dictionary_does_not_cover(self):
        result = self.translator.translate("bird", ["ja"])["ja"]
        self.assertIn("not in the offline dictionary", result["error"])

    def test_every_entry_covers_every_advertised_language(self):
        languages = self.translator.languages
        self.assertGreaterEqual(len(languages), 8)
        for word in self.translator.words:
            results = self.translator.translate(word, languages)
            for lang, result in results.items():
                self.assertIsNone(result["error"], f"{word}/{lang}")
                self.assertTrue(result["text"].strip(), f"{word}/{lang}")

    def test_the_dictionary_is_big_enough_to_be_useful(self):
        self.assertGreaterEqual(len(self.translator.words), 40)

    def test_requested_language_order_is_preserved(self):
        results = self.translator.translate("bird", ["pl", "de", "fr"])
        self.assertEqual(list(results), ["pl", "de", "fr"])


class GoogleTranslatorTests(unittest.TestCase):
    """The HTTP call itself is stubbed; only the caching and error paths run."""

    def test_failures_are_reported_per_language_and_not_cached(self):
        translator = translate.GoogleTranslator()
        calls = []

        def failing(word, lang):
            calls.append((word, lang))
            return translate._result(lang, error="boom")

        translator._fetch = failing
        self.assertEqual(translator.translate("bird", ["de"])["de"]["error"], "boom")
        translator.translate("bird", ["de"])
        self.assertEqual(len(calls), 2, "a failed lookup should be retried")

    def test_successes_are_cached(self):
        translator = translate.GoogleTranslator()
        calls = []

        def succeeding(word, lang):
            calls.append((word, lang))
            return translate._result(lang, text="Vogel")

        translator._fetch = succeeding
        self.assertEqual(translator.translate("bird", ["de"])["de"]["text"], "Vogel")
        self.assertEqual(translator.translate("bird", ["de"])["de"]["text"], "Vogel")
        self.assertEqual(len(calls), 1, "a successful lookup should be cached")

    def test_results_keep_the_requested_language_order(self):
        translator = translate.GoogleTranslator()
        translator._fetch = lambda word, lang: translate._result(lang, text=lang.upper())
        self.assertEqual(list(translator.translate("bird", ["pl", "de", "fr"])),
                         ["pl", "de", "fr"])


if __name__ == "__main__":
    unittest.main()

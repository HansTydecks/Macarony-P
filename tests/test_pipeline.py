"""Step 1 (tokenizing) and the end-to-end pipeline, run against the
bundled offline dictionary so the tests need no network."""

import unittest

from macarony import pipeline
from macarony.translate import OfflineTranslator

OFFLINE = {"offline": True}


def run(sentence, selected, **options):
    merged = dict(OFFLINE)
    merged.update(options)
    return pipeline.process(sentence, selected, merged, translator=OfflineTranslator())


class TokenizeTests(unittest.TestCase):
    def test_words_and_separators_are_both_kept(self):
        tokens = pipeline.tokenize("The bird sings.")
        self.assertEqual([t["text"] for t in tokens],
                         ["The", " ", "bird", " ", "sings", "."])
        self.assertEqual([t["is_word"] for t in tokens],
                         [True, False, True, False, True, False])

    def test_indices_are_positions_in_the_token_list(self):
        tokens = pipeline.tokenize("a b")
        self.assertEqual([t["index"] for t in tokens], [0, 1, 2])

    def test_the_sentence_can_be_rebuilt_exactly(self):
        for sentence in ["The bird sings in the garden.",
                         "  spaced   out  ",
                         "Hyphen-ated, don't you think?",
                         "Über straße — fine!",
                         ""]:
            tokens = pipeline.tokenize(sentence)
            self.assertEqual("".join(t["text"] for t in tokens), sentence)

    def test_apostrophes_and_hyphens_stay_inside_a_word(self):
        words = [t["text"] for t in pipeline.tokenize("don't well-known") if t["is_word"]]
        self.assertEqual(words, ["don't", "well-known"])

    def test_digits_are_not_words(self):
        words = [t["text"] for t in pipeline.tokenize("3 birds") if t["is_word"]]
        self.assertEqual(words, ["birds"])

    def test_non_ascii_letters_are_words(self):
        words = [t["text"] for t in pipeline.tokenize("Über straße") if t["is_word"]]
        self.assertEqual(words, ["Über", "straße"])


class MatchCaseTests(unittest.TestCase):
    def test_capitalized_source_capitalizes_the_result(self):
        self.assertEqual(pipeline.match_case("Bird", "vogtak"), "Vogtak")

    def test_all_caps_source_upcases_the_result(self):
        self.assertEqual(pipeline.match_case("BIRD", "vogtak"), "VOGTAK")

    def test_lowercase_source_is_left_alone(self):
        self.assertEqual(pipeline.match_case("bird", "vogtak"), "vogtak")

    def test_single_capital_is_not_treated_as_all_caps(self):
        self.assertEqual(pipeline.match_case("A", "vogtak"), "Vogtak")


class ProcessTests(unittest.TestCase):
    def test_picked_words_are_replaced_and_the_rest_is_untouched(self):
        result = run("The bird sings in the garden.", [2, 10])
        self.assertEqual(len(result["words"]), 2)
        self.assertNotIn(" bird ", result["sentence_out"])
        self.assertTrue(result["sentence_out"].startswith("The "))
        self.assertTrue(result["sentence_out"].endswith("."))
        self.assertIn(" sings in the ", result["sentence_out"])

    def test_the_replacement_is_the_top_candidate(self):
        result = run("The bird sings.", [2])
        word = result["words"][0]
        self.assertIn(word["candidates"][0]["display"], result["sentence_out"])

    def test_nothing_picked_leaves_the_sentence_alone(self):
        result = run("The bird sings.", [])
        self.assertEqual(result["sentence_out"], "The bird sings.")
        self.assertEqual(result["words"], [])

    def test_selecting_a_separator_or_a_bad_index_is_ignored(self):
        result = run("The bird sings.", [1, 99, -4])
        self.assertEqual(result["selected"], [])
        self.assertEqual(result["sentence_out"], "The bird sings.")

    def test_capitalization_of_the_source_word_is_carried_over(self):
        result = run("Bird sings.", [0])
        self.assertTrue(result["sentence_out"][0].isupper())

    def test_results_are_deterministic(self):
        first = run("The bird sings.", [2])
        second = run("The bird sings.", [2])
        self.assertEqual(first["sentence_out"], second["sentence_out"])
        self.assertEqual([c["word"] for c in first["words"][0]["candidates"]],
                         [c["word"] for c in second["words"][0]["candidates"]])

    def test_a_word_outside_the_offline_dictionary_is_reported(self):
        result = run("The zebra sings.", [2])
        word = result["words"][0]
        self.assertEqual(word["candidates"], [])
        self.assertIn("no translations available", word["error"])
        # The sentence survives a word that could not be translated.
        self.assertEqual(result["sentence_out"], "The zebra sings.")

    def test_translations_identical_to_the_english_word_are_skipped(self):
        # "warm" is also "warm" in German and Dutch; those add nothing.
        result = run("stay warm", [2])
        rows = {row["lang"]: row for row in result["words"][0]["translations"]}
        self.assertEqual(rows["de"]["normalized"], "warm")
        self.assertFalse(rows["de"]["used"])
        self.assertFalse(rows["nl"]["used"])
        self.assertEqual(rows["de"]["dropped"], "same as the English word")
        self.assertTrue(rows["fr"]["used"])

    def test_no_candidate_repeats_a_translation_or_the_source(self):
        result = run("The bird sings in the garden.", [2, 10], count=20)
        for word in result["words"]:
            forbidden = {row["normalized"] for row in word["translations"] if row["used"]}
            forbidden.add(word["source"].lower())
            for candidate in word["candidates"]:
                self.assertNotIn(candidate["word"], forbidden)

    def test_each_candidate_mixes_distinct_languages(self):
        result = run("The bird sings.", [2], count=20)
        for candidate in result["words"][0]["candidates"]:
            languages = [part["lang"] for part in candidate["parts"]]
            self.assertEqual(len(set(languages)), 3)

    def test_the_fragment_view_matches_the_used_translations(self):
        result = run("The bird sings.", [2])
        word = result["words"][0]
        used = {row["lang"] for row in word["translations"] if row["used"]}
        self.assertEqual({entry["lang"] for entry in word["fragments"]}, used)
        for entry in word["fragments"]:
            for role, pieces in entry["roles"].items():
                for piece in pieces:
                    self.assertIn(piece, entry["word"])

    def test_tokens_are_returned_so_a_caller_can_rebuild_the_sentence(self):
        result = run("The bird sings.", [2])
        self.assertEqual("".join(t["text"] for t in result["tokens"]), "The bird sings.")


class OptionTests(unittest.TestCase):
    def test_options_come_back_normalized(self):
        result = run("The bird sings.", [2], parts=9, min_frag=0, max_frag=99, count=999)
        options = result["options"]
        self.assertEqual(options["parts"], 3)
        self.assertEqual(options["min_frag"], 1)
        self.assertEqual(options["max_frag"], 8)
        self.assertEqual(options["count"], 60)

    def test_max_frag_is_lifted_to_min_frag_when_inverted(self):
        result = run("The bird sings.", [2], min_frag=4, max_frag=2)
        self.assertEqual(result["options"]["max_frag"], 4)

    def test_duplicate_languages_are_collapsed(self):
        result = run("The bird sings.", [2], languages=["de", "fr", "de", "pl"])
        self.assertEqual(result["options"]["languages"], ["de", "fr", "pl"])

    def test_an_empty_language_list_falls_back_to_the_defaults(self):
        result = run("The bird sings.", [2], languages=[])
        self.assertTrue(len(result["options"]["languages"]) >= 3)

    def test_a_language_order_outside_the_chosen_languages_is_dropped(self):
        result = run("The bird sings.", [2], languages=["de", "fr", "pl"],
                     language_order=["ja", "ko"])
        self.assertIsNone(result["options"]["language_order"])

    def test_two_part_mode_produces_two_part_words(self):
        result = run("The bird sings.", [2], parts=2)
        for candidate in result["words"][0]["candidates"]:
            self.assertEqual(len(candidate["parts"]), 2)

    def test_too_few_languages_for_three_parts_is_explained(self):
        result = run("The bird sings.", [2], languages=["de", "fr"])
        word = result["words"][0]
        self.assertEqual(word["candidates"], [])
        self.assertIn("3 different languages", word["error"])

    def test_accents_survive_when_ascii_only_is_off(self):
        result = run("The bird sings.", [2], ascii_only=False)
        rows = {row["lang"]: row["normalized"] for row in result["words"][0]["translations"]}
        self.assertEqual(rows["sv"], "fågel")

    def test_a_different_seed_changes_the_result(self):
        first = run("The bird sings.", [2], seed=1)["words"][0]["candidates"]
        second = run("The bird sings.", [2], seed=2)["words"][0]["candidates"]
        self.assertNotEqual([c["word"] for c in first], [c["word"] for c in second])


if __name__ == "__main__":
    unittest.main()

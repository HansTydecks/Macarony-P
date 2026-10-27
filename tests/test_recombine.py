"""Step 3: positional recombination."""

import unittest

from macarony import recombine
from macarony.fragments import MIDDLE, PREFIX, SUFFIX

# Normalized translations of "bird", the shape step 3 expects.
BIRD = {
    "de": "vogel",
    "fr": "oiseau",
    "es": "pajaro",
    "it": "uccello",
    "pt": "passaro",
    "nl": "vogel",
    "sv": "fagel",
    "pl": "ptak",
}


class StructureTests(unittest.TestCase):
    def setUp(self):
        self.candidates = recombine.recombine("bird", BIRD, count=12, seed=1)

    def test_candidates_are_produced(self):
        self.assertTrue(self.candidates)
        self.assertLessEqual(len(self.candidates), 12)

    def test_three_parts_in_prefix_middle_suffix_order(self):
        for candidate in self.candidates:
            roles = [part["role"] for part in candidate["parts"]]
            self.assertEqual(roles, [PREFIX, MIDDLE, SUFFIX])

    def test_every_part_comes_from_a_different_language(self):
        for candidate in self.candidates:
            languages = [part["lang"] for part in candidate["parts"]]
            self.assertEqual(len(set(languages)), len(languages))

    def test_the_word_is_exactly_its_parts_joined(self):
        for candidate in self.candidates:
            joined = "".join(part["text"] for part in candidate["parts"])
            self.assertEqual(joined, candidate["word"])

    def test_each_fragment_really_occurs_in_its_language(self):
        for candidate in self.candidates:
            for part in candidate["parts"]:
                self.assertIn(part["text"], BIRD[part["lang"]])

    def test_a_prefix_starts_its_translation_and_a_suffix_ends_it(self):
        for candidate in self.candidates:
            prefix, _, suffix = candidate["parts"]
            self.assertTrue(BIRD[prefix["lang"]].startswith(prefix["text"]))
            self.assertTrue(BIRD[suffix["lang"]].endswith(suffix["text"]))

    def test_scores_are_between_zero_and_one_and_descending(self):
        scores = [candidate["score"] for candidate in self.candidates]
        self.assertEqual(scores, sorted(scores, reverse=True))
        for score in scores:
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)

    def test_internal_sort_key_is_not_exposed(self):
        for candidate in self.candidates:
            self.assertNotIn("_tiebreak", candidate)


class GibberishTests(unittest.TestCase):
    def test_no_candidate_is_a_real_translation_or_the_source_word(self):
        real = set(BIRD.values()) | {"bird"}
        for candidate in recombine.recombine("bird", BIRD, count=40, seed=2):
            self.assertNotIn(candidate["word"], real)

    def test_no_candidate_is_merely_a_piece_of_a_real_translation(self):
        for candidate in recombine.recombine("bird", BIRD, count=40, seed=3):
            for real in BIRD.values():
                self.assertNotIn(candidate["word"], real)

    def test_results_are_unique(self):
        words = [c["word"] for c in recombine.recombine("bird", BIRD, count=40, seed=4)]
        self.assertEqual(len(words), len(set(words)))

    def test_length_stays_near_the_median_translation(self):
        for candidate in recombine.recombine("bird", BIRD, count=40, seed=5):
            self.assertGreaterEqual(len(candidate["word"]), 3)
            self.assertLessEqual(len(candidate["word"]), 11)


class DeterminismTests(unittest.TestCase):
    def test_same_seed_gives_the_same_list(self):
        first = recombine.recombine("bird", BIRD, count=10, seed=42)
        second = recombine.recombine("bird", BIRD, count=10, seed=42)
        self.assertEqual([c["word"] for c in first], [c["word"] for c in second])

    def test_different_seeds_give_different_lists(self):
        first = [c["word"] for c in recombine.recombine("bird", BIRD, count=10, seed=1)]
        second = [c["word"] for c in recombine.recombine("bird", BIRD, count=10, seed=99)]
        self.assertNotEqual(first, second)

    def test_sampling_path_is_deterministic_too(self):
        # A tiny cap forces the random-sampling branch instead of enumeration.
        first = recombine.recombine("bird", BIRD, count=8, seed=7, sample_cap=50)
        second = recombine.recombine("bird", BIRD, count=8, seed=7, sample_cap=50)
        self.assertTrue(first)
        self.assertEqual([c["word"] for c in first], [c["word"] for c in second])


class OptionTests(unittest.TestCase):
    def test_two_part_mode_uses_prefix_and_suffix_only(self):
        for candidate in recombine.recombine("bird", BIRD, parts=2, count=10, seed=1):
            roles = [part["role"] for part in candidate["parts"]]
            self.assertEqual(roles, [PREFIX, SUFFIX])

    def test_a_fixed_language_order_is_obeyed(self):
        candidates = recombine.recombine(
            "bird", BIRD, language_order=["de", "pl", "fr"], count=10, seed=1)
        self.assertTrue(candidates)
        for candidate in candidates:
            self.assertEqual([part["lang"] for part in candidate["parts"]],
                             ["de", "pl", "fr"])

    def test_fragment_length_bounds_are_obeyed(self):
        for candidate in recombine.recombine(
                "bird", BIRD, min_frag=3, max_frag=3, count=10, seed=1):
            for part in candidate["parts"]:
                self.assertEqual(len(part["text"]), 3)

    def test_count_caps_the_result(self):
        self.assertLessEqual(len(recombine.recombine("bird", BIRD, count=3, seed=1)), 3)

    def test_too_few_languages_for_the_part_count(self):
        self.assertEqual(recombine.recombine("bird", {"de": "vogel", "pl": "ptak"}), [])

    def test_two_languages_are_enough_for_two_parts(self):
        self.assertTrue(
            recombine.recombine("bird", {"de": "vogel", "pl": "ptak"}, parts=2, seed=1))

    def test_no_usable_translations(self):
        self.assertEqual(recombine.recombine("bird", {}), [])

    def test_language_order_with_a_repeated_language_is_rejected(self):
        self.assertEqual(
            recombine.recombine("bird", BIRD, language_order=["de", "de", "fr"]), [])

    def test_variety_cap_spreads_results_over_language_triples(self):
        candidates = recombine.recombine("bird", BIRD, count=10, seed=11, max_per_order=2)
        counts = {}
        for candidate in candidates:
            key = tuple(candidate["order"])
            counts[key] = counts.get(key, 0) + 1
        self.assertTrue(all(value <= 2 for value in counts.values()))


class ScoringHelperTests(unittest.TestCase):
    def test_runs_split_vowels_from_consonants(self):
        self.assertEqual(recombine._runs("vogel"), [(0, 1), (1, 1), (2, 1), (3, 1), (4, 1)])
        self.assertEqual(recombine._runs("strand"), [(0, 3), (3, 1), (4, 2)])

    def test_consonant_pile_up_scores_worse_than_an_alternating_word(self):
        easy = recombine._pronounceability("vogelo", [])
        hard = recombine._pronounceability("vstrkdo", [])
        self.assertGreater(easy, hard)

    def test_a_pile_up_across_a_seam_is_penalized_harder(self):
        at_seam = recombine._pronounceability("vstrka", [1])
        inside = recombine._pronounceability("vstrka", [5])
        self.assertLess(at_seam, inside)

    def test_balanced_parts_score_higher(self):
        self.assertGreater(recombine._balance([3, 3, 3]), recombine._balance([1, 1, 7]))


if __name__ == "__main__":
    unittest.main()

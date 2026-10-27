"""Step 2b: normalization and fragment extraction."""

import unittest

from macarony import fragments


class NormalizeTests(unittest.TestCase):
    def test_lowercases_and_keeps_letters_only(self):
        self.assertEqual(fragments.normalize("Vogel"), "vogel")
        self.assertEqual(fragments.normalize("  Haus! "), "haus")

    def test_multi_word_translation_keeps_the_longest_word(self):
        self.assertEqual(fragments.normalize("der Vogel"), "vogel")
        self.assertEqual(fragments.normalize("l'oiseau"), "oiseau")
        self.assertEqual(fragments.normalize("a casa"), "casa")

    def test_ascii_only_strips_diacritics(self):
        self.assertEqual(fragments.normalize("fågel", ascii_only=True), "fagel")
        self.assertEqual(fragments.normalize("pássaro", ascii_only=True), "passaro")
        self.assertEqual(fragments.normalize("Straße", ascii_only=True), "strasse")
        self.assertEqual(fragments.normalize("książka", ascii_only=True), "ksiazka")

    def test_keeps_diacritics_when_not_asked_to_strip(self):
        self.assertEqual(fragments.normalize("fågel"), "fågel")

    def test_empty_input(self):
        self.assertEqual(fragments.normalize(""), "")
        self.assertEqual(fragments.normalize("123 !?"), "")


class LatinFormTests(unittest.TestCase):
    def test_non_latin_script_uses_the_romanization(self):
        self.assertEqual(
            fragments.latin_form({"text": "птица", "romanized": "ptitsa"}), "ptitsa")

    def test_latin_script_keeps_its_own_spelling(self):
        self.assertEqual(
            fragments.latin_form({"text": "Vogel", "romanized": "bərd"}), "Vogel")

    def test_missing_translation_falls_back_to_the_romanization(self):
        self.assertEqual(fragments.latin_form({"text": "", "romanized": "tori"}), "tori")


class ExtractFragmentsTests(unittest.TestCase):
    def setUp(self):
        self.fragments = fragments.extract_fragments("vogel", "de", 2, 4)
        self.by_role = {
            role: [f["text"] for f in self.fragments if f["role"] == role]
            for role in fragments.ROLES
        }

    def test_prefixes_start_at_the_first_letter(self):
        self.assertEqual(self.by_role["prefix"], ["vo", "vog", "voge"])
        for fragment in self.fragments:
            if fragment["role"] == "prefix":
                self.assertEqual(fragment["start"], 0)

    def test_suffixes_end_at_the_last_letter(self):
        self.assertEqual(self.by_role["suffix"], ["ogel", "gel", "el"])
        for fragment in self.fragments:
            if fragment["role"] == "suffix":
                self.assertEqual(fragment["end"], len("vogel"))

    def test_middles_sit_strictly_inside(self):
        self.assertEqual(self.by_role["middle"], ["og", "oge", "ge"])
        for fragment in self.fragments:
            if fragment["role"] == "middle":
                self.assertGreater(fragment["start"], 0)
                self.assertLess(fragment["end"], len("vogel"))

    def test_the_whole_word_is_never_a_fragment(self):
        self.assertNotIn("vogel", [f["text"] for f in self.fragments])

    def test_length_bounds_are_respected(self):
        for fragment in fragments.extract_fragments("tradgard", "sv", 3, 5):
            self.assertGreaterEqual(len(fragment["text"]), 3)
            self.assertLessEqual(len(fragment["text"]), 5)

    def test_every_fragment_is_a_real_substring_at_its_offsets(self):
        word = "giardino"
        for fragment in fragments.extract_fragments(word, "it", 2, 4):
            self.assertEqual(word[fragment["start"]:fragment["end"]], fragment["text"])

    def test_short_word_yields_a_prefix_and_a_suffix_only(self):
        found = fragments.extract_fragments("sol", "es", 2, 4)
        self.assertEqual([(f["text"], f["role"]) for f in found],
                         [("so", "prefix"), ("ol", "suffix")])

    def test_word_too_short_for_the_minimum_yields_nothing(self):
        self.assertEqual(fragments.extract_fragments("ei", "de", 3, 4), [])


class GroupByRoleTests(unittest.TestCase):
    def test_duplicates_within_a_role_are_dropped(self):
        found = fragments.extract_fragments("mama", "it", 2, 2)
        grouped = fragments.group_by_role(found)
        texts = [f["text"] for f in grouped["middle"]]
        self.assertEqual(len(texts), len(set(texts)))

    def test_every_role_key_is_present(self):
        grouped = fragments.group_by_role(fragments.extract_fragments("ei", "de", 3, 4))
        self.assertEqual(sorted(grouped), sorted(fragments.ROLES))


if __name__ == "__main__":
    unittest.main()

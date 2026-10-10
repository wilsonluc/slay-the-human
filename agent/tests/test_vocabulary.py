"""Tests for vocabulary.py. Run: python -m unittest discover -s agent/tests -t ."""

import tempfile
import unittest
from pathlib import Path

from agent.env.vocabulary import FILE, PROTOCOL_KEYS, Vocabulary, VocabularyError


class VocabularyTest(unittest.TestCase):
    def setUp(self):
        self.vocabulary = Vocabulary("v1", ["CARD.BASH", "MONSTER.BYRDPIP", "RELIC.BYRDPIP"])

    def test_keys_are_by_category_and_zero_is_padding(self):
        self.assertEqual(self.vocabulary.index("CARD", "BASH"), 1)
        self.assertNotEqual(self.vocabulary.index("MONSTER", "BYRDPIP"), self.vocabulary.index("RELIC", "BYRDPIP"))
        self.assertEqual(self.vocabulary.index("CARD", None), 0)
        self.assertEqual(len(self.vocabulary), 4)

    def test_unknown_value_raises(self):
        with self.assertRaisesRegex(VocabularyError, "CARD.NOPE is not in the vocabulary"):
            self.vocabulary.index("CARD", "NOPE")

    def test_update_only_appends_and_keeps_indices(self):
        updated = self.vocabulary.updated("v2", ["CARD.ANGER", "CARD.BASH"])
        self.assertEqual(updated.keys[:3], self.vocabulary.keys, "existing keys keep their place")
        self.assertIn("CARD.ANGER", updated.keys[3:])
        self.assertTrue(set(PROTOCOL_KEYS) <= set(updated.keys))
        self.assertIn("RELIC.BYRDPIP", updated.keys, "a key the game dropped keeps its index")
        self.assertEqual(updated.game_version, "v2")
        self.assertEqual(updated.updated("v2", ["CARD.ANGER"]).keys, updated.keys, "a second update adds nothing")

    def test_hash_follows_the_keys(self):
        self.assertEqual(self.vocabulary.hash, Vocabulary("other", list(self.vocabulary.keys)).hash)
        self.assertNotEqual(self.vocabulary.hash, self.vocabulary.updated("v1", ["CARD.ANGER"]).hash)

    def test_game_checks(self):
        self.vocabulary.check({"game_version": "v1", "vocabulary": ["CARD.BASH"]})
        with self.assertRaisesRegex(VocabularyError, "the game is v2"):
            self.vocabulary.check({"game_version": "v2", "vocabulary": []})
        with self.assertRaisesRegex(VocabularyError, "lacks 1"):
            self.vocabulary.check({"game_version": "v1", "vocabulary": ["CARD.ANGER"]})

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "vocabulary.json"
            self.vocabulary.save(path)
            loaded = Vocabulary.load(path)
        self.assertEqual((loaded.game_version, loaded.keys), (self.vocabulary.game_version, self.vocabulary.keys))

    @unittest.skipUnless(FILE.exists(), "no committed vocabulary yet")
    def test_committed_vocabulary_has_no_duplicates_and_every_protocol_name(self):
        committed = Vocabulary.load()
        self.assertTrue(set(PROTOCOL_KEYS) <= set(committed.keys))


if __name__ == "__main__":
    unittest.main()

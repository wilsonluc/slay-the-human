"""Tests for games.py: the game copy's hash and its check. Run: python -m unittest discover -s agent/tests -t ."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent.env import games


class GameCopyTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.copy = Path(self.dir.name) / "123"
        (self.copy / "data").mkdir(parents=True)
        (self.copy / games.EXECUTABLE).write_bytes(b"exe")
        (self.copy / "data" / "sts2.dll").write_bytes(b"dll")
        self.env = mock.patch.dict(os.environ, {"STH_GAMES_DIR": self.dir.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.dir.cleanup()

    def targeting(self, digest):
        return mock.patch.object(games, "targeted", return_value=("123", "v0", digest))

    def test_hash_is_stable_and_ignores_mods(self):
        first = games.copy_hash(self.copy)
        (self.copy / "mods" / "SlayTheHuman").mkdir(parents=True)
        (self.copy / "mods" / "SlayTheHuman" / "SlayTheHuman.dll").write_bytes(b"mod")
        self.assertEqual(games.copy_hash(self.copy), first)

    def test_hash_changes_with_contents_and_names(self):
        first = games.copy_hash(self.copy)
        (self.copy / "data" / "sts2.dll").write_bytes(b"patched")
        second = games.copy_hash(self.copy)
        self.assertNotEqual(second, first)
        (self.copy / "data" / "sts2.dll").rename(self.copy / "data" / "other.dll")
        self.assertNotEqual(games.copy_hash(self.copy), second)

    def test_matching_copy_is_used(self):
        with self.targeting(games.copy_hash(self.copy)):
            self.assertEqual(games.game_copy(), self.copy)

    def test_changed_copy_is_refused(self):
        with self.targeting(games.copy_hash(self.copy)):
            (self.copy / "data" / "sts2.dll").write_bytes(b"patched")
            with self.assertRaisesRegex(games.GameCopyError, "hash"):
                games.game_copy()

    def test_missing_copy_is_refused(self):
        with mock.patch.object(games, "targeted", return_value=("999", "v0", "x")):
            with self.assertRaisesRegex(games.GameCopyError, "copy-game.sh"):
                games.game_copy()

    def test_game_version_rows(self):
        build, version, digest = games.targeted()
        self.assertTrue(build.isdigit())
        self.assertTrue(version.startswith("v"))
        self.assertRegex(digest, "^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()

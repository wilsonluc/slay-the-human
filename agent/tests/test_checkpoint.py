"""Tests for checkpoint.py: the training run's record, metrics, checkpoints and resuming. Run: python -m unittest
discover -s agent/tests -t ."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent.checkpoint import CheckpointMismatch, TrainingRun
from agent.env import encoding, reward
from agent.env.vocabulary import Vocabulary
from agent.ppo.config import Config
from agent.ppo.train import Trainer
from agent.tests.fake_env import FakeEnvironment
from agent.tests.test_train import rows, small, without_timing


class CheckpointTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vocabulary = Vocabulary.load()

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def trainer(self, config: Config, run: TrainingRun | None = None, vocabulary: Vocabulary | None = None) -> Trainer:
        vocabulary = vocabulary or self.vocabulary
        run = run or TrainingRun.create(config.as_dict(), vocabulary,
                                        root=self.root / str(len(list(self.root.iterdir()))))
        envs = [FakeEnvironment(seed=i, name=f"fake{i}") for i in range(config.games)]
        return Trainer(config, run, envs, vocabulary)

    def test_the_record_holds_everything_that_produced_the_run(self):
        run = TrainingRun.create(small().as_dict(), self.vocabulary, root=self.root)
        record = json.loads(run.config_file.read_text(encoding="utf-8"))
        for field in ("config", "seed", "git_commit", "git_dirty", "game_build", "vocabulary", "schema", "protocol",
                      "reward", "python", "torch"):
            self.assertIn(field, record)
        self.assertEqual(record["config"], small().as_dict())
        self.assertEqual(record["schema"], encoding.schema_hash())
        self.assertEqual(record["reward"], reward.definition_hash())
        self.assertEqual(record["vocabulary"], self.vocabulary.hash)

    def test_resuming_gives_the_same_updates_as_training_on(self):
        straight = self.trainer(small(total_steps=800))
        straight.train()

        first = self.trainer(small(total_steps=400))
        first.train()
        state = first.run.load(self.vocabulary)
        first.run.trim_metrics(state["updates"])
        resumed = self.trainer(small(total_steps=800), run=first.run)
        resumed.restore(state)
        resumed.train()

        self.assertEqual([without_timing(r) for r in rows(resumed.run)],
                         [without_timing(r) for r in rows(straight.run)])

    def test_a_checkpoint_from_other_code_is_refused_naming_each_difference(self):
        trainer = self.trainer(small(total_steps=200))
        trainer.train()
        with mock.patch.object(reward, "WEIGHTS", {**reward.WEIGHTS, "hp": 0.5}), \
                mock.patch.object(encoding, "SCHEMA_REVISION", encoding.SCHEMA_REVISION + 1):
            with self.assertRaises(CheckpointMismatch) as refused:
                trainer.run.load(self.vocabulary)
        self.assertIn("reward:", str(refused.exception))
        self.assertIn("schema:", str(refused.exception))
        other = Vocabulary(self.vocabulary.game_version, self.vocabulary.keys[1:])
        with self.assertRaises(CheckpointMismatch) as refused:
            trainer.run.load(other)
        self.assertIn("vocabulary:", str(refused.exception))

    def test_a_grown_vocabulary_loads_with_new_embedding_rows(self):
        trainer = self.trainer(small(total_steps=200))
        trainer.train()
        grown = Vocabulary(self.vocabulary.game_version, self.vocabulary.keys + ["CARD.SOMETHING_NEW"])
        state = trainer.run.load(grown)
        self.assertEqual(state["model"]["embedding.weight"].shape[0], len(grown))
        resumed = self.trainer(small(total_steps=400), run=trainer.run, vocabulary=grown)
        resumed.restore(state)
        resumed.train()
        self.assertEqual(len(rows(resumed.run)), 2)

    def test_a_row_cut_short_and_rows_past_the_checkpoint_are_dropped_on_resume(self):
        run = TrainingRun.create(small().as_dict(), self.vocabulary, root=self.root)
        for update in (1, 2, 3):
            run.write_metrics({"update": update, "step": update * 100, "loss": 0.5})
        with run.metrics_file.open("a", encoding="utf-8") as file:
            file.write("4,400")  # killed mid-row
        run.trim_metrics(2)
        self.assertEqual([row["update"] for row in rows(run)], ["1", "2"])
        run.write_metrics({"update": 3, "step": 300, "loss": 0.25})
        self.assertEqual([row["update"] for row in rows(run)], ["1", "2", "3"])

    def test_a_checkpoint_is_saved_on_schedule(self):
        trainer = self.trainer(small(total_steps=10_000, checkpoint_every=2))
        saved = []
        save = trainer.run.save
        trainer.run.save = lambda state: (saved.append(state["updates"]), save(state))
        step = trainer.envs[0].step
        calls = [0]

        def stop_in_update_five(action):
            calls[0] += 1
            if calls[0] == 450:
                raise KeyboardInterrupt
            return step(action)

        trainer.envs[0].step = stop_in_update_five
        with self.assertRaises(KeyboardInterrupt):
            trainer.train()
        self.assertEqual(saved, [2, 4, 4])


if __name__ == "__main__":
    unittest.main()

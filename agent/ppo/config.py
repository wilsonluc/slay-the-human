"""Every training setting, in one dataclass. Each field is a command-line flag of `python -m agent.ppo.train`, and the
whole config is recorded in the training run's config.json."""

import argparse
from dataclasses import asdict, dataclass, fields


@dataclass
class Config:
    # A run is thousands of steps and the win comes at the end; 0.99 would see about one combat (docs/architecture.md).
    gamma: float = 0.999
    # High, so credit reaches back from a boss to the choices that built the deck, hundreds of decisions before; 0.95
    # weighs about the next 20 (spec 011).
    lam: float = 0.99
    # The usual PPO clip range.
    clip: float = 0.2
    # The rate at the start; it falls linearly to zero at total_steps, so a run's late updates settle the policy instead
    # of moving it further (spec 011's run, at a constant rate, fell back over its last 250,000 steps as approximate KL
    # climbed to 0.04; spec 013). Set from 20,000-step runs on the game (spec 011), each update's approximate KL over its
    # last epoch: 2.5e-4 gave 0.003, 5e-4 0.007, 1e-3 0.022 (clip fraction 0.03, 0.08, 0.19). The lowest in PPO's usual
    # 0.005 to 0.03.
    lr: float = 5e-4
    # Steps per game per rollout: about 1,000 a rollout with 4 games, several random runs or part of a long one.
    steps: int = 256
    # Four, though six are faster on an 8-core machine (spec 012: 4 games 43 steps/s, 6 games 53 in training). With six,
    # each update's rollout is half as large again, and all three six-game training runs drifted into skipping card
    # rewards by 300,000 steps; the four-game runs kept taking them (spec 013). Raise it only with a training run that
    # shows it learns as well.
    games: int = 4
    # The usual number of passes over a rollout, and minibatch size.
    epochs: int = 4
    minibatch: int = 256
    # The usual loss weights and gradient clipping.
    value_coef: float = 0.5
    entropy_coef: float = 0.01
    max_grad_norm: float = 0.5
    # Small widths: the observation's structure does the work.
    embed: int = 32
    hidden: int = 128
    state: int = 256
    # ROADMAP.md's stop-and-look point. The learning rate reaches zero here, so set it to the length meant to train.
    total_steps: int = 10_000_000
    # Updates between checkpoints: about 10 to 20 minutes of training lost at worst.
    checkpoint_every: int = 10
    # Training stops when more than failure_budget of the last failure_window runs failed: a few failures are expected,
    # more means they cluster, and the policy would learn to seek them out.
    failure_budget: int = 5
    failure_window: int = 100
    # Steps between evaluations on the evaluation seeds (agent/evaluate.py, best action), each making a generation:
    # about 30,000 steps of play each, near a tenth of training's time at this interval.
    evaluate_every: int = 250_000
    # How many evaluation seeds a generation plays (all 200 by default; fewer for quick tests).
    evaluation_seeds: int = 200
    # The latest generations whose checkpoints are kept; the best is kept besides.
    generations_kept: int = 3
    # The training run's seed; a new random one when not given, recorded either way.
    seed: int | None = None
    # Where the update trains: cpu, or cuda with a CUDA build of torch installed. The games always play on the CPU.
    device: str = "cpu"
    # Passed to the environment (agent/env/environment.py); its defaults.
    character: str = "IRONCLAD"
    hang_seconds: float = 120.0
    step_cap: int = 5000
    trace_every: int = 100
    time_scale: float = 20.0

    def as_dict(self) -> dict:
        return asdict(self)


def parse(argv=None) -> tuple[Config, str | None]:
    """The config from the command line, and the training run folder to resume, if any."""
    parser = argparse.ArgumentParser(prog="python -m agent.ppo.train",
                                     description="Train a PPO policy on several games at once.")
    parser.add_argument("--resume", metavar="FOLDER", help="continue this training run from its latest checkpoint")
    defaults = Config()
    for field in fields(Config):
        default = getattr(defaults, field.name)
        kind = int if field.name == "seed" else type(default)
        parser.add_argument(f"--{field.name.replace('_', '-')}", type=kind, default=default,
                            help=f"default {default}")
    args = vars(parser.parse_args(argv))
    resume = args.pop("resume")
    return Config(**args), resume

"""Every training setting, in one dataclass. Each field is a command-line flag of `python -m agent.ppo.train`, and the
whole config is recorded in the training run's config.json."""

import argparse
from dataclasses import asdict, dataclass, fields


@dataclass
class Config:
    # A run is thousands of steps and the win comes at the end; 0.99 would see about one combat (docs/architecture.md).
    gamma: float = 0.999
    # The usual GAE trade-off between bias and variance.
    lam: float = 0.95
    # The usual PPO clip range.
    clip: float = 0.2
    # Constant: training length is open-ended, with resuming.
    lr: float = 2.5e-4
    # Steps per game per rollout: about 1,000 a rollout with 4 games, several random runs or part of a long one.
    steps: int = 256
    # The speed measurement's best rate per game; set per machine (about one per CPU core at most).
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
    # ROADMAP.md's stop-and-look point.
    total_steps: int = 10_000_000
    # Updates between checkpoints: about 10 to 20 minutes of training lost at worst.
    checkpoint_every: int = 10
    # Training stops when more than failure_budget of the last failure_window runs failed: a few failures are expected,
    # more means they cluster, and the policy would learn to seek them out.
    failure_budget: int = 5
    failure_window: int = 100
    # The training run's seed; a new random one when not given, recorded either way.
    seed: int | None = None
    # cpu, or cuda with a CUDA build of torch installed.
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

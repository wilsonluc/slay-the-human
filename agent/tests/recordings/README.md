# Recorded decisions

`decisions.jsonl` holds one real decision of every kind, taken from traces of protocol 4 runs with the random agent: a mid-combat card selection and one that takes several cards as well. The Crystal Sphere only appears in act 3, which random play does not reach, so its `crystal_sphere` object comes from an earlier run's trace (its shape has not changed) with the `run` and `map` of a protocol 4 decision.

The tests' fake game (`../fake_game.py`) plays them in order, and `../test_encoding.py` round-trips each.
